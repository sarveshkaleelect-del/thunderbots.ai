"""
ThunderBots Knowledge Base API v5
ROOT CAUSE FIX: _ingest_document now loads the KnowledgeBase row BEFORE
     calling kb_pipeline.ingest() (previously it was only loaded afterward,
     to update aggregate counters) so the KB's already-pinned
     embedding_provider/embedding_model (if any) can be passed through and
     reused — see app/knowledge/pipeline.py for why this pin exists. On a
     KB's first successful ingest, the provider/model the pipeline actually
     used is persisted back onto the KB row so every later document/query
     for this KB stays in the same vector space regardless of what the
     user's default AI provider is set to later.
FIX: search_knowledge_base passes the KB's pinned embedding_provider/model
     through to retrieval_engine.retrieve() for the same reason.
FIX: delete_document/delete_knowledge_base now surface a real ChromaDB
     failure as an error response instead of silently returning
     success/204 while vectors remain orphaned in the collection — the
     pipeline's delete_document/delete_collection no longer swallow
     genuine failures (only an already-absent collection/document, which is
     a legitimate no-op).
FIX: _ingest_document passes user_id to kb_pipeline.ingest() so the correct
     API key is used for embedding generation.
FIX: Error messages are always non-empty strings.
FIX: Stale KB retrieval cache is invalidated after upload and delete.
"""
import os
import uuid
import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.models.user import User
from app.models.knowledge import KnowledgeBase, KBDocument
from app.knowledge.pipeline import kb_pipeline, retrieval_engine
from app.config import settings
from app.services import audit_service
from app.services.audit_service import Action

router  = APIRouter()
logger  = logging.getLogger(__name__)
ALLOWED = {"pdf", "docx", "txt", "md", "markdown"}


def _user_facing_error_message(e: Exception) -> str:
    """Turn an ingestion-pipeline exception into a short, actionable message
    safe to store on KBDocument.error_message and show directly in the UI.

    ROOT CAUSE FIX: the previous code stored str(e) unconditionally. That's
    fine for the ValueError's this codebase deliberately raises with
    hand-written, already-friendly text (API-key-missing, dimension-mismatch,
    etc.) — those are passed through as-is below. But any *other* exception
    (a raw SDK error from openai/google-generativeai, an httpx connection
    error talking to ChromaDB, a driver-level DB error, ...) was also being
    stored and displayed verbatim, which can surface library-internal
    wording, HTTP status dumps, or connection details that mean nothing to
    an end user. Those classes are now caught and rewritten into a plain,
    actionable sentence; anything still unrecognized falls back to a generic
    message instead of whatever the exception's __str__ happened to produce.
    The full exception (with traceback) is always still logged server-side
    via exc_info=True at the call site — only what reaches the user is
    changed here.
    """
    msg = str(e).strip()

    # Deliberately-raised, already-friendly messages from this codebase —
    # pass through unchanged.
    if isinstance(e, ValueError):
        return msg or f"Ingestion failed ({type(e).__name__})"

    type_name = type(e).__name__
    lower = msg.lower()

    # OpenAI / Gemini SDK error classes are named consistently enough across
    # both libraries to key off the class name rather than importing both
    # SDKs here just to catch their exception types.
    if "authenticat" in type_name.lower() or "permissiondenied" in type_name.lower() or "unauthenticated" in type_name.lower() or "401" in msg or "invalid_api_key" in lower or "api key not valid" in lower:
        return ("The embedding provider rejected the configured API key. "
                "Check the key under Settings → API Keys and try again.")
    if "ratelimit" in type_name.lower() or "429" in msg or "quota" in lower:
        return ("The embedding provider is rate-limiting requests right now. "
                "Please wait a moment and try again.")
    if "timeout" in type_name.lower() or "connect" in type_name.lower() or "connection" in lower or "not in allowlist" in lower or "name or service not known" in lower:
        return ("Couldn't reach the embedding or vector database service. "
                "Please check connectivity and try again.")
    if "apistatuserror" in type_name.lower() or "internalservererror" in type_name.lower() or "badgateway" in type_name.lower() or "serviceunavailable" in type_name.lower():
        return ("The embedding provider is temporarily unavailable. Please try again shortly.")

    # Defensive: never let anything resembling a traceback/file path through.
    if not msg or "traceback" in lower or "/site-packages/" in msg or '\n  File "' in msg:
        return f"Document processing failed unexpectedly ({type_name}). Please try again."

    return msg[:500]


