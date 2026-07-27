"""
ThunderBots Settings API v4
Google Gemini is the only supported AI (LLM) provider.
FIX: test_api_key builds provider from the SAVED key, not a newly created instance,
     to avoid double-decryption bugs.
FIX: get_preferences returns default values when preferences column is empty dict.
FIX: provider list endpoint passes user's saved provider IDs for 'configured' flag.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User, UserAPIKey
from app.services.ai_engine import (
    ai_engine,
    encrypt_key,
    decrypt_key,
    invalidate_user_provider_cache,
    _build_provider_from_key,
)
from app.services.user_preferences import DEFAULT_PREFS
from app.services import tts_engine
from app.services.tts_engine import TTSError
from app.services import audit_service
from app.services.audit_service import Action

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"gemini"}

# Voice Responses (Deploy Settings / Test Chat) — credential-only providers.
# Gemini TTS reuses the LLM key above (VALID_PROVIDERS), these three
# are TTS-only vendors and need their own saved key.
VALID_VOICE_PROVIDERS = {"elevenlabs", "azure_speech", "google_tts"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    provider: str
    api_key:  str
    label:    str        = ""
    base_url: Optional[str] = None


class PreferencesUpdate(BaseModel):
    default_provider: Optional[str] = None
    default_model:    Optional[str] = None
    theme:            Optional[str] = None
    language:         Optional[str] = None


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAPIKey).where(UserAPIKey.user_id == current_user.id)
        .order_by(UserAPIKey.created_at)
    )
    keys = result.scalars().all()
    return [
        {
            "id":          k.id,
            "provider":    k.provider,
            "label":       k.label or "",
            "base_url":    k.base_url,
            "is_valid":    k.is_valid,
            "has_key":     bool(k.encrypted_key),
            "key_preview": _preview(decrypt_key(k.encrypted_key)) if k.encrypted_key else None,
            "created_at":  k.created_at.isoformat()   if k.created_at   else None,
            "last_tested": k.last_tested.isoformat()   if k.last_tested  else None,
        }
        for k in keys
    ]


@router.post("/api-keys", status_code=201)
async def add_api_key(
    payload:      APIKeyCreate,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    if payload.provider not in VALID_PROVIDERS and payload.provider not in VALID_VOICE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {payload.provider}")

    if not payload.api_key.strip():
        raise HTTPException(
            status_code=400,
            detail=f"api_key is required for provider '{payload.provider}'",
        )
    effective_key      = payload.api_key.strip()
    # Azure Speech has no "base URL" — this field carries the Azure
    # region (e.g. "eastus"), which the TTS engine needs at call time.
    effective_base_url = payload.base_url

    # Upsert: one key per provider per user
    result   = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id  == current_user.id,
            UserAPIKey.provider == payload.provider,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if effective_key:
            existing.encrypted_key = encrypt_key(effective_key)
        existing.label    = payload.label or existing.label
        existing.base_url = effective_base_url or existing.base_url
        existing.is_valid = False   # reset until re-tested
        key_id            = existing.id
    else:
        new_key = UserAPIKey(
            user_id=current_user.id,
            provider=payload.provider,
            encrypted_key=encrypt_key(effective_key) if effective_key else "",
            label=payload.label or "",
            base_url=effective_base_url,
        )
        db.add(new_key)
        await db.flush()
        key_id = new_key.id

    await db.commit()
    invalidate_user_provider_cache(current_user.id, payload.provider)
    await audit_service.record(
        db, Action.API_KEY_CREATE, actor=current_user, request=request,
        target_type="api_key", target_id=str(key_id), target_label=payload.provider,
        metadata={"provider": payload.provider, "updated_existing": bool(existing)},
    )

    return {"id": key_id, "provider": payload.provider, "message": "API key saved"}


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id:       str,
    request:      Request,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.id      == key_id,
            UserAPIKey.user_id == current_user.id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    provider = key.provider
    await db.delete(key)
    await db.commit()
    invalidate_user_provider_cache(current_user.id, provider)
    await audit_service.record(
        db, Action.API_KEY_DELETE, actor=current_user, request=request,
        target_type="api_key", target_id=key_id, target_label=provider,
    )


@router.post("/api-keys/{key_id}/test")
async def test_api_key(
    key_id:       str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.id      == key_id,
            UserAPIKey.user_id == current_user.id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    try:
        raw_key = decrypt_key(key.encrypted_key) if key.encrypted_key else ""
        if key.provider in VALID_VOICE_PROVIDERS:
            # Voice-only providers (ElevenLabs, Azure Speech, Google Cloud TTS)
            # have no ai_engine chat provider — test them by actually
            # synthesizing a couple words and checking it comes back as audio.
            test_result = await _test_voice_provider(key.provider, raw_key, key.base_url)
        else:
            # FIX: Build a fresh provider from the stored key (bypasses provider cache)
            # so we always test the actual saved value, not any cached instance.
            provider_instance = _build_provider_from_key(key.provider, raw_key, key.base_url)
            test_result = await provider_instance.test_connection()
    except Exception as e:
        # FIX v5: guarantee a non-empty, descriptive error even if provider
        # construction itself fails (e.g. malformed base_url, missing SDK dep)
        error_msg = str(e).strip() or f"{type(e).__name__}: failed to initialize the {key.provider} client"
        logger.error(f"API key test setup failed for provider={key.provider}: {error_msg}", exc_info=True)
        test_result = {"ok": False, "error": error_msg, "latency_ms": 0}

    key.is_valid    = test_result.get("ok", False)
    key.last_tested = datetime.now(timezone.utc)
    await db.commit()

    # Refresh provider cache so the tested key is used going forward
    if test_result.get("ok"):
        invalidate_user_provider_cache(current_user.id, key.provider)

    return test_result


# ── Providers ─────────────────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """Return all providers with configured=True for any provider the user has saved a key for."""
    result = await db.execute(
        select(UserAPIKey.provider).where(UserAPIKey.user_id == current_user.id)
    )
    user_provider_ids = [r[0] for r in result.all()]
    return ai_engine.get_available_providers(user_keys=user_provider_ids)


# ── Preferences ────────────────────────────────────────────────────────────────
# DEFAULT_PREFS now lives in app.services.user_preferences — the single
# source of truth shared with AI provider resolution (see that module's
# docstring for why display and resolution must never disagree again).


@router.get("/preferences")
async def get_preferences(current_user: User = Depends(get_current_user)):
    # FIX: merge with defaults so missing keys always have a safe fallback
    prefs = {**DEFAULT_PREFS, **(current_user.preferences or {})}
    return prefs


@router.patch("/preferences")
async def update_preferences(
    payload:      PreferencesUpdate,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    prefs = {**DEFAULT_PREFS, **(current_user.preferences or {})}

    if payload.default_provider is not None:
        if payload.default_provider not in VALID_PROVIDERS:
            raise HTTPException(status_code=400, detail="Invalid provider")
        prefs["default_provider"] = payload.default_provider
    if payload.default_model is not None:
        prefs["default_model"] = payload.default_model
    if payload.theme is not None:
        if payload.theme not in ("dark", "light", "midnight", "thunder"):
            raise HTTPException(status_code=400, detail="theme must be one of: dark, light, midnight, thunder")
        prefs["theme"] = payload.theme
    if payload.language is not None:
        prefs["language"] = payload.language

    current_user.preferences = prefs
    await db.commit()
    return prefs


# ── Voice provider test (ElevenLabs / Azure Speech / Google Cloud TTS) ──────────

async def _test_voice_provider(provider: str, api_key: str, base_url: Optional[str]) -> dict:
    import time
    started = time.monotonic()
    try:
        await tts_engine.synthesize(provider, api_key, "Voice test.", base_url=base_url)
        return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
    except TTSError as e:
        return {"ok": False, "error": str(e), "latency_ms": int((time.monotonic() - started) * 1000)}


# ── Helper ─────────────────────────────────────────────────────────────────────

def _preview(key: str) -> str:
    if len(key) <= 8:
        return "••••••••"
    return key[:4] + "•" * min(len(key) - 8, 20) + key[-4:]
