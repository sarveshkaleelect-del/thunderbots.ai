"""
ThunderBots Voice Responses API v1

Independent, optional module. Reads the FINAL bot response text after the
workflow has already produced it — never touches workflow execution, the
AI Agent, ThunderGuide, the Knowledge Base, or any existing route.

Two entry points:
  - POST /synthesize              (authenticated) — Test Chat "Test Voice"
    and live playback while testing a workflow in the builder.
  - POST /live/{slug}/synthesize  (public, no auth) — the deployed chatbot's
    Speaker toggle. API keys never reach the browser in either path: the
    frontend only ever receives synthesized audio bytes back.

Every failure here degrades gracefully (an HTTP error the caller can catch
and ignore) — it never raises anything that could crash the chatbot, and it
never blocks or slows down chat/workflow responses since it is only ever
called *after* the text has already been rendered.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.redis import CacheService
from app.models.user import User, UserAPIKey
from app.models.workflow import Deployment, Workflow
from app.services import tts_engine
from app.services.ai_engine import decrypt_key
from app.services.tts_engine import TTSError

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_TEST_TEXT = 500          # Test Voice samples are short by design
LIVE_RATE_LIMIT_PER_MIN = 30  # per deployed slug — degrades to "no limit" if Redis is down


class SynthesizeRequest(BaseModel):
    provider: str
    text: str = Field(..., min_length=1, max_length=tts_engine.MAX_TEXT_LENGTH)
    voice: Optional[str] = None
    # Playback styling only (rate/pitch/tone) — never changes bot text.
    # Unknown/omitted values safely fall back to the default preset.
    personality: Optional[str] = None


async def _get_user_key(db: AsyncSession, user_id: str, credential_provider: str) -> Optional[UserAPIKey]:
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id,
            UserAPIKey.provider == credential_provider,
        )
    )
    return result.scalar_one_or_none()


# ── Builder: Test Chat panel ─────────────────────────────────────────────────

@router.get("/providers")
async def get_voice_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Browser is always available (no key, no network call). Premium
    providers report configured=True once a matching key exists."""
    result = await db.execute(
        select(UserAPIKey.provider).where(UserAPIKey.user_id == current_user.id)
    )
    user_provider_ids = {r[0] for r in result.all()}

    providers = [
        {"id": "browser", "name": "Browser (Free)", "requires_key": False,
         "requires_region": False, "configured": True, "voices": []},
    ]
    for entry in tts_engine.list_provider_catalog():
        providers.append({**entry, "configured": entry["credential_provider"] in user_provider_ids})
    return providers


@router.post("/synthesize")
async def synthesize_test_voice(
    payload: SynthesizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Used by the builder's Test Chat panel: the 'Test Voice' button and
    (when Voice is enabled there) speaking the bot's replies while testing."""
    if payload.provider == "browser":
        raise HTTPException(
            status_code=400,
            detail="Browser voice is generated client-side and never calls this endpoint",
        )

    meta = tts_engine.PROVIDER_CATALOG.get(payload.provider)
    if not meta:
        raise HTTPException(status_code=400, detail=f"Unknown voice provider: {payload.provider}")

    key_row = await _get_user_key(db, current_user.id, meta["credential_provider"])
    if not key_row or not key_row.encrypted_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key saved for {meta['name']}. Add one in Settings → API Keys.",
        )

    try:
        api_key = decrypt_key(key_row.encrypted_key)
        audio, content_type = await tts_engine.synthesize(
            payload.provider, api_key, payload.text[:MAX_TEST_TEXT], payload.voice,
            base_url=key_row.base_url, personality=payload.personality,
        )
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return Response(content=audio, media_type=content_type)


# ── Deployed chatbot: Speaker toggle ─────────────────────────────────────────

async def _voice_rate_limited(cache: CacheService, slug: str) -> bool:
    key = f"voice_rl:{slug}"
    count = await cache.get(key) or 0
    if count >= LIVE_RATE_LIMIT_PER_MIN:
        return True
    await cache.set(key, count + 1, ttl=60)
    return False


@router.post("/live/{slug}/synthesize")
async def synthesize_live_voice(
    slug: str,
    payload: SynthesizeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Public — no auth, called by the deployed chatbot page. The provider,
    voice, and API key are all resolved server-side from the bot's deployed
    Voice Responses settings — end users never choose or see any of that,
    only the Speaker ON/OFF icon that decides whether this is called at all."""
    cache = CacheService()
    if await _voice_rate_limited(cache, slug):
        raise HTTPException(status_code=429, detail="Voice request limit reached, please try again shortly")

    result = await db.execute(
        select(Deployment).where(Deployment.slug == slug, Deployment.is_active == True)  # noqa: E712
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Bot not found or not published")

    voice_cfg = (dep.chat_settings or {}).get("voice") or {}
    if not voice_cfg.get("enabled") or voice_cfg.get("response_mode", "text_only") == "text_only":
        raise HTTPException(status_code=403, detail="Voice Responses are not enabled for this bot")

    configured_provider = voice_cfg.get("provider", "browser")
    if payload.provider == "browser" or configured_provider == "browser":
        raise HTTPException(
            status_code=400,
            detail="Browser voice is generated client-side and never calls this endpoint",
        )
    if payload.provider != configured_provider:
        raise HTTPException(status_code=400, detail="Voice provider mismatch")

    meta = tts_engine.PROVIDER_CATALOG.get(configured_provider)
    if not meta:
        raise HTTPException(status_code=400, detail="Unsupported voice provider")

    wf_result = await db.execute(select(Workflow).where(Workflow.id == dep.workflow_id))
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Bot not found")

    key_row = await _get_user_key(db, workflow.user_id, meta["credential_provider"])
    if not key_row or not key_row.encrypted_key:
        raise HTTPException(status_code=503, detail="Voice is not configured for this bot")

    try:
        api_key = decrypt_key(key_row.encrypted_key)
        voice_id = voice_cfg.get("voice_id") or payload.voice
        personality = voice_cfg.get("personality") or payload.personality
        audio, content_type = await tts_engine.synthesize(
            configured_provider, api_key, payload.text, voice_id, base_url=key_row.base_url,
            personality=personality,
        )
    except TTSError as e:
        logger.info(f"Live voice synthesis failed for slug={slug}: {e}")
        raise HTTPException(status_code=502, detail="Voice generation failed")

    return Response(content=audio, media_type=content_type)
