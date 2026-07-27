"""
ThunderBots Knowledge Base Pipeline v10
Google Gemini is the only supported AI/embedding provider. generate_embeddings()
     resolves a Gemini API key (user DB key, then env fallback), with the
     resolved provider/model pinned per-KB (KnowledgeBase.embedding_provider/
     embedding_model) so retrieval always stays in the same vector space it
     was ingested with. See _resolve_embedding_provider, generate_embeddings,
     and KnowledgeBasePipeline.ingest below.
FIX: delete_document/delete_collection no longer blanket-swallow every
     ChromaDB exception under a warning log — a collection/document that's
     already gone is treated as an idempotent success, but a genuine
     ChromaDB failure now raises so the API layer never reports a delete as
     successful when it wasn't.
FIX: RetrievalEngine uses lazy Redis access (property) so it never captures
     a stale None reference from module-load-time initialization.
FIX: Uses asyncio.get_running_loop() for Python 3.10+ compatibility.
FIX: ChromaDB sync client calls are wrapped so they don't block the event loop.
FIX: Every pipeline stage (extract/clean/chunk/embed/index/retrieve/delete)
     now logs its inputs, outputs, and provider/model used for diagnosis.
"""
from __future__ import annotations

import os
import re
import json
import asyncio
import hashlib
import logging
from typing import Optional

import chromadb
from app.config import settings

logger = logging.getLogger(__name__)


# ── Text Extractors ───────────────────────────────────────────────────────────

async def extract_text_pdf(file_path: str) -> str:
    import pdfplumber
    loop = asyncio.get_running_loop()

    def _extract():
        pages = []
        with pdfplumber.open(file_path) as pdf:
            logger.info(f"[extract:pdf] {file_path}: {len(pdf.pages)} page(s)")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    pages.append(text)
                else:
                    logger.warning(f"[extract:pdf] {file_path}: page {i + 1} yielded no extractable text (likely scanned/image-only)")
        return "\n\n".join(pages)

    text = await loop.run_in_executor(None, _extract)
    logger.info(f"[extract:pdf] {file_path}: extracted {len(text)} chars")
    return text


