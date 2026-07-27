"""
ThunderBots Telegram API — Part 1 (Connect Bot + Manage Subscribers)
NEW (Telegram Channel).

Two groups of routes:

1. Management (authenticated, owner-scoped) — connection wizard, settings
   UI, enable/disable/reconnect/disconnect, webhook info, subscriber stats.

2. Webhook (public, no auth — this IS Telegram's callback endpoint,
   protected instead by the X-Telegram-Bot-Api-Secret-Token header) — every
   inbound text message is executed through the EXISTING Workflow Runtime
   (app.engine.runner.WorkflowRunner) using the exact same
   run()/ExecutionContext/Redis-session pattern already used by the REST
   chat endpoint, the WebSocket endpoint, and the WhatsApp/Instagram
   channels (none of which are modified here, only imported from). Every
   turn is recorded via the existing app.services.analytics_service with
   source="telegram" — the only thing required for Telegram conversations
   to automatically appear on the Analytics Dashboard.

Subscriber safety: a TelegramSubscriber row is only ever created inside the
webhook handler below, in direct response to an inbound update for that
chat_id — i.e. only for people who have themselves started the bot
conversation. There is no endpoint anywhere in this module that adds a
subscriber from a chat_id supplied by the caller, and no send path that
targets a chat_id not already on file as a subscriber.
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.core.database import get_db, AsyncSessionLocal
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.engine.runner import WorkflowRunner
from app.engine.context import ExecutionContext
from app.models.user import User
from app.models.workflow import Workflow
from app.models.telegram import TelegramChannel, TelegramSubscriber
from app.config import settings
from app.services import analytics_service
from app.services import telegram_service as tg
from app.services import campaign_dispatch_service as campaign_dispatch
from app.services import live_agent_service
from app.services import owner_assistant_service as owner_assistant
from app.api.ws.chat_ws import get_workflow_data, get_deployed_workflow_data
from app.models.live_agent import LiveAgentHandoff
from app.models.analytics import Conversation

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionPayload(BaseModel):
    bot_token: str


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


async def _get_channel(workflow_id: str, db: AsyncSession) -> Optional[TelegramChannel]:
    result = await db.execute(select(TelegramChannel).where(TelegramChannel.workflow_id == workflow_id))
    return result.scalar_one_or_none()


def _webhook_url(channel_id: str) -> str:
    return f"{settings.APP_API_URL}/api/v1/telegram/webhook/{channel_id}"


async def _subscriber_count(channel_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(TelegramSubscriber.id)).where(
            TelegramSubscriber.channel_id == channel_id, TelegramSubscriber.is_subscribed.is_(True)
        )
    )
    return result.scalar_one() or 0


def _serialize_channel(channel: Optional[TelegramChannel], subscriber_count: int = 0) -> dict:
    if not channel:
        return {"connected": False}
    return {
        "connected": True,
        "id": channel.id,
        "workflow_id": channel.workflow_id,
        "bot_id": channel.bot_id,
        "bot_username": channel.bot_username,
        "bot_first_name": channel.bot_first_name,
        "status": channel.status,
        "is_enabled": channel.is_enabled,
        "health_status": channel.health_status,
        "last_error": channel.last_error,
        "webhook_registered": channel.webhook_registered,
        "subscriber_count": subscriber_count,
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


async def _apply_getme_result(channel: TelegramChannel, me: dict) -> None:
    channel.bot_id = str(me.get("id")) if me.get("id") is not None else None
    channel.bot_username = me.get("username")
    channel.bot_first_name = me.get("first_name")


def _status_from_error(exc: "tg.TelegramAPIError") -> str:
    """401 (Unauthorized) from Telegram is a definitive 'this token is
    wrong/revoked' signal — surfaced as its own status per the requirements
    (Connected / Disconnected / Invalid Token) rather than a generic error."""
    return "invalid_token" if exc.error_code == 401 else "error"


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
    count = await _subscriber_count(channel.id, db) if channel else 0
    return _serialize_channel(channel, count)


@router.put("/channels/{workflow_id}")
async def connect_channel(
    workflow_id: str,
    payload: ConnectionPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connection wizard save. Validates the bot token against Telegram's
    live getMe API immediately (Telegram has no separate offline "save
    then test" step the way the WhatsApp wizard does — a bot token is
    either accepted by Telegram or it isn't), then registers our webhook
    so the bot starts receiving updates right away."""
    await _get_owned_workflow(workflow_id, db, current_user)

    bot_token = payload.bot_token.strip()
    if not bot_token:
        raise HTTPException(status_code=400, detail="Bot token is required")
    if not tg.looks_like_bot_token(bot_token):
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a Telegram Bot API token. Get one from @BotFather.",
        )

    channel = await _get_channel(workflow_id, db)
    if channel:
        channel.encrypted_bot_token = tg.encrypt_credential(bot_token)
        channel.status = "connecting"
        channel.health_status = "unknown"
        channel.last_error = None
        channel.webhook_registered = False
    else:
        channel = TelegramChannel(
            workflow_id=workflow_id,
            user_id=current_user.id,
            encrypted_bot_token=tg.encrypt_credential(bot_token),
            encrypted_webhook_secret=tg.encrypt_credential(tg.generate_webhook_secret()),
            status="connecting",
        )
        db.add(channel)

    await db.commit()
    await db.refresh(channel)

    await _test_and_register(channel, db)

    count = await _subscriber_count(channel.id, db)
    return _serialize_channel(channel, count)