# ── Schemas ───────────────────────────────────────────────────────────────────

class KBCreate(BaseModel):
    name:        str
    description: Optional[str] = None
    # NEW (Part 4): "file" (default, unchanged) | "text" — purely a label,
    # see KnowledgeBase.kb_type docstring in models/knowledge.py.
    kb_type:     str = "file"


class SearchRequest(BaseModel):
    query:           str
    n_results:       int   = 5
    score_threshold: float = 0.3


# NEW (Voice AI Part 4) — Text Knowledge Base ───────────────────────────────
# "Virtually unlimited" pasted text is still bounded by a real server-side
# limit (never an unbounded write) — large enough that no realistic pasted
# document (an FAQ page, a policy doc, a full product manual) ever hits it.
MAX_TEXT_KB_CHARS = 2_000_000  # ~2M characters (~400k words)


class TextEntryCreate(BaseModel):
    title:   str = Field(default="", max_length=255)
    content: str = Field(..., min_length=1)


class TextEntryUpdate(BaseModel):
    title:   Optional[str] = Field(default=None, max_length=255)
    content: str = Field(..., min_length=1)


class TextEntryAppend(BaseModel):
    content: str = Field(..., min_length=1)


# ── Background ingestion ──────────────────────────────────────────────────────

async def _ingest_document(
    doc_id:     str,
    kb_id:      str,
    file_path:  Optional[str],
    file_type:  str,
    filename:   str,
    collection: str,
    user_id:    str,        # FIX: needed to resolve correct embedding provider's API key
    raw_text:   Optional[str] = None,   # NEW (Part 4): Text Knowledge Base pasted content
):
    logger.info(f"[kb:upload] background ingest starting: doc={doc_id} kb={kb_id} file={filename} type={file_type} pasted_text={raw_text is not None}")
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            # ROOT CAUSE FIX: load the KB row FIRST so an already-pinned
            # embedding_provider/embedding_model (set by a previous
            # successful ingest into this same KB) is reused. Without this,
            # a second document could get embedded by a *different*
            # provider than the first (e.g. if the user's default provider
            # preference changed between uploads), producing vectors of a
            # different dimensionality in the same Chroma collection.
            kb_result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            kb = kb_result.scalar_one_or_none()
            if not kb:
                # The KB was deleted while this document was queued/processing.
                raise ValueError(f"Knowledge base {kb_id} no longer exists")

            result = await kb_pipeline.ingest(
                file_path=file_path,
                file_type=file_type,
                document_id=doc_id,
                kb_id=kb_id,
                collection_name=collection,
                filename=filename,
                user_id=user_id,
                embedding_provider=kb.embedding_provider,   # None on first ingest
                embedding_model=kb.embedding_model,         # None on first ingest
                raw_text=raw_text,
            )

            now = datetime.now(timezone.utc)
            await db.execute(
                update(KBDocument)
                .where(KBDocument.id == doc_id)
                .values(
                    status="ready",
                    chunk_count=result["chunk_count"],
                    processed_at=now,
                )
            )

            # Update KB aggregate stats + pin the embedding provider/model on
            # this KB's very first successful ingest.
            kb.chunk_count    = (kb.chunk_count    or 0) + result["chunk_count"]
            kb.document_count = (kb.document_count or 0) + 1
            if not kb.embedding_provider:
                kb.embedding_provider = result["embedding_provider"]
                kb.embedding_model    = result["embedding_model"]
                logger.info(
                    f"[kb:upload] kb={kb_id}: pinned embedding_provider="
                    f"'{result['embedding_provider']}' model='{result['embedding_model']}'"
                )

            await db.commit()

            # FIX: Invalidate any stale retrieval caches for this KB
            cache = CacheService()
            await cache.delete_pattern(f"retrieval:{kb_id}:*")
            await cache.delete(f"kb:{kb_id}")

            logger.info(
                f"[kb:upload] ingest complete: doc={doc_id} kb={kb_id} "
                f"chunks={result['chunk_count']} file={filename} provider={result['embedding_provider']}"
            )

        except Exception as e:
            # FIX: always store a non-empty, user-safe error message. Never
            # suppressed — the document is explicitly marked status="error"
            # so the frontend never shows a false "ready" for a failed
            # pipeline run. The full exception is logged (with traceback)
            # server-side; only a sanitized summary is persisted/shown.
            error_msg = _user_facing_error_message(e)
            logger.error(f"[kb:upload] ingest FAILED: doc={doc_id} kb={kb_id}: {e}", exc_info=True)
            await db.execute(
                update(KBDocument)
                .where(KBDocument.id == doc_id)
                .values(status="error", error_message=error_msg[:2000])
            )
            await db.commit()
        finally:
            # ROOT CAUSE FIX: only remove the temp upload once it has been
            # successfully indexed (or the KB it belonged to is gone). A
            # failed ingest keeps its temp file so "Retry" can re-run the
            # exact same pipeline without asking the user to re-upload —
            # previously this ran unconditionally, so even a transient
            # failure (a rate limit, a momentary ChromaDB blip) permanently
            # destroyed the only copy of the file, making retry impossible
            # even after the transient issue passed.
            doc_row = await db.execute(select(KBDocument.status).where(KBDocument.id == doc_id))
            row = doc_row.first()
            status_now = row[0] if row else None
            if status_now != "error" and file_path:
                try:
                    os.unlink(file_path)
                except Exception:
                    pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