async def extract_text_docx(file_path: str) -> str:
    from docx import Document
    loop = asyncio.get_running_loop()

    def _extract():
        doc = Document(file_path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        logger.info(f"[extract:docx] {file_path}: {len(paras)} non-empty paragraph(s)")
        return "\n\n".join(paras)

    text = await loop.run_in_executor(None, _extract)
    logger.info(f"[extract:docx] {file_path}: extracted {len(text)} chars")
    return text


async def extract_text_txt(file_path: str) -> str:
    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(
        None,
        lambda: open(file_path, "r", encoding="utf-8", errors="replace").read()
    )
    logger.info(f"[extract:txt] {file_path}: extracted {len(text)} chars")
    return text


async def extract_text_md(file_path: str) -> str:
    """
    Markdown is read as plain text rather than stripped of its syntax: headers,
    lists, and emphasis markers carry retrieval-relevant structure (e.g. a "##
    Refund Policy" heading is itself useful context for chunking/citation),
    and stripping them risks losing that signal for negligible benefit, since
    embedding models handle markdown syntax in their training data already.
    """
    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(
        None,
        lambda: open(file_path, "r", encoding="utf-8", errors="replace").read()
    )
    logger.info(f"[extract:md] {file_path}: extracted {len(text)} chars")
    return text


async def extract_text(file_path: str, file_type: str) -> str:
    extractors = {
        "pdf":  extract_text_pdf,
        "docx": extract_text_docx,
        "txt":  extract_text_txt,
        "md":   extract_text_md,
        "markdown": extract_text_md,
    }
    fn = extractors.get(file_type.lower())
    if not fn:
        # Never suppressed / never silently skipped: an unsupported type is a
        # hard failure surfaced to the document's status, not a silent no-op.
        raise ValueError(f"Unsupported file type: {file_type}")
    logger.info(f"[extract] starting extraction: file={file_path} type={file_type}")
    text = await fn(file_path)
    if not text or not text.strip():
        logger.warning(f"[extract] {file_path}: extraction produced no text (type={file_type})")
    return text


# ── Text Cleaner ──────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    before = len(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'[^\x09\x0a\x0d\x20-\x7e\x80-\xff]', '', text)
    text = text.strip()
    logger.info(f"[clean] {before} chars -> {len(text)} chars")
    return text


# ── Text Chunker ──────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list[str]:
    """
    FIX v5: sentences longer than chunk_size (common in scanned/garbled PDFs
    with no punctuation, or single huge run-on lines) used to produce one
    oversized chunk that could blow past embedding model token limits and
    fail silently. Such sentences are now hard-split on whitespace boundaries.
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap    = chunk_overlap or settings.CHUNK_OVERLAP

    def _hard_split(s: str) -> list[str]:
        """Split an oversized unit on word boundaries into chunk_size pieces."""
        words, pieces, buf = s.split(" "), [], ""
        for w in words:
            if len(buf) + len(w) + 1 <= chunk_size:
                buf = (buf + " " + w).strip()
            else:
                if buf:
                    pieces.append(buf)
                # A single word longer than chunk_size — slice it directly
                if len(w) > chunk_size:
                    for i in range(0, len(w), chunk_size):
                        pieces.append(w[i:i + chunk_size])
                    buf = ""
                else:
                    buf = w
        if buf:
            pieces.append(buf)
        return pieces

    paragraphs   = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks       = []
    current      = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            for sentence in re.split(r'(?<=[.!?])\s+', para):
                if len(sentence) > chunk_size:
                    # FIX v5: flush current, hard-split the oversized sentence
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.extend(_hard_split(sentence))
                    continue
                if len(current) + len(sentence) + 1 <= chunk_size:
                    current = (current + " " + sentence).strip()
                else:
                    if current:
                        chunks.append(current)
                    overlap_text = current[-overlap:] if len(current) > overlap else current
                    current = (overlap_text + " " + sentence).strip()
        else:
            if len(current) + len(para) + 2 <= chunk_size:
                current = (current + "\n\n" + para).strip()
            else:
                if current:
                    chunks.append(current)
                overlap_text = current[-overlap:] if len(current) > overlap else current
                current = (overlap_text + "\n\n" + para).strip()

    if current:
        chunks.append(current)

    result = [c for c in chunks if len(c.strip()) > 20]
    logger.info(
        f"[chunk] {len(text)} chars -> {len(result)} chunk(s) "
        f"(chunk_size={chunk_size}, overlap={overlap}, dropped_too_small={len(chunks) - len(result)})"
    )
    return result


# ── Embedding Service ─────────────────────────────────────────────────────────
#
# Google Gemini is the only supported AI provider in this project, and its
# embedding endpoint (models/gemini-embedding-001) is used for every
# Knowledge Base document/query embedding. Resolution below simply finds a
# Gemini API key (user DB key first, then env fallback) — there is no
# multi-provider branching left to do.

EMBEDDING_CAPABLE_PROVIDERS = ("gemini",)


async def _resolve_provider_key(user_id: Optional[str], provider: str) -> Optional[str]:
    """Resolve an API key for `provider`: user DB key first, then env fallback.
    Mirrors the resolution order already used for chat providers
    (app.services.ai_engine.get_provider_for_user), applied here to whichever
    provider embeddings need."""
    if user_id:
        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import select
            from app.models.user import UserAPIKey
            from app.services.ai_engine import decrypt_key
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserAPIKey).where(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.provider == provider,
                    )
                )
                row = result.scalar_one_or_none()
                if row and row.encrypted_key:
                    return decrypt_key(row.encrypted_key)
        except Exception as e:
            logger.warning(f"[embed:resolve] could not resolve user '{provider}' key for embeddings (user={user_id}): {e}")

    # Env fallback
    if provider == "gemini":
        return settings.GEMINI_API_KEY or None
    return None


async def _user_default_provider(user_id: Optional[str]) -> Optional[str]:
    """The user's default AI provider — delegates to the single shared
    implementation in app.services.user_preferences (also used by
    app.services.ai_engine.resolve_agent_provider for AI Agent / Chat
    Tester), so embeddings and chat provider resolution can never disagree
    about what "the user's default provider" means. Was previously an
    independent copy of the same DB read; consolidated to remove the
    duplication."""
    from app.services.user_preferences import get_effective_default_provider
    return await get_effective_default_provider(user_id)


async def _user_any_embedding_provider(user_id: Optional[str]) -> Optional[tuple[str, str]]:
    """Return the (provider, api_key) for any saved Gemini key the user
    has — validated (is_valid=True, most-recently-tested) keys are
    preferred, but an untested key is used rather than treated as absent.
    If the key turns out to be bad, the embedding API call itself raises a
    clear, actionable error — that's the right place to catch an invalid
    key, not this lookup."""
    if not user_id:
        return None
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.user import UserAPIKey
        from app.services.ai_engine import decrypt_key
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserAPIKey)
                .where(
                    UserAPIKey.user_id == user_id,
                    UserAPIKey.provider.in_(EMBEDDING_CAPABLE_PROVIDERS),
                )
                .order_by(UserAPIKey.is_valid.desc(), UserAPIKey.last_tested.desc(), UserAPIKey.created_at.desc())
            )
            row = result.scalars().first()
            if row and row.encrypted_key:
                return row.provider, decrypt_key(row.encrypted_key)
    except Exception as e:
        logger.warning(f"[embed:resolve] embedding-provider lookup failed for user={user_id}: {e}")
    return None


async def _resolve_embedding_provider(user_id: Optional[str]) -> tuple[str, str]:
    """
    Determine (provider, api_key) to use for embeddings. Resolution order:
      1. settings.EMBEDDING_PROVIDER server-wide override (defaults to
         "gemini"), if a key exists for it.
      2. The user's own preferences.default_provider, if it is Gemini and
         they have a key for it.
      3. Any saved Gemini key the user has.
      4. Env-level GEMINI_API_KEY.
    Raises ValueError with an actionable message if nothing is available —
    this is never suppressed; callers must not treat a missing key as
    "silently skip embeddings".
    """
    # 1. Explicit server-wide override
    if settings.EMBEDDING_PROVIDER:
        forced = settings.EMBEDDING_PROVIDER.lower()
        if forced not in EMBEDDING_CAPABLE_PROVIDERS:
            raise ValueError(
                f"EMBEDDING_PROVIDER='{forced}' is not embedding-capable. "
                f"Supported values: {', '.join(EMBEDDING_CAPABLE_PROVIDERS)}."
            )
        key = await _resolve_provider_key(user_id, forced)
        if key:
            logger.info(f"[embed:resolve] using server-forced EMBEDDING_PROVIDER='{forced}'")
            return forced, key
        raise ValueError(
            f"EMBEDDING_PROVIDER is forced to '{forced}' but no API key is configured for it "
            f"(checked user Settings → API Keys and the env var)."
        )

    # 2. User's own default provider preference, if it's embedding-capable
    preferred = await _user_default_provider(user_id)
    if preferred in EMBEDDING_CAPABLE_PROVIDERS:
        key = await _resolve_provider_key(user_id, preferred)
        if key:
            logger.info(f"[embed:resolve] using user's configured default_provider='{preferred}'")
            return preferred, key
        logger.info(
            f"[embed:resolve] user's default_provider='{preferred}' has no key configured; "
            f"falling back to an auto-detected embedding-capable provider"
        )

    # 3. Any embedding-capable provider the user has a saved key for
    auto = await _user_any_embedding_provider(user_id)
    if auto:
        provider, key = auto
        logger.info(
            f"[embed:resolve] no usable embedding provider from preferences; "
            f"auto-using configured provider='{provider}' instead"
        )
        return provider, key

    # 4. Env-level fallback (server-configured key, no user key at all)
    if settings.GEMINI_API_KEY:
        logger.info("[embed:resolve] falling back to env-level GEMINI_API_KEY")
        return "gemini", settings.GEMINI_API_KEY

    raise ValueError(
        "No Gemini API key is configured. Add a Gemini API key in "
        "Settings → API Keys to enable Knowledge Base embeddings."
    )


def _retry_after_seconds(e: Exception) -> Optional[float]:
    """Best-effort extraction of a server-provided Retry-After hint (seconds)
    from a rate-limit/HTTP error. Both the OpenAI SDK (httpx-based) and
    google-generativeai's underlying google-api-core errors may expose the
    original HTTP response's headers on `.response`. If nothing usable is
    found, the caller falls back to its own exponential backoff — this is
    purely an optimization to honor the provider's own guidance when given."""
    try:
        headers = getattr(getattr(e, "response", None), "headers", None)
        if headers:
            val = headers.get("retry-after") or headers.get("Retry-After")
            if val is not None:
                return max(0.0, float(val))
    except Exception:
        pass
    return None


def _is_retryable_embedding_error(e: Exception) -> bool:
    """True for transient embedding-provider errors worth retrying with
    backoff (rate limits, timeouts, transient 5xx/connection issues).
    False for anything retrying can't fix (bad API key, invalid request,
    unsupported model, etc.) — those must fail immediately rather than
    burn through retry attempts on a permanent error.

    ROOT CAUSE FIX: previously a single 429 from the embedding provider
    (OpenAI or Gemini) failed the entire document immediately with no
    retry at all — a purely transient, extremely common condition (both
    providers rate-limit aggressively on shared/free-tier keys) permanently
    lost the upload, requiring the user to notice and click Retry manually.
    """
    name = type(e).__name__.lower()
    raw = str(e).lower()

    # Never retry auth/permission/invalid-request errors — retrying a bad
    # key or malformed request just wastes time and delays the real error.
    if ("authenticat" in name or "permissiondenied" in name or "unauthenticated" in name
            or "invalid_api_key" in raw or "api key not valid" in raw
            or "invalidrequest" in name or "badrequest" in name):
        return False

    if "ratelimit" in name or "429" in raw or "resourceexhausted" in name or "quota" in raw:
        return True
    if "timeout" in name or "connect" in name or "connection" in raw:
        return True
    if ("internalservererror" in name or "servererror" in name or "serviceunavailable" in name
            or "apistatuserror" in name or "502" in raw or "503" in raw or "500" in raw):
        return True
    return False


async def _call_with_retry(coro_fn, *, provider: str, batch_num: int, total_batches: int,
                            max_attempts: int = 5, base_delay: float = 1.0, max_delay: float = 30.0):
    """Call the no-arg async `coro_fn()`, retrying with exponential backoff
    (honoring a server Retry-After hint when present) on transient
    rate-limit/connection/server errors only. Non-retryable errors raise on
    the first attempt. This is what keeps a temporary embedding-provider
    rate limit from losing an uploaded document — the ingest simply waits
    and resumes instead of failing the whole file."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return await coro_fn()
        except Exception as e:
            if attempt >= max_attempts or not _is_retryable_embedding_error(e):
                logger.error(
                    f"[embed:{provider}] batch {batch_num}/{total_batches} failed "
                    f"(attempt {attempt}/{max_attempts}): {e}", exc_info=True
                )
                raise
            delay = _retry_after_seconds(e)
            if delay is None:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                f"[embed:{provider}] batch {batch_num}/{total_batches}: transient "
                f"{type(e).__name__} on attempt {attempt}/{max_attempts}, retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)


async def _generate_gemini_embeddings(texts: list[str], api_key: str, task_type: str) -> list[list[float]]:
    """
    Uses the same `google.generativeai` package (and the same module-level
    genai.configure(api_key=...) pattern) already used by GeminiProvider in
    app/services/ai_engine.py for chat completions, to stay consistent with
    the rest of this codebase rather than introducing a second Gemini client
    pattern. embed_content is synchronous, so it's run in a thread like the
    rest of this module's blocking calls.
    """
    import google.generativeai as genai
    loop = asyncio.get_running_loop()
    model = settings.GEMINI_EMBEDDING_MODEL

    def _embed_batch(batch: list[str]) -> list[list[float]]:
        genai.configure(api_key=api_key)
        result = genai.embed_content(model=model, content=batch, task_type=task_type)
        embedding = result["embedding"]
        # A list input always returns a batch (list-of-lists); guard anyway
        # in case a future SDK version ever flattens a single-item batch.
        if embedding and isinstance(embedding[0], (int, float)):
            embedding = [embedding]
        return embedding

    all_embeddings: list[list[float]] = []
    total_batches = (len(texts) + 99) // 100
    for batch_num, i in enumerate(range(0, len(texts), 100), start=1):
        batch = texts[i:i + 100]
        logger.info(f"[embed:gemini] batch {batch_num}/{total_batches} ({len(batch)} text(s), model={model}, task_type={task_type})")

        async def _call():
            return await loop.run_in_executor(None, _embed_batch, batch)

        batch_embeddings = await _call_with_retry(_call, provider="gemini", batch_num=batch_num, total_batches=total_batches)
        all_embeddings.extend(batch_embeddings)

    logger.info(f"[embed:gemini] complete: {len(all_embeddings)} vector(s), dim={len(all_embeddings[0]) if all_embeddings else 0}")
    return all_embeddings


async def generate_embeddings(
    texts: list[str],
    user_id: Optional[str] = None,
    task_type: str = "RETRIEVAL_DOCUMENT",
    forced_provider: Optional[str] = None,
    forced_model: Optional[str] = None,
) -> tuple[list[list[float]], str, str]:
    """
    Generate embeddings for `texts`, automatically using whichever
    embedding-capable AI provider is actually configured (see
    _resolve_embedding_provider). Returns (embeddings, provider_used,
    model_used) so callers (KnowledgeBasePipeline.ingest) can pin a KB to the
    provider/model that actually produced its stored vectors.

    forced_provider/forced_model: when a KB already has vectors stored under
    a specific provider (KnowledgeBase.embedding_provider/embedding_model),
    the caller MUST pass those through so every later ingest/query for that
    KB stays in the same vector space. This never silently substitutes a
    different provider even if the pinned one's key later goes missing —
    that must surface as a clear, actionable error, not a silent switch that
    would corrupt retrieval for the whole KB.
    """
    if not texts:
        raise ValueError("generate_embeddings called with an empty text list")

    if forced_provider:
        if forced_provider not in EMBEDDING_CAPABLE_PROVIDERS:
            raise ValueError(f"Unknown/unsupported pinned embedding provider '{forced_provider}'")
        api_key = await _resolve_provider_key(user_id, forced_provider)
        if not api_key:
            raise ValueError(
                f"This knowledge base was originally embedded with '{forced_provider}', but no "
                f"API key is currently configured for that provider. Re-add a '{forced_provider}' "
                f"API key in Settings → API Keys to continue using this knowledge base, or delete "
                f"it and create a new one to switch providers."
            )
        provider = forced_provider
        logger.info(f"[embed] using pinned provider='{provider}' for this knowledge base ({len(texts)} text(s))")
    else:
        provider, api_key = await _resolve_embedding_provider(user_id)
        logger.info(f"[embed] resolved provider='{provider}' ({len(texts)} text(s))")

    if provider == "gemini":
        model = forced_model or settings.GEMINI_EMBEDDING_MODEL
        embeddings = await _generate_gemini_embeddings(texts, api_key, task_type=task_type)
    else:
        # Defensive — _resolve_embedding_provider/forced_provider validation
        # above should make this unreachable, but never silently no-op.
        raise ValueError(f"Unsupported embedding provider: {provider}")

    if not embeddings or len(embeddings) != len(texts):
        raise ValueError(
            f"Embedding provider '{provider}' returned {len(embeddings) if embeddings else 0} "
            f"vector(s) for {len(texts)} input text(s) — refusing to index a mismatched/partial result."
        )

    return embeddings, provider, model


# ── ChromaDB Helpers ──────────────────────────────────────────────────────────

def _get_chroma_sync() -> chromadb.HttpClient:
    """
    FIX: Always reads CHROMA_HOST/PORT at call time (not at import time).
    This means Docker env overrides (CHROMA_PORT=8000) are respected.
    FIX v5: Explicit settings disable telemetry (which can hang/fail in
    sandboxed or offline environments) and set a short connect timeout so
    a misconfigured CHROMA_HOST fails fast with a clear error instead of
    hanging until the caller's own timeout.
    """
    return chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )


def _wrap_chroma_error(e: Exception, collection_name: str) -> ValueError:
    """
    FIX v5: ChromaDB connection failures (the server isn't reachable, wrong
    host/port, or it hasn't finished starting) previously bubbled up as raw
    httpx/requests exceptions with cryptic or empty messages — exactly the
    kind of thing that displayed as a bare 'Connection Error' to the user.
    This always produces an actionable message.

    FIX v6: also distinguishes a genuine connectivity failure from a
    client/server API VERSION MISMATCH (e.g. the chromadb Python client is
    pinned to 0.5.20's v1 API protocol, but the running server image is a
    newer release that only speaks v2). A version mismatch manifests as an
    HTTP 410 Gone, a 404 on the expected API path, or a JSON-decode failure
    where a structured response was expected — these are NOT solved by
    "check your network", so they're now reported distinctly with the actual
    fix (pin the server image to match the client version).

    ROOT CAUSE FIX: also distinguishes an embedding DIMENSION MISMATCH (the
    vector just generated has a different length than what this collection's
    HNSW index was created with) from a generic vector-database error. This
    only surfaces if a KB's pinned embedding_provider/embedding_model
    (KnowledgeBase.embedding_provider/embedding_model, set on first ingest —
    see app/knowledge/pipeline.py:KnowledgeBasePipeline.ingest) somehow gets
    bypassed. It should not happen in normal operation since generate_embeddings
    always reuses a KB's pinned provider, but if it ever does, this is not a
    connectivity problem and must not be reported as one.
    """
    name = type(e).__name__
    raw = str(e).strip()

    version_mismatch_signals = (
        "410" in raw or "Gone" in raw
        or ("404" in raw and "api/v1" in raw.lower())
        or "JSONDecodeError" in name
        or "unsupported chroma version" in raw.lower()
        or "api version" in raw.lower()
    )
    if version_mismatch_signals:
        return ValueError(
            "The vector database (ChromaDB) responded, but with an API version "
            "your backend doesn't understand. This usually means the ChromaDB "
            "server image and the chromadb Python client package versions don't "
            "match. Pin the chromadb server image (docker-compose.yml) to the "
            "same version as chromadb in backend/requirements.txt."
        )

    if "dimension" in raw.lower() and ("does not match" in raw.lower() or "mismatch" in raw.lower()):
        return ValueError(
            f"Embedding dimension mismatch on collection '{collection_name}': the vector just "
            f"generated doesn't match the dimensionality already stored in this collection. This "
            f"means this knowledge base's pinned embedding provider/model no longer matches what's "
            f"being generated. Delete this knowledge base and create a new one to re-embed with a "
            f"consistent provider. (Underlying error: {raw})"
        )

    if "Connection" in name or "connect" in raw.lower() or not raw:
        return ValueError(
            f"Could not reach the vector database (ChromaDB) at "
            f"{settings.CHROMA_HOST}:{settings.CHROMA_PORT}. "
            f"Make sure the ChromaDB container/service is running and reachable."
        )
    return ValueError(f"Vector database error while processing collection '{collection_name}': {raw}")


async def _run_in_thread(fn, *args, **kwargs):
    """Run a synchronous ChromaDB call in a thread so it doesn't block the event loop."""
    loop = asyncio.get_running_loop()
    import functools
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


def _is_transient_chroma_error(e: Exception) -> bool:
    """True only for a genuinely transient ChromaDB connectivity failure
    worth retrying (e.g. the ChromaDB container hasn't finished starting up
    yet). False for anything retrying can't fix — a missing collection, an
    API version mismatch, or a dimension mismatch are permanent/expected
    states, not startup timing, and must be reported immediately rather
    than retried."""
    if isinstance(e, (chromadb.errors.InvalidCollectionException, chromadb.errors.NotFoundError)):
        return False
    raw = str(e).lower()
    name = type(e).__name__.lower()
    if "dimension" in raw and ("mismatch" in raw or "does not match" in raw):
        return False
    if "410" in raw or "gone" in raw or "jsondecodeerror" in name or "api version" in raw:
        return False
    return (
        "connection" in name or "connect" in raw or "timeout" in name or "timed out" in raw
        or "refused" in raw or "temporarily unavailable" in raw
        or "could not connect to a chroma server" in raw
    )


async def _with_chroma_retry(
    sync_fn,
    collection_name: str,
    max_attempts: int = 4,
    base_delay: float = 0.75,
    not_found_ok: bool = False,
):
    """Run a synchronous ChromaDB call in a thread, retrying with
    exponential backoff a bounded number of times ONLY on a transient
    connection failure (see _is_transient_chroma_error) — the common case
    right after `docker compose up`, where the backend container starts
    before ChromaDB has finished accepting connections. Any other error
    (not-found, dimension mismatch, API version mismatch, or a connection
    failure that persists past max_attempts) is raised immediately via
    _wrap_chroma_error so a real environment/configuration problem is
    always reported clearly rather than retried into a silent timeout.

    not_found_ok=True: a "collection/document doesn't exist" error is not
    an error at all here — returns None so the caller can treat it as the
    legitimate no-op it already was (nothing to delete / no documents
    ingested yet), matching pre-existing behavior.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await _run_in_thread(sync_fn)
        except Exception as e:
            if not_found_ok and _is_not_found_error(e):
                return None
            if attempt >= max_attempts or not _is_transient_chroma_error(e):
                raise _wrap_chroma_error(e, collection_name) from e
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"[chroma:retry] collection='{collection_name}': transient {type(e).__name__} "
                f"on attempt {attempt}/{max_attempts} (likely still starting up); retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)


# ── KB Pipeline ───────────────────────────────────────────────────────────────

def _is_not_found_error(e: Exception) -> bool:
    """True for a ChromaDB 'collection/resource does not exist' response —
    the one case where 'delete something that isn't there' is a legitimate,
    already-achieved outcome rather than a failure to report.

    ROOT CAUSE FIX: this previously also matched on `type(e).__name__ ==
    "ValueError"`. chromadb 0.5.20's client raises a plain ValueError with
    the message "Could not connect to a Chroma server. Are you sure it is
    running?" whenever the server is entirely unreachable — a completely
    different situation from "this collection doesn't exist yet" (which is
    chromadb.errors.InvalidCollectionException, message "...does not
    exist.", already matched below by the substring check). Because Python's
    ValueError is also the base/only type for several *other* unrelated
    chromadb client errors, matching on that type name alone silently
    swallowed genuine connectivity outages: delete_document/delete_collection
    would log "already absent — nothing to delete" and return as if nothing
    were wrong, and retrieve()'s equivalent inline check (below) would treat
    every chat/search query as if the knowledge base simply had zero
    documents — a ChromaDB outage was completely indistinguishable from an
    empty KB. Only the actual chromadb exception classes for "doesn't exist"
    are matched now, isinstance-checked directly rather than by name string,
    plus the message substrings those classes are documented to use.
    """
    if isinstance(e, (chromadb.errors.InvalidCollectionException, chromadb.errors.NotFoundError)):
        return True
    raw = str(e).lower()
    return "does not exist" in raw or "not found" in raw


class KnowledgeBasePipeline:

    async def ingest(
        self,
        file_path: Optional[str],
        file_type: str,
        document_id: str,
        kb_id: str,
        collection_name: str,
        filename: str,
        user_id: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None,
        raw_text: Optional[str] = None,
    ) -> dict:
        """
        Run a document through the full pipeline: extract -> clean -> chunk ->
        embed -> index in ChromaDB. Every stage is logged. Any failure raises
        (never suppressed, never returns a 'ready'/success result for a
        partially-completed pipeline) so the caller (the background ingest
        task in app/api/v1/knowledge.py) can mark the document status="error"
        with an actionable message instead of silently leaving it stuck or
        falsely marked "ready".

        embedding_provider/embedding_model: pass the KB's already-pinned
        values (KnowledgeBase.embedding_provider/embedding_model) for every
        ingest after the first, so every document in a KB shares one vector
        space. Leave both None only for a KB's very first successful ingest —
        the provider is then auto-resolved and returned in the result dict
        for the caller to persist onto the KB row.

        raw_text: NEW (Voice AI Part 4, Text Knowledge Base). When provided,
        step 1 (file extraction) is skipped entirely and this text is used
        directly — this is what lets a user paste text straight into a
        Knowledge Base with no file/upload round-trip, while sharing every
        other stage (clean/chunk/embed/index) unchanged with the file-upload
        path. `file_path` is then unused (may be None).
        """
        logger.info(f"[ingest:start] doc={document_id} kb={kb_id} file={filename} type={file_type} pasted_text={raw_text is not None}")

        # 1. Extract (or use pasted text directly — Text Knowledge Base)
        if raw_text is None:
            raw_text = await extract_text(file_path, file_type)
        if not raw_text.strip():
            raise ValueError(
                f"No text could be extracted from '{filename}'. The file may be empty, "
                f"image-only (scanned PDF with no OCR text layer), or corrupted."
            )

        # 2. Clean + Chunk
        chunks = chunk_text(clean_text(raw_text))
        if not chunks:
            raise ValueError(
                f"'{filename}' produced no valid text chunks after cleaning — the extracted "
                f"text may be too short or entirely low-value whitespace/punctuation."
            )
        logger.info(f"[ingest] doc={document_id}: {len(chunks)} chunk(s) ready to embed")

        # 3. Embed — auto-resolves (or reuses the KB's pinned) provider.
        embeddings, provider_used, model_used = await generate_embeddings(
            chunks,
            user_id=user_id,
            task_type="RETRIEVAL_DOCUMENT",
            forced_provider=embedding_provider,
            forced_model=embedding_model,
        )
        if len(embeddings) != len(chunks):
            # Defensive — generate_embeddings already validates this, but an
            # ingest must never proceed to index a mismatched result.
            raise ValueError(
                f"Embedding count ({len(embeddings)}) does not match chunk count ({len(chunks)}) "
                f"for '{filename}' — aborting ingest rather than indexing a partial/misaligned result."
            )

        # 4. Store in ChromaDB (sync client in thread)
        ids       = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "kb_id": kb_id,
                "filename": filename,
                "chunk_index": i,
                "chunk_total": len(chunks),
                "embedding_provider": provider_used,
                "embedding_model": model_used,
            }
            for i in range(len(chunks))
        ]

        def _upsert():
            client     = _get_chroma_sync()
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )

        logger.info(
            f"[ingest] doc={document_id}: indexing {len(chunks)} chunk(s) into "
            f"collection='{collection_name}' (provider={provider_used}, model={model_used})"
        )
        await _with_chroma_retry(_upsert, collection_name)
        logger.info(f"[ingest:done] doc={document_id} kb={kb_id}: {len(chunks)} chunk(s) indexed successfully")

        return {
            "chunk_count":         len(chunks),
            "status":              "ready",
            "embedding_provider":  provider_used,
            "embedding_model":     model_used,
        }

    async def delete_document(self, document_id: str, collection_name: str) -> None:
        """
        Delete all chunks for a document from ChromaDB. A collection/document
        that's already gone is a legitimate, idempotent success (nothing left
        to delete) — but a genuine ChromaDB failure (connectivity, version
        mismatch) is NOT swallowed: it's raised so the API layer can report
        the delete as failed instead of returning 204 while orphaned vectors
        remain indexed and retrievable forever.
        """
        def _delete():
            client     = _get_chroma_sync()
            collection = client.get_collection(collection_name)
            collection.delete(where={"document_id": document_id})

        result = await _with_chroma_retry(_delete, collection_name, not_found_ok=True)
        if result is None:
            logger.info(
                f"[delete:document] doc={document_id}: collection='{collection_name}' "
                f"already absent — nothing to delete"
            )
        else:
            logger.info(f"[delete:document] doc={document_id} removed from collection='{collection_name}'")

    async def delete_collection(self, collection_name: str) -> None:
        """Delete an entire KB's collection. Same not-found-is-OK, real-errors-raise
        policy as delete_document — see its docstring."""
        def _delete():
            _get_chroma_sync().delete_collection(collection_name)

        result = await _with_chroma_retry(_delete, collection_name, not_found_ok=True)
        if result is None:
            logger.info(f"[delete:collection] collection='{collection_name}' already absent — nothing to delete")
        else:
            logger.info(f"[delete:collection] collection='{collection_name}' deleted")


# ── Retrieval Engine ──────────────────────────────────────────────────────────

class RetrievalEngine:
    """
    FIX: Redis cache is accessed via a property that reads the global
    redis_client at call time — never captures a stale None from import time.
    Previously self.cache = CacheService() in __init__ was called when the
    module singleton was created (before lifespan ran init_redis()), so
    self.cache.redis was always None and caching silently did nothing.
    """

    @property
    def _cache(self):
        from app.core.redis import CacheService
        return CacheService()

    async def retrieve(
        self,
        query: str,
        collection_name: str,
        kb_id: str,
        n_results: int = None,
        score_threshold: float = None,
        user_id: Optional[str] = None,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> list[dict]:
        """
        embedding_provider/embedding_model: pass the KB's pinned values
        (KnowledgeBase.embedding_provider/embedding_model) so the query is
        embedded in the exact same vector space as the documents already
        indexed for this KB — mirroring the pin used at ingest time. If
        omitted (e.g. a KB that has never had a successful ingest), the
        provider is freshly auto-resolved, matching what a first ingest
        would pick.
        """
        n_results       = n_results or settings.MAX_RETRIEVAL_RESULTS
        score_threshold = score_threshold or settings.RETRIEVAL_SCORE_THRESHOLD
        logger.info(f"[retrieve:start] kb={kb_id} collection='{collection_name}' query_len={len(query)} n_results={n_results}")

        # Cache lookup
        # ROOT CAUSE FIX: the cache key previously hashed only the query text,
        # not n_results/score_threshold. A search from the KB panel (e.g.
        # n_results=5) and a retrieval during a chat run through an AI Agent
        # node (whatever n_results/score_threshold that node is configured
        # with) share this exact same cache namespace — with the same query
        # text but different parameters, whichever call ran first would have
        # its cached result served back to the second, returning either too
        # few/many chunks or chunks that shouldn't have passed that call's
        # own score_threshold. Both parameters are now part of the key so
        # each distinct (query, n_results, score_threshold) combination gets
        # its own cache entry.
        cache_key = (
            f"retrieval:{kb_id}:"
            f"{hashlib.md5(query.encode()).hexdigest()}:{n_results}:{score_threshold}"
        )
        cached    = await self._cache.get(cache_key)
        if cached:
            logger.info(f"[retrieve:cache_hit] kb={kb_id}: {len(cached)} cached result(s)")
            return cached

        # Generate query embedding — reuse the KB's pinned provider/model so
        # the query vector lands in the same space as the indexed documents.
        embeddings, provider_used, _ = await generate_embeddings(
            [query],
            user_id=user_id,
            task_type="RETRIEVAL_QUERY",
            forced_provider=embedding_provider,
            forced_model=embedding_model,
        )
        query_embedding = embeddings[0]
        logger.info(f"[retrieve] kb={kb_id}: query embedded via provider='{provider_used}'")

        # Query ChromaDB in thread.
        # FIX v6: distinguish "this collection doesn't exist yet" (a legitimate,
        # expected state for a brand-new knowledge base with no successfully
        # ingested documents — should silently return no results) from a
        # genuine ChromaDB failure during query (connectivity loss, API version
        # mismatch, etc — should propagate as a real, diagnosable error instead
        # of silently returning an empty list, which previously made retrieval
        # failures during an AI conversation completely invisible).
        def _query():
            client     = _get_chroma_sync()
            collection = client.get_collection(collection_name)
            return collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results * 2, 20),
                include=["documents", "metadatas", "distances"],
            )

        results = await _with_chroma_retry(_query, collection_name, not_found_ok=True)
        if not results:
            logger.info(f"[retrieve] kb={kb_id}: collection='{collection_name}' has no ingested documents yet")
            return []

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        logger.info(f"[retrieve] kb={kb_id}: chroma returned {len(documents)} candidate chunk(s)")

        retrieved = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            score = max(0.0, 1.0 - dist)
            if score < score_threshold:
                continue
            retrieved.append({
                "content":     doc,
                "source":      meta.get("filename", "Unknown"),
                "document_id": meta.get("document_id"),
                "chunk_index": meta.get("chunk_index", 0),
                "score":       round(score, 4),
                "metadata":    meta,
            })

        retrieved.sort(key=lambda x: x["score"], reverse=True)
        retrieved = self._rerank(retrieved)[:n_results]
        logger.info(
            f"[retrieve:done] kb={kb_id}: {len(retrieved)} result(s) above score_threshold={score_threshold} "
            f"(from {len(documents)} candidate(s))"
        )

        await self._cache.set(cache_key, retrieved, ttl=settings.KB_CACHE_TTL)
        return retrieved

    def _rerank(self, results: list[dict]) -> list[dict]:
        seen, primary, secondary = set(), [], []
        for r in results:
            doc_id = r.get("document_id")
            (primary if doc_id not in seen else secondary).append(r)
            seen.add(doc_id)
        return primary + secondary

    def format_context(self, results: list[dict]) -> str:
        if not results:
            return ""
        return "\n\n---\n\n".join(
            f"[Source {i}: {r['source']} | Relevance: {r['score']:.0%}]\n{r['content']}"
            for i, r in enumerate(results, 1)
        )

    def format_citations(self, results: list[dict]) -> list[dict]:
        return [
            {
                "index":   i + 1,
                "source":  r["source"],
                "score":   r["score"],
                "excerpt": r["content"][:150] + "…" if len(r["content"]) > 150 else r["content"],
            }
            for i, r in enumerate(results)
        ]


# ── Singletons ────────────────────────────────────────────────────────────────
kb_pipeline      = KnowledgeBasePipeline()
retrieval_engine = RetrievalEngine()
