"""
ThunderBots Owner Assistant — Part 2 (Campaign QR Marketing System)
NEW.

Lets a business owner control their campaigns conversationally from
Telegram or WhatsApp, without opening the dashboard. This module is the
ONLY place command text is interpreted — there is exactly one parser (the
AI-driven `classify_intent` below, with a small deterministic fallback for
when the AI provider is unavailable) and exactly one place a campaign is
actually sent (app.services.campaign_dispatch_service.dispatch_campaign,
imported and called here, never re-implemented).

Everything this module does is a thin orchestration layer over already-
existing services/models:
    - AI Agent            -> app.services.ai_engine (same provider-resolution
                              chain as api/v1/campaigns.py's ai/generate and
                              ai/improve endpoints)
    - Campaign Engine      -> app.models.campaign / campaign_broadcast +
                              app.services.campaign_dispatch_service
    - QR system             -> app.models.campaign_qr + the exact same
                              helpers api/v1/campaigns.py uses to create/
                              serialize a QR code (imported from there, not
                              duplicated)
    - Analytics            -> app.services.analytics_service
    - Live Agent / Workflow Runtime / Knowledge Base / Memory are untouched
      — the Owner Assistant never runs a workflow or talks to a customer;
      it only reads/writes Campaign-related rows for the OWNER's account.

Routing into this module happens in api/v1/telegram.py and api/v1/
whatsapp.py's existing webhook handlers: a very small, additive check right
after their existing subscriber/contact bookkeeping (chat_id has an active
OwnerAssistantLink row?) — if so, this module's `handle_owner_message` runs
INSTEAD OF the Workflow Runtime for that turn and the function returns
early. Every other inbound message on every channel is completely
unaffected; nothing here can break an existing customer chat flow.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import CacheService
from app.models.user import User
from app.models.campaign import Campaign, CampaignHistoryEntry
from app.models.campaign_broadcast import CampaignRecipient
from app.models.campaign_qr import CampaignQRCode
from app.models.telegram import TelegramChannel, TelegramSubscriber
from app.models.whatsapp import WhatsAppChannel, WhatsAppContact
from app.models.workflow import Workflow
from app.models.owner_assistant import OwnerAssistantLink
from app.services import analytics_service
from app.services import campaign_dispatch_service as campaign_dispatch
from app.services.ai_engine import (
    ProviderError,
    ai_engine,
    get_provider_for_user,
    resolve_agent_provider,
    validate_model_for_provider,
)

logger = logging.getLogger(__name__)

PENDING_TTL_SECONDS = 1800  # 30 minutes to reply YES/EDIT/SCHEDULE/CANCEL


def _pending_key(user_id: str) -> str:
    return f"owner_assistant:pending:{user_id}"


# ── Intent vocabulary (single source of truth for the AI classifier AND the
# deterministic fallback below — no second/competing parser) ────────────────
INTENTS = (
    "generate_qr", "show_qr", "download_qr",
    "campaign_status", "pause_campaign", "resume_campaign", "stop_campaign",
    "todays_analytics", "subscribers", "todays_new_customers",
    "send_offer", "generate_broadcast", "schedule_campaign",
    "show_failed_messages", "retry_failed",
    "help", "unknown",
)

_CLASSIFIER_SYSTEM_PROMPT = f"""You are the intent-classification layer for ThunderBots' Owner Assistant,
a chat control-panel that lets a business owner manage marketing campaigns
by texting their own bot. Classify the owner's message into exactly one of
these intents: {", ".join(INTENTS)}.

- "send_offer" and "generate_broadcast" both mean the owner wants a new
  marketing/broadcast message drafted and sent — treat them the same way.
- "schedule_campaign" means the owner wants a broadcast drafted but sent
  later rather than now.
- "stop_campaign" means permanently cancel; "pause_campaign" means
  temporarily halt; "resume_campaign" means un-pause.
- If the owner names a specific campaign, extract it in "campaign_name".
- If the owner mentions a QR placement (shop entrance, cash counter,
  product packaging, bills, visiting card, posters, menu, website), extract
  it in "placement" using one of those exact lowercase-with-underscores
  values, else null.