# ROOT CAUSE FIX: these two routes were declared as "/" (only matching
# .../knowledge/ with a trailing slash) while every frontend call hits
# .../knowledge with NO trailing slash (see frontend/lib/api/knowledge.ts).
# Starlette's default redirect_slashes behavior turns the mismatched
# request into a 307 redirect to the slashed URL. GET redirects are
# mostly harmless, but a 307 on a cross-origin POST is exactly the kind
# of request browsers/proxies/HTTP clients handle inconsistently (lost
# Authorization header, a second CORS preflight, some clients not
# re-sending the body at all) — this is what made "Create Knowledge
# Base" intermittently fail before any document was ever uploaded.
# Both the slash and no-slash paths are now registered explicitly so
# the request is served directly, with no redirect, either way.
@router.get("")
@router.get("/")
async def list_knowledge_bases(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == current_user.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()
    return [
        {
            "id":             str(kb.id),
            "name":           kb.name,
            "description":    kb.description,
            "kb_type":        kb.kb_type or "file",
            "document_count": kb.document_count or 0,
            "chunk_count":    kb.chunk_count    or 0,
            "created_at":     kb.created_at.isoformat() if kb.created_at else None,
        }
        for kb in kbs
    ]


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_knowledge_base(
    payload:      KBCreate,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    # Sanitize collection name: alphanumeric + underscore only
    safe_uid = str(uuid.uuid4()).replace("-", "")[:12]
    safe_id  = current_user.id.replace("-", "")[:12]
    collection_name = f"kb_{safe_id}_{safe_uid}"

    kb = KnowledgeBase(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        chroma_collection=collection_name,
        kb_type=payload.kb_type if payload.kb_type in ("file", "text") else "file",
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    await audit_service.record(
        db, Action.KNOWLEDGE_BASE_CREATE, actor=current_user, request=request,
        target_type="knowledge_base", target_id=str(kb.id), target_label=kb.name,
    )
    return {
        "id":                 str(kb.id),
        "name":               kb.name,
        "kb_type":            kb.kb_type,
        "chroma_collection":  kb.chroma_collection,
        "document_count":     0,
        "chunk_count":        0,
    }


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id:        str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    kb_name = kb.name

    # Failed documents keep their temp upload on disk to support retry (see
    # _ingest_document's finally block) — collect those paths before the
    # cascade delete removes the rows that reference them, so they don't
    # become orphaned files once the KB itself is gone.
    orphaned_result = await db.execute(
        select(KBDocument.id, KBDocument.file_type)
        .where(KBDocument.knowledge_base_id == kb_id, KBDocument.status == "error")
    )
    orphaned_files = orphaned_result.all()

    # ROOT CAUSE FIX: delete_collection now raises on a genuine ChromaDB
    # failure (it only swallows "already doesn't exist"). Never delete the
    # KB's Postgres row / return 204 success if the vector data could not
    # actually be removed — that would silently orphan the collection with
    # no KB row left to ever clean it up, and falsely tell the user it's gone.
    try:
        await kb_pipeline.delete_collection(kb.chroma_collection)
    except Exception as e:
        logger.error(f"[kb:delete] failed to delete collection for kb={kb_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=_user_facing_error_message(e) or "Failed to delete the knowledge base's vector data")

    await db.delete(kb)
    await db.commit()

    for orphan_id, orphan_type in orphaned_files:
        try:
            os.unlink(os.path.join(settings.UPLOAD_DIR, f"{orphan_id}.{orphan_type}"))
        except Exception:
            pass

    cache = CacheService()
    await cache.delete_pattern(f"retrieval:{kb_id}:*")
    await cache.delete(f"kb:{kb_id}")
    logger.info(f"[kb:delete] knowledge base deleted: kb={kb_id}")
    await audit_service.record(
        db, Action.KNOWLEDGE_BASE_DELETE, actor=current_user, request=request,
        target_type="knowledge_base", target_id=kb_id, target_label=kb_name,
    )


@router.post("/{kb_id}/upload")
async def upload_document(
    kb_id:            str,
    background_tasks: BackgroundTasks,
    request:          Request,
    file:             UploadFile = File(...),
    db:               AsyncSession = Depends(get_db),
    current_user:     User         = Depends(get_current_user),
):
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{suffix}' not supported. Allowed: pdf, docx, txt, md",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File size {size_mb:.1f}MB exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit",
        )

    # ROOT CAUSE FIX: no duplicate-upload detection existed at all — the same
    # file could be uploaded to a KB any number of times, each time
    # re-embedding and re-indexing the identical text as a brand-new
    # document. Besides wasting embedding-API calls, this crowds out
    # genuinely-different content in retrieval (near-duplicate chunks
    # competing for the same top-N results). A KB is not append-only log
    # storage, so identical content already present (or currently being
    # processed) is rejected with a clear, actionable message instead of
    # silently duplicating it. A document that previously failed to index
    # (status="error") does NOT count as a duplicate — re-uploading is a
    # legitimate way to retry without knowing about the dedicated endpoint.
    content_hash = hashlib.sha256(content).hexdigest()
    existing_result = await db.execute(
        select(KBDocument.filename, KBDocument.status, KBDocument.doc_metadata)
        .where(
            KBDocument.knowledge_base_id == kb_id,
            KBDocument.status.in_(["processing", "ready"]),
        )
    )
    for existing_filename, existing_status, existing_meta in existing_result.all():
        if (existing_meta or {}).get("content_hash") == content_hash:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This file is already in this knowledge base as "
                    f"'{existing_filename}' ({existing_status}). Delete it first "
                    f"if you want to re-upload the same content."
                ),
            )

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    doc_id    = str(uuid.uuid4())
    temp_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}.{suffix}")

    with open(temp_path, "wb") as fh:
        fh.write(content)

    doc = KBDocument(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=file.filename,
        file_type=suffix,
        file_size=len(content),
        status="processing",
        doc_metadata={"content_hash": content_hash},
    )
    db.add(doc)
    await db.commit()

    logger.info(
        f"[kb:upload] accepted: doc={doc_id} kb={kb_id} file={file.filename} "
        f"type={suffix} size_mb={size_mb:.2f} — queuing background ingest"
    )

    # FIX: pass user_id so background task can resolve correct embedding key
    background_tasks.add_task(
        _ingest_document,
        doc_id, kb_id, temp_path, suffix, file.filename,
        kb.chroma_collection, str(current_user.id),
    )

    audit_service.record_bg(
        background_tasks, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="knowledge_base_document", target_id=doc_id, target_label=file.filename,
        metadata={"knowledge_base_id": kb_id, "file_type": suffix, "size_mb": round(size_mb, 2)},
    )

    return {
        "id":       doc_id,
        "filename": file.filename,
        "status":   "processing",
        "size_mb":  round(size_mb, 2),
    }