async def _test_and_register(channel: TelegramChannel, db: AsyncSession) -> dict:
    """Shared by Connect / Reconnect: validates the token via getMe, then
    (re)registers the webhook with Telegram so it points at this channel's
    dedicated URL with the channel's own secret token."""
    client = tg.client_from_channel(channel)
    started = time.monotonic()
    try:
        me = await client.get_me()
        await _apply_getme_result(channel, me)

        webhook_secret = tg.decrypt_credential(channel.encrypted_webhook_secret)
        await client.set_webhook(_webhook_url(channel.id), webhook_secret)

        channel.status = "connected"
        channel.health_status = "healthy"
        channel.last_error = None
        channel.webhook_registered = True
        channel.last_tested_at = datetime.now(timezone.utc)
        channel.last_sync_at = datetime.now(timezone.utc)
        await db.commit()
        return {"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)}
    except tg.TelegramAPIError as e:
        channel.status = _status_from_error(e)
        channel.health_status = "error"
        channel.last_error = e.description or str(e)
        channel.webhook_registered = False
        await db.commit()
        return {"ok": False, "error": channel.last_error, "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as e:
        error_msg = str(e).strip() or f"{type(e).__name__} while connecting to Telegram"
        logger.warning(f"Telegram connect/reconnect failed for channel={channel.id}: {error_msg}")
        channel.status = "error"
        channel.health_status = "error"
        channel.last_error = error_msg
        channel.webhook_registered = False
        await db.commit()
        return {"ok": False, "error": error_msg, "latency_ms": int((time.monotonic() - started) * 1000)}


@router.post("/channels/{workflow_id}/test")
async def test_connection(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test Connection — re-validates the currently saved bot token and
    re-registers the webhook, same as Reconnect. Kept as its own endpoint
    to match the Settings UI pattern shared with WhatsApp/Instagram."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=400, detail="No credentials to test — connect a bot first")
    result = await _test_and_register(channel, db)
    result["bot_username"] = channel.bot_username
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
        raise HTTPException(status_code=404, detail="No Telegram bot configured for this bot")
    if channel.status != "connected":
        raise HTTPException(status_code=400, detail="Connect a valid bot token before enabling Telegram")
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
        raise HTTPException(status_code=404, detail="No Telegram bot configured for this bot")
    channel.is_enabled = False
    await db.commit()
    return {"is_enabled": False, "status": channel.status}


@router.post("/channels/{workflow_id}/reconnect")
async def reconnect_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-validates the currently saved bot token against Telegram's API
    and re-registers the webhook (useful if it was ever removed/overwritten
    by calling setWebhook from elsewhere, e.g. BotFather's own tools)."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="No Telegram bot configured for this bot")

    result = await _test_and_register(channel, db)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=f"Reconnect failed: {result['error']}")
    return {"ok": True, "status": channel.status, "latency_ms": result["latency_ms"]}


@router.post("/channels/{workflow_id}/disconnect")
async def disconnect_channel(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnects Telegram: removes the webhook from Telegram's side (best
    effort — proceeds even if that call fails, e.g. token already revoked),
    clears the stored token, and disables the channel. The row (and
    subscribers/analytics already recorded) is kept, so reconnecting a bot
    with the same @username doesn't lose subscriber history."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        raise HTTPException(status_code=404, detail="No Telegram bot configured for this bot")

    try:
        client = tg.client_from_channel(channel)
        await client.delete_webhook()
    except Exception as e:  # noqa: BLE001 — disconnect must succeed even if the token is already dead
        logger.warning(f"Telegram delete_webhook failed during disconnect for channel={channel.id}: {e}")

    channel.is_enabled = False
    channel.status = "disconnected"
    channel.health_status = "unknown"
    channel.last_error = None
    channel.webhook_registered = False
    channel.encrypted_bot_token = ""
    channel.bot_id = None
    channel.bot_username = None
    channel.bot_first_name = None
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
        raise HTTPException(status_code=404, detail="Connect a bot first to get a webhook URL")
    return {
        "webhook_url": _webhook_url(channel.id),
        "webhook_registered": channel.webhook_registered,
        "managed_automatically": True,
    }


@router.get("/channels/{workflow_id}/stats")
async def channel_stats(
    workflow_id: str,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)
    if not channel:
        return {"connected": False}

    conversations = await analytics_service.list_conversations(
        db, str(current_user.id), workflow_id=workflow_id, source="telegram",
        page=page, page_size=page_size,
    )
    subscribers_result = await db.execute(
        select(TelegramSubscriber)
        .where(TelegramSubscriber.channel_id == channel.id, TelegramSubscriber.is_subscribed.is_(True))
        .order_by(TelegramSubscriber.last_message_at.desc())
        .limit(50)
    )
    subscribers = subscribers_result.scalars().all()
    count = await _subscriber_count(channel.id, db)

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
        "subscriber_count": count,
        "subscribers": [
            {
                "chat_id": s.chat_id,
                "username": s.username,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "message_count": s.message_count,
                "subscribed_at": s.subscribed_at.isoformat() if s.subscribed_at else None,
                "last_message_at": s.last_message_at.isoformat() if s.last_message_at else None,
            }
            for s in subscribers
        ],
        "conversations": conversations,
    }


@router.get("/analytics/{workflow_id}")
async def telegram_analytics(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telegram-specific analytics (NEW — Part 3): Active Conversations, AI
    Resolved, Human Handoff, Replies, Failed Deliveries. Reuses the EXISTING
    Conversation/Message tables (app.services.analytics_service already
    writes these for every Telegram turn — source="telegram") and the
    EXISTING Live Agent handoff table, filtered down to this workflow. No
    new tables, no change to how either is written."""
    await _get_owned_workflow(workflow_id, db, current_user)
    channel = await _get_channel(workflow_id, db)

    base = [Conversation.workflow_id == workflow_id, Conversation.source == "telegram"]

    active_result = await db.execute(
        select(func.count(Conversation.id)).where(*base, Conversation.status == "active")
    )
    active_conversations = active_result.scalar_one() or 0

    replies_result = await db.execute(
        select(func.coalesce(func.sum(Conversation.user_message_count), 0)).where(*base)
    )
    replies = replies_result.scalar_one() or 0

    # Conversations ever escalated to a human (Live Agent handoff status
    # other than the default "ai") for this workflow's Telegram channel.
    handoff_result = await db.execute(
        select(func.count(func.distinct(LiveAgentHandoff.session_id))).where(
            LiveAgentHandoff.workflow_id == workflow_id,
            LiveAgentHandoff.channel == "telegram",
            LiveAgentHandoff.status != "ai",
        )
    )
    human_handoff = handoff_result.scalar_one() or 0

    # Ended conversations that were never escalated — i.e. the AI Agent
    # handled the entire conversation on its own.
    escalated_sessions_subq = select(LiveAgentHandoff.session_id).where(
        LiveAgentHandoff.workflow_id == workflow_id,
        LiveAgentHandoff.channel == "telegram",
        LiveAgentHandoff.status != "ai",
    )
    ai_resolved_result = await db.execute(
        select(func.count(Conversation.id)).where(
            *base, Conversation.status == "ended",
            Conversation.session_id.not_in(escalated_sessions_subq),
        )
    )
    ai_resolved = ai_resolved_result.scalar_one() or 0

    return {
        "active_conversations": active_conversations,
        "ai_resolved": ai_resolved,
        "human_handoff": human_handoff,
        "replies": int(replies),
        "failed_deliveries": channel.messages_failed_count if channel else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Webhook — public, called by Telegram
# ─────────────────────────────────────────────────────────────────────────────

def _session_id_for(channel_id: str, chat_id: str) -> str:
    return f"tg_{channel_id}_{chat_id}"


# ── Human handoff trigger (NEW — Part 3) ────────────────────────────────────
# Mirrors the web widget's explicit "Talk to a human" action
# (api/ws/chat_ws.py's msg_type == "request_human"): a subscriber can type
# any of these to be queued for a live agent without the AI Agent/Workflow
# Runtime ever running for that turn.
_HANDOFF_COMMANDS = {
    "/agent", "/human", "/help", "talk to a human", "talk to human",
    "human agent", "speak to an agent", "speak to a human",
}


def _is_handoff_command(text: str) -> bool:
    return bool(text) and text.strip().lower() in _HANDOFF_COMMANDS


@router.post("/webhook/{channel_id}")
async def receive_webhook(
    channel_id: str,
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TelegramChannel).where(TelegramChannel.id == channel_id))
        channel = result.scalar_one_or_none()

        if not channel:
            # Unknown channel — nothing to validate against; ack quietly so
            # Telegram doesn't hammer retries against a stale/removed webhook.
            return {"status": "ignored"}

        # ── Secret token validation ──────────────────────────────────────────
        expected_secret = tg.decrypt_credential(channel.encrypted_webhook_secret)
        if not tg.verify_webhook_secret(expected_secret, x_telegram_bot_api_secret_token):
            logger.warning(f"Telegram webhook secret validation failed for channel={channel_id}")
            raise HTTPException(status_code=403, detail="Invalid webhook secret token")

        if not channel.is_enabled:
            return {"status": "disabled"}

        try:
            update = await request.json()
        except Exception:
            return {"status": "invalid_json"}

        message = update.get("message") or update.get("edited_message")
        if not message or "text" not in message:
            # Non-text update (photo, sticker, etc.) or a non-message update
            # (e.g. callback_query) — Part 1 tracks/handles text only.
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "ignored_non_text"}

        chat = message.get("chat") or {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else None
        if not chat_id:
            return {"status": "ignored"}

        user_message = message.get("text", "")
        from_user = message.get("from") or {}

        cache = CacheService()
        workflow_id = channel.workflow_id
        session_id = _session_id_for(channel.id, chat_id)

        # ── Subscriber bookkeeping — created ONLY here, in direct response
        # to this chat_id actually messaging the bot ────────────────────────
        sub_result = await db.execute(
            select(TelegramSubscriber).where(
                TelegramSubscriber.channel_id == channel.id, TelegramSubscriber.chat_id == chat_id
            )
        )
        subscriber = sub_result.scalar_one_or_none()
        if not subscriber:
            subscriber = TelegramSubscriber(
                channel_id=channel.id, workflow_id=workflow_id, chat_id=chat_id,
                username=from_user.get("username"), first_name=from_user.get("first_name"),
                last_name=from_user.get("last_name"), session_id=session_id,
            )
            db.add(subscriber)
        else:
            subscriber.is_subscribed = True
            subscriber.username = from_user.get("username") or subscriber.username
            subscriber.first_name = from_user.get("first_name") or subscriber.first_name
            subscriber.last_name = from_user.get("last_name") or subscriber.last_name
        subscriber.message_count += 1
        subscriber.last_message_at = datetime.now(timezone.utc)

        # ── Owner Assistant (NEW — Part 2, Campaign QR Marketing System) ───
        # Two additive checks, both fully isolated from the customer-facing
        # Workflow Runtime below:
        #   1. "/assistant <code>" — the one-time linking handshake, valid
        #      from ANY chat that messages this bot (that's how a new link
        #      gets created in the first place).
        #   2. Every other message from a chat_id that ALREADY has an
        #      active OwnerAssistantLink — routed entirely to
        #      app.services.owner_assistant_service instead of the AI
        #      Agent/Workflow Runtime, and the webhook returns early.
        # A chat_id with no link, sending anything other than "/assistant
        # <code>", falls straight through to the unmodified behavior below —
        # existing customer chat flows are completely unaffected.
        if owner_assistant.is_link_command(user_message):
            link_reply = await owner_assistant.try_handle_link_command(
                db, channel="telegram", chat_id=chat_id, workflow_owner_id=channel.user_id,
                workflow_id=workflow_id, text=user_message,
            )
            if link_reply:
                sent = 0
                try:
                    client = tg.client_from_channel(channel)
                    await client.send_message(chat_id, link_reply)
                    sent = 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Telegram owner-assistant link reply send failed channel={channel_id}: {e}")
                channel.messages_received_count += 1
                channel.messages_sent_count += sent
                channel.last_webhook_at = datetime.now(timezone.utc)
                await db.commit()
                return {"status": "owner_assistant_linked"}

        owner_link = await owner_assistant.get_active_link(db, channel="telegram", chat_id=chat_id)
        if owner_link:
            owner_link.last_used_at = datetime.now(timezone.utc)
            owner_result = await db.execute(select(User).where(User.id == owner_link.user_id))
            owner_user = owner_result.scalar_one_or_none()
            assistant_reply = (
                await owner_assistant.handle_owner_message(
                    db, owner_user, channel="telegram", chat_id=chat_id,
                    workflow_id=owner_link.workflow_id or workflow_id, text=user_message,
                )
                if owner_user else
                "Your Owner Assistant link is no longer valid — please re-link from the dashboard."
            )
            sent = 0
            try:
                client = tg.client_from_channel(channel)
                await client.send_message(chat_id, assistant_reply)
                sent = 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Telegram owner-assistant reply send failed channel={channel_id}: {e}")
            channel.messages_received_count += 1
            channel.messages_sent_count += sent
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "owner_assistant"}

        workflow = await get_deployed_workflow_data(workflow_id, cache)
        if not workflow:
            # Fall back to the live draft so a bot only ever used via
            # Telegram (never explicitly Published) still works — the
            # Telegram connection itself is already an owner-authorized,
            # explicit "go live" action, same trust level as Publish.
            workflow = await get_workflow_data(workflow_id, cache)

        if not workflow or not workflow.get("nodes"):
            channel.last_error = "Workflow has no nodes / could not be loaded"
            channel.health_status = "error"
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "workflow_unavailable"}

        # ── Load ExecutionContext (same Redis session pattern used by the
        # REST + WS chat paths, and by WhatsApp/Instagram) ──────────────────
        context_data = await cache.get(f"session:{session_id}")
        context = (
            ExecutionContext.from_dict(context_data) if context_data
            else ExecutionContext(session_id=session_id, workflow_id=workflow_id)
        )
        if not context.session_id:
            context.session_id = session_id
        if not context.workflow_id:
            context.workflow_id = workflow_id

        # ── Human takeover check (future-ready — no-ops today since no
        # campaign can yet dispatch on Telegram, see campaign_dispatch_
        # service.LIVE_SEND_CHANNELS) ────────────────────────────────────────
        campaign_recipient = await campaign_dispatch.find_recipient_by_session(db, session_id)
        human_active = bool(campaign_recipient and campaign_recipient.human_takeover)

        if human_active:
            await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)
            await analytics_service.record_turn(
                session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                user_message=user_message, bot_response=None,
                node_type="human_takeover", source="telegram",
                visitor_key=analytics_service.hash_visitor(chat_id, "telegram"),
                ended=False,
            )
            channel.messages_received_count += 1
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "human_takeover"}

        # ── Live Agent handoff gate (NEW — Part 3) ──────────────────────────
        # Mirrors api/ws/chat_ws.py's own handoff-status gate: once a
        # conversation is queued for or being handled by a human (via
        # app.services.live_agent_service — the EXISTING Human Handoff
        # module), incoming Telegram messages are persisted to the shared
        # conversation thread and pushed to the Live Agent dashboard instead
        # of running through the AI Agent/Workflow Runtime. Every other
        # Telegram conversation runs exactly as it did before Part 3.
        handoff_status = await live_agent_service.get_handoff_status(session_id=session_id)
        if handoff_status in ("waiting", "active", "paused"):
            await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)
            await live_agent_service.record_visitor_message(
                session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                content=user_message,
            )
            channel.messages_received_count += 1
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "human_handoff"}

        # ── Visitor-requested handoff (NEW — Part 3) ────────────────────────
        # A subscriber can ask for a human at any time (e.g. "/agent") —
        # queues the conversation via the EXISTING Live Agent module without
        # the AI Agent/Workflow Runtime running for this turn, exactly like
        # the web widget's "Talk to a human" button.
        if _is_handoff_command(user_message):
            await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)
            try:
                await live_agent_service.request_handoff(
                    session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                    channel="telegram", reason=user_message, requested_by="visitor",
                    visitor_label=(
                        f"@{subscriber.username}" if subscriber.username
                        else (subscriber.first_name or f"Telegram {chat_id}")
                    ),
                )
                confirmation = "You're being connected to a human agent. Someone will be with you shortly."
            except Exception as e:  # noqa: BLE001 — handoff request must never break the webhook
                logger.error(f"Telegram handoff request failed channel={channel_id}: {e}", exc_info=True)
                confirmation = "Sorry, we couldn't reach a human agent right now — please try again shortly."

            sent = 0
            try:
                client = tg.client_from_channel(channel)
                await client.send_message(chat_id, confirmation)
                sent = 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Telegram handoff confirmation send failed channel={channel_id}: {e}")

            channel.messages_received_count += 1
            channel.messages_sent_count += sent
            channel.last_webhook_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "handoff_requested"}

        # ── Execute the EXISTING Workflow Runtime ───────────────────────────
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
                f"Telegram workflow execution error channel={channel_id}: {turn_error_content}", exc_info=True
            )
            run_result = {"response": None, "ended": False, "context": context.to_dict(),
                          "node_type": "error", "choices": None, "citations": []}

        # ── Automatic handoff on AI failure (NEW — Part 3) ──────────────────
        # "If AI cannot answer, hand off to the existing Live Agent system":
        # a Workflow Runtime execution error means the AI Agent could not
        # produce a response for this turn, so the conversation is queued
        # for a human agent via the EXISTING Live Agent module. Best-effort —
        # a failure here must never break the webhook's own error handling.
        if turn_error:
            try:
                await live_agent_service.request_handoff(
                    session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
                    channel="telegram", reason="AI Agent could not process this message",
                    requested_by="ai",
                    visitor_label=(
                        f"@{subscriber.username}" if subscriber.username
                        else (subscriber.first_name or f"Telegram {chat_id}")
                    ),
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Telegram auto-handoff-on-error failed channel={channel_id}: {e}", exc_info=True)
            run_result["response"] = (
                "I'm having trouble answering that right now — connecting you with a human agent."
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)

        if campaign_recipient:
            try:
                await campaign_dispatch.record_reply_outcome(db, campaign_recipient, context, turn_error)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Campaign reply-outcome update failed: {e}")

        # ── Send reply back to Telegram (choices rendered as plain text —
        # interactive keyboards are a future enhancement, not required for
        # Part 1) ────────────────────────────────────────────────────────────
        sent, failed = 0, 0
        if not turn_error or run_result.get("response"):
            response_text = (run_result.get("response") or "").strip()
            choices = run_result.get("choices")
            if choices:
                options_text = "\n".join(
                    f"{i + 1}. {c.get('label') or c.get('value') or f'Option {i + 1}'}"
                    for i, c in enumerate(choices)
                )
                response_text = f"{response_text}\n\n{options_text}".strip() if response_text else options_text
            if response_text:
                try:
                    client = tg.client_from_channel(channel)
                    await client.send_message(chat_id, response_text)
                    sent = 1
                except tg.TelegramAPIError as e:
                    failed = 1
                    if e.error_code == 403:
                        # Bot was blocked by the user — stop counting them as
                        # an active subscriber for future broadcasts, but keep
                        # the row (and history) in case they unblock later.
                        subscriber.is_subscribed = False
                    logger.warning(f"Telegram send failed channel={channel_id} chat_id={chat_id}: {e}")
                except Exception as e:
                    failed = 1
                    logger.error(f"Telegram send failed channel={channel_id} chat_id={chat_id}: {e}", exc_info=True)

        channel.messages_received_count += 1
        channel.messages_sent_count += sent
        channel.messages_failed_count += failed
        channel.last_webhook_at = datetime.now(timezone.utc)
        channel.last_sync_at = datetime.now(timezone.utc)
        channel.health_status = "degraded" if failed else "healthy"
        if not failed:
            channel.last_error = None

        await analytics_service.record_turn(
            session_id=session_id, workflow_id=workflow_id, owner_id=channel.user_id,
            user_message=user_message, bot_response=run_result.get("response"),
            node_type=run_result.get("node_type"), provider=run_result.get("provider"),
            latency_ms=latency_ms, is_error=turn_error, error_message=turn_error_content,
            citations=run_result.get("citations", []), source="telegram",
            visitor_key=analytics_service.hash_visitor(chat_id, "telegram"),
            ended=bool(context.completed),
        )

        await db.commit()

    return {"status": "ok"}
