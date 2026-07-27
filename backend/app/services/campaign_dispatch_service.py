"""
ThunderBots AI Broadcast & Auto-Reply Engine — Dispatch Service
NEW: Purely additive. This is the send pipeline app/models/campaign.py's
docstring said didn't exist yet.

What this module does, and does NOT do:
- Builds/refreshes the campaign_recipients ledger from a bot's already
  opted-in contacts (WhatsAppContact rows — i.e. people who have already
  messaged the connected WhatsApp number at least once), then sends the
  campaign message to each pending/retryable recipient using the EXISTING
  app.services.whatsapp_service client (same retry-on-transient-error HTTP
  layer already used for normal bot replies) and EXISTING
  encrypt_key/decrypt_key credential handling. It does not add a second
  WhatsApp client or duplicate Graph API logic.
- Auto-reply itself is NOT implemented here: it already exists, unmodified,
  in app/api/v1/whatsapp.py's webhook, which runs the EXISTING Workflow
  Runtime (AI Agent + Knowledge Base) for every inbound message on a
  session. What this module adds is a small, additive hook the webhook
  calls (`should_run_ai` / `record_ai_turn_outcome` below) so a reply that
  happens to belong to a campaign recipient (i) is skipped when the owner
  has taken over that conversation, and (ii) updates campaign analytics
  (replied / ai_resolved / escalated) — see the two, and only two, extra
  calls added inside receive_webhook() in app/api/v1/whatsapp.py.
- Instagram/Email are recognized channel values everywhere (matches
  app/models/campaign.py's VALID_CHANNELS) but have no live send transport
  yet — dispatching a campaign on one of them fails fast with a clear,
  honest "not available yet" error instead of silently no-opping or
  fabricating a successful send.

NEW (Telegram Integration — Part 2): Telegram is now a live send channel,
following the exact same shape as WhatsApp above — a `_resolve_telegram_
channel` / `_sync_telegram_recipients` / `_send_one_telegram` trio mirrors
the WhatsApp trio, reusing the EXISTING app.services.telegram_service
client (same retry-on-transient-error HTTP layer already used for normal
bot replies) and EXISTING encrypt_credential/decrypt_credential handling.
Telegram's Bot API has no separate delivery/read-receipt webhook the way
WhatsApp's Cloud API does, so a successful sendMessage call is treated as
both "sent" and "delivered" immediately — that HTTP 200 IS Telegram's own
confirmation the message reached the chat.

Opt-in: a WhatsApp campaign only ever sends to WhatsAppContact rows
already on file for the connected workflow; a Telegram campaign only ever
sends to TelegramSubscriber rows already on file for the connected bot —
i.e. people who have already opened a conversation with the bot. This is
enforced in app/services/audience_service.py (resolve_audience), which
every dispatch path below goes through — there is no code path in this
module that can add a recipient bypassing that resolution.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.redis import CacheService
from app.config import settings
from app.engine.context import ExecutionContext
from app.models.campaign import Campaign, CampaignHistoryEntry
from app.models.campaign_broadcast import CampaignRecipient, DEFAULT_MAX_RETRIES
from app.models.whatsapp import WhatsAppChannel, WhatsAppContact
from app.models.telegram import TelegramChannel, TelegramSubscriber
from app.services import analytics_service
from app.services import audience_service
from app.services import whatsapp_service as wa
from app.services import telegram_service as tg

logger = logging.getLogger(__name__)

# Channels with a live send transport wired up today. Instagram/Email are
# valid campaign channel *values* (see models/campaign.py /
# api/v1/campaigns.py VALID_CHANNELS) so campaigns can already be drafted
# for them — they just can't be launched yet.
LIVE_SEND_CHANNELS = {"whatsapp", "telegram"}
FUTURE_CHANNELS = {"instagram", "email"}


class DispatchError(RuntimeError):
    """Raised for a campaign-level (not per-recipient) failure — e.g. no
    connected channel — so the caller can surface one clear message instead
    of a wall of per-recipient errors."""


# ─────────────────────────────────────────────────────────────────────────────
# Channel resolution
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_whatsapp_channel(db: AsyncSession, campaign: Campaign) -> WhatsAppChannel:
    """Finds the connected+enabled WhatsAppChannel this campaign should send
    from. Uses campaign.workflow_id when set; otherwise, if the user has
    exactly one connected+enabled WhatsApp channel, uses that (so existing
    campaigns/clients that never set workflow_id keep working)."""
    if campaign.workflow_id:
        result = await db.execute(
            select(WhatsAppChannel).where(WhatsAppChannel.workflow_id == campaign.workflow_id)
        )
        channel = result.scalar_one_or_none()
        if not channel:
            raise DispatchError("The bot connected to this campaign has no WhatsApp connection configured.")
    else:
        result = await db.execute(
            select(WhatsAppChannel).where(
                WhatsAppChannel.user_id == campaign.user_id,
                WhatsAppChannel.is_enabled.is_(True),
                WhatsAppChannel.status == "connected",
            )
        )
        channels = result.scalars().all()
        if not channels:
            raise DispatchError(
                "No connected, enabled WhatsApp channel found. Connect WhatsApp for a bot first."
            )
        if len(channels) > 1:
            raise DispatchError(
                "You have more than one connected WhatsApp bot. Set a specific bot on this "
                "campaign (workflow_id) before launching."
            )
        channel = channels[0]

    if not channel.is_enabled or channel.status != "connected":
        raise DispatchError(
            "The WhatsApp channel for this campaign is not connected/enabled. "
            "Run Test Connection and enable it before launching."
        )
    return channel


async def _resolve_telegram_channel(db: AsyncSession, campaign: Campaign) -> TelegramChannel:
    """Finds the connected+enabled TelegramChannel this campaign should
    send from. Mirrors _resolve_whatsapp_channel exactly: uses
    campaign.workflow_id when set; otherwise, if the user has exactly one
    connected+enabled Telegram bot, uses that."""
    if campaign.workflow_id:
        result = await db.execute(
            select(TelegramChannel).where(TelegramChannel.workflow_id == campaign.workflow_id)
        )
        channel = result.scalar_one_or_none()
        if not channel:
            raise DispatchError("The bot connected to this campaign has no Telegram connection configured.")
    else:
        result = await db.execute(
            select(TelegramChannel).where(
                TelegramChannel.user_id == campaign.user_id,
                TelegramChannel.is_enabled.is_(True),
                TelegramChannel.status == "connected",
            )
        )
        channels = result.scalars().all()
        if not channels:
            raise DispatchError(
                "No connected, enabled Telegram bot found. Connect Telegram for a bot first."
            )
        if len(channels) > 1:
            raise DispatchError(
                "You have more than one connected Telegram bot. Set a specific bot on this "
                "campaign (workflow_id) before launching."
            )
        channel = channels[0]

    if not channel.is_enabled or channel.status != "connected":
        raise DispatchError(
            "The Telegram bot for this campaign is not connected/enabled. "
            "Run Test Connection and enable it before launching."
        )
    return channel


# ─────────────────────────────────────────────────────────────────────────────
# Recipient ledger
# ─────────────────────────────────────────────────────────────────────────────

def _session_id_for(channel_id: str, wa_id: str) -> str:
    # MUST match app.api.v1.whatsapp._session_id_for exactly — this is what
    # lets an inbound reply land back on the same Workflow Runtime session
    # a campaign message was sent on.
    return f"wa_{channel_id}_{wa_id}"


async def _sync_whatsapp_recipients(
    db: AsyncSession, campaign: Campaign, channel: WhatsAppChannel,
    contact_ids: Optional[list[str]] = None,
) -> list[CampaignRecipient]:
    """Upserts campaign_recipients from the campaign's resolved audience
    (audience_type/audience_config — see app/services/audience_service.py).
    Defaults to every opted-in WhatsApp contact when no audience was
    explicitly configured, preserving old behavior for existing campaigns.
    Idempotent — safe to call again on retry/resume without duplicating
    rows (unique on campaign_id + contact_identifier)."""
    audience_type = campaign.audience_type or "contacts"
    audience_config = dict(campaign.audience_config or {})
    if contact_ids and audience_type == "contacts":
        audience_config = {**audience_config, "contact_ids": contact_ids}

    resolved = await audience_service.resolve_audience(
        db, campaign.user_id, channel.workflow_id, audience_type, audience_config,
    )
    if not resolved.entries:
        raise DispatchError(
            "This campaign's audience is empty. Select at least one valid recipient "
            "(WhatsApp contacts, a contact group, a tag, or manual/CSV numbers)."
        )

    existing_result = await db.execute(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)
    )
    existing_by_identifier = {r.contact_identifier: r for r in existing_result.scalars().all()}

    recipients: list[CampaignRecipient] = []
    for entry in resolved.entries:
        existing = existing_by_identifier.get(entry.identifier)
        if existing:
            recipients.append(existing)
            continue
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            user_id=campaign.user_id,
            channel="whatsapp",
            contact_identifier=entry.identifier,
            contact_name=entry.name,
            contact_city=entry.city,
            contact_company=entry.company,
            source=audience_type,
            session_id=_session_id_for(channel.id, entry.identifier),
            workflow_id=channel.workflow_id,
            max_retries=DEFAULT_MAX_RETRIES,
        )
        db.add(recipient)
        recipients.append(recipient)

    await db.flush()
    return recipients


def _session_id_for_telegram(channel_id: str, chat_id: str) -> str:
    # MUST match app.api.v1.telegram._session_id_for exactly — this is what
    # lets an inbound reply land back on the same Workflow Runtime session
    # a campaign message was sent on (the Telegram webhook already has the
    # human-takeover + record_reply_outcome hooks wired in from Part 1).
    return f"tg_{channel_id}_{chat_id}"


async def _sync_telegram_recipients(
    db: AsyncSession, campaign: Campaign, channel: TelegramChannel,
    contact_ids: Optional[list[str]] = None,
) -> list[CampaignRecipient]:
    """Upserts campaign_recipients from the campaign's resolved Telegram
    audience (audience_service.resolve_audience(..., channel="telegram")),
    which only ever resolves chat_ids that are real, currently-subscribed
    TelegramSubscriber rows for this bot — see that module's docstring for
    the opt-in guarantee. Mirrors _sync_whatsapp_recipients exactly; safe
    to call again on retry/resume without duplicating rows."""
    audience_type = campaign.audience_type or "contacts"
    audience_config = dict(campaign.audience_config or {})
    if contact_ids and audience_type == "contacts":
        audience_config = {**audience_config, "contact_ids": contact_ids}

    resolved = await audience_service.resolve_audience(
        db, campaign.user_id, channel.workflow_id, audience_type, audience_config,
        channel="telegram",
    )
    if not resolved.entries:
        raise DispatchError(
            "This campaign's audience is empty. Select at least one Telegram subscriber who "
            "has started a conversation with this bot."
        )

    existing_result = await db.execute(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)
    )
    existing_by_identifier = {r.contact_identifier: r for r in existing_result.scalars().all()}

    recipients: list[CampaignRecipient] = []
    for entry in resolved.entries:
        existing = existing_by_identifier.get(entry.identifier)
        if existing:
            recipients.append(existing)
            continue
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            user_id=campaign.user_id,
            channel="telegram",
            contact_identifier=entry.identifier,
            contact_name=entry.name,
            contact_city=entry.city,
            contact_company=entry.company,
            source=audience_type,
            session_id=_session_id_for_telegram(channel.id, entry.identifier),
            workflow_id=channel.workflow_id,
            max_retries=DEFAULT_MAX_RETRIES,
        )
        db.add(recipient)
        recipients.append(recipient)

    await db.flush()
    return recipients


def _personalize(message: str, recipient: CampaignRecipient) -> str:
    values = {
        "name": recipient.contact_name or "there",
        "city": recipient.contact_city or "",
        "company": recipient.contact_company or "",
    }
    text = message
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
        text = text.replace("{{ " + key + " }}", val)
    # Legacy single-brace {name} form kept for backward compatibility with
    # campaigns created before {{name}}/{{city}}/{{company}} were supported.
    text = text.replace("{name}", values["name"])
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Sending
# ─────────────────────────────────────────────────────────────────────────────

async def _send_one_whatsapp(
    db: AsyncSession, campaign: Campaign, channel: WhatsAppChannel, recipient: CampaignRecipient,
) -> None:
    client = wa.client_from_channel(channel)
    recipient.last_attempt_at = datetime.now(timezone.utc)
    recipient.status = "queued"

    body = _personalize(campaign.message, recipient)
    try:
        response = await client.send_text(recipient.contact_identifier, body)
        message_id = ((response.get("messages") or [{}])[0]).get("id")
        recipient.status = "sent"
        recipient.provider_message_id = message_id
        recipient.sent_at = datetime.now(timezone.utc)
        recipient.error_message = None
        campaign.sent_count = (campaign.sent_count or 0) + 1
        channel.messages_sent_count += 1

        # Seed/attach the analytics Conversation now, tagged with this
        # campaign, so the reply this message provokes — handled entirely
        # by the existing, unmodified webhook -> Workflow Runtime path —
        # is attributable back to this campaign without touching the
        # Conversation/Message schema.
        await analytics_service.get_or_create_conversation(
            db, session_id=recipient.session_id, workflow_id=channel.workflow_id,
            owner_id=campaign.user_id, source="whatsapp",
            visitor_key=analytics_service.hash_visitor(recipient.contact_identifier, "whatsapp"),
            meta={"campaign_id": campaign.id, "campaign_recipient_id": recipient.id},
        )
    except Exception as e:  # noqa: BLE001 — one recipient's failure must not abort the batch
        error_msg = str(e).strip() or f"{type(e).__name__} while sending"
        recipient.status = "failed"
        recipient.error_message = error_msg[:2000]
        recipient.retry_count += 1
        campaign.failed_count = (campaign.failed_count or 0) + 1
        channel.messages_failed_count += 1
        logger.warning(f"Campaign {campaign.id} send failed to={recipient.contact_identifier}: {error_msg}")


async def _send_one_telegram(
    db: AsyncSession, campaign: Campaign, channel: TelegramChannel, recipient: CampaignRecipient,
) -> None:
    """Sends one Telegram broadcast message via the EXISTING
    telegram_service.TelegramBotClient (same client/retry layer used for
    normal bot replies). Telegram's Bot API has no separate delivery
    receipt for bots the way WhatsApp's Cloud API does — a successful
    sendMessage call IS the delivery confirmation, so 'sent' and
    'delivered' are recorded together here rather than waiting on a
    webhook callback that will never arrive."""
    client = tg.client_from_channel(channel)
    recipient.last_attempt_at = datetime.now(timezone.utc)
    recipient.status = "queued"

    body = _personalize(campaign.message, recipient)
    now = datetime.now(timezone.utc)
    try:
        response = await client.send_message(recipient.contact_identifier, body)
        message_id = response.get("message_id")
        recipient.status = "delivered"
        recipient.provider_message_id = str(message_id) if message_id is not None else None
        recipient.sent_at = now
        recipient.delivered_at = now
        recipient.error_message = None
        campaign.sent_count = (campaign.sent_count or 0) + 1
        campaign.delivered_count = (campaign.delivered_count or 0) + 1
        channel.messages_sent_count += 1

        # Seed/attach the analytics Conversation now, tagged with this
        # campaign, so the reply this message provokes — handled entirely
        # by the existing, unmodified Telegram webhook -> Workflow Runtime
        # path (app/api/v1/telegram.py, which already carries the
        # human-takeover + record_reply_outcome hooks from Part 1) — is
        # attributable back to this campaign without touching the
        # Conversation/Message schema.
        await analytics_service.get_or_create_conversation(
            db, session_id=recipient.session_id, workflow_id=channel.workflow_id,
            owner_id=campaign.user_id, source="telegram",
            visitor_key=analytics_service.hash_visitor(recipient.contact_identifier, "telegram"),
            meta={"campaign_id": campaign.id, "campaign_recipient_id": recipient.id},
        )
    except tg.TelegramAPIError as e:
        if e.error_code == 403:
            # Bot was blocked by this user — never a retryable failure, and
            # never something to keep counting as a reachable subscriber.
            recipient.status = "opted_out"
            recipient.error_message = (e.description or "Bot was blocked by this user")[:2000]
            sub_result = await db.execute(
                select(TelegramSubscriber).where(
                    TelegramSubscriber.channel_id == channel.id,
                    TelegramSubscriber.chat_id == recipient.contact_identifier,
                )
            )
            subscriber = sub_result.scalar_one_or_none()
            if subscriber:
                subscriber.is_subscribed = False
        else:
            error_msg = (e.description or str(e)).strip() or f"{type(e).__name__} while sending"
            recipient.status = "failed"
            recipient.error_message = error_msg[:2000]
            recipient.retry_count += 1
            campaign.failed_count = (campaign.failed_count or 0) + 1
            channel.messages_failed_count += 1
        logger.warning(f"Campaign {campaign.id} Telegram send failed to={recipient.contact_identifier}: {e}")
    except Exception as e:  # noqa: BLE001 — one recipient's failure must not abort the batch
        error_msg = str(e).strip() or f"{type(e).__name__} while sending"
        recipient.status = "failed"
        recipient.error_message = error_msg[:2000]
        recipient.retry_count += 1
        campaign.failed_count = (campaign.failed_count or 0) + 1
        channel.messages_failed_count += 1
        logger.warning(f"Campaign {campaign.id} Telegram send failed to={recipient.contact_identifier}: {error_msg}")


async def dispatch_campaign(campaign_id: str, contact_ids: Optional[list[str]] = None) -> dict:
    """Sends (or retries) a campaign. Runs in its own DB session so it can
    be safely invoked from a BackgroundTask or the scheduler loop. Never
    raises for per-recipient failures — only for campaign-level setup
    problems (DispatchError), which the caller logs to campaign_history."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise DispatchError("Campaign not found")

        if campaign.channel in FUTURE_CHANNELS:
            raise DispatchError(
                f"Sending on {campaign.channel} isn't available yet — it's coming soon. "
                "WhatsApp is fully supported today."
            )
        if campaign.channel not in LIVE_SEND_CHANNELS:
            raise DispatchError(f"Unsupported channel: {campaign.channel}")

        is_telegram = campaign.channel == "telegram"
        channel = (
            await _resolve_telegram_channel(db, campaign) if is_telegram
            else await _resolve_whatsapp_channel(db, campaign)
        )
        if not campaign.workflow_id:
            campaign.workflow_id = channel.workflow_id

        recipients = (
            await _sync_telegram_recipients(db, campaign, channel, contact_ids) if is_telegram
            else await _sync_whatsapp_recipients(db, campaign, channel, contact_ids)
        )
        sendable = [
            r for r in recipients
            if r.status in ("pending", "failed") and r.retry_count < r.max_retries
        ]

        for recipient in sendable:
            if is_telegram:
                await _send_one_telegram(db, campaign, channel, recipient)
            else:
                await _send_one_whatsapp(db, campaign, channel, recipient)
            await db.commit()  # persist progress per-recipient so a mid-batch crash loses nothing

        channel.last_sync_at = datetime.now(timezone.utc)
        campaign.status = "active" if campaign.status in ("draft", "scheduled") else campaign.status
        db.add(CampaignHistoryEntry(
            campaign_id=campaign.id, user_id=campaign.user_id, event_type="dispatch",
            detail={"attempted": len(sendable), "recipients_total": len(recipients)},
        ))
        await db.commit()

        # A campaign is "completed" once every recipient has reached a
        # terminal state (sent/delivered/read/failed-out-of-retries/opted_out).
        await _maybe_mark_completed(db, campaign)

        return {
            "attempted": len(sendable),
            "recipients_total": len(recipients),
            "sent": sum(1 for r in sendable if r.status in ("sent", "delivered")),
            "failed": sum(1 for r in sendable if r.status == "failed"),
        }