- "instructions" should be the owner's raw marketing intent/instructions
  when the intent is send_offer/generate_broadcast/schedule_campaign
  (e.g. what the offer is about), else null.

Respond with ONLY a single JSON object, no prose, no markdown fences:
{{"intent": "...", "campaign_name": "...|null", "placement": "...|null", "instructions": "...|null"}}
"""

# Deterministic fallback — used only if the AI provider call itself fails
# (no key configured, provider outage, etc.) so the Owner Assistant degrades
# gracefully instead of going silent. This is NOT a second command parser;
# it is a safety net covering the exact same intent vocabulary above.
_FALLBACK_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("generate_qr", re.compile(r"\b(generate|create|make|new)\b.*\bqr\b", re.I)),
    ("download_qr", re.compile(r"\bdownload\b.*\bqr\b", re.I)),
    ("show_qr", re.compile(r"\b(show|view|see)\b.*\bqr\b", re.I)),
    ("campaign_status", re.compile(r"\bcampaign\b.*\bstatus\b|\bstatus\b.*\bcampaign\b", re.I)),
    ("pause_campaign", re.compile(r"\bpause\b", re.I)),
    ("resume_campaign", re.compile(r"\bresume\b|\bunpause\b|\bcontinue\b.*\bcampaign\b", re.I)),
    ("stop_campaign", re.compile(r"\bstop\b|\bcancel\b.*\bcampaign\b", re.I)),
    ("todays_analytics", re.compile(r"\banalytics\b|\bstats?\b|\bperformance\b", re.I)),
    ("todays_new_customers", re.compile(r"\bnew\s+customers?\b|\bnew\s+leads?\b", re.I)),
    ("subscribers", re.compile(r"\bsubscribers?\b|\bcontacts?\b|\baudience\s+size\b", re.I)),
    ("show_failed_messages", re.compile(r"\bfailed\b", re.I)),
    ("retry_failed", re.compile(r"\bretry\b", re.I)),
    ("schedule_campaign", re.compile(r"\bschedule\b", re.I)),
    ("send_offer", re.compile(r"\boffer\b|\bbroadcast\b|\bpromo(tion)?\b|\bsend\b.*\ball\b", re.I)),
    ("generate_broadcast", re.compile(r"\bgenerate\b.*\b(broadcast|campaign|message)\b", re.I)),
    ("help", re.compile(r"\bhelp\b|\bcommands?\b|\bwhat can you do\b", re.I)),
]


async def classify_intent(user_id: str, text: str) -> dict:
    try:
        provider_id = await resolve_agent_provider(None, user_id)
        raw = await ai_engine.complete(
            provider=provider_id,
            system_prompt=_CLASSIFIER_SYSTEM_PROMPT,
            instructions="",
            messages=[{"role": "user", "content": text}],
            context={},
            temperature=0.0,
            max_tokens=250,
            user_id=user_id,
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned[4:] if cleaned.lower().startswith("json") else cleaned
        data = json.loads(cleaned)
        intent = data.get("intent") if data.get("intent") in INTENTS else "unknown"
        return {
            "intent": intent,
            "campaign_name": data.get("campaign_name") or None,
            "placement": data.get("placement") or None,
            "instructions": data.get("instructions") or text,
        }
    except Exception as e:  # noqa: BLE001 — classification must never crash the webhook
        logger.warning(f"Owner Assistant AI intent classification failed, using fallback: {e}")
        for intent, pattern in _FALLBACK_PATTERNS:
            if pattern.search(text or ""):
                return {"intent": intent, "campaign_name": None, "placement": None, "instructions": text}
        return {"intent": "unknown", "campaign_name": None, "placement": None, "instructions": text}


# ── Pending confirmation state (YES / EDIT / SCHEDULE / CANCEL flow) ────────

async def _get_pending(cache: CacheService, user_id: str) -> Optional[dict]:
    return await cache.get(_pending_key(user_id))


async def _set_pending(cache: CacheService, user_id: str, data: dict) -> None:
    await cache.set(_pending_key(user_id), data, ttl=PENDING_TTL_SECONDS)


async def _clear_pending(cache: CacheService, user_id: str) -> None:
    await cache.delete(_pending_key(user_id))


_CONFIRM_WORDS = {"yes", "y", "confirm", "approve", "send it", "go", "ok", "okay"}
_EDIT_WORDS = {"edit", "change", "revise", "modify"}
_SCHEDULE_WORDS = {"schedule", "later", "delay"}
_CANCEL_WORDS = {"cancel", "no", "stop", "abort", "discard"}


def _classify_confirmation_word(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    if t in _CONFIRM_WORDS:
        return "yes"
    if t in _EDIT_WORDS:
        return "edit"
    if t in _SCHEDULE_WORDS:
        return "schedule"
    if t in _CANCEL_WORDS:
        return "cancel"
    return None


# ── Small stdlib-only time parser for SCHEDULE step (no new dependency) ─────
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)


def _parse_schedule_time(text: str) -> Optional[datetime]:
    t = (text or "").strip().lower()
    now = datetime.now(timezone.utc)

    in_match = re.search(r"in\s+(\d+)\s*(minute|hour)s?", t)
    if in_match:
        qty = int(in_match.group(1))
        delta = timedelta(minutes=qty) if in_match.group(2) == "minute" else timedelta(hours=qty)
        return now + delta

    base_day = now
    if "tomorrow" in t:
        base_day = now + timedelta(days=1)

    m = _TIME_RE.search(t)
    if not m:
        return base_day.replace(hour=9, minute=0, second=0, microsecond=0) if "tomorrow" in t else None

    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    candidate = base_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now and "tomorrow" not in t:
        candidate += timedelta(days=1)
    return candidate


# ── Owned-resource helpers ───────────────────────────────────────────────────

async def _connected_channels(db: AsyncSession, user_id: str) -> list[dict]:
    out: list[dict] = []
    tg = await db.execute(
        select(TelegramChannel, Workflow.name)
        .join(Workflow, Workflow.id == TelegramChannel.workflow_id)
        .where(TelegramChannel.user_id == user_id)
    )
    for ch, wf_name in tg.all():
        out.append({
            "workflow_id": ch.workflow_id, "channel": "telegram", "bot_name": wf_name,
            "connected": bool(ch.is_enabled and ch.status == "connected" and ch.bot_username),
        })
    wa = await db.execute(
        select(WhatsAppChannel, Workflow.name)
        .join(Workflow, Workflow.id == WhatsAppChannel.workflow_id)
        .where(WhatsAppChannel.user_id == user_id)
    )
    for ch, wf_name in wa.all():
        out.append({
            "workflow_id": ch.workflow_id, "channel": "whatsapp", "bot_name": wf_name,
            "connected": bool(ch.is_enabled and ch.status == "connected" and ch.display_phone_number),
        })
    return out


async def _most_recent_campaign(
    db: AsyncSession, user_id: str, statuses: tuple[str, ...], name_hint: Optional[str] = None
) -> Optional[Campaign]:
    query = select(Campaign).where(Campaign.user_id == user_id, Campaign.status.in_(statuses))
    if name_hint:
        query = query.where(func.lower(Campaign.name).contains(name_hint.lower()))
    query = query.order_by(Campaign.updated_at.desc()).limit(1)
    return (await db.execute(query)).scalar_one_or_none()


async def _log_history(db: AsyncSession, campaign_id: str, user_id: str, event_type: str, detail: Optional[dict] = None) -> None:
    db.add(CampaignHistoryEntry(
        id=str(uuid.uuid4()), campaign_id=campaign_id, user_id=user_id,
        event_type=event_type, detail=detail or {"via": "owner_assistant"},
    ))


# ── Command implementations ─────────────────────────────────────────────────

async def _cmd_generate_qr(db: AsyncSession, user: User, default_workflow_id: Optional[str], placement: Optional[str]) -> str:
    # Local imports avoid a circular import (api/v1/campaigns.py imports
    # nothing from this module) while reusing its exact QR helpers instead
    # of re-implementing short-code generation / serialization.
    from app.api.v1.campaigns import (
        _generate_qr_short_code, _get_qr_channel_connection, _qr_redirect_url, VALID_QR_PLACEMENTS,
    )

    channels = [c for c in await _connected_channels(db, user.id) if c["connected"]]
    if not channels:
        return "You don't have any connected Telegram or WhatsApp bot yet, so I can't generate a QR code. Connect one from the dashboard first."

    target = next((c for c in channels if c["workflow_id"] == default_workflow_id), channels[0])
    placement_value = (placement or "other").strip().lower()
    if placement_value not in VALID_QR_PLACEMENTS:
        placement_value = "other"

    is_connected, _ = await _get_qr_channel_connection(db, target["workflow_id"], target["channel"])
    if not is_connected:
        return f"Your {target['channel'].capitalize()} bot isn't fully connected yet — please finish connecting it from the dashboard first."

    qr = CampaignQRCode(
        user_id=user.id, workflow_id=target["workflow_id"], channel=target["channel"],
        placement=placement_value, short_code=_generate_qr_short_code(),
    )
    db.add(qr)
    await db.commit()
    await db.refresh(qr)
    link = _qr_redirect_url(qr.short_code)
    return (
        f"✅ New QR code generated for {target['bot_name']} ({target['channel'].capitalize()}), "
        f"placement: {placement_value.replace('_', ' ')}.\nLink: {link}\n\n"
        f"Open the Campaigns → QR Marketing page in your dashboard to view/print the QR image."
    )


async def _cmd_show_qr(db: AsyncSession, user: User) -> str:
    result = await db.execute(
        select(CampaignQRCode).where(CampaignQRCode.user_id == user.id, CampaignQRCode.is_active.is_(True))
        .order_by(CampaignQRCode.created_at.desc()).limit(5)
    )
    from app.api.v1.campaigns import _qr_redirect_url
    codes = result.scalars().all()
    if not codes:
        return "You don't have any QR codes yet. Say \"Generate QR\" to create one."
    lines = ["Your most recent QR codes:"]
    for qr in codes:
        lines.append(
            f"• {qr.channel.capitalize()} / {qr.placement.replace('_', ' ')} — "
            f"{qr.scan_count} scans — {_qr_redirect_url(qr.short_code)}"
        )
    return "\n".join(lines)


async def _cmd_download_qr(db: AsyncSession, user: User) -> str:
    result = await db.execute(
        select(CampaignQRCode).where(CampaignQRCode.user_id == user.id, CampaignQRCode.is_active.is_(True))
        .order_by(CampaignQRCode.created_at.desc()).limit(1)
    )
    qr = result.scalar_one_or_none()
    if not qr:
        return "You don't have any QR codes yet. Say \"Generate QR\" to create one."
    from app.api.v1.campaigns import _qr_redirect_url
    return (
        f"Here's your latest QR code link — open it on the dashboard's Campaigns → QR Marketing "
        f"page to download the printable image:\n{_qr_redirect_url(qr.short_code)}"
    )


async def _cmd_campaign_status(db: AsyncSession, user: User, name_hint: Optional[str]) -> str:
    query = select(Campaign).where(Campaign.user_id == user.id)
    if name_hint:
        query = query.where(func.lower(Campaign.name).contains(name_hint.lower()))
    query = query.order_by(Campaign.updated_at.desc()).limit(5)
    campaigns = (await db.execute(query)).scalars().all()
    if not campaigns:
        return "You don't have any campaigns yet."
    lines = ["Campaign status:"]
    for c in campaigns:
        lines.append(
            f"• {c.name} — {c.status} — sent {c.sent_count}, delivered {c.delivered_count}, "
            f"failed {c.failed_count}, replied {c.replied_count}"
        )
    return "\n".join(lines)


async def _cmd_set_status(db: AsyncSession, user: User, name_hint: Optional[str], action: str) -> str:
    if action == "pause":
        campaign = await _most_recent_campaign(db, user.id, ("active", "scheduled"), name_hint)
        if not campaign:
            return "I couldn't find an active or scheduled campaign to pause."
        campaign.status = "paused"
        await _log_history(db, campaign.id, user.id, "paused")
        await db.commit()
        return f"⏸️ Paused campaign \"{campaign.name}\"."

    if action == "resume":
        campaign = await _most_recent_campaign(db, user.id, ("paused",), name_hint)
        if not campaign:
            return "I couldn't find a paused campaign to resume."
        if campaign.schedule_type == "later" and campaign.scheduled_at and campaign.scheduled_at > datetime.now(timezone.utc):
            campaign.status = "scheduled"
        else:
            campaign.status = "active"
        await _log_history(db, campaign.id, user.id, "resumed", {"status": campaign.status})
        await db.commit()
        if campaign.status == "active":
            try:
                await campaign_dispatch.dispatch_campaign(campaign.id)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Owner Assistant resume-dispatch failed: {e}")
        return f"▶️ Resumed campaign \"{campaign.name}\"."

    if action == "stop":
        campaign = await _most_recent_campaign(db, user.id, ("active", "scheduled", "paused"), name_hint)
        if not campaign:
            return "I couldn't find a running campaign to stop."
        campaign.status = "cancelled"
        await _log_history(db, campaign.id, user.id, "status_change", {"status": "cancelled"})
        await db.commit()
        return f"🛑 Stopped campaign \"{campaign.name}\"."

    return "I didn't understand that campaign action."


async def _cmd_todays_analytics(db: AsyncSession, user: User) -> str:
    overview = await analytics_service.get_overview(db, user.id, range_key="today")
    return (
        "Today's analytics:\n"
        f"• Conversations: {overview['total_conversations']}\n"
        f"• Messages: {overview['total_messages']}\n"
        f"• Active users: {overview['active_users']}\n"
        f"• Avg response time: {overview['avg_response_time_ms']} ms\n"
        f"• Avg satisfaction: {overview['avg_satisfaction'] if overview['avg_satisfaction'] is not None else 'n/a'}"
    )


async def _cmd_subscribers(db: AsyncSession, user: User) -> str:
    tg_count = (await db.execute(
        select(func.count(TelegramSubscriber.id))
        .join(TelegramChannel, TelegramChannel.id == TelegramSubscriber.channel_id)
        .where(TelegramChannel.user_id == user.id, TelegramSubscriber.is_subscribed.is_(True))
    )).scalar() or 0
    wa_count = (await db.execute(
        select(func.count(WhatsAppContact.id))
        .join(WhatsAppChannel, WhatsAppChannel.id == WhatsAppContact.channel_id)
        .where(WhatsAppChannel.user_id == user.id)
    )).scalar() or 0
    return f"Subscribers:\n• Telegram: {tg_count}\n• WhatsApp: {wa_count}\n• Total: {tg_count + wa_count}"


async def _cmd_todays_new_customers(db: AsyncSession, user: User) -> str:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tg_count = (await db.execute(
        select(func.count(TelegramSubscriber.id))
        .join(TelegramChannel, TelegramChannel.id == TelegramSubscriber.channel_id)
        .where(TelegramChannel.user_id == user.id, TelegramSubscriber.subscribed_at >= start)
    )).scalar() or 0
    wa_count = (await db.execute(
        select(func.count(WhatsAppContact.id))
        .join(WhatsAppChannel, WhatsAppChannel.id == WhatsAppContact.channel_id)
        .where(WhatsAppChannel.user_id == user.id, WhatsAppContact.created_at >= start)
    )).scalar() or 0
    total = tg_count + wa_count
    if total == 0:
        return "No new customers yet today."
    return f"Today's new customers: {total}\n• Telegram: {tg_count}\n• WhatsApp: {wa_count}"


async def _cmd_show_failed_messages(db: AsyncSession, user: User, name_hint: Optional[str]) -> str:
    campaign = await _most_recent_campaign(db, user.id, ("active", "paused", "completed", "scheduled"), name_hint)
    if not campaign:
        return "I couldn't find a campaign with failed messages."
    result = await db.execute(
        select(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "failed")
        .order_by(CampaignRecipient.updated_at.desc()).limit(10)
    )
    failed = result.scalars().all()
    if not failed:
        return f"No failed messages for \"{campaign.name}\"."
    lines = [f"Failed messages for \"{campaign.name}\" ({campaign.failed_count} total):"]
    for r in failed:
        lines.append(f"• {r.contact_name or r.contact_identifier}: {r.error_message or 'unknown error'}")
    lines.append("\nSay \"Retry Failed\" to retry them.")
    return "\n".join(lines)


async def _cmd_retry_failed(db: AsyncSession, user: User, name_hint: Optional[str]) -> str:
    campaign = await _most_recent_campaign(db, user.id, ("active", "paused", "completed", "scheduled"), name_hint)
    if not campaign:
        return "I couldn't find a campaign with failed messages to retry."
    try:
        result = await campaign_dispatch.retry_failed_recipients(campaign.id)
    except campaign_dispatch.DispatchError as e:
        return f"Couldn't retry: {e}"
    return f"🔁 Retrying failed messages for \"{campaign.name}\": {result}"


async def _generate_offer_message(user_id: str, instructions: str, channel: str) -> str:
    system_prompt = (
        "You are an expert marketing copywriter helping a small business "
        f"write a {channel} broadcast campaign message from scratch. "
        "Write a concise, on-brand, persuasive message based on the "
        "owner's instructions. You may use the personalization variables "
        "{{name}}, {{city}}, and {{company}} where they'd naturally improve "
        "the message — don't force them in if they don't fit. Return ONLY "
        "the message text — no preamble, no quotes, no explanation."
    )
    provider_id = await resolve_agent_provider(None, user_id)
    llm = await get_provider_for_user(provider_id, user_id)
    model, _ = validate_model_for_provider(provider_id, None)
    generated = await llm.complete(
        system=system_prompt,
        messages=[{"role": "user", "content": instructions or "A friendly promotional offer for our customers."}],
        temperature=0.8, max_tokens=600, model=model,
    )
    return (generated or "").strip()


async def _cmd_draft_broadcast(
    db: AsyncSession, cache: CacheService, user: User, workflow_id: Optional[str],
    channel_default: str, instructions: str, schedule_hint: bool,
) -> str:
    try:
        message = await _generate_offer_message(user.id, instructions, channel_default)
    except ProviderError as e:
        return f"I couldn't generate a message right now ({e}). Please configure an AI provider in Settings and try again."
    except Exception as e:  # noqa: BLE001
        logger.error(f"Owner Assistant broadcast generation failed: {e}", exc_info=True)
        return "Sorry, I couldn't generate a campaign message right now — please try again shortly."

    if not message:
        return "I couldn't generate a campaign message from that — could you describe the offer in a bit more detail?"

    await _set_pending(cache, user.id, {
        "stage": "awaiting_schedule_time" if schedule_hint else "awaiting_confirmation",
        "message": message,
        "instructions": instructions,
        "workflow_id": workflow_id,
        "channel": channel_default,
    })

    if schedule_hint:
        return (
            f"Here's the draft:\n\n\"{message}\"\n\n"
            f"When should I send it? (e.g. \"tomorrow 9am\", \"in 2 hours\")"
        )

    return (
        f"Here's the campaign message I drafted:\n\n\"{message}\"\n\n"
        f"Reply YES to send now, EDIT to revise it, SCHEDULE to send later, or CANCEL."
    )


async def _launch_broadcast_campaign(db: AsyncSession, user: User, pending: dict, scheduled_at: Optional[datetime]) -> Campaign:
    channel = pending.get("channel") or "whatsapp"
    schedule_type = "later" if scheduled_at else "now"
    status_value = "scheduled" if scheduled_at else "active"
    campaign = Campaign(
        id=str(uuid.uuid4()), user_id=user.id, workflow_id=pending.get("workflow_id"),
        name=f"Owner Assistant Broadcast {datetime.now(timezone.utc):%Y-%m-%d %H:%M}",
        channel=channel, template="custom", message=pending["message"],
        ai_prompt=pending.get("instructions"), audience_type="contacts", audience_config={},
        schedule_type=schedule_type, scheduled_at=scheduled_at, status=status_value,
    )
    db.add(campaign)
    await db.flush()
    await _log_history(db, campaign.id, user.id, "created", {"via": "owner_assistant", "status": status_value})
    await db.commit()
    await db.refresh(campaign)

    if status_value == "active":
        try:
            await campaign_dispatch.dispatch_campaign(campaign.id)
        except Exception as e:  # noqa: BLE001 — dispatch failure must not break the assistant reply
            logger.error(f"Owner Assistant dispatch failed for campaign={campaign.id}: {e}", exc_info=True)
    return campaign


async def _handle_pending_reply(
    db: AsyncSession, cache: CacheService, user: User, pending: dict, text: str,
) -> str:
    stage = pending.get("stage")

    if stage == "awaiting_confirmation":
        word = _classify_confirmation_word(text)
        if word == "yes":
            campaign = await _launch_broadcast_campaign(db, user, pending, None)
            await _clear_pending(cache, user.id)
            return f"🚀 Campaign \"{campaign.name}\" is sending now to your opted-in contacts."
        if word == "edit":
            pending["stage"] = "awaiting_edit_instructions"
            await _set_pending(cache, user.id, pending)
            return "Sure — what would you like to change about the message?"
        if word == "schedule":
            pending["stage"] = "awaiting_schedule_time"
            await _set_pending(cache, user.id, pending)
            return "When should I send it? (e.g. \"tomorrow 9am\", \"in 2 hours\")"
        if word == "cancel":
            await _clear_pending(cache, user.id)
            return "Cancelled — the draft was discarded."
        return (
            f"Here's the draft again:\n\n\"{pending['message']}\"\n\n"
            f"Reply YES to send now, EDIT to revise it, SCHEDULE to send later, or CANCEL."
        )

    if stage == "awaiting_edit_instructions":
        combined = f"Previous draft: {pending['message']}\n\nRequested change: {text}"
        try:
            new_message = await _generate_offer_message(user.id, combined, pending.get("channel") or "whatsapp")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Owner Assistant edit generation failed: {e}", exc_info=True)
            return "Sorry, I couldn't apply that edit right now — please try again."
        pending["message"] = new_message or pending["message"]
        pending["stage"] = "awaiting_confirmation"
        await _set_pending(cache, user.id, pending)
        return (
            f"Updated draft:\n\n\"{pending['message']}\"\n\n"
            f"Reply YES to send now, EDIT to revise it again, SCHEDULE to send later, or CANCEL."
        )

    if stage == "awaiting_schedule_time":
        if _classify_confirmation_word(text) == "cancel":
            await _clear_pending(cache, user.id)
            return "Cancelled — the draft was discarded."
        when = _parse_schedule_time(text)
        if not when:
            return "I couldn't understand that time — try something like \"tomorrow 9am\" or \"in 2 hours\", or say CANCEL."
        campaign = await _launch_broadcast_campaign(db, user, pending, when)
        await _clear_pending(cache, user.id)
        return f"🗓️ Campaign \"{campaign.name}\" is scheduled for {when.strftime('%b %d, %Y %H:%M UTC')}."

    await _clear_pending(cache, user.id)
    return "Let's start over — what would you like to do?"


# ── Linking handshake — shared by api/v1/telegram.py and api/v1/whatsapp.py
# webhooks so the "/assistant <code>" flow is implemented exactly once ──────
_LINK_COMMAND_RE = re.compile(r"^/assistant\s+([A-Za-z0-9]{6,12})$")


def is_link_command(text: str) -> bool:
    return bool(_LINK_COMMAND_RE.match((text or "").strip()))


async def try_handle_link_command(
    db: AsyncSession, channel: str, chat_id: str, workflow_owner_id: str,
    workflow_id: Optional[str], text: str,
) -> Optional[str]:
    """If `text` is a valid "/assistant <code>" link command, validates the
    code (issued by POST /api/v1/assistant/link-code) and creates/reactivates
    the OwnerAssistantLink row for this chat_id. Returns the reply to send,
    or None if `text` isn't a link command at all (caller should fall
    through to normal handling)."""
    match = _LINK_COMMAND_RE.match((text or "").strip())
    if not match:
        return None

    from app.api.v1.assistant import _link_code_key  # local import avoids a circular import

    code = match.group(1).upper()
    cache = CacheService()
    payload = await cache.get(_link_code_key(code))
    if not payload or not payload.get("user_id"):
        return ("That link code is invalid or has expired. Generate a new one from the "
                "ThunderBots dashboard (Settings → Owner Assistant).")

    code_owner_id = payload["user_id"]
    if code_owner_id != workflow_owner_id:
        return "This bot doesn't belong to the account that generated that code. Open the code from the correct ThunderBots account."

    existing = await db.execute(
        select(OwnerAssistantLink).where(
            OwnerAssistantLink.channel == channel, OwnerAssistantLink.external_chat_id == chat_id
        )
    )
    link = existing.scalar_one_or_none()
    if link:
        link.user_id = code_owner_id
        link.workflow_id = workflow_id
        link.is_active = True
        link.last_used_at = datetime.now(timezone.utc)
    else:
        link = OwnerAssistantLink(
            user_id=code_owner_id, workflow_id=workflow_id, channel=channel,
            external_chat_id=chat_id, is_active=True, last_used_at=datetime.now(timezone.utc),
        )
        db.add(link)
    await db.commit()
    await cache.delete(_link_code_key(code))

    return (
        "✅ This chat is now linked as your Owner Assistant. You can control your campaigns "
        "here — try \"Campaign Status\" or \"Today's Analytics\". Say \"help\" any time for the full list."
    )


async def get_active_link(db: AsyncSession, channel: str, chat_id: str) -> Optional[OwnerAssistantLink]:
    result = await db.execute(
        select(OwnerAssistantLink).where(
            OwnerAssistantLink.channel == channel,
            OwnerAssistantLink.external_chat_id == chat_id,
            OwnerAssistantLink.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


HELP_TEXT = (
    "Here's what I can do:\n"
    "• Generate QR / Show QR / Download QR\n"
    "• Campaign Status / Pause Campaign / Resume Campaign / Stop Campaign\n"
    "• Today's Analytics / Subscribers / Today's New Customers\n"
    "• Send Offer / Generate Broadcast / Schedule Campaign\n"
    "• Show Failed Messages / Retry Failed\n\n"
    "Just tell me naturally, e.g. \"Send today's offer to all customers\"."
)


async def handle_owner_message(
    db: AsyncSession, user: User, channel: str, chat_id: str,
    workflow_id: Optional[str], text: str,
) -> str:
    """Single entry point called by the Telegram/WhatsApp webhooks once a
    chat_id is confirmed to be an active OwnerAssistantLink. Returns the
    reply text to send back on the same channel."""
    cache = CacheService()
    text = (text or "").strip()
    if not text:
        return HELP_TEXT

    pending = await _get_pending(cache, user.id)
    if pending:
        return await _handle_pending_reply(db, cache, user, pending, text)

    parsed = await classify_intent(user.id, text)
    intent = parsed["intent"]
    name_hint = parsed.get("campaign_name")
    placement = parsed.get("placement")
    instructions = parsed.get("instructions") or text

    if intent == "help":
        return HELP_TEXT
    if intent == "generate_qr":
        return await _cmd_generate_qr(db, user, workflow_id, placement)
    if intent == "show_qr":
        return await _cmd_show_qr(db, user)
    if intent == "download_qr":
        return await _cmd_download_qr(db, user)
    if intent == "campaign_status":
        return await _cmd_campaign_status(db, user, name_hint)
    if intent == "pause_campaign":
        return await _cmd_set_status(db, user, name_hint, "pause")
    if intent == "resume_campaign":
        return await _cmd_set_status(db, user, name_hint, "resume")
    if intent == "stop_campaign":
        return await _cmd_set_status(db, user, name_hint, "stop")
    if intent == "todays_analytics":
        return await _cmd_todays_analytics(db, user)
    if intent == "subscribers":
        return await _cmd_subscribers(db, user)
    if intent == "todays_new_customers":
        return await _cmd_todays_new_customers(db, user)
    if intent == "show_failed_messages":
        return await _cmd_show_failed_messages(db, user, name_hint)
    if intent == "retry_failed":
        return await _cmd_retry_failed(db, user, name_hint)
    if intent in ("send_offer", "generate_broadcast"):
        return await _cmd_draft_broadcast(db, cache, user, workflow_id, channel, instructions, schedule_hint=False)
    if intent == "schedule_campaign":
        return await _cmd_draft_broadcast(db, cache, user, workflow_id, channel, instructions, schedule_hint=True)

    return (
        "I didn't quite catch that. " + HELP_TEXT
    )
