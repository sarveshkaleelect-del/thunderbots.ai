"""
ThunderBots Owner Assistant API — Part 2 (Campaign QR Marketing System)
NEW.

Authenticated, owner-scoped management endpoints for linking a Telegram
chat or WhatsApp number as an Owner Assistant control channel. The actual
linking handshake (owner sends "/assistant <code>" to their own bot) is
handled inside the existing Telegram/WhatsApp webhooks
(api/v1/telegram.py, api/v1/whatsapp.py) — this module only issues and
tracks the short-lived link codes and lets the owner view/revoke links.

Does not touch the Campaign Engine, AI Agent, Workflow Runtime, Knowledge
Base, Memory, or Live Agent — see app/services/owner_assistant_service.py
for where the actual command handling reuses those.
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.models.user import User
from app.models.owner_assistant import OwnerAssistantLink

router = APIRouter()
logger = logging.getLogger(__name__)

LINK_CODE_TTL_SECONDS = 600  # 10 minutes


def _link_code_key(code: str) -> str:
    return f"owner_assistant:link_code:{code}"


def _generate_link_code() -> str:
    # 8-character, easy to type on a phone keyboard, still effectively
    # unguessable within the 10-minute TTL.
    return secrets.token_hex(4).upper()


def _serialize_link(link: OwnerAssistantLink) -> dict:
    return {
        "id": link.id,
        "channel": link.channel,
        "workflow_id": link.workflow_id,
        "is_active": link.is_active,
        "linked_at": link.linked_at.isoformat() if link.linked_at else None,
        "last_used_at": link.last_used_at.isoformat() if link.last_used_at else None,
    }


@router.post("/link-code")
async def create_link_code(
    current_user: User = Depends(get_current_user),
):
    """Issues a one-time code the owner types into their own Telegram or
    WhatsApp bot as "/assistant <code>" to link that chat for conversational
    campaign control. Valid for 10 minutes."""
    cache = CacheService()
    code = _generate_link_code()
    stored = await cache.set(_link_code_key(code), {"user_id": current_user.id}, ttl=LINK_CODE_TTL_SECONDS)
    if not stored:
        raise HTTPException(status_code=503, detail="Could not generate a link code right now — please try again.")
    return {
        "code": code,
        "expires_in_seconds": LINK_CODE_TTL_SECONDS,
        "instructions": (
            f"Open Telegram or WhatsApp chat with your bot and send: /assistant {code}"
        ),
    }


@router.get("/links")
async def list_links(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(OwnerAssistantLink).where(
            OwnerAssistantLink.user_id == current_user.id, OwnerAssistantLink.is_active.is_(True)
        ).order_by(OwnerAssistantLink.linked_at.desc())
    )
    return [_serialize_link(link) for link in result.scalars().all()]


@router.delete("/links/{link_id}", status_code=204)
async def unlink(
    link_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(OwnerAssistantLink).where(
            OwnerAssistantLink.id == link_id, OwnerAssistantLink.user_id == current_user.id
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    link.is_active = False
    await db.commit()
    return None