async def retry_failed_recipients(campaign_id: str, recipient_ids: Optional[list[str]] = None) -> dict:
    """Retries recipients currently in `failed` status (still under
    max_retries) — or a specific set of recipient_ids regardless of retry
    count, for an explicit manual retry."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise DispatchError("Campaign not found")
        if campaign.channel not in LIVE_SEND_CHANNELS:
            raise DispatchError(f"Retry isn't available for channel: {campaign.channel}")

        is_telegram = campaign.channel == "telegram"
        channel = (
            await _resolve_telegram_channel(db, campaign) if is_telegram
            else await _resolve_whatsapp_channel(db, campaign)
        )

        query = select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "failed",
        )
        if recipient_ids:
            query = select(CampaignRecipient).where(
                CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.id.in_(recipient_ids),
            )
        result = await db.execute(query)
        targets = result.scalars().all()

        retried = 0
        for recipient in targets:
            if recipient_ids is None and recipient.retry_count >= recipient.max_retries:
                continue
            if is_telegram:
                await _send_one_telegram(db, campaign, channel, recipient)
            else:
                await _send_one_whatsapp(db, campaign, channel, recipient)
            retried += 1
            await db.commit()

        db.add(CampaignHistoryEntry(
            campaign_id=campaign.id, user_id=campaign.user_id, event_type="retry",
            detail={"retried": retried},
        ))
        await db.commit()
        await _maybe_mark_completed(db, campaign)
        return {"retried": retried}


async def _maybe_mark_completed(db: AsyncSession, campaign: Campaign) -> None:
    result = await db.execute(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)
    )
    recipients = result.scalars().all()
    if not recipients:
        return
    terminal = {"sent", "delivered", "read", "opted_out"}
    all_terminal_or_exhausted = all(
        r.status in terminal or (r.status == "failed" and r.retry_count >= r.max_retries)
        for r in recipients
    )
    if all_terminal_or_exhausted and campaign.status == "active":
        campaign.status = "completed"
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Delivery / read status callbacks — called from the WhatsApp webhook's
# `statuses` handling (additive addition to api/v1/whatsapp.py; the inbound
# `messages` handling / Workflow Runtime call there is untouched)
# ─────────────────────────────────────────────────────────────────────────────

async def record_delivery_status(db: AsyncSession, provider_message_id: str, status: str, error: Optional[str] = None) -> None:
    """status: 'sent' | 'delivered' | 'read' | 'failed' (Meta's message status webhook values)."""
    result = await db.execute(
        select(CampaignRecipient).where(CampaignRecipient.provider_message_id == provider_message_id)
    )
    recipient = result.scalar_one_or_none()
    if not recipient:
        return  # not a campaign message (e.g. a normal AI reply) — nothing to track here

    campaign_result = await db.execute(select(Campaign).where(Campaign.id == recipient.campaign_id))
    campaign = campaign_result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if status == "delivered" and recipient.status not in ("delivered", "read"):
        recipient.status = "delivered"
        recipient.delivered_at = now
        if campaign:
            campaign.delivered_count = (campaign.delivered_count or 0) + 1
    elif status == "read":
        if recipient.status != "read":
            recipient.status = "read"
            recipient.read_at = now
            recipient.opened = True
    elif status == "failed":
        recipient.status = "failed"
        recipient.error_message = (error or "Delivery failed")[:2000]
        recipient.retry_count += 1
        if campaign:
            campaign.failed_count = (campaign.failed_count or 0) + 1

    recipient.updated_at = now


# ─────────────────────────────────────────────────────────────────────────────
# Auto-reply hooks — called from receive_webhook() in api/v1/whatsapp.py,
# around its existing, unmodified WorkflowRunner.run() call
# ─────────────────────────────────────────────────────────────────────────────

async def find_recipient_by_session(db: AsyncSession, session_id: str) -> Optional[CampaignRecipient]:
    result = await db.execute(
        select(CampaignRecipient).where(CampaignRecipient.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def record_reply_outcome(
    db: AsyncSession, recipient: CampaignRecipient, context: ExecutionContext, turn_error: bool,
) -> None:
    """Called after the (unmodified) Workflow Runtime finishes a turn for a
    campaign recipient's session. Updates the campaign's Replied / AI
    Resolved counters. Escalated is driven separately by human takeover
    (see set_human_takeover) since that's the one unambiguous signal that
    a human, not the AI, is now handling the conversation."""
    now = datetime.now(timezone.utc)
    campaign_result = await db.execute(select(Campaign).where(Campaign.id == recipient.campaign_id))
    campaign = campaign_result.scalar_one_or_none()

    if not recipient.replied:
        recipient.replied = True
        recipient.replied_at = now
        if campaign:
            campaign.replied_count = (campaign.replied_count or 0) + 1

    if not turn_error and context.completed and not recipient.escalated:
        recipient.ai_resolved = True

    recipient.updated_at = now


async def set_human_takeover(db: AsyncSession, recipient: CampaignRecipient, enabled: bool) -> None:
    recipient.human_takeover = enabled
    if enabled:
        recipient.escalated = True
        recipient.ai_resolved = False
    recipient.updated_at = datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler — polls for due "scheduled" campaigns. Started as an in-process
# asyncio task from main.py's existing lifespan (additive: one new
# background task, does not change any existing startup behavior).
# ─────────────────────────────────────────────────────────────────────────────

SCHEDULER_POLL_SECONDS = 60


async def run_scheduler_loop() -> None:
    import asyncio
    logger.info("Campaign scheduler loop started")
    while True:
        try:
            await _dispatch_due_scheduled_campaigns()
        except Exception as e:  # noqa: BLE001 — the loop must never die
            logger.error(f"Campaign scheduler tick failed: {e}", exc_info=True)
        await asyncio.sleep(SCHEDULER_POLL_SECONDS)


async def _dispatch_due_scheduled_campaigns() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Campaign).where(
                Campaign.status == "scheduled",
                Campaign.schedule_type == "later",
                Campaign.scheduled_at <= now,
            )
        )
        due = result.scalars().all()
        due_ids = [c.id for c in due]

    for campaign_id in due_ids:
        try:
            await dispatch_campaign(campaign_id)
        except DispatchError as e:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
                campaign = result.scalar_one_or_none()
                if campaign:
                    db.add(CampaignHistoryEntry(
                        campaign_id=campaign.id, user_id=campaign.user_id,
                        event_type="dispatch_failed", detail={"error": str(e)},
                    ))
                    await db.commit()
            logger.warning(f"Scheduled campaign {campaign_id} failed to dispatch: {e}")
