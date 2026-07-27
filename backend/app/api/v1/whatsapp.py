"""
ThunderBots WhatsApp API
NEW (WhatsApp Channel).

Two groups of routes:

1. Management (authenticated, owner-scoped) — connection wizard, settings UI,
   enable/disable/reconnect/disconnect, test connection, webhook info, stats.

2. Webhook (public, no auth — this IS Meta's callback endpoint) — GET for
   the Cloud API subscription handshake, POST for inbound message/status
   events. Every inbound message is executed through the EXISTING Workflow
   Runtime (app.engine.runner.WorkflowRunner) using the exact same
   run()/ExecutionContext/Redis-session pattern already used by the REST
   chat endpoint (api/v1/chat.py) and the WebSocket endpoint
   (api/ws/chat_ws.py) — neither of which is modified by this module, only
   imported from (get_workflow_data / get_deployed_workflow_data). Every
   turn is recorded via the existing app.services.analytics_service with
   source="whatsapp", which is the ONLY thing required for WhatsApp
   conversations to automatically appear on the Analytics Dashboard —
   analytics_service, models/analytics.py, and api/v1/analytics.py are
   untouched.
"""
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db, AsyncSessionLocal
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.engine.runner import WorkflowRunner
from app.engine.context import ExecutionContext
from app.models.user import User
from app.models.workflow import Workflow
from app.models.whatsapp import WhatsAppChannel, WhatsAppContact, WhatsAppMediaAsset
from app.config import settings
from app.services import analytics_service
from app.services import whatsapp_service as wa
from app.services import campaign_dispatch_service as campaign_dispatch
from app.services import live_agent_service
from app.services import owner_assistant_service as owner_assistant
from app.api.ws.chat_ws import get_workflow_data, get_deployed_workflow_data

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionPayload(BaseModel):
    phone_number_id: str
    business_account_id: str
    access_token: str
    verify_token: str
    app_secret: Optional[str] = None