@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id:        str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    kb_result = await db.execute(
        select(KnowledgeBase.id).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    if not kb_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    result = await db.execute(
        select(KBDocument)
        .where(KBDocument.knowledge_base_id == kb_id)
        .order_by(KBDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        {
            "id":            str(d.id),
            "filename":      d.filename,
            "file_type":     d.file_type,
            "file_size":     d.file_size,
            "status":        d.status,
            "chunk_count":   d.chunk_count or 0,
            "error_message": d.error_message,
            "source_type":   d.source_type or "upload",
            # Preview only (list view) — full text via GET .../text/{doc_id}
            "text_preview":  (d.raw_text[:280] + "…") if d.raw_text and len(d.raw_text) > 280 else d.raw_text,
            "created_at":    d.created_at.isoformat()    if d.created_at    else None,
            "processed_at":  d.processed_at.isoformat()  if d.processed_at  else None,
        }
        for d in docs
    ]


# ── Text Knowledge Base (NEW, Voice AI Part 4) ──────────────────────────────
# Paste text directly into a Knowledge Base instead of uploading a file.
# Reuses every stage of the existing pipeline (clean/chunk/embed/index,
# dedup-by-hash convention, background ingestion, retry-on-error) — the
# only difference from upload_document is that step 1 (file extraction) is
# skipped because the text is already in hand. A pasted-text entry is a
# perfectly ordinary KBDocument (source_type="pasted_text", file_type="txt")
# so it shows up in list_documents/search/retrieval exactly like an
# uploaded .txt file — no second storage system, no duplicated ingestion
# logic.

@router.post("/{kb_id}/text", status_code=201)
async def create_text_entry(
    kb_id:            str,
    payload:          TextEntryCreate,
    background_tasks: BackgroundTasks,
    request:          Request,
    db:               AsyncSession = Depends(get_db),
    current_user:     User         = Depends(get_current_user),
):
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Pasted text cannot be empty")
    if len(content) > MAX_TEXT_KB_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Pasted text is {len(content):,} characters, which exceeds the "
                   f"{MAX_TEXT_KB_CHARS:,}-character limit per entry. Split it into multiple entries.",
        )

    title = payload.title.strip() or f"Pasted text ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})"
    doc_id = str(uuid.uuid4())

    doc = KBDocument(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=title,
        file_type="txt",
        file_size=len(content.encode("utf-8")),
        status="processing",
        source_type="pasted_text",
        raw_text=content,
        doc_metadata={"content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()},
    )
    db.add(doc)
    await db.commit()

    logger.info(f"[kb:text] accepted: doc={doc_id} kb={kb_id} title='{title}' chars={len(content)} — queuing background ingest")

    # NEW (Part 4): "index instantly" — queued the same way an upload is,
    # which already runs within a second or two of the request returning
    # for typical entry sizes (no queueing behind a slow multi-MB file).
    background_tasks.add_task(
        _ingest_document,
        doc_id, kb_id, None, "txt", title, kb.chroma_collection, str(current_user.id), content,
    )

    audit_service.record_bg(
        background_tasks, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="knowledge_base_document", target_id=doc_id, target_label=title,
        metadata={"knowledge_base_id": kb_id, "source_type": "pasted_text", "chars": len(content)},
    )

    return {"id": doc_id, "filename": title, "status": "processing", "chars": len(content)}


@router.get("/{kb_id}/text/{doc_id}")
async def get_text_entry(
    kb_id:        str,
    doc_id:       str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """Full raw text of a pasted entry — used to populate the edit form
    (list_documents only returns a short preview)."""
    kb_result = await db.execute(
        select(KnowledgeBase.id).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
    )
    if not kb_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc_result = await db.execute(
        select(KBDocument).where(KBDocument.id == doc_id, KBDocument.knowledge_base_id == kb_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc or doc.source_type != "pasted_text":
        raise HTTPException(status_code=404, detail="Text entry not found")

    return {
        "id": str(doc.id), "title": doc.filename, "content": doc.raw_text or "",
        "status": doc.status, "chunk_count": doc.chunk_count or 0,
    }


async def _replace_text_entry(
    *, kb: KnowledgeBase, doc: KBDocument, new_title: Optional[str], new_content: str,
    background_tasks: BackgroundTasks, current_user: User, db: AsyncSession,
) -> dict:
    """Shared by PUT (replace/edit) and the append endpoint: removes the
    document's existing vectors (old content must not stay retrievable
    alongside the new content) then re-queues ingestion with the updated
    text — same background pipeline as a first-time paste."""
    try:
        await kb_pipeline.delete_document(doc.id, kb.chroma_collection)
    except Exception as e:
        logger.error(f"[kb:text] failed to clear old vectors before re-ingest: doc={doc.id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=_user_facing_error_message(e) or "Failed to update this text entry")

    kb.chunk_count = max(0, (kb.chunk_count or 0) - (doc.chunk_count or 0))
    doc.filename = (new_title or doc.filename).strip() or doc.filename
    doc.raw_text = new_content
    doc.file_size = len(new_content.encode("utf-8"))
    doc.status = "processing"
    doc.error_message = None
    doc.chunk_count = 0
    doc.doc_metadata = {"content_hash": hashlib.sha256(new_content.encode("utf-8")).hexdigest()}
    await db.commit()

    cache = CacheService()
    await cache.delete_pattern(f"retrieval:{kb.id}:*")

    background_tasks.add_task(
        _ingest_document,
        doc.id, kb.id, None, "txt", doc.filename, kb.chroma_collection, str(current_user.id), new_content,
    )
    return {"id": doc.id, "filename": doc.filename, "status": "processing", "chars": len(new_content)}


@router.put("/{kb_id}/text/{doc_id}")
async def update_text_entry(
    kb_id:            str,
    doc_id:           str,
    payload:          TextEntryUpdate,
    background_tasks: BackgroundTasks,
    request:          Request,
    db:               AsyncSession = Depends(get_db),
    current_user:     User         = Depends(get_current_user),
):
    """Replace/edit a pasted-text entry's content in place."""
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc_result = await db.execute(
        select(KBDocument).where(KBDocument.id == doc_id, KBDocument.knowledge_base_id == kb_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc or doc.source_type != "pasted_text":
        raise HTTPException(status_code=404, detail="Text entry not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Pasted text cannot be empty")
    if len(content) > MAX_TEXT_KB_CHARS:
        raise HTTPException(status_code=413, detail=f"Pasted text exceeds the {MAX_TEXT_KB_CHARS:,}-character limit")

    result = await _replace_text_entry(
        kb=kb, doc=doc, new_title=payload.title, new_content=content,
        background_tasks=background_tasks, current_user=current_user, db=db,
    )
    await audit_service.record(
        db, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="knowledge_base_document", target_id=doc_id, target_label=doc.filename,
        metadata={"knowledge_base_id": kb_id, "source_type": "pasted_text", "action": "replace"},
    )
    return result


@router.post("/{kb_id}/text/{doc_id}/append")
async def append_text_entry(
    kb_id:            str,
    doc_id:           str,
    payload:          TextEntryAppend,
    background_tasks: BackgroundTasks,
    request:          Request,
    db:               AsyncSession = Depends(get_db),
    current_user:     User         = Depends(get_current_user),
):
    """Append more text onto an existing pasted-text entry, then re-index
    the combined content (the previous vectors are cleared first so the
    entry never has two overlapping/duplicated versions retrievable at
    once)."""
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc_result = await db.execute(
        select(KBDocument).where(KBDocument.id == doc_id, KBDocument.knowledge_base_id == kb_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc or doc.source_type != "pasted_text":
        raise HTTPException(status_code=404, detail="Text entry not found")

    addition = payload.content.strip()
    if not addition:
        raise HTTPException(status_code=400, detail="Text to append cannot be empty")

    combined = f"{doc.raw_text or ''}\n\n{addition}".strip()
    if len(combined) > MAX_TEXT_KB_CHARS:
        raise HTTPException(status_code=413, detail=f"Combined text would exceed the {MAX_TEXT_KB_CHARS:,}-character limit")

    result = await _replace_text_entry(
        kb=kb, doc=doc, new_title=None, new_content=combined,
        background_tasks=background_tasks, current_user=current_user, db=db,
    )
    await audit_service.record(
        db, Action.KNOWLEDGE_BASE_UPLOAD, actor=current_user, request=request,
        target_type="knowledge_base_document", target_id=doc_id, target_label=doc.filename,
        metadata={"knowledge_base_id": kb_id, "source_type": "pasted_text", "action": "append"},
    )
    return result


# Deleting a text entry reuses the exact same DELETE /{kb_id}/documents/{doc_id}
# endpoint used for uploaded files (below) — a pasted-text KBDocument is
# deleted identically, no separate route needed.


@router.post("/{kb_id}/documents/{doc_id}/retry")
async def retry_document(
    kb_id:             str,
    doc_id:            str,
    background_tasks:  BackgroundTasks,
    db:                AsyncSession = Depends(get_db),
    current_user:      User         = Depends(get_current_user),
):
    """ROOT CAUSE FIX: there was no way to recover from a failed document
    other than deleting it and re-uploading from scratch — and until the
    'finally' block above stopped unconditionally deleting the temp upload
    on every outcome, there wasn't even a file left to retry from. This
    re-queues the exact same ingestion using the file that upload_document
    already saved to UPLOAD_DIR, which failed ingestion now preserves."""
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc_result = await db.execute(
        select(KBDocument).where(
            KBDocument.id == doc_id,
            KBDocument.knowledge_base_id == kb_id,
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status != "error":
        raise HTTPException(
            status_code=400,
            detail=f"Only a failed document can be retried (this one is '{doc.status}').",
        )

    temp_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}.{doc.file_type}")
    if not os.path.exists(temp_path):
        raise HTTPException(
            status_code=410,
            detail="The original uploaded file is no longer available. Please delete this document and upload it again.",
        )

    await db.execute(
        update(KBDocument)
        .where(KBDocument.id == doc_id)
        .values(status="processing", error_message=None)
    )
    await db.commit()

    logger.info(f"[kb:retry] re-queuing ingest: doc={doc_id} kb={kb_id} file={doc.filename}")
    background_tasks.add_task(
        _ingest_document,
        doc_id, kb_id, temp_path, doc.file_type, doc.filename,
        kb.chroma_collection, str(current_user.id),
    )

    return {"id": doc_id, "filename": doc.filename, "status": "processing"}


@router.delete("/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    kb_id:        str,
    doc_id:       str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc_result = await db.execute(
        select(KBDocument).where(
            KBDocument.id == doc_id,
            KBDocument.knowledge_base_id == kb_id,
        )
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # ROOT CAUSE FIX: delete_document now raises on a genuine ChromaDB
    # failure (only "already doesn't exist" is swallowed). Never delete the
    # document's DB row / return 204 success if its vectors could not
    # actually be removed from the collection — that would leave the chunks
    # permanently retrievable while the UI shows the document as gone.
    try:
        await kb_pipeline.delete_document(doc_id, kb.chroma_collection)
    except Exception as e:
        logger.error(f"[kb:delete] failed to delete doc={doc_id} from kb={kb_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=_user_facing_error_message(e) or "Failed to delete the document's indexed vectors")

    kb.chunk_count    = max(0, (kb.chunk_count    or 0) - (doc.chunk_count or 0))
    kb.document_count = max(0, (kb.document_count or 0) - 1)
    doc_file_type = doc.file_type
    await db.delete(doc)
    await db.commit()

    # A failed document keeps its temp upload on disk so it can be retried
    # (see _ingest_document's finally block); once the document row itself
    # is deleted that file is orphaned and should go with it.
    try:
        os.unlink(os.path.join(settings.UPLOAD_DIR, f"{doc_id}.{doc_file_type}"))
    except Exception:
        pass

    # Invalidate retrieval cache so stale results are not returned
    cache = CacheService()
    await cache.delete_pattern(f"retrieval:{kb_id}:*")
    logger.info(f"[kb:delete] document deleted: doc={doc_id} kb={kb_id}")
    await audit_service.record(
        db, Action.KNOWLEDGE_BASE_DOCUMENT_DELETE, actor=current_user, request=request,
        target_type="knowledge_base_document", target_id=doc_id, target_label=doc.filename,
        metadata={"knowledge_base_id": kb_id},
    )


@router.post("/{kb_id}/search")
async def search_knowledge_base(
    kb_id:        str,
    payload:      SearchRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        results = await retrieval_engine.retrieve(
            query=payload.query,
            collection_name=kb.chroma_collection,
            kb_id=kb_id,
            n_results=payload.n_results,
            score_threshold=payload.score_threshold,
            user_id=str(current_user.id),
            embedding_provider=kb.embedding_provider,   # None until first successful ingest
            embedding_model=kb.embedding_model,
        )
    except Exception as e:
        logger.error(f"[kb:search] retrieval failed for kb={kb_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=_user_facing_error_message(e) or "Knowledge base search failed")

    return {
        "query":     payload.query,
        "results":   results,
        "citations": retrieval_engine.format_citations(results),
        "count":     len(results),
    }
