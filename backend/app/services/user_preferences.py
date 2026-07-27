"""
ThunderBots — shared user-preferences resolution.

ROOT CAUSE (v62): "AI Provider API Key Required" kept showing in Chat Tester
even with a valid Gemini key saved, Gemini "selected" as the default
provider, and the AI Agent node set to "auto (my default)".

Two places computed a user's default AI provider and they disagreed:

  1. GET /preferences (app/api/v1/settings.py) merged the raw DB column with
     DEFAULT_PREFS (default_provider="gemini") before returning it, purely so
     the Settings page always has something sensible to display/highlight as
     "selected" — including for a user who has never explicitly chosen one.
  2. app.services.ai_engine._user_default_provider (and an independent copy
     in app.knowledge.pipeline) read ONLY the raw, unmerged DB column, and
     treated an empty column as "genuinely unconfigured".

A user who opens Settings, sees Gemini already highlighted as their default
(because of #1), adds a Gemini key, and never clicks the Gemini card again
(there's nothing to change) never triggers a PATCH — so the DB column stays
empty. Settings displays "Gemini", but provider resolution (#2) saw "no
default provider at all" and raised, which the frontend renders as the
"AI Provider API Key Required" card even though a valid key exists.

Fix: one shared implementation of "what is this user's default provider,
really" — the exact same merged value Settings shows them — used by both the
Settings API (display) and provider resolution (AI Agent / Chat Tester /
Knowledge Base embeddings). There is now only one place this is computed.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Single source of truth. app/api/v1/settings.py imports this rather than
# keeping its own copy, so display and resolution can never drift apart again.
DEFAULT_PREFS = {
    "default_provider": "gemini",
    "default_model":    "gemini-2.5-flash",
    "theme":            "dark",
    "language":         "en",
}


async def get_raw_preferences(user_id: Optional[str]) -> Optional[dict]:
    """The User.preferences JSON column exactly as stored — no defaults
    merged in. None if the user has never saved anything (or the row can't
    be read)."""
    if not user_id:
        return None
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User.preferences).where(User.id == user_id))
            row = result.first()
            if row and row[0]:
                return row[0]
    except Exception as e:
        logger.warning(f"[prefs] could not read preferences for user={user_id}: {e}")
    return None


async def get_effective_preferences(user_id: Optional[str]) -> dict:
    """The same merged view Settings -> GET /preferences shows the user."""
    raw = await get_raw_preferences(user_id) or {}
    return {**DEFAULT_PREFS, **raw}


async def get_effective_default_provider(user_id: Optional[str]) -> Optional[str]:
    """The user's default AI provider exactly as Settings displays it to
    them (raw saved choice if they made one, otherwise the same DEFAULT_PREFS
    fallback the Settings UI already shows as "selected"). None only when
    there is no authenticated user at all (anonymous/public callers)."""
    if not user_id:
        logger.info("[prefs] no user_id — cannot resolve a default provider (anonymous caller)")
        return None
    prefs = await get_effective_preferences(user_id)
    provider = prefs.get("default_provider")
    logger.info(f"[prefs] effective default_provider='{provider}' for user={user_id}")
    return provider
