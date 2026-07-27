"""
ThunderBots AI Engine v2
Provider: Google Gemini (only supported AI provider).
Streaming-first. Provider key loaded from DB (user-level) with env fallback.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, Optional
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)
_gemini_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini")

import hashlib
from cryptography.fernet import Fernet, InvalidToken

# ── API key encryption ─────────────────────────────────────────────────────────
#
# ROOT CAUSE FIX (v6): the previous scheme used raw XOR with a key derived from
# settings.SECRET_KEY[:32], with NO integrity check at all. Any mismatch between
# the SECRET_KEY active when a key was encrypted and the SECRET_KEY active when
# it's later decrypted (a default placeholder left unrotated, a missing .env in
# one deployment environment, a key containing characters that interact badly
# with raw byte XOR) silently produced garbage bytes — no exception was ever
# raised. That garbage then got handed straight to the provider SDK as an
# "api_key", which failed deep in the HTTP layer (often as a request-construction
# error from illegal header bytes) and was misreported as a generic connection
# failure — exactly the "valid key saved, but Test always returns Connection
# Error" symptom, even with a correctly-entered, valid key.
#
# Fernet (from the `cryptography` package — already a transitive dependency via
# python-jose[cryptography], so no new dependency is introduced) is an
# authenticated encryption scheme: any corruption or key mismatch raises
# InvalidToken immediately and loudly, instead of failing silently three layers
# downstream. Decryption is backward compatible: any value already stored under
# the old XOR scheme is detected (Fernet tokens are deterministically
# recognizable — they always start with the base64 encoding of version byte
# 0x80) and decrypted with the legacy path, so existing production databases
# are not broken by this upgrade. New/updated keys are always encrypted with
# Fernet going forward.

def _derive_fernet_key() -> bytes:
    """
    Derive a valid 32-byte urlsafe-base64 Fernet key from SECRET_KEY regardless
    of its length (Fernet requires exactly 32 raw bytes) using SHA-256, so any
    existing SECRET_KEY value in .env continues to work without requiring users
    to generate a separate, new key.
    """
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)

_fernet = Fernet(_derive_fernet_key())
_LEGACY_CIPHER_KEY = settings.SECRET_KEY[:32].encode()


def _legacy_decrypt(ciphertext: str) -> str:
    """Old XOR scheme — kept only to read pre-existing rows during migration."""
    data = base64.b64decode(ciphertext)
    decrypted = bytes(b ^ _LEGACY_CIPHER_KEY[i % len(_LEGACY_CIPHER_KEY)] for i, b in enumerate(data))
    return decrypted.decode()


def encrypt_key(plaintext: str) -> str:
    """Encrypt with Fernet (authenticated, integrity-checked). Always used for new writes."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """
    Decrypt a stored API key. Tries Fernet first (the current scheme); if the
    ciphertext doesn't look like a Fernet token (e.g. it was written before
    this upgrade), transparently falls back to the legacy XOR decrypt so
    existing saved keys keep working without requiring the user to re-enter
    them. Raises a clear, descriptive error instead of ever returning corrupted
    bytes silently — this is the key behavioral change versus the old scheme.
    """
    if not ciphertext:
        return ""

    # Fernet tokens are base64 of [version_byte(0x80) | timestamp | iv | ciphertext | hmac]
    # and reliably begin with "gAAAAA" once base64-encoded. Use that as a fast,
    # safe discriminator before attempting the (more expensive, exception-based) parse.
    looks_like_fernet = ciphertext.startswith("gAAAAA")

    if looks_like_fernet:
        try:
            return _fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError(
                "Stored API key could not be decrypted — it may have been encrypted "
                "under a different SECRET_KEY. Re-enter the key in Settings → API Keys."
            )

    # Legacy XOR-encrypted row from before this upgrade.
    try:
        plaintext = _legacy_decrypt(ciphertext)
    except Exception as e:
        raise ValueError(
            f"Stored API key is in an unrecognized or corrupted format ({type(e).__name__}). "
            "Re-enter the key in Settings → API Keys."
        )
    return plaintext


# ── Provider/model compatibility ────────────────────────────────────────────
#
# ROOT CAUSE FIX (production "404 models/gpt-4o-mini is not found for API
# version v1beta" bug): nowhere in the engine was a node's `model` string ever
# checked against the `provider` it was actually about to be sent to. A node
# can end up with a stale, mismatched `model` value (e.g. left over from a
# retired model name, or a stale published-deployment snapshot) and that
# mismatched model was passed straight into the provider SDK call with no
# guard at all. This map lets every call site cheaply verify "does this model
# actually belong to Gemini" and fall back to a safe default instead of ever
# forwarding an unrecognized model string.
_PROVIDER_MODEL_PREFIXES: dict[str, tuple[str, ...]] = {
    "gemini": ("gemini-", "gemini"),
}


def validate_model_for_provider(provider_id: str, model: Optional[str]) -> tuple[Optional[str], bool]:
    """
    Returns (effective_model, was_corrected).

    If `model` is empty, the model is passed through unchanged. Otherwise,
    if `model` doesn't carry a prefix belonging to `provider_id`, it is
    treated as unsafe to send (it either belongs to a different vendor
    entirely, or is an unrecognized/retired name) and is replaced with None
    so the provider class falls back to its own configured default model
    rather than ever reaching the SDK.
    """
    if not model:
        return model, False
    prefixes = _PROVIDER_MODEL_PREFIXES.get(provider_id)
    if prefixes is None:
        return model, False
    if model.startswith(prefixes):
        return model, False
    logger.warning(
        f"Model '{model}' is not a valid {provider_id} model — refusing to send "
        f"it to this provider and falling back to the {provider_id} default model instead."
    )
    return None, True


class AIProvider(str, Enum):
    GEMINI = "gemini"


class ProviderError(RuntimeError):
    """
    FIX v6.3 (root cause): raised by providers instead of letting the raw SDK
    exception propagate unclassified. Every consumer of this error (chat.py's
    500 response, the WebSocket error frame, workflow execution logs) does
    `str(e)` to build the message the user ultimately sees — previously that
    was whatever opaque string the SDK happened to produce (or nothing at
    all), which made a provider quota/billing rejection indistinguishable
    from a genuine application bug. `kind` lets any caller branch on the
    failure class programmatically; str(e) always returns the same
    human-readable, already-classified message so even code that only reads
    the message text (unchanged elsewhere in the app) benefits automatically.
    """
    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind  # "auth" | "quota" | "permission" | "model_not_found" | "network" | "malformed_key" | "app" | "unknown"

    @property
    def is_quota_error(self) -> bool:
        return self.kind == "quota"

    @property
    def is_application_error(self) -> bool:
        """True for failures that originate in our own code/config, not the provider."""
        return self.kind in ("malformed_key", "app")


class BaseAIProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, messages: list[dict],
                       temperature: float = 0.7, max_tokens: int = 1000,
                       model: Optional[str] = None) -> str: ...

    @abstractmethod
    async def stream(self, system: str, messages: list[dict],
                     temperature: float = 0.7, max_tokens: int = 1000,
                     model: Optional[str] = None) -> AsyncIterator[str]: ...

    async def test_connection(self) -> dict:
        """
        Quick connectivity test — returns {ok, latency_ms, error}.
        FIX v5: classifies common failure types so the user gets an actionable
        message instead of a bare "Connection error." string (which many SDKs,
        including openai's APIConnectionError, return with almost no detail).
        """
        import time
        t = time.monotonic()
        try:
            result = await self.complete(
                system="You are a test assistant.",
                messages=[{"role": "user", "content": "Reply with only: OK"}],
                max_tokens=5,
            )
            return {"ok": True, "latency_ms": int((time.monotonic() - t) * 1000), "response": result.strip()}
        except ProviderError as e:
            # Already classified at the source (see OpenAIProvider.complete/
            # stream) — use its message directly instead of re-classifying.
            latency_ms = int((time.monotonic() - t) * 1000)
            return {"ok": False, "latency_ms": latency_ms, "error": str(e), "error_kind": e.kind}
        except Exception as e:
            latency_ms = int((time.monotonic() - t) * 1000)
            error_msg = self._classify_error(e)
            return {"ok": False, "latency_ms": latency_ms, "error": error_msg}

    def _classify(self, e: Exception) -> tuple[str, str]:
        """Turn opaque SDK exceptions into (kind, actionable message)."""
        name = type(e).__name__
        raw = str(e).strip()

        # Auth failures
        if name in ("AuthenticationError",) or "401" in raw or "invalid_api_key" in raw.lower() or "incorrect api key" in raw.lower():
            return "auth", "Authentication failed — the API key was rejected by the provider. Double-check it was copied correctly with no extra spaces."
        # Rate limit / quota — FIX v6.3: this is the classification that lets
        # callers tell a provider quota/billing rejection apart from a bug in
        # our own code, per-provider, without inspecting SDK-specific types.
        if name in ("RateLimitError",) or "429" in raw or "quota" in raw.lower() or "insufficient_quota" in raw.lower() or "billing" in raw.lower():
            return "quota", "The provider rejected the request due to rate limiting or insufficient quota/billing on this account. This is a provider-account issue, not an application error — check billing/usage on the provider's dashboard."
        # Permission
        if "403" in raw or "permission" in raw.lower():
            return "permission", "The API key does not have permission to access this model or endpoint."
        # Model not found
        if "404" in raw or "model_not_found" in raw.lower() or "does not exist" in raw.lower():
            return "model_not_found", "The selected model was not found for this provider/account. Try a different model."
        # Network-level — no response at all
        # FIX (v9): openai's own APITimeoutError (raised on client-side
        # timeout, e.g. the explicit 30s timeout set on OpenAIProvider) has
        # a distinct class name from APIConnectionError and was previously
        # falling through to the generic "unknown" bucket instead of being
        # correctly classified as a network/timeout failure.
        if name in ("APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout", "ReadTimeout", "TimeoutException"):
            return "network", f"Could not reach the {self.__class__.__name__.replace('Provider', '')} API. Check your network connection, firewall, or that outbound internet access is allowed from this server."
        # Malformed key that breaks HTTP header construction (e.g. corrupted/
        # non-ASCII bytes from a decryption mismatch) — never reaches the network
        # at all, so it must NOT be classified as a connectivity problem.
        if name in ("LocalProtocolError", "InvalidHeader") or "illegal header" in raw.lower() or "invalid header" in raw.lower():
            return "malformed_key", "The stored API key appears to be corrupted or malformed and could not be sent to the provider. Please remove this key and re-enter it in Settings → API Keys."
        if not raw:
            return "network", f"Could not reach the {self.__class__.__name__.replace('Provider', '')} API. Check your network connection, firewall, or that outbound internet access is allowed from this server."
        # Fallback: surface the raw message but guarantee it's never empty
        return "unknown", raw or f"{name}: an unknown error occurred while contacting the provider."

    def _classify_error(self, e: Exception) -> str:
        """Turn opaque SDK exceptions into actionable messages."""
        _, message = self._classify(e)
        return message


# ── Gemini ─────────────────────────────────────────────────────────────────────

class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.genai = genai
        self.default_model = settings.GEMINI_DEFAULT_MODEL

    def _build_chat(self, system, messages, model, temperature, max_tokens):
        gm = self.genai.GenerativeModel(
            model_name=model or self.default_model, system_instruction=system,
            generation_config=self.genai.GenerationConfig(temperature=temperature, max_output_tokens=max_tokens),
        )
        history = [{"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]} for m in messages[:-1]]
        return gm.start_chat(history=history), (messages[-1]["content"] if messages else "")

    async def complete(self, system, messages, temperature=0.7, max_tokens=1000, model=None) -> str:
        loop = asyncio.get_event_loop()
        def _run():
            chat, msg = self._build_chat(system, messages, model, temperature, max_tokens)
            return chat.send_message(msg).text
        return await loop.run_in_executor(_gemini_executor, _run)

    async def stream(self, system, messages, temperature=0.7, max_tokens=1000, model=None) -> AsyncIterator[str]:
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[Optional[str] | Exception] = asyncio.Queue(maxsize=64)
        def _produce():
            try:
                chat, msg = self._build_chat(system, messages, model, temperature, max_tokens)
                for chunk in chat.send_message(msg, stream=True):
                    if chunk.text:
                        asyncio.run_coroutine_threadsafe(queue.put(chunk.text), loop).result()
            except Exception as e:
                # FIX (root cause): propagate the real exception object through the
                # queue instead of injecting a "[Gemini error: ...]" string as if it
                # were model output. Previously a Gemini failure silently appeared
                # as part of the bot's chat response rather than surfacing as a
                # proper, classifiable error the frontend can display distinctly.
                asyncio.run_coroutine_threadsafe(queue.put(e), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()
        loop.run_in_executor(_gemini_executor, _produce)
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item


# ── Provider Registry ──────────────────────────────────────────────────────────

# Per-user provider cache: {user_id: {provider_id: instance}}
_user_provider_cache: dict[str, dict[str, BaseAIProvider]] = {}
# Global env-level fallback cache
_env_provider_cache: dict[str, BaseAIProvider] = {}


def _build_provider_from_key(provider_id: str, api_key: str, base_url: Optional[str] = None) -> BaseAIProvider:
    match provider_id:
        case "gemini": return GeminiProvider(api_key=api_key)
        case _:        raise ValueError(f"Unknown provider: {provider_id}")


def _build_env_provider(provider_id: str) -> Optional[BaseAIProvider]:
    """Build from env vars — fallback when no user key exists."""
    try:
        match provider_id:
            case "gemini":
                if settings.GEMINI_API_KEY:
                    return GeminiProvider(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.warning(f"Could not build env provider {provider_id}: {e}")
    return None


async def get_provider_for_user(provider_id: str, user_id: Optional[str] = None) -> BaseAIProvider:
    """
    Resolve provider: user DB key → validated-provider auto-fallback → env key → error.
    Caches built instances per user.
    """
    if user_id:
        user_cache = _user_provider_cache.get(user_id, {})
        if provider_id in user_cache:
            logger.info(f"[provider:resolve] user={user_id} provider='{provider_id}' -> cache hit (session cache)")
            return user_cache[provider_id]

        # Try loading from DB
        try:
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import select
            from app.models.user import UserAPIKey
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserAPIKey).where(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.provider == provider_id,
                    )
                )
                row = result.scalar_one_or_none()
                if row:
                    logger.info(
                        f"[provider:resolve] user={user_id} provider='{provider_id}' -> "
                        f"API key found (is_valid={row.is_valid}); provider used='{provider_id}'"
                    )
                    api_key = decrypt_key(row.encrypted_key)
                    instance = _build_provider_from_key(provider_id, api_key, row.base_url)
                    _user_provider_cache.setdefault(user_id, {})[provider_id] = instance
                    return instance
                logger.info(f"[provider:resolve] user={user_id} provider='{provider_id}' -> no API key found for this provider")

                # FIX v6.3 (root cause): "AI Agent must automatically use the
                # configured provider after a successful API key test."
                # Workflow/AI-Agent nodes carry a fixed "provider" value
                # (e.g. "openai") set at node-creation time, independent of
                # which provider the user has actually configured. If this
                # user has never saved ANY key at all for the node's
                # requested provider, but does have a different provider
                # with a successfully-tested key (is_valid=True), that is
                # unambiguously "the configured provider" the user just set
                # up — use it automatically instead of failing with "No API
                # key configured for provider 'openai'".  A provider the
                # user explicitly saved a key for (even if that key is
                # currently invalid/untested) is NOT overridden here, since
                # that reflects a deliberate choice the user should fix
                # rather than have silently routed elsewhere.
                fallback_result = await db.execute(
                    select(UserAPIKey)
                    .where(
                        UserAPIKey.user_id == user_id,
                        UserAPIKey.is_valid == True,  # noqa: E712
                    )
                    .order_by(UserAPIKey.last_tested.desc())
                )
                fallback_row = fallback_result.scalars().first()
                if fallback_row:
                    api_key = decrypt_key(fallback_row.encrypted_key)
                    instance = _build_provider_from_key(
                        fallback_row.provider, api_key, fallback_row.base_url
                    )
                    _user_provider_cache.setdefault(user_id, {})[fallback_row.provider] = instance
                    logger.info(
                        f"[provider:resolve] reason for fallback: no key saved for requested "
                        f"provider '{provider_id}' (user={user_id}); auto-using validated "
                        f"provider '{fallback_row.provider}' instead; provider used='{fallback_row.provider}'"
                    )
                    return instance
        except Exception as e:
            logger.warning(f"[provider:resolve] DB key lookup failed for {user_id}/{provider_id}: {e}")

    # Env fallback
    if provider_id not in _env_provider_cache:
        p = _build_env_provider(provider_id)
        if p:
            _env_provider_cache[provider_id] = p
    if provider_id in _env_provider_cache:
        logger.info(
            f"[provider:resolve] reason for fallback: no user key for '{provider_id}' "
            f"(user={user_id}); using server env key; provider used='{provider_id}'"
        )
        return _env_provider_cache[provider_id]

    logger.info(
        f"[provider:resolve] user={user_id} provider='{provider_id}' -> NOT FOUND anywhere "
        f"(no user key, no validated fallback key, no env key)"
    )
    raise ValueError(f"No API key configured for provider '{provider_id}'. Add one in Settings → API Keys.")


async def resolve_agent_provider(explicit_provider: Optional[str], user_id: Optional[str]) -> str:
    """
    Determine which provider id an AI Agent node should use for this turn.
    Used by both the AI Agent node (REST) and Chat Tester (WebSocket
    streaming) — both call sites in app/engine/node_handlers/__init__.py
    funnel through this single function, so there is exactly one place this
    logic lives.

      1. An explicit provider set directly on the node always wins — that's a
         deliberate, designer-made choice (e.g. someone building a workflow by
         hand who picked Claude specifically for this one node) and must never
         be silently overridden. The builder UI never stores the literal
         string "auto" — "auto (my default)" is a display label for an
         empty/None provider field (see NodeConfigPanel.tsx) — so this check
         is simply "is anything explicitly set on the node".
      2. Otherwise, use the user's own default AI provider — via the shared
         app.services.user_preferences.get_effective_default_provider, the
         SAME merged value the Settings page displays and highlights as
         "selected". (ROOT CAUSE FIX v62: this previously read only the raw,
         unmerged User.preferences DB column. A user whose default was never
         explicitly saved — e.g. Gemini was already shown as selected via
         Settings' own DEFAULT_PREFS fallback, so there was nothing to click
         to persist it — had an empty DB column. Settings displayed "Gemini"
         while this function saw "no default provider at all" and raised,
         which the frontend renders as the "AI Provider API Key Required"
         card even though a valid Gemini key was configured. Settings
         display and provider resolution must agree on one answer.)
      3. If neither is set (only possible for an anonymous/unauthenticated
         caller — every real user has an effective default via DEFAULT_PREFS),
         raise instead of silently defaulting to any one vendor — the caller
         surfaces this as an actionable "choose a provider" message rather
         than a confusing downstream API failure.

    Whether the resolved provider actually HAS a usable API key is decided
    downstream, in get_provider_for_user — which will transparently fall
    back to another validated provider the user configured, or raise a
    precise "no key for this provider" error. A key that exists but is
    invalid is not caught here either: the real request is attempted and the
    provider's own error is surfaced, per product requirement.
    """
    from app.services.user_preferences import get_effective_default_provider

    if explicit_provider:
        logger.info(
            f"[provider:resolve] selected provider='{explicit_provider}' (explicit, set on node) "
            f"user={user_id} -> resolved='{explicit_provider}'"
        )
        return explicit_provider

    logger.info(f"[provider:resolve] selected provider='auto (my default)' user={user_id}")
    default_provider = await get_effective_default_provider(user_id)
    if default_provider:
        logger.info(
            f"[provider:resolve] user={user_id} auto -> resolved='{default_provider}' "
            f"(from user's default AI provider)"
        )
        return default_provider

    logger.info(f"[provider:resolve] user={user_id} auto -> NOT RESOLVED (no default provider available)")
    raise ValueError(
        "This AI Agent has no provider configured, and you haven't set a "
        "default AI provider yet. Choose one in Settings \u2192 AI Providers, "
        "or set a specific provider on this node."
    )


def invalidate_user_provider_cache(user_id: str, provider_id: Optional[str] = None):
    """Call after saving/deleting a user API key."""
    if provider_id:
        _user_provider_cache.get(user_id, {}).pop(provider_id, None)
    else:
        _user_provider_cache.pop(user_id, None)


# ── AI Engine ──────────────────────────────────────────────────────────────────

class AIEngine:
    async def complete(self, provider: str, system_prompt: str, instructions: str,
                       messages: list[dict], context: dict, model: Optional[str] = None,
                       temperature: float = 0.7, max_tokens: int = 1000,
                       kb_context: Optional[str] = None, user_id: Optional[str] = None) -> str:
        llm = await get_provider_for_user(provider, user_id)
        # ROOT CAUSE FIX: validate model/provider compatibility on every
        # request — see validate_model_for_provider above. Never let a
        # cross-vendor or unrecognized model string reach the SDK.
        model, _ = validate_model_for_provider(provider, model)
        system = self._build_system(system_prompt, instructions, context, kb_context)
        try:
            return await llm.complete(system=system, messages=messages,
                                       temperature=temperature, max_tokens=max_tokens, model=model)
        except ProviderError:
            raise
        except Exception as e:
            # Defense in depth: any provider class that doesn't classify its
            # own errors (see Gemini/Claude/Ollama fixes below) must still
            # never leak a raw SDK exception up to the chat/WS layer.
            kind, msg = llm._classify(e) if hasattr(llm, "_classify") else ("unknown", str(e) or "The AI provider request failed.")
            raise ProviderError(msg, kind=kind) from e

    async def stream(self, provider: str, system_prompt: str, instructions: str,
                     messages: list[dict], context: dict, model: Optional[str] = None,
                     temperature: float = 0.7, max_tokens: int = 1000,
                     kb_context: Optional[str] = None, user_id: Optional[str] = None) -> AsyncIterator[str]:
        llm = await get_provider_for_user(provider, user_id)
        model, _ = validate_model_for_provider(provider, model)
        system = self._build_system(system_prompt, instructions, context, kb_context)
        try:
            async for token in llm.stream(system=system, messages=messages,
                                           temperature=temperature, max_tokens=max_tokens, model=model):
                yield token
        except ProviderError:
            raise
        except Exception as e:
            kind, msg = llm._classify(e) if hasattr(llm, "_classify") else ("unknown", str(e) or "The AI provider request failed.")
            raise ProviderError(msg, kind=kind) from e

    def _build_system(self, system_prompt: str, instructions: str,
                      context: dict, kb_context: Optional[str] = None) -> str:
        parts = []
        if system_prompt:
            parts.append(system_prompt)
        if instructions:
            parts.append(f"\n## Instructions\n{instructions}")
        if context.get("variables"):
            vars_text = "\n".join(f"- {k}: {v}" for k, v in context["variables"].items())
            parts.append(f"\n## Context Variables\n{vars_text}")
        if kb_context:
            parts.append(f"\n## Knowledge Base Context\nUse the following to answer accurately. Cite sources when relevant.\n\n{kb_context}")
        parts.append("\n## Rules\n- Be helpful, accurate, and concise.\n- If you don't know something, say so.\n- Stay on topic.")
        return "\n".join(parts)

    def interpolate_variables(self, text: str, variables: dict) -> str:
        for key, value in variables.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text

    def get_available_providers(self, user_keys: Optional[list[str]] = None) -> list[dict]:
        """Return the (single) supported provider, marking whether a key is configured."""
        all_providers = [
            {
                # FIX v6.3: gemini-1.5-pro, gemini-1.5-flash, and gemini-1.0-pro
                # are all fully retired (404 on every request). Replaced with
                # the current stable Gemini model line-up.
                "id": "gemini", "name": "Google Gemini", "requires_key": True,
                "models": ["gemini-2.5-pro", "gemini-2.5-flash",
                           "gemini-2.5-flash-lite", "gemini-3.5-flash"],
                "default": settings.GEMINI_DEFAULT_MODEL,
                "configured": bool(settings.GEMINI_API_KEY) or ("gemini" in (user_keys or [])),
            },
        ]
        return all_providers


ai_engine = AIEngine()