class TestPayload(BaseModel):
    phone_number_id: Optional[str] = None
    access_token: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_owned_workflow(workflow_id: str, db: AsyncSession, current_user: User) -> Workflow:
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if str(workflow.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this workflow")
    return workflow


async def _get_channel(workflow_id: str, db: AsyncSession) -> Optional[WhatsAppChannel]:
    result = await db.execute(select(WhatsAppChannel).where(WhatsAppChannel.workflow_id == workflow_id))
    return result.scalar_one_or_none()


def _webhook_url(channel_id: str) -> str:
    return f"{settings.APP_API_URL}/api/v1/whatsapp/webhook/{channel_id}"


def _preview(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "••••••••"
    return secret[:4] + "•" * min(len(secret) - 8, 24) + secret[-4:]


def _serialize_channel(channel: Optional[WhatsAppChannel]) -> dict:
    if not channel:
        return {"connected": False}
    return {
        "connected": True,
        "id": channel.id,
        "workflow_id": channel.workflow_id,
        "phone_number_id": channel.phone_number_id,
        "business_account_id": channel.business_account_id,
        "access_token_preview": _preview(wa.decrypt_credential(channel.encrypted_access_token)),
        "has_app_secret": bool(channel.encrypted_app_secret),
        "display_phone_number": channel.display_phone_number,
        "verified_name": channel.verified_name,
        "quality_rating": channel.quality_rating,
        "status": channel.status,
        "is_enabled": channel.is_enabled,
        "health_status": channel.health_status,
        "last_error": channel.last_error,
        "last_sync_at": channel.last_sync_at.isoformat() if channel.last_sync_at else None,
        "last_webhook_at": channel.last_webhook_at.isoformat() if channel.last_webhook_at else None,
        "last_tested_at": channel.last_tested_at.isoformat() if channel.last_tested_at else None,
        "messages_received_count": channel.messages_received_count,
        "messages_sent_count": channel.messages_sent_count,
        "messages_failed_count": channel.messages_failed_count,
        "webhook_url": _webhook_url(channel.id),
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
        "updated_at": channel.updated_at.isoformat() if channel.updated_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Management API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/channels/{workflow_id}")
async def get_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    return _serialize_channel(channel)


@router.put("/channels/{workflow_id}")
async def connect_channel(
    workflow_id: str,
    payload: ConnectionPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connection wizard save. Persists encrypted credentials. Does not by
    itself mark the channel 'connected' — call POST .../test (or .../reconnect)
    to validate against the live Graph API, matching the explicit
    'Test Connection' step in the wizard."""
    await _get_owned_workflow(workflow_id, db, current_user)

    if not payload.phone_number_id.strip() or not payload.access_token.strip():
        raise HTTPException(status_code=400, detail="Phone Number ID and Access Token are required")
    if not payload.verify_token.strip():
        raise HTTPException(status_code=400, detail="Verify Token is required")

    channel = await _get_channel(workflow_id, db)
    if channel:
        channel.phone_number_id = payload.phone_number_id.strip()
        channel.business_account_id = payload.business_account_id.strip()
        channel.encrypted_access_token = wa.encrypt_credential(payload.access_token.strip())
        channel.encrypted_verify_token = wa.encrypt_credential(payload.verify_token.strip())
        if payload.app_secret is not None:
            channel.encrypted_app_secret = (
                wa.encrypt_credential(payload.app_secret.strip()) if payload.app_secret.strip() else None
            )
        channel.status = "connecting"
        channel.health_status = "unknown"
        channel.last_error = None
    else:
        channel = WhatsAppChannel(
            workflow_id=workflow_id,
            user_id=current_user.id,
            phone_number_id=payload.phone_number_id.strip(),
            business_account_id=payload.business_account_id.strip(),
            encrypted_access_token=wa.encrypt_credential(payload.access_token.strip()),
            encrypted_verify_token=wa.encrypt_credential(payload.verify_token.strip()),
            encrypted_app_secret=(
                wa.encrypt_credential(payload.app_secret.strip())
                if payload.app_secret and payload.app_secret.strip() else None
            ),
            status="connecting",
        )
        db.add(channel)

    await db.commit()
    await db.refresh(channel)
    return _serialize_channel(channel)


@router.post("/channels/{workflow_id}/test")
async def test_connection(
    workflow_id: str,
    payload: Optional[TestPayload] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test Connection. If phone_number_id/access_token are provided in the
    body (the wizard testing values not yet saved), those are used; otherwise
    the channel's currently saved credentials are tested."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)

    phone_number_id = (payload.phone_number_id if payload and payload.phone_number_id else None) or (
        channel.phone_number_id if channel else None
    )
    access_token = (payload.access_token if payload and payload.access_token else None) or (
        wa.decrypt_credential(channel.encrypted_access_token) if channel else None
    )

    if not phone_number_id or not access_token:
        raise HTTPException(status_code=400, detail="No credentials to test — save a connection first")

    client = wa.WhatsAppCloudClient(phone_number_id, access_token)
    started = time.monotonic()
    try:
        details = await client.get_phone_number_details()
        latency_ms = int((time.monotonic() - started) * 1000)
        result = {
            "ok": True,
            "latency_ms": latency_ms,
            "display_phone_number": details.get("display_phone_number"),
            "verified_name": details.get("verified_name"),
            "quality_rating": details.get("quality_rating"),
        }
    except Exception as e:
        error_msg = str(e).strip() or f"{type(e).__name__} while testing WhatsApp connection"
        logger.warning(f"WhatsApp test_connection failed for workflow={workflow_id}: {error_msg}")
        result = {"ok": False, "error": error_msg, "latency_ms": int((time.monotonic() - started) * 1000)}

    if channel:
        channel.last_tested_at = datetime.now(timezone.utc)
        if result["ok"]:
            channel.status = "connected"
            channel.health_status = "healthy"
            channel.last_error = None
            channel.display_phone_number = result.get("display_phone_number")
            channel.verified_name = result.get("verified_name")
            channel.quality_rating = result.get("quality_rating")
        else:
            channel.status = "error"
            channel.health_status = "error"
            channel.last_error = result.get("error")
        await db.commit()

    return result


@router.post("/channels/{workflow_id}/enable")
async def enable_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="No WhatsApp connection configured for this bot")
    if channel.status != "connected":
        raise HTTPException(
            status_code=400,
            detail="Run Test Connection successfully before enabling WhatsApp",
        )
    channel.is_enabled = True
    await db.commit()
    return {"is_enabled": True, "status": channel.status}


@router.post("/channels/{workflow_id}/disable")
async def disable_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="No WhatsApp connection configured for this bot")
    channel.is_enabled = False
    await db.commit()
    return {"is_enabled": False, "status": channel.status}


@router.post("/channels/{workflow_id}/reconnect")
async def reconnect_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-validates the currently saved credentials against the Graph API
    and refreshes phone-number metadata + health status."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="No WhatsApp connection configured for this bot")

    client = wa.client_from_channel(channel)
    started = time.monotonic()
    try:
        details = await client.get_phone_number_details()
        channel.status = "connected"
        channel.health_status = "healthy"
        channel.last_error = None
        channel.display_phone_number = details.get("display_phone_number")
        channel.verified_name = details.get("verified_name")
        channel.quality_rating = details.get("quality_rating")
        channel.last_tested_at = datetime.now(timezone.utc)
        channel.last_sync_at = datetime.now(timezone.utc)
        await db.commit()
        return {"ok": True, "status": channel.status, "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as e:
        error_msg = str(e).strip() or f"{type(e).__name__} while reconnecting"
        channel.status = "error"
        channel.health_status = "error"
        channel.last_error = error_msg
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Reconnect failed: {error_msg}")


@router.post("/channels/{workflow_id}/disconnect")
async def disconnect_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnects WhatsApp: clears stored credentials and disables the
    channel. The row (and any historical conversations/messages already
    recorded in Analytics) is kept, so reconnecting doesn't lose history."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="No WhatsApp connection configured for this bot")

    channel.is_enabled = False
    channel.status = "disconnected"
    channel.health_status = "unknown"
    channel.last_error = None
    channel.encrypted_access_token = ""
    channel.display_phone_number = None
    channel.verified_name = None
    channel.quality_rating = None
    await db.commit()
    return {"disconnected": True}


@router.get("/channels/{workflow_id}/webhook-info")
async def webhook_info(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="Save a connection first to get a webhook URL")
    return {
        "webhook_url": _webhook_url(channel.id),
        "verify_token": wa.decrypt_credential(channel.encrypted_verify_token),
        "app_secret_configured": bool(channel.encrypted_app_secret),
        "subscribe_fields": ["messages"],
    }


@router.get("/channels/{workflow_id}/stats")
async def channel_stats(
    workflow_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        return {"connected": False}

    conversations = await analytics_service.list_conversations(
        db, str(current_user.id), workflow_id=workflow_id, source="whatsapp",
        page=page, page_size=page_size,
    )
    contacts_result = await db.execute(
        select(WhatsAppContact)
        .where(WhatsAppContact.channel_id == channel.id)
        .order_by(WhatsAppContact.last_message_at.desc())
        .limit(50)
    )
    contacts = contacts_result.scalars().all()

    return {
        "connected": True,
        "status": channel.status,
        "is_enabled": channel.is_enabled,
        "health_status": channel.health_status,
        "last_error": channel.last_error,
        "last_sync_at": channel.last_sync_at.isoformat() if channel.last_sync_at else None,
        "last_webhook_at": channel.last_webhook_at.isoformat() if channel.last_webhook_at else None,
        "messages_received_count": channel.messages_received_count,
        "messages_sent_count": channel.messages_sent_count,
        "messages_failed_count": channel.messages_failed_count,
        "contact_count": len(contacts),
        "contacts": [
            {
                "wa_id": c.wa_id, "profile_name": c.profile_name,
                "message_count": c.message_count,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            }
            for c in contacts
        ],
        "conversations": conversations,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Webhook — public, called by Meta
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook/{channel_id}")
async def verify_webhook(
    channel_id: str,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta's subscription handshake: GET with hub.mode=subscribe and
    hub.verify_token must echo back hub.challenge verbatim as plain text,
    otherwise respond 403."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WhatsAppChannel).where(WhatsAppChannel.id == channel_id))
        channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(status_code=404, detail="Unknown WhatsApp channel")

    saved_verify_token = wa.decrypt_credential(channel.encrypted_verify_token)
    # SECURITY FIX: constant-time comparison, matching the pattern already
    # used for the POST webhook's X-Hub-Signature-256 check, so the verify
    # token can't be brute-forced via response-timing differences.
    if hub_mode == "subscribe" and hub_verify_token and hmac.compare_digest(hub_verify_token, saved_verify_token):
        return PlainTextResponse(content=hub_challenge or "")

    raise HTTPException(status_code=403, detail="Webhook verification failed")


def _session_id_for(channel_id: str, wa_id: str) -> str:
    return f"wa_{channel_id}_{wa_id}"


def _normalize_incoming_message(message: dict) -> dict:
    """Turns a single Cloud API `messages[]` entry into a normalized dict:
    {type, text, media_id, media_type, mime_type, filename, caption, location, contacts}.
    `text` is always populated with something safe to feed into the Workflow
    Runtime as user_message, even for non-text message types."""
    mtype = message.get("type", "text")
    out: dict = {"type": mtype, "text": "", "media_id": None, "media_type": None,
                 "mime_type": None, "filename": None, "caption": None,
                 "location": None, "contacts": None}

    if mtype == "text":
        out["text"] = (message.get("text") or {}).get("body", "")

    elif mtype in ("image", "video", "sticker"):
        media = message.get(mtype) or {}
        out["media_id"] = media.get("id")
        out["media_type"] = mtype
        out["mime_type"] = media.get("mime_type")
        out["caption"] = media.get("caption")
        out["text"] = media.get("caption") or f"[{mtype.capitalize()} received]"

    elif mtype == "document":
        media = message.get("document") or {}
        out["media_id"] = media.get("id")
        out["media_type"] = "document"
        out["mime_type"] = media.get("mime_type")
        out["filename"] = media.get("filename")
        out["caption"] = media.get("caption")
        label = media.get("filename") or "document"
        out["text"] = media.get("caption") or f"[Document received: {label}]"

    elif mtype == "audio":
        media = message.get("audio") or {}
        out["media_id"] = media.get("id")
        out["media_type"] = "audio"
        out["mime_type"] = media.get("mime_type")
        out["text"] = "[Voice message received]"

    elif mtype == "location":
        loc = message.get("location") or {}
        out["location"] = loc
        lat, lng = loc.get("latitude"), loc.get("longitude")
        name = loc.get("name") or loc.get("address") or ""
        out["text"] = f"[Location shared: {name} ({lat}, {lng})]".strip()

    elif mtype == "contacts":
        contacts = message.get("contacts") or []
        out["contacts"] = contacts
        names = [c.get("name", {}).get("formatted_name", "Unknown") for c in contacts]
        out["text"] = f"[Contact(s) shared: {', '.join(names)}]"

    elif mtype == "interactive":
        interactive = message.get("interactive") or {}
        itype = interactive.get("type")
        if itype == "button_reply":
            out["text"] = (interactive.get("button_reply") or {}).get("id", "")
        elif itype == "list_reply":
            out["text"] = (interactive.get("list_reply") or {}).get("id", "")
        else:
            out["text"] = ""

    elif mtype == "button":
        # Legacy quick-reply button tap on a template message.
        out["text"] = (message.get("button") or {}).get("text", "")

    else:
        out["text"] = f"[Unsupported message type: {mtype}]"

    return out


async def _send_runner_result(client: wa.WhatsAppCloudClient, to: str, result: dict) -> tuple[int, int]:
    """Sends the WorkflowRunner result to WhatsApp using the richest
    available message type. Returns (sent_count, failed_count)."""
    sent, failed = 0, 0
    choices = result.get("choices")
    response_text = (result.get("response") or "").strip()
    image = result.get("image")

    try:
        if choices:
            body_text = response_text or "Please choose an option:"
            if len(choices) <= 3:
                buttons = [
                    {"id": str(i + 1), "title": str(c.get("label") or c.get("value") or f"Option {i + 1}")}
                    for i, c in enumerate(choices)
                ]
                await client.send_buttons(to, body_text, buttons)
            else:
                rows = [
                    {"id": str(i + 1), "title": str(c.get("label") or c.get("value") or f"Option {i + 1}")}
                    for i, c in enumerate(choices)
                ]
                await client.send_list(to, body_text, "View options", rows)
            sent += 1
        elif response_text:
            await client.send_text(to, response_text)
            sent += 1

        if image:
            await client.send_image(to, image)
            sent += 1
    except Exception as e:
        logger.error(f"WhatsApp send failed to={to}: {e}", exc_info=True)
        failed += 1

    return sent, failed


@router.post("/webhook/{channel_id}")
async def receive_webhook(channel_id: str, request: Request):
    raw_body = await request.body()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WhatsAppChannel).where(WhatsAppChannel.id == channel_id))
        channel = result.scalar_one_or_none()

        if not channel:
            # Unknown channel — nothing to validate against; ack quietly so
            # Meta doesn't hammer retries against a stale/removed webhook.
            return {"status": "ignored"}

        # ── Signature validation ────────────────────────────────────────────
        app_secret = wa.decrypt_credential(channel.encrypted_app_secret) if channel.encrypted_app_secret else ""
        signature = request.headers.get("x-hub-signature-256")
        if not wa.verify_webhook_signature(app_secret, raw_body, signature):
            logger.warning(f"WhatsApp webhook signature validation failed for channel={channel_id}")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

        if not channel.is_enabled:
            return {"status": "disabled"}

        try:
            payload = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return {"status": "invalid_json"}

        cache = CacheService()
        workflow_id = channel.workflow_id

        workflow = await get_deployed_workflow_data(workflow_id, cache)
        if not workflow:
            # Fall back to the live draft so a bot that's only ever been used
            # via WhatsApp (never explicitly Published) still works — the
            # WhatsApp connection itself is already an owner-authorized,
            # explicit "go live" action, same trust level as Publish.
            workflow = await get_workflow_data(workflow_id, cache)

        if not workflow or not workflow.get("nodes"):
            channel.last_error = "Workflow has no nodes / could not be loaded"
            channel.health_status = "error"
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "workflow_unavailable"}

        entries = payload.get("entry", [])
        any_processed = False
        any_failed = False

        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if change.get("field") and change.get("field") != "messages":
                    continue

                profiles = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                            for c in (value.get("contacts") or [])}

                # ── Campaign delivery/read status callbacks (NEW) ───────────
                # Meta sends a separate `statuses` array (no `messages` key)
                # for delivery/read/failed receipts on messages WE sent. This
                # is purely additive: campaign_dispatch.record_delivery_status
                # no-ops for any provider_message_id that isn't a tracked
                # campaign send (e.g. an ordinary AI reply), so normal bot
                # traffic through this webhook is unaffected.
                for status_event in value.get("statuses", []):
                    try:
                        await campaign_dispatch.record_delivery_status(
                            db,
                            provider_message_id=status_event.get("id", ""),
                            status=status_event.get("status", ""),
                            error=((status_event.get("errors") or [{}])[0]).get("title"),
                        )
                    except Exception as e:  # noqa: BLE001 — status tracking must never break the webhook
                        logger.warning(f"Campaign delivery-status update failed: {e}")

                for message in value.get("messages", []):
                    any_processed = True
                    wa_id = message.get("from")
                    if not wa_id:
                        continue

                    normalized = _normalize_incoming_message(message)
                    user_message = normalized["text"]

                    session_id = _session_id_for(channel.id, wa_id)

                    # ── Contact / session bookkeeping ───────────────────────
                    contact_result = await db.execute(
                        select(WhatsAppContact).where(
                            WhatsAppContact.channel_id == channel.id, WhatsAppContact.wa_id == wa_id
                        )
                    )
                    contact = contact_result.scalar_one_or_none()
                    profile_name = profiles.get(wa_id)
                    if not contact:
                        contact = WhatsAppContact(
                            channel_id=channel.id, workflow_id=workflow_id, wa_id=wa_id,
                            profile_name=profile_name, session_id=session_id,
                        )
                        db.add(contact)
                    elif profile_name:
                        contact.profile_name = profile_name
                    contact.message_count += 1
                    contact.last_message_at = datetime.now(timezone.utc)

                    # ── Owner Assistant (NEW — Part 2, Campaign QR Marketing
                    # System) — mirrors api/v1/telegram.py's identical hook.
                    # Two additive checks, both fully isolated from the
                    # customer-facing Workflow Runtime below: the one-time
                    # "/assistant <code>" linking handshake, and — for any
                    # wa_id that already has an active OwnerAssistantLink —
                    # routing the entire turn to
                    # app.services.owner_assistant_service instead of the AI
                    # Agent/Workflow Runtime. Any other wa_id/message falls
                    # straight through to the unmodified behavior below.
                    if owner_assistant.is_link_command(user_message):
                        link_reply = await owner_assistant.try_handle_link_command(
                            db, channel="whatsapp", chat_id=wa_id, workflow_owner_id=channel.user_id,
                            workflow_id=workflow_id, text=user_message,
                        )
                        if link_reply:
                            client = wa.client_from_channel(channel)
                            try:
                                await client.send_text(wa_id, link_reply)
                                any_processed = True
                            except Exception as e:  # noqa: BLE001
                                logger.warning(f"WhatsApp owner-assistant link reply send failed channel={channel_id}: {e}")
                                any_failed = True
                            continue

                    owner_link = await owner_assistant.get_active_link(db, channel="whatsapp", chat_id=wa_id)
                    if owner_link:
                        owner_link.last_used_at = datetime.now(timezone.utc)
                        owner_result = await db.execute(select(User).where(User.id == owner_link.user_id))
                        owner_user = owner_result.scalar_one_or_none()
                        assistant_reply = (
                            await owner_assistant.handle_owner_message(
                                db, owner_user, channel="whatsapp", chat_id=wa_id,
                                workflow_id=owner_link.workflow_id or workflow_id, text=user_message,
                            )
                            if owner_user else
                            "Your Owner Assistant link is no longer valid — please re-link from the dashboard."
                        )
                        client = wa.client_from_channel(channel)
                        try:
                            await client.send_text(wa_id, assistant_reply)
                            any_processed = True
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"WhatsApp owner-assistant reply send failed channel={channel_id}: {e}")
                            any_failed = True
                        continue

                    # ── Load ExecutionContext (same Redis session pattern
                    # used by the REST + WS chat paths) ─────────────────────
                    context_data = await cache.get(f"session:{session_id}")
                    context = (
                        ExecutionContext.from_dict(context_data) if context_data
                        else ExecutionContext(session_id=session_id, workflow_id=workflow_id)
                    )
                    if not context.session_id:
                        context.session_id = session_id
                    if not context.workflow_id:
                        context.workflow_id = workflow_id

                    # ── Secure media download ───────────────────────────────
                    client = wa.client_from_channel(channel)
                    if normalized["media_id"]:
                        try:
                            asset_meta = await wa.download_and_store_media(
                                client, normalized["media_id"], channel.id, normalized["media_type"],
                            )
                            db.add(WhatsAppMediaAsset(
                                channel_id=channel.id, workflow_id=workflow_id, **asset_meta,
                            ))
                            context.set_variable("last_media_url", wa.media_asset_url(asset_meta["file_path"]))
                            context.set_variable("last_media_type", normalized["media_type"])
                        except Exception as e:
                            logger.error(f"WhatsApp media download failed: {e}", exc_info=True)

                    if normalized["location"]:
                        context.set_variable("last_location", normalized["location"])
                    if normalized["contacts"]:
                        context.set_variable("last_shared_contacts", normalized["contacts"])

                    # ── Human takeover check (NEW) ──────────────────────────
                    # If the owner has taken this conversation over (only
                    # possible for a session that originated from a campaign
                    # send — see campaign_dispatch.set_human_takeover), skip
                    # the Workflow Runtime entirely for this turn: the human
                    # is expected to reply from the WhatsApp Business app.
                    # For every other conversation (the overwhelming
                    # majority — anything not started by a campaign) this
                    # lookup finds nothing and behavior is 100% unchanged.
                    campaign_recipient = await campaign_dispatch.find_recipient_by_session(db, session_id)
                    human_active = bool(campaign_recipient and campaign_recipient.human_takeover)

                    if human_active:
                        await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)
                        await analytics_service.record_turn(
                            session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                            user_message=user_message, bot_response=None,
                            node_type="human_takeover", source="whatsapp",
                            visitor_key=analytics_service.hash_visitor(wa_id, "whatsapp"),
                            ended=False,
                        )
                        if campaign_recipient and not campaign_recipient.replied:
                            campaign_recipient.replied = True
                            campaign_recipient.replied_at = datetime.now(timezone.utc)
                        await client.mark_read(message.get("id", ""))
                        channel.messages_received_count += 1
                        continue

                    # ── Execute the EXISTING Workflow Runtime ───────────────
                    runner = WorkflowRunner(workflow, user_id=channel.user_id)
                    started = time.monotonic()
                    turn_error = False
                    turn_error_content = None
                    try:
                        run_result = await runner.run(user_message, context)
                        context = ExecutionContext.from_dict(run_result["context"])
                    except Exception as e:
                        turn_error = True
                        turn_error_content = str(e).strip() or f"{type(e).__name__} during workflow execution"
                        logger.error(
                            f"WhatsApp workflow execution error channel={channel_id}: {turn_error_content}",
                            exc_info=True,
                        )
                        run_result = {"response": None, "ended": False, "context": context.to_dict(),
                                      "node_type": "error", "choices": None, "image": None, "citations": []}

                    # ROOT CAUSE FIX (Issue 2 — "generated chatbot sometimes
                    # does not answer"): a Workflow Runtime execution error
                    # used to leave run_result["response"] as None and, below,
                    # skip sending anything back to WhatsApp entirely — the
                    # real customer saw total silence with no indication
                    # anything went wrong. Mirrors the EXISTING, already-correct
                    # Telegram behavior (api/v1/telegram.py): queue a Live
                    # Agent handoff and always send a friendly fallback
                    # message, so every inbound message gets some reply.
                    if turn_error:
                        try:
                            await live_agent_service.request_handoff(
                                session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                                channel="whatsapp", reason="AI Agent could not process this message",
                                requested_by="ai",
                                visitor_label=contact.profile_name if contact and contact.profile_name else wa_id,
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.error(f"WhatsApp auto-handoff-on-error failed channel={channel_id}: {e}", exc_info=True)
                        run_result["response"] = (
                            "I'm having trouble answering that right now — connecting you with a human agent."
                        )

                    latency_ms = int((time.monotonic() - started) * 1000)

                    await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)

                    # ── Campaign auto-reply outcome tracking (NEW, additive) ──
                    if campaign_recipient:
                        try:
                            await campaign_dispatch.record_reply_outcome(
                                db, campaign_recipient, context, turn_error,
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"Campaign reply-outcome update failed: {e}")

                    # ── Send reply back to WhatsApp (with retry, inside the client) ──
                    # ROOT CAUSE FIX: previously gated on `not turn_error`, which
                    # meant an execution error skipped sending anything at all.
                    # Now always attempts to send whatever run_result["response"]
                    # holds — the real answer on success, or the friendly
                    # fallback message set above on failure.
                    sent, failed = (0, 0)
                    if run_result.get("response") or run_result.get("choices"):
                        sent, failed = await _send_runner_result(client, wa_id, run_result)
                        if failed:
                            any_failed = True
                    await client.mark_read(message.get("id", ""))

                    channel.messages_received_count += 1
                    channel.messages_sent_count += sent
                    channel.messages_failed_count += failed

                    # ── Analytics — same call shape as chat.py / chat_ws.py ──
                    await analytics_service.record_turn(
                        session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                        user_message=user_message, bot_response=None if turn_error else run_result.get("response"),
                        node_type=run_result.get("node_type"), provider=run_result.get("provider"),
                        latency_ms=latency_ms, is_error=turn_error, error_message=turn_error_content,
                        citations=run_result.get("citations", []), source="whatsapp",
                        visitor_key=analytics_service.hash_visitor(wa_id, "whatsapp"),
                        ended=bool(context.completed),
                    )

        channel.last_webhook_at = datetime.now(timezone.utc)
        channel.last_sync_at = datetime.now(timezone.utc)
        if any_processed:
            channel.health_status = "degraded" if any_failed else "healthy"
            if not any_failed:
                channel.last_error = None
        await db.commit()

    return {"status": "ok"}
