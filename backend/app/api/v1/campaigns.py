"""
ThunderBots AI Campaign Manager API

Campaign CRUD/templates/AI-rewrite (unchanged from before), PLUS the AI
Broadcast & Auto-Reply Engine: launching a campaign now actually dispatches
messages (app.services.campaign_dispatch_service), and delivery/read
status, retries, human takeover, per-recipient conversation history, and
engine-level analytics (opened/replied/ai_resolved/escalated) are exposed
below. The AI Agent + Knowledge Base auto-reply behavior itself lives
entirely in the existing, unmodified Workflow Runtime — reached through the
existing WhatsApp webhook (app/api/v1/whatsapp.py), which this feature only
adds two small, additive hooks to (a human-takeover gate and outcome
tracking) around its untouched WorkflowRunner.run() call.

Does not modify app/engine (Workflow Engine / Runtime) or the Builder
frontend. The AI rewrite/improve feature reuses the EXISTING
provider-resolution helpers (resolve_agent_provider / get_provider_for_user)
the same way app/api/v1/thunderguide.py does — no new AI transport, no new
model list.
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, Integer, cast
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.config import settings
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.campaign import Campaign, CampaignHistoryEntry
from app.models.campaign_broadcast import CampaignRecipient
from app.models.campaign_qr import CampaignQRCode, CampaignQRScan, PLACEMENT_CHOICES, ACTIVE_QR_CHANNELS
from app.models.contact_group import ContactGroup, ContactGroupMember
from app.models.whatsapp import WhatsAppChannel, WhatsAppContact
from app.models.telegram import TelegramChannel, TelegramSubscriber
from app.models.workflow import Workflow
from app.models.analytics import Conversation
from app.services import audit_service
from app.services import analytics_service
from app.services import audience_service
from app.services import campaign_dispatch_service as campaign_dispatch
from app.services.totp_service import generate_qr_svg  # reused as-is, not modified
from app.services.ai_engine import (
    ProviderError,
    get_provider_for_user,
    resolve_agent_provider,
    validate_model_for_provider,
)

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_CHANNELS = {"whatsapp", "instagram", "telegram", "email"}
VALID_SCHEDULE_TYPES = {"now", "later"}
VALID_STATUSES = {"draft", "scheduled", "active", "paused", "completed", "cancelled"}

MAX_MESSAGE_LENGTH = 4000
MAX_AI_PROMPT_LENGTH = 2000

# ── QR Marketing System (NEW — Part 1) ───────────────────────────────────────
# Every connected channel gets its own QR "system"; Telegram/WhatsApp already
# have a real, scannable acquisition deep link (t.me/<bot>, wa.me/<phone>).
# Facebook/Instagram are listed so the frontend can render their card in the
# same grid, but are architecture-only until an equivalent deep link exists —
# no QR is ever generated for them in Part 1.
QR_ALL_CHANNELS = ("telegram", "whatsapp", "facebook", "instagram")
QR_ARCHITECTURE_ONLY_CHANNELS = {"facebook", "instagram"}
VALID_QR_PLACEMENTS = set(PLACEMENT_CHOICES)


# ── Templates (static, purely presentational starting points) ────────────────

CAMPAIGN_TEMPLATES = [
    {
        "id": "discount",
        "name": "Discount",
        "description": "Announce a limited-time discount to drive quick purchases.",
        "message": "🎉 Special offer just for you! Enjoy {discount}% off on {product} — "
                    "use code {code} at checkout. Offer valid until {end_date}.",
        "ai_prompt": "Rewrite this as an exciting, concise discount announcement that "
                     "creates urgency without sounding pushy.",
    },
    {
        "id": "festival_offer",
        "name": "Festival Offer",
        "description": "Seasonal/festival-themed promotion for your customers.",
        "message": "✨ Happy {festival}! Celebrate with us — get {discount}% off "
                    "storewide, only until {end_date}. Shop now and treat yourself!",
        "ai_prompt": "Rewrite this with a warm, festive tone appropriate for the occasion, "
                     "keeping it short and friendly.",
    },
    {
        "id": "new_product",
        "name": "New Product",
        "description": "Introduce a new product or service to your audience.",
        "message": "🚀 Introducing {product}! We just launched something new — "
                    "check it out and be among the first to try it.",
        "ai_prompt": "Rewrite this as an exciting product-launch announcement that "
                     "highlights what's new and why it matters.",
    },
    {
        "id": "reminder",
        "name": "Reminder",
        "description": "Gentle nudge for an upcoming appointment, cart, or renewal.",
        "message": "👋 Just a friendly reminder about {subject}. Let us know if you "
                    "have any questions — we're happy to help!",
        "ai_prompt": "Rewrite this as a polite, brief reminder that doesn't feel pushy.",
    },
    {
        "id": "announcement",
        "name": "Announcement",
        "description": "General business update or announcement.",
        "message": "📢 We have an update to share: {announcement}. Thank you for "
                    "being a valued customer!",
        "ai_prompt": "Rewrite this as a clear, professional announcement suitable for "
                     "all customers.",
    },
]


# ── Schemas ───────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel: str = Field(default="whatsapp")
    template: Optional[str] = None
    message: str = Field(default="", max_length=MAX_MESSAGE_LENGTH)
    ai_prompt: Optional[str] = Field(default=None, max_length=MAX_AI_PROMPT_LENGTH)
    # Audience Selection (Step 2 of the Campaign Flow) — see
    # app/services/audience_service.py for valid audience_type values and
    # the audience_config shape each expects.
    audience_type: str = Field(default="contacts")
    audience_config: dict = Field(default_factory=dict)
    schedule_type: str = Field(default="now")
    scheduled_at: Optional[datetime] = None
    # Which connected bot to send from. Optional — if omitted, dispatch
    # auto-resolves to the user's single connected+enabled WhatsApp channel.
    workflow_id: Optional[str] = None
    # If true, the campaign is saved as "scheduled"/"active" AND, for an
    # immediate ("now") campaign, dispatch is triggered right away.
    launch: bool = False


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    channel: Optional[str] = None
    template: Optional[str] = None
    message: Optional[str] = Field(None, max_length=MAX_MESSAGE_LENGTH)
    ai_prompt: Optional[str] = Field(None, max_length=MAX_AI_PROMPT_LENGTH)
    audience_type: Optional[str] = None
    audience_config: Optional[dict] = None
    schedule_type: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None
    workflow_id: Optional[str] = None


class TakeoverRequest(BaseModel):
    enabled: bool


class RetryRequest(BaseModel):
    recipient_ids: Optional[list[str]] = None


class AIImproveRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    ai_prompt: Optional[str] = Field(default=None, max_length=MAX_AI_PROMPT_LENGTH)
    channel: str = Field(default="whatsapp")
    campaign_id: Optional[str] = None


class AIImproveResponse(BaseModel):
    improved_message: str


class AIGenerateRequest(BaseModel):
    ai_prompt: str = Field(min_length=1, max_length=MAX_AI_PROMPT_LENGTH)
    channel: str = Field(default="whatsapp")


class AudienceResolveRequest(BaseModel):
    workflow_id: Optional[str] = None
    # NEW (Telegram Integration — Part 2): which opt-in source of truth to
    # resolve against — "whatsapp" (default, unchanged) or "telegram". See
    # app/services/audience_service.py.
    channel: str = Field(default="whatsapp")
    audience_type: str = Field(default="contacts")
    audience_config: dict = Field(default_factory=dict)
    message: Optional[str] = None  # when provided, sample entries include a rendered preview
    sample_size: int = Field(default=10, ge=1, le=50)


class AudienceEntryOut(BaseModel):
    identifier: str
    name: Optional[str] = None
    city: Optional[str] = None
    company: Optional[str] = None
    valid: bool = True
    reason: Optional[str] = None
    preview: Optional[str] = None


class AudienceResolveResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    duplicate: int
    sample: list[AudienceEntryOut]


class ContactGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    members: list[dict] = Field(default_factory=list)  # [{identifier|phone, name?, city?, company?}]


class AddGroupMembersRequest(BaseModel):
    members: list[dict] = Field(default_factory=list)


class QRCodeCreate(BaseModel):
    workflow_id: str
    channel: str
    placement: str = "other"
    label: Optional[str] = Field(default=None, max_length=120)


class CampaignsAnalyticsOverview(BaseModel):
    total_campaigns: int
    active_campaigns: int
    paused_campaigns: int
    draft_campaigns: int
    scheduled_campaigns: int
    completed_campaigns: int
    sent: int
    delivered: int
    failed: int
    replied: int
    opened: int = 0
    ai_resolved: int = 0
    escalated: int = 0
    # NEW (Campaign QR Marketing System — Part 3)
    subscribers: int = 0
    qr_scans: int = 0
    unique_qr_scans: int = 0
    conversion_rate: float = 0.0


class GrowthPoint(BaseModel):
    period: str  # ISO date (daily) / ISO week-start (weekly) / YYYY-MM (monthly)
    subscribers: int
    qr_scans: int
    sent: int


class GrowthResponse(BaseModel):
    range: str
    points: list[GrowthPoint]


class BroadcastHistoryEntry(BaseModel):
    id: str
    campaign_id: str
    campaign_name: str
    channel: str
    contact_identifier: str
    contact_name: Optional[str] = None
    status: str
    replied: bool
    ai_resolved: bool
    escalated: bool
    sent_at: Optional[str] = None
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_channel(channel: str) -> str:
    if channel not in VALID_CHANNELS:
        raise HTTPException(status_code=422, detail=f"Invalid channel. Must be one of: {', '.join(sorted(VALID_CHANNELS))}")
    return channel


def _validate_schedule_type(schedule_type: str) -> str:
    if schedule_type not in VALID_SCHEDULE_TYPES:
        raise HTTPException(status_code=422, detail="schedule_type must be 'now' or 'later'")
    return schedule_type


def _validate_audience_type(audience_type: str) -> str:
    if audience_type not in audience_service.AUDIENCE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid audience_type. Must be one of: {', '.join(sorted(audience_service.AUDIENCE_TYPES))}",
        )
    return audience_type


async def _get_owned_campaign(db: AsyncSession, campaign_id: str, user_id: str) -> Campaign:
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


async def _get_owned_workflow_or_404(db: AsyncSession, workflow_id: str, user_id: str) -> Workflow:
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="workflow_id does not refer to a bot you own")
    return workflow


async def _get_owned_group(db: AsyncSession, group_id: str, user_id: str) -> ContactGroup:
    result = await db.execute(
        select(ContactGroup).where(ContactGroup.id == group_id, ContactGroup.user_id == user_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Contact group not found")
    return group


def _add_group_members(group_id: str, members: list[dict], db: AsyncSession) -> None:
    for m in members:
        identifier = audience_service.normalize_phone(str(m.get("identifier") or m.get("phone") or ""))
        if not identifier:
            continue
        db.add(ContactGroupMember(
            id=str(uuid.uuid4()), group_id=group_id, wa_id=identifier,
            contact_name=m.get("name") or None, city=m.get("city") or None, company=m.get("company") or None,
        ))


def _serialize_campaign(c: Campaign) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "channel": c.channel,
        "template": c.template,
        "message": c.message or "",
        "ai_prompt": c.ai_prompt,
        "audience_type": c.audience_type or "contacts",
        "audience_config": c.audience_config or {},
        "schedule_type": c.schedule_type,
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "status": c.status,
        "workflow_id": c.workflow_id,
        "sent_count": c.sent_count or 0,
        "delivered_count": c.delivered_count or 0,
        "failed_count": c.failed_count or 0,
        "replied_count": c.replied_count or 0,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _serialize_recipient(r: CampaignRecipient) -> dict:
    return {
        "id": str(r.id),
        "campaign_id": str(r.campaign_id),
        "channel": r.channel,
        "contact_identifier": r.contact_identifier,
        "contact_name": r.contact_name,
        "status": r.status,
        "error_message": r.error_message,
        "retry_count": r.retry_count,
        "max_retries": r.max_retries,
        "opened": r.opened,
        "replied": r.replied,
        "ai_resolved": r.ai_resolved,
        "escalated": r.escalated,
        "human_takeover": r.human_takeover,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
        "read_at": r.read_at.isoformat() if r.read_at else None,
        "replied_at": r.replied_at.isoformat() if r.replied_at else None,
    }


async def _get_owned_recipient(db: AsyncSession, campaign_id: str, recipient_id: str, user_id: str) -> CampaignRecipient:
    result = await db.execute(
        select(CampaignRecipient).where(
            CampaignRecipient.id == recipient_id,
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.user_id == user_id,
        )
    )
    recipient = result.scalar_one_or_none()
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return recipient


def _serialize_history_entry(h: CampaignHistoryEntry) -> dict:
    return {
        "id": str(h.id),
        "event_type": h.event_type,
        "detail": h.detail or {},
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


async def _log_history(db: AsyncSession, campaign_id: str, user_id: str, event_type: str, detail: Optional[dict] = None):
    entry = CampaignHistoryEntry(
        id=str(uuid.uuid4()),
        campaign_id=campaign_id,
        user_id=user_id,
        event_type=event_type,
        detail=detail or {},
    )
    db.add(entry)


async def _dispatch_bg(campaign_id: str) -> None:
    """BackgroundTasks entrypoint — swallows DispatchError into campaign
    history instead of raising (there's no request/response left by the
    time a background task runs)."""
    try:
        await campaign_dispatch.dispatch_campaign(campaign_id)
    except campaign_dispatch.DispatchError as e:
        logger.warning(f"Campaign {campaign_id} dispatch failed: {e}")
        await _log_dispatch_failure(campaign_id, str(e))
    except Exception as e:  # noqa: BLE001 — background task must never crash the process
        logger.error(f"Campaign {campaign_id} dispatch raised unexpectedly: {e}", exc_info=True)
        await _log_dispatch_failure(campaign_id, str(e))


async def _log_dispatch_failure(campaign_id: str, error: str) -> None:
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if not campaign:
            return
        db.add(CampaignHistoryEntry(
            id=str(uuid.uuid4()), campaign_id=campaign.id, user_id=campaign.user_id,
            event_type="dispatch_failed", detail={"error": error},
        ))
        await db.commit()


# ── Templates ─────────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(current_user: User = Depends(get_current_user)):
    return CAMPAIGN_TEMPLATES


# ── Analytics overview (static route must be before /{campaign_id}) ──────────

@router.get("/analytics/overview", response_model=CampaignsAnalyticsOverview)
async def campaigns_analytics_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(
            func.count(Campaign.id),
            func.coalesce(func.sum(Campaign.sent_count), 0),
            func.coalesce(func.sum(Campaign.delivered_count), 0),
            func.coalesce(func.sum(Campaign.failed_count), 0),
            func.coalesce(func.sum(Campaign.replied_count), 0),
        ).where(Campaign.user_id == current_user.id)
    )
    total, sent, delivered, failed, replied = result.one()

    status_counts: dict[str, int] = {}
    status_result = await db.execute(
        select(Campaign.status, func.count(Campaign.id))
        .where(Campaign.user_id == current_user.id)
        .group_by(Campaign.status)
    )
    for status_value, count in status_result.all():
        status_counts[status_value] = count

    outcome_result = await db.execute(
        select(
            func.coalesce(func.sum(cast(CampaignRecipient.opened, Integer)), 0),
            func.coalesce(func.sum(cast(CampaignRecipient.ai_resolved, Integer)), 0),
            func.coalesce(func.sum(cast(CampaignRecipient.escalated, Integer)), 0),
        ).where(CampaignRecipient.user_id == current_user.id)
    )
    opened, ai_resolved, escalated = outcome_result.one()

    # NEW (Campaign QR Marketing System — Part 3): Subscribers = total
    # Telegram + WhatsApp subscribers/contacts across this user's connected
    # bots (read-only counts over the existing, unmodified tables — no new
    # subscriber logic). QR Scans / Unique QR Scans come from the additive
    # campaign_qr_scans log; Conversion Rate approximates "scans that turned
    # into a subscriber" via CampaignQRScan.converted (set by scan_qr_code's
    # best-effort attribution — see below).
    tg_sub_result = await db.execute(
        select(func.count(TelegramSubscriber.id))
        .join(TelegramChannel, TelegramChannel.id == TelegramSubscriber.channel_id)
        .where(TelegramChannel.user_id == current_user.id)
    )
    wa_sub_result = await db.execute(
        select(func.count(WhatsAppContact.id))
        .join(WhatsAppChannel, WhatsAppChannel.id == WhatsAppContact.channel_id)
        .where(WhatsAppChannel.user_id == current_user.id)
    )
    subscribers = (tg_sub_result.scalar_one() or 0) + (wa_sub_result.scalar_one() or 0)

    scans_result = await db.execute(
        select(
            func.count(CampaignQRScan.id),
            func.count(func.distinct(CampaignQRScan.visitor_hash)),
            func.coalesce(func.sum(cast(CampaignQRScan.converted, Integer)), 0),
        ).where(CampaignQRScan.user_id == current_user.id)
    )
    qr_scans, unique_qr_scans, converted_scans = scans_result.one()
    qr_scans = qr_scans or 0
    unique_qr_scans = unique_qr_scans or 0
    conversion_rate = round((converted_scans or 0) / unique_qr_scans * 100, 1) if unique_qr_scans else 0.0

    return CampaignsAnalyticsOverview(
        total_campaigns=total or 0,
        active_campaigns=status_counts.get("active", 0),
        paused_campaigns=status_counts.get("paused", 0),
        draft_campaigns=status_counts.get("draft", 0),
        scheduled_campaigns=status_counts.get("scheduled", 0),
        completed_campaigns=status_counts.get("completed", 0),
        sent=sent or 0,
        delivered=delivered or 0,
        failed=failed or 0,
        replied=replied or 0,
        opened=opened or 0,
        ai_resolved=ai_resolved or 0,
        escalated=escalated or 0,
        subscribers=subscribers,
        qr_scans=qr_scans,
        unique_qr_scans=unique_qr_scans,
        conversion_rate=conversion_rate,
    )


# ── Growth & Broadcast History (NEW — Part 3) ────────────────────────────────
# Static routes — MUST be registered before "/{campaign_id}" below.

def _period_bucket(dt: datetime, range_: str) -> str:
    if range_ == "monthly":
        return dt.strftime("%Y-%m")
    if range_ == "weekly":
        start = dt - timedelta(days=dt.weekday())
        return start.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d")


@router.get("/analytics/growth", response_model=GrowthResponse)
async def campaigns_analytics_growth(
    range: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Subscriber Growth + QR Scans + Sent, bucketed Daily/Weekly/Monthly, for
    the QR Marketing dashboard's growth chart. Read-only aggregation over
    existing subscriber tables plus the additive campaign_qr_scans /
    campaign_recipients logs — nothing here mutates state."""
    days_back = {"daily": 30, "weekly": 12 * 7, "monthly": 365}[range]
    since = datetime.now(timezone.utc) - timedelta(days=days_back)

    tg_rows = (await db.execute(
        select(TelegramSubscriber.created_at)
        .join(TelegramChannel, TelegramChannel.id == TelegramSubscriber.channel_id)
        .where(TelegramChannel.user_id == current_user.id, TelegramSubscriber.created_at >= since)
    )).scalars().all()
    wa_rows = (await db.execute(
        select(WhatsAppContact.created_at)
        .join(WhatsAppChannel, WhatsAppChannel.id == WhatsAppContact.channel_id)
        .where(WhatsAppChannel.user_id == current_user.id, WhatsAppContact.created_at >= since)
    )).scalars().all()
    scan_rows = (await db.execute(
        select(CampaignQRScan.created_at)
        .where(CampaignQRScan.user_id == current_user.id, CampaignQRScan.created_at >= since)
    )).scalars().all()
    sent_rows = (await db.execute(
        select(CampaignRecipient.sent_at)
        .where(
            CampaignRecipient.user_id == current_user.id,
            CampaignRecipient.sent_at.is_not(None),
            CampaignRecipient.sent_at >= since,
        )
    )).scalars().all()

    buckets: dict[str, dict[str, int]] = {}

    def _bump(dt: Optional[datetime], key: str) -> None:
        if not dt:
            return
        period = _period_bucket(dt, range)
        buckets.setdefault(period, {"subscribers": 0, "qr_scans": 0, "sent": 0})
        buckets[period][key] += 1

    for dt in tg_rows:
        _bump(dt, "subscribers")
    for dt in wa_rows:
        _bump(dt, "subscribers")
    for dt in scan_rows:
        _bump(dt, "qr_scans")
    for dt in sent_rows:
        _bump(dt, "sent")

    points = [
        GrowthPoint(period=period, **counts)
        for period, counts in sorted(buckets.items())
    ]
    return GrowthResponse(range=range, points=points)


@router.get("/analytics/broadcast-history", response_model=list[BroadcastHistoryEntry])
async def campaigns_broadcast_history(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recent sends across ALL campaigns (not scoped to one campaign like
    GET /{campaign_id}/recipients) for the QR Marketing dashboard's Broadcast
    History section. Read-only over the existing campaign_recipients ledger."""
    result = await db.execute(
        select(CampaignRecipient, Campaign.name)
        .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
        .where(CampaignRecipient.user_id == current_user.id, CampaignRecipient.sent_at.is_not(None))
        .order_by(CampaignRecipient.sent_at.desc())
        .limit(limit)
    )
    out = []
    for r, campaign_name in result.all():
        out.append(BroadcastHistoryEntry(
            id=r.id,
            campaign_id=r.campaign_id,
            campaign_name=campaign_name,
            channel=r.channel,
            contact_identifier=r.contact_identifier,
            contact_name=r.contact_name,
            status=r.status,
            replied=r.replied,
            ai_resolved=r.ai_resolved,
            escalated=r.escalated,
            sent_at=r.sent_at.isoformat() if r.sent_at else None,
            created_at=r.created_at.isoformat(),
        ))
    return out


def _render_preview(message: str, name: Optional[str], city: Optional[str], company: Optional[str]) -> str:
    values = {"name": name or "there", "city": city or "", "company": company or ""}
    text = message or ""
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
        text = text.replace("{{ " + key + " }}", val)
    return text.replace("{name}", values["name"])


# ── Audience Selection (Step 1 & 2 of the Campaign Flow) ─────────────────────
# Static routes — MUST be registered before "/{campaign_id}" below.

@router.get("/channels")
async def list_connected_channels(
    channel: str = Query("whatsapp"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connected accounts the user can launch a campaign from — Step 1 of
    the Campaign Flow. Reuses the existing WhatsAppChannel / TelegramChannel
    connections (app/api/v1/whatsapp.py, app/api/v1/telegram.py); read-only
    here. `channel` (NEW — Part 2) selects which connection type to list;
    defaults to "whatsapp" so existing callers are unaffected."""
    if channel == "telegram":
        result = await db.execute(
            select(TelegramChannel, Workflow.name)
            .join(Workflow, Workflow.id == TelegramChannel.workflow_id)
            .where(TelegramChannel.user_id == current_user.id)
        )
        rows = result.all()
        return [
            {
                "workflow_id": ch.workflow_id,
                "bot_name": wf_name,
                "display_phone_number": None,
                "bot_username": ch.bot_username,
                "verified_name": ch.bot_first_name,
                "status": ch.status,
                "is_enabled": ch.is_enabled,
            }
            for ch, wf_name in rows
        ]

    result = await db.execute(
        select(WhatsAppChannel, Workflow.name)
        .join(Workflow, Workflow.id == WhatsAppChannel.workflow_id)
        .where(WhatsAppChannel.user_id == current_user.id)
    )
    rows = result.all()
    return [
        {
            "workflow_id": ch.workflow_id,
            "bot_name": wf_name,
            "display_phone_number": ch.display_phone_number,
            "bot_username": None,
            "verified_name": ch.verified_name,
            "status": ch.status,
            "is_enabled": ch.is_enabled,
        }
        for ch, wf_name in rows
    ]


# ── QR Marketing System (NEW — Part 1) ───────────────────────────────────────
# Turns each already-connected channel into a scannable customer-acquisition
# QR code. Deliberately thin: it never touches contact/subscriber creation,
# the welcome workflow, or conversation history — those all already happen,
# unchanged, the moment a scanned link opens Telegram/WhatsApp and the
# customer presses START or sends "Hi" (app/api/v1/telegram.py::receive_webhook,
# app/api/v1/whatsapp.py's webhook). This block only generates/manages the
# QR image + the short, trackable redirect link a scan resolves through.

def _generate_qr_short_code() -> str:
    # Matches the entropy/convention of services/telegram_service.py's
    # webhook-secret generation — unguessable, URL-safe.
    return secrets.token_urlsafe(16)


async def _get_qr_channel_connection(
    db: AsyncSession, workflow_id: str, channel: str
) -> tuple[bool, Optional[str]]:
    """Returns (is_connected, deep_link_or_None) for a Telegram/WhatsApp
    channel already connected to workflow_id. Read-only over the existing
    TelegramChannel/WhatsAppChannel tables — no new connection logic."""
    if channel == "telegram":
        result = await db.execute(
            select(TelegramChannel).where(TelegramChannel.workflow_id == workflow_id)
        )
        ch = result.scalar_one_or_none()
        if not ch or not ch.bot_username:
            return False, None
        return bool(ch.is_enabled and ch.status == "connected"), f"https://t.me/{ch.bot_username}"

    if channel == "whatsapp":
        result = await db.execute(
            select(WhatsAppChannel).where(WhatsAppChannel.workflow_id == workflow_id)
        )
        ch = result.scalar_one_or_none()
        if not ch or not ch.display_phone_number:
            return False, None
        digits = "".join(c for c in ch.display_phone_number if c.isdigit())
        return bool(ch.is_enabled and ch.status == "connected"), f"https://wa.me/{digits}?text=Hi"

    return False, None


def _qr_redirect_url(short_code: str) -> str:
    return f"{settings.APP_API_URL}/api/v1/campaigns/qr/r/{short_code}"


def _serialize_qr(qr: CampaignQRCode) -> dict:
    return {
        "id": qr.id,
        "workflow_id": qr.workflow_id,
        "channel": qr.channel,
        "placement": qr.placement,
        "label": qr.label,
        "invite_link": _qr_redirect_url(qr.short_code),
        "scan_count": qr.scan_count,
        "last_scanned_at": qr.last_scanned_at.isoformat() if qr.last_scanned_at else None,
        "is_active": qr.is_active,
        "created_at": qr.created_at.isoformat(),
        "updated_at": qr.updated_at.isoformat(),
    }


@router.get("/qr/channels")
async def list_qr_channels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every channel that should show its own QR "system" in the QR
    Marketing section — one entry per connected Telegram/WhatsApp bot, plus
    the Facebook/Instagram architecture-only placeholders. Read-only,
    reuses the exact same connected-channel data as GET /campaigns/channels."""
    out: list[dict] = []

    tg_result = await db.execute(
        select(TelegramChannel, Workflow.name)
        .join(Workflow, Workflow.id == TelegramChannel.workflow_id)
        .where(TelegramChannel.user_id == current_user.id)
    )
    for ch, wf_name in tg_result.all():
        connected = bool(ch.is_enabled and ch.status == "connected" and ch.bot_username)
        out.append({
            "workflow_id": ch.workflow_id,
            "bot_name": wf_name,
            "channel": "telegram",
            "identifier": f"@{ch.bot_username}" if ch.bot_username else None,
            "is_connected": connected,
            "is_architecture_only": False,
        })

    wa_result = await db.execute(
        select(WhatsAppChannel, Workflow.name)
        .join(Workflow, Workflow.id == WhatsAppChannel.workflow_id)
        .where(WhatsAppChannel.user_id == current_user.id)
    )
    for ch, wf_name in wa_result.all():
        connected = bool(ch.is_enabled and ch.status == "connected" and ch.display_phone_number)
        out.append({
            "workflow_id": ch.workflow_id,
            "bot_name": wf_name,
            "channel": "whatsapp",
            "identifier": ch.display_phone_number,
            "is_connected": connected,
            "is_architecture_only": False,
        })

    # Facebook/Instagram — architecture only (NEW, Part 1 scope): no deep
    # link/QR is generated for these; surfaced so the UI can show the card
    # as "coming soon" without special-casing anything client-side.
    for channel in QR_ARCHITECTURE_ONLY_CHANNELS:
        out.append({
            "workflow_id": None,
            "bot_name": None,
            "channel": channel,
            "identifier": None,
            "is_connected": False,
            "is_architecture_only": True,
        })

    return out


@router.get("/qr")
async def list_qr_codes(
    workflow_id: Optional[str] = None,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(CampaignQRCode).where(
        CampaignQRCode.user_id == current_user.id, CampaignQRCode.is_active.is_(True)
    )
    if workflow_id:
        query = query.where(CampaignQRCode.workflow_id == workflow_id)
    if channel:
        query = query.where(CampaignQRCode.channel == channel)
    query = query.order_by(CampaignQRCode.created_at.desc())
    result = await db.execute(query)
    return [_serialize_qr(qr) for qr in result.scalars().all()]


@router.post("/qr", status_code=201)
async def create_qr_code(
    payload: QRCodeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = payload.channel.strip().lower()
    if channel in QR_ARCHITECTURE_ONLY_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"{channel.capitalize()} QR codes are not available yet — architecture only.",
        )
    if channel not in ACTIVE_QR_CHANNELS:
        raise HTTPException(status_code=422, detail=f"Unsupported channel: {payload.channel}")

    placement = (payload.placement or "other").strip().lower()
    if placement not in VALID_QR_PLACEMENTS:
        raise HTTPException(status_code=422, detail=f"Unsupported placement: {payload.placement}")

    await _get_owned_workflow_or_404(db, payload.workflow_id, current_user.id)

    is_connected, _ = await _get_qr_channel_connection(db, payload.workflow_id, channel)
    if not is_connected:
        raise HTTPException(
            status_code=422,
            detail=f"Connect and enable {channel.capitalize()} for this bot before generating a QR code.",
        )

    qr = CampaignQRCode(
        user_id=current_user.id,
        workflow_id=payload.workflow_id,
        channel=channel,
        placement=placement,
        label=(payload.label or None),
        short_code=_generate_qr_short_code(),
    )
    db.add(qr)
    await db.commit()
    await db.refresh(qr)
    return _serialize_qr(qr)


@router.get("/qr/{qr_id}/svg")
async def get_qr_code_svg(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renders the QR image for Preview/Download/Print, on demand, so the
    encoded target URL is always the current one on file (regenerate takes
    effect immediately without needing a separate image-cache invalidation)."""
    result = await db.execute(
        select(CampaignQRCode).where(
            CampaignQRCode.id == qr_id, CampaignQRCode.user_id == current_user.id
        )
    )
    qr = result.scalar_one_or_none()
    if not qr or not qr.is_active:
        raise HTTPException(status_code=404, detail="QR code not found")

    svg = generate_qr_svg(_qr_redirect_url(qr.short_code))
    return {"qr_svg": svg, "invite_link": _qr_redirect_url(qr.short_code)}


@router.post("/qr/{qr_id}/regenerate")
async def regenerate_qr_code(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issues a fresh short_code for the same channel/placement and
    archives the old one (is_active=False) instead of mutating it in
    place, so a previously-printed QR image simply stops resolving rather
    than silently pointing scans somewhere new."""
    result = await db.execute(
        select(CampaignQRCode).where(
            CampaignQRCode.id == qr_id, CampaignQRCode.user_id == current_user.id
        )
    )
    qr = result.scalar_one_or_none()
    if not qr or not qr.is_active:
        raise HTTPException(status_code=404, detail="QR code not found")

    qr.is_active = False
    new_qr = CampaignQRCode(
        user_id=current_user.id,
        workflow_id=qr.workflow_id,
        channel=qr.channel,
        placement=qr.placement,
        label=qr.label,
        short_code=_generate_qr_short_code(),
    )
    db.add(new_qr)
    await db.commit()
    await db.refresh(new_qr)
    return _serialize_qr(new_qr)


@router.delete("/qr/{qr_id}", status_code=204)
async def delete_qr_code(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CampaignQRCode).where(
            CampaignQRCode.id == qr_id, CampaignQRCode.user_id == current_user.id
        )
    )
    qr = result.scalar_one_or_none()
    if not qr:
        raise HTTPException(status_code=404, detail="QR code not found")
    await db.delete(qr)
    await db.commit()


def _visitor_hash(short_code: str, request: Request) -> str:
    # SHA-256 of short_code + client IP + User-Agent — never stores the raw
    # IP, just enough entropy to de-duplicate repeat scans from one device
    # for "Unique QR Scans" (Part 3). Best-effort: proxies without
    # X-Forwarded-For simply fall back to request.client.host.
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else ""
    )
    ua = request.headers.get("user-agent", "")
    raw = f"{short_code}:{ip}:{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("/qr/r/{short_code}")
async def scan_qr_code(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public — no auth. What the printed QR image actually encodes: counts
    the scan, then 302-redirects straight to the channel's own existing
    t.me/wa.me deep link. Everything from there (subscriber/contact
    creation, welcome workflow, conversation history, tags) is unchanged,
    existing Telegram/WhatsApp webhook behavior — this endpoint never
    creates a contact/subscriber itself.

    NEW (Part 3): also logs a CampaignQRScan row (visitor_hash) so the
    analytics overview/growth endpoints can report Unique QR Scans and an
    approximate Conversion Rate, without touching the webhook/subscriber
    creation path at all."""
    result = await db.execute(
        select(CampaignQRCode).where(CampaignQRCode.short_code == short_code)
    )
    qr = result.scalar_one_or_none()
    if not qr or not qr.is_active:
        raise HTTPException(status_code=404, detail="This QR code is no longer active")

    is_connected, deep_link = await _get_qr_channel_connection(db, qr.workflow_id, qr.channel)
    if not deep_link:
        raise HTTPException(status_code=404, detail="This bot's channel is no longer connected")

    qr.scan_count += 1
    qr.last_scanned_at = datetime.now(timezone.utc)

    visitor_hash = _visitor_hash(short_code, request)
    is_first_scan = not (await db.execute(
        select(CampaignQRScan.id).where(
            CampaignQRScan.qr_id == qr.id, CampaignQRScan.visitor_hash == visitor_hash
        ).limit(1)
    )).scalar_one_or_none()

    # Best-effort conversion attribution: on this visitor's FIRST scan of
    # this code, if a subscriber already exists for this workflow+channel
    # (i.e. they'd already messaged the bot before — a rough proxy since
    # scans carry no cookie), mark it converted. Read-only check — never
    # creates or edits a subscriber.
    converted = False
    if is_first_scan:
        if qr.channel == "telegram":
            sub_exists = (await db.execute(
                select(TelegramSubscriber.id)
                .join(TelegramChannel, TelegramChannel.id == TelegramSubscriber.channel_id)
                .where(TelegramChannel.workflow_id == qr.workflow_id)
                .limit(1)
            )).scalar_one_or_none()
        elif qr.channel == "whatsapp":
            sub_exists = (await db.execute(
                select(WhatsAppContact.id)
                .join(WhatsAppChannel, WhatsAppChannel.id == WhatsAppContact.channel_id)
                .where(WhatsAppChannel.workflow_id == qr.workflow_id)
                .limit(1)
            )).scalar_one_or_none()
        else:
            sub_exists = None
        converted = bool(sub_exists)

    db.add(CampaignQRScan(
        qr_id=qr.id, user_id=qr.user_id, visitor_hash=visitor_hash, converted=converted,
    ))
    await db.commit()

    return RedirectResponse(url=deep_link, status_code=302)


@router.get("/contacts")
async def list_whatsapp_contacts(
    workflow_id: str,
    channel: str = Query("whatsapp"),
    search: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Opted-in contacts for a bot — used by the 'Contacts' audience
    source. `channel` (NEW — Part 2) picks WhatsAppContact (default,
    unchanged) or TelegramSubscriber; either way this is read-only over the
    existing table, doesn't modify the underlying integration, and only
    ever returns people who have themselves messaged the bot first."""
    await _get_owned_workflow_or_404(db, workflow_id, current_user.id)

    if channel == "telegram":
        query = select(TelegramSubscriber).where(TelegramSubscriber.workflow_id == workflow_id)
        if search:
            like = f"%{search.strip()}%"
            query = query.where(
                (TelegramSubscriber.first_name.ilike(like))
                | (TelegramSubscriber.username.ilike(like))
                | (TelegramSubscriber.chat_id.ilike(like))
            )
        result = await db.execute(query.order_by(TelegramSubscriber.last_message_at.desc()))
        subs = [s for s in result.scalars().all() if s.is_subscribed]

        total = len(subs)
        start = (page - 1) * page_size
        page_items = subs[start:start + page_size]
        return {
            "contacts": [
                {
                    "id": s.id, "identifier": s.chat_id,
                    "name": (f"{s.first_name} {s.last_name}".strip() if s.first_name else None)
                            or (f"@{s.username}" if s.username else None),
                    "city": None, "company": None, "tags": [],
                    "message_count": s.message_count,
                }
                for s in page_items
            ],
            "total": total, "page": page, "page_size": page_size,
        }

    query = select(WhatsAppContact).where(WhatsAppContact.workflow_id == workflow_id)
    if search:
        like = f"%{search.strip()}%"
        query = query.where((WhatsAppContact.profile_name.ilike(like)) | (WhatsAppContact.wa_id.ilike(like)))
    result = await db.execute(query.order_by(WhatsAppContact.last_message_at.desc()))
    contacts = result.scalars().all()
    if tag:
        wanted = tag.strip().lower()
        contacts = [c for c in contacts if wanted in {str(t).lower() for t in (c.tags or [])}]

    total = len(contacts)
    start = (page - 1) * page_size
    page_items = contacts[start:start + page_size]
    return {
        "contacts": [
            {
                "id": c.id, "identifier": c.wa_id, "name": c.profile_name,
                "city": c.city, "company": c.company, "tags": c.tags or [],
                "message_count": c.message_count,
            }
            for c in page_items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/tags")
async def list_contact_tags(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Distinct tags across a bot's WhatsApp contacts — powers the 'Customer
    tags' audience source picker."""
    await _get_owned_workflow_or_404(db, workflow_id, current_user.id)
    result = await db.execute(
        select(WhatsAppContact.tags).where(WhatsAppContact.workflow_id == workflow_id)
    )
    tags: set[str] = set()
    for (row_tags,) in result.all():
        for t in (row_tags or []):
            if str(t).strip():
                tags.add(str(t).strip())
    return sorted(tags)


@router.get("/groups")
async def list_contact_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ContactGroup).where(ContactGroup.user_id == current_user.id).order_by(ContactGroup.created_at.desc())
    )
    groups = result.scalars().all()
    out = []
    for g in groups:
        count_result = await db.execute(
            select(func.count(ContactGroupMember.id)).where(ContactGroupMember.group_id == g.id)
        )
        out.append({
            "id": g.id, "name": g.name, "member_count": count_result.scalar() or 0,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        })
    return out


@router.post("/groups", status_code=201)
async def create_contact_group(
    payload: ContactGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Creates a reusable contact group — the 'Contact groups' audience
    source. Members can be pre-existing WhatsApp contacts or brand-new
    numbers (e.g. from a CSV), same {identifier, name?, city?, company?}
    shape used everywhere else in the audience picker."""
    group = ContactGroup(id=str(uuid.uuid4()), user_id=current_user.id, name=payload.name)
    db.add(group)
    await db.flush()
    _add_group_members(group.id, payload.members, db)
    await db.commit()
    return {"id": group.id, "name": group.name, "member_count": len(payload.members)}


@router.post("/groups/{group_id}/members")
async def add_contact_group_members(
    group_id: str,
    payload: AddGroupMembersRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = await _get_owned_group(db, group_id, current_user.id)
    _add_group_members(group.id, payload.members, db)
    await db.commit()
    count_result = await db.execute(
        select(func.count(ContactGroupMember.id)).where(ContactGroupMember.group_id == group.id)
    )
    return {"id": group.id, "name": group.name, "member_count": count_result.scalar() or 0}


@router.delete("/groups/{group_id}", status_code=204)
async def delete_contact_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = await _get_owned_group(db, group_id, current_user.id)
    await db.delete(group)
    await db.commit()
    return None


@router.post("/audience/resolve", response_model=AudienceResolveResponse)
async def resolve_audience_preview(
    payload: AudienceResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Step 2 (audience counts) and Step 4 (per-customer preview) of the
    Campaign Flow, in one call: resolves the audience_type/audience_config
    exactly as the send pipeline will (app/services/audience_service.py),
    without writing anything, so the UI can show total/valid/invalid/
    duplicate recipients and — when `message` is provided — exactly what a
    sample of customers will receive after personalization."""
    if payload.workflow_id:
        await _get_owned_workflow_or_404(db, payload.workflow_id, current_user.id)

    result = await audience_service.resolve_audience(
        db, current_user.id, payload.workflow_id, payload.audience_type, payload.audience_config,
        channel=payload.channel,
    )

    sample_entries = result.entries[:payload.sample_size]
    sample = [
        AudienceEntryOut(
            identifier=e.identifier, name=e.name, city=e.city, company=e.company, valid=True,
            preview=_render_preview(payload.message, e.name, e.city, e.company) if payload.message else None,
        )
        for e in sample_entries
    ]
    # Surface a few invalid rows too so the UI can show *why* something was skipped.
    sample += [
        AudienceEntryOut(identifier=e.identifier, valid=False, reason=e.reason)
        for e in result.invalid[:max(0, payload.sample_size - len(sample))]
    ]

    return AudienceResolveResponse(
        total=result.total, valid=result.valid_count,
        invalid=len(result.invalid), duplicate=result.duplicate_count, sample=sample,
    )


# ── AI rewrite/improve ─────────────────────────────────────────────────────────

@router.post("/ai/improve", response_model=AIImproveResponse)
async def ai_improve_message(
    payload: AIImproveRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rewrite/improve a campaign message using the user's configured default
    AI provider (same resolution chain as an AI Agent workflow node — see
    app.services.ai_engine.resolve_agent_provider / get_provider_for_user).
    This only returns improved text; it never sends anything.
    """
    instruction = payload.ai_prompt or (
        "Rewrite this marketing message to be more engaging and persuasive "
        "while keeping it concise and on-topic."
    )
    system_prompt = (
        "You are an expert marketing copywriter helping a small business "
        f"write a {payload.channel} campaign message. Rewrite the user's "
        "draft message according to their instructions. Keep it concise, "
        "on-brand, and appropriate for the channel. Return ONLY the "
        "rewritten message text — no preamble, no quotes, no explanation."
    )

    try:
        provider_id = await resolve_agent_provider(None, current_user.id)
        llm = await get_provider_for_user(provider_id, current_user.id)
        model, _ = validate_model_for_provider(provider_id, None)
        improved = await llm.complete(
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Instructions: {instruction}\n\nOriginal message:\n{payload.message}",
            }],
            temperature=0.7,
            max_tokens=600,
            model=model,
        )
    except ProviderError as e:
        status_by_kind = {
            "auth": 422, "permission": 422, "quota": 429,
            "model_not_found": 404, "network": 504, "malformed_key": 400,
        }
        raise HTTPException(status_code=status_by_kind.get(e.kind, 502), detail=str(e)) from e
    except ValueError as e:
        # resolve_agent_provider raises ValueError when there's no default
        # provider configured at all — surface as an actionable 422.
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Campaign AI improve failed for user={current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="The AI provider request failed. Please try again.") from e

    improved = (improved or "").strip() or payload.message

    if payload.campaign_id:
        campaign = await _get_owned_campaign(db, payload.campaign_id, current_user.id)
        if campaign:
            await _log_history(db, campaign.id, current_user.id, "ai_rewrite", {
                "ai_prompt": instruction,
            })
            await db.commit()

    return AIImproveResponse(improved_message=improved)


@router.post("/ai/generate", response_model=AIImproveResponse)
async def ai_generate_message(
    payload: AIGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Generates a brand-new broadcast message purely from a prompt (e.g.
    'Create a Diwali offer for existing customers') — Step 3 of the
    Campaign Flow when the user doesn't write the message manually. Reuses
    the same provider-resolution chain as /ai/improve and every other
    AI Agent call; no new AI transport."""
    system_prompt = (
        "You are an expert marketing copywriter helping a small business "
        f"write a {payload.channel} broadcast campaign message from scratch. "
        "Write a concise, on-brand, persuasive message based on the user's "
        "instructions. You may use the personalization variables {{name}}, "
        "{{city}}, and {{company}} where they'd naturally improve the "
        "message (e.g. greeting the customer by name) — don't force them "
        "in if they don't fit. Return ONLY the message text — no preamble, "
        "no quotes, no explanation."
    )
    try:
        provider_id = await resolve_agent_provider(None, current_user.id)
        llm = await get_provider_for_user(provider_id, current_user.id)
        model, _ = validate_model_for_provider(provider_id, None)
        generated = await llm.complete(
            system=system_prompt,
            messages=[{"role": "user", "content": payload.ai_prompt}],
            temperature=0.8,
            max_tokens=600,
            model=model,
        )
    except ProviderError as e:
        status_by_kind = {
            "auth": 422, "permission": 422, "quota": 429,
            "model_not_found": 404, "network": 504, "malformed_key": 400,
        }
        raise HTTPException(status_code=status_by_kind.get(e.kind, 502), detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Campaign AI generate failed for user={current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="The AI provider request failed. Please try again.") from e

    return AIImproveResponse(improved_message=(generated or "").strip())


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_campaigns(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Campaign).where(Campaign.user_id == current_user.id)
    if status:
        query = query.where(Campaign.status == status)
    if channel:
        query = query.where(Campaign.channel == channel)
    query = query.order_by(Campaign.created_at.desc())
    result = await db.execute(query)
    return [_serialize_campaign(c) for c in result.scalars().all()]


@router.post("/", status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = _validate_channel(payload.channel)
    schedule_type = _validate_schedule_type(payload.schedule_type)
    audience_type = _validate_audience_type(payload.audience_type)

    if schedule_type == "later" and not payload.scheduled_at:
        raise HTTPException(status_code=422, detail="scheduled_at is required when schedule_type is 'later'")

    if payload.launch:
        status_value = "scheduled" if schedule_type == "later" else "active"
    else:
        status_value = "draft"

    workflow_id = None
    if payload.workflow_id:
        wf_result = await db.execute(
            select(Workflow).where(Workflow.id == payload.workflow_id, Workflow.user_id == current_user.id)
        )
        if not wf_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="workflow_id does not refer to a bot you own")
        workflow_id = payload.workflow_id

    campaign = Campaign(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        workflow_id=workflow_id,
        name=payload.name,
        channel=channel,
        template=payload.template,
        message=payload.message,
        ai_prompt=payload.ai_prompt,
        audience_type=audience_type,
        audience_config=payload.audience_config or {},
        schedule_type=schedule_type,
        scheduled_at=payload.scheduled_at,
        status=status_value,
    )
    db.add(campaign)
    await db.flush()
    await _log_history(db, campaign.id, current_user.id, "created", {"status": status_value})
    await db.commit()
    await db.refresh(campaign)

    audit_service.record_bg(
        background_tasks, "campaign.create",
        actor=current_user, target_type="campaign", target_id=campaign.id, target_label=campaign.name,
    )

    # NEW: an immediate ("now") launch actually dispatches now, in the
    # background, via the real send pipeline (campaign_dispatch_service).
    # A "later" launch is picked up by the scheduler loop once due.
    if payload.launch and schedule_type == "now":
        background_tasks.add_task(_dispatch_bg, campaign.id)

    return _serialize_campaign(campaign)


@router.get("/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = await _get_owned_campaign(db, campaign_id, current_user.id)
    return _serialize_campaign(campaign)


@router.put("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = await _get_owned_campaign(db, campaign_id, current_user.id)

    changes: dict[str, Any] = {}
    if payload.name is not None:
        campaign.name = payload.name
        changes["name"] = payload.name
    if payload.channel is not None:
        campaign.channel = _validate_channel(payload.channel)
        changes["channel"] = campaign.channel
    if payload.template is not None:
        campaign.template = payload.template
    if payload.message is not None:
        campaign.message = payload.message
        changes["message"] = True
    if payload.ai_prompt is not None:
        campaign.ai_prompt = payload.ai_prompt
    if payload.audience_type is not None:
        campaign.audience_type = _validate_audience_type(payload.audience_type)
        changes["audience_type"] = campaign.audience_type
    if payload.audience_config is not None:
        campaign.audience_config = payload.audience_config
        changes["audience_config"] = True
    if payload.schedule_type is not None:
        campaign.schedule_type = _validate_schedule_type(payload.schedule_type)
        changes["schedule_type"] = campaign.schedule_type
    if payload.scheduled_at is not None:
        campaign.scheduled_at = payload.scheduled_at
    if payload.workflow_id is not None:
        wf_result = await db.execute(
            select(Workflow).where(Workflow.id == payload.workflow_id, Workflow.user_id == current_user.id)
        )
        if not wf_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="workflow_id does not refer to a bot you own")
        campaign.workflow_id = payload.workflow_id
        changes["workflow_id"] = payload.workflow_id

    should_dispatch = False
    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
        # Transitioning an immediate campaign into "active" is what actually
        # triggers a send — same real pipeline as launch=True on create.
        should_dispatch = payload.status == "active" and campaign.status != "active" and campaign.schedule_type == "now"
        campaign.status = payload.status
        changes["status"] = payload.status

    if campaign.schedule_type == "later" and not campaign.scheduled_at:
        raise HTTPException(status_code=422, detail="scheduled_at is required when schedule_type is 'later'")

    await _log_history(db, campaign.id, current_user.id, "updated", changes)
    await db.commit()
    await db.refresh(campaign)

    audit_service.record_bg(
        background_tasks, "campaign.update",
        actor=current_user, target_type="campaign", target_id=campaign.id, target_label=campaign.name,
    )

    if should_dispatch:
        background_tasks.add_task(_dispatch_bg, campaign.id)

    return _serialize_campaign(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = await _get_owned_campaign(db, campaign_id, current_user.id)
    name = campaign.name
    await db.delete(campaign)
    await db.commit()

    audit_service.record_bg(
        background_tasks, "campaign.delete",
        actor=current_user, target_type="campaign", target_id=campaign_id, target_label=name,
    )
    return None


@router.post("/{campaign_id}/duplicate", status_code=201)
async def duplicate_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    original = await _get_owned_campaign(db, campaign_id, current_user.id)

    copy = Campaign(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=f"{original.name} (Copy)",
        channel=original.channel,
        template=original.template,
        message=original.message,
        ai_prompt=original.ai_prompt,
        schedule_type=original.schedule_type,
        scheduled_at=original.scheduled_at,
        status="draft",
    )
    db.add(copy)
    await db.flush()
    await _log_history(db, copy.id, current_user.id, "created", {"duplicated_from": original.id})
    await db.commit()
    await db.refresh(copy)

    audit_service.record_bg(
        background_tasks, "campaign.duplicate",
        actor=current_user, target_type="campaign", target_id=copy.id, target_label=copy.name,
    )
    return _serialize_campaign(copy)


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = await _get_owned_campaign(db, campaign_id, current_user.id)
    if campaign.status not in ("active", "scheduled"):
        raise HTTPException(status_code=409, detail=f"Cannot pause a campaign with status '{campaign.status}'")

    campaign.status = "paused"
    await _log_history(db, campaign.id, current_user.id, "paused")
    await db.commit()
    await db.refresh(campaign)

    audit_service.record_bg(
        background_tasks, "campaign.pause",
        actor=current_user, target_type="campaign", target_id=campaign.id, target_label=campaign.name,
    )
    return _serialize_campaign(campaign)


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = await _get_owned_campaign(db, campaign_id, current_user.id)
    if campaign.status != "paused":
        raise HTTPException(status_code=409, detail=f"Cannot resume a campaign with status '{campaign.status}'")

    if campaign.schedule_type == "later" and campaign.scheduled_at and campaign.scheduled_at > datetime.now(timezone.utc):
        campaign.status = "scheduled"
    else:
        campaign.status = "active"

    await _log_history(db, campaign.id, current_user.id, "resumed", {"status": campaign.status})
    await db.commit()
    await db.refresh(campaign)

    audit_service.record_bg(
        background_tasks, "campaign.resume",
        actor=current_user, target_type="campaign", target_id=campaign.id, target_label=campaign.name,
    )

    if campaign.status == "active":
        # Resuming re-runs dispatch, which is idempotent (only sends to
        # recipients still pending/retryable) — picks up anyone missed
        # while paused, and retries anything that failed before pausing.
        background_tasks.add_task(_dispatch_bg, campaign.id)

    return _serialize_campaign(campaign)


@router.get("/{campaign_id}/history")
async def get_campaign_history(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_campaign(db, campaign_id, current_user.id)  # ownership check
    result = await db.execute(
        select(CampaignHistoryEntry)
        .where(CampaignHistoryEntry.campaign_id == campaign_id)
        .order_by(CampaignHistoryEntry.created_at.desc())
    )
    return [_serialize_history_entry(h) for h in result.scalars().all()]


# ── Broadcast & Auto-Reply Engine ───────────────────────────────────────────

@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicitly sends a draft/scheduled campaign now, regardless of its
    schedule_type — the one-click 'Send Now' action. Actually dispatches
    (via campaign_dispatch_service), unlike create(launch=True) with
    schedule_type='later', which only arms the scheduler."""
    campaign = await _get_owned_campaign(db, campaign_id, current_user.id)
    if campaign.status not in ("draft", "scheduled", "paused"):
        raise HTTPException(status_code=409, detail=f"Cannot launch a campaign with status '{campaign.status}'")
    if not (campaign.message or "").strip():
        raise HTTPException(status_code=422, detail="Campaign message is empty")

    campaign.status = "active"
    await _log_history(db, campaign.id, current_user.id, "launched")
    await db.commit()
    await db.refresh(campaign)

    audit_service.record_bg(
        background_tasks, "campaign.launch",
        actor=current_user, target_type="campaign", target_id=campaign.id, target_label=campaign.name,
    )
    background_tasks.add_task(_dispatch_bg, campaign.id)
    return _serialize_campaign(campaign)


@router.get("/{campaign_id}/recipients")
async def list_recipients(
    campaign_id: str,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_campaign(db, campaign_id, current_user.id)  # ownership check
    query = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
    if status:
        query = query.where(CampaignRecipient.status == status)
    query = query.order_by(CampaignRecipient.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    recipients = result.scalars().all()

    count_query = select(func.count(CampaignRecipient.id)).where(CampaignRecipient.campaign_id == campaign_id)
    if status:
        count_query = count_query.where(CampaignRecipient.status == status)
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "recipients": [_serialize_recipient(r) for r in recipients],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{campaign_id}/recipients/retry")
async def retry_recipients(
    campaign_id: str,
    payload: RetryRequest = RetryRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retries failed deliveries. Body: optional {"recipient_ids": [...]}
    (retries those specific recipients regardless of retry count) — omit to
    retry every failed recipient still under max_retries."""
    await _get_owned_campaign(db, campaign_id, current_user.id)  # ownership check
    try:
        result = await campaign_dispatch.retry_failed_recipients(campaign_id, payload.recipient_ids)
    except campaign_dispatch.DispatchError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return result


@router.post("/{campaign_id}/recipients/{recipient_id}/takeover")
async def set_recipient_takeover(
    campaign_id: str,
    recipient_id: str,
    payload: TakeoverRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Human takeover: when enabled, the AI stops auto-replying to this
    contact — the existing WhatsApp webhook checks this flag on every
    inbound message for the contact's session (see
    campaign_dispatch_service.find_recipient_by_session) and skips invoking
    the Workflow Runtime while it's set. Disabling it hands the
    conversation back to the AI."""
    recipient = await _get_owned_recipient(db, campaign_id, recipient_id, current_user.id)
    await campaign_dispatch.set_human_takeover(db, recipient, payload.enabled)
    await _log_history(
        db, campaign_id, current_user.id,
        "human_takeover_enabled" if payload.enabled else "human_takeover_disabled",
        {"recipient_id": recipient_id, "contact": recipient.contact_identifier},
    )
    await db.commit()
    await db.refresh(recipient)
    return _serialize_recipient(recipient)


@router.get("/{campaign_id}/recipients/{recipient_id}/conversation")
async def get_recipient_conversation(
    campaign_id: str,
    recipient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full conversation history for this recipient — the campaign message,
    every reply, and every AI/human response. Reuses the existing Analytics
    Conversation/Message tables (same ones the Analytics Dashboard and
    WhatsApp stats already read from) via recipient.session_id, so there's
    no duplicate message store to keep in sync."""
    recipient = await _get_owned_recipient(db, campaign_id, recipient_id, current_user.id)
    conv_result = await db.execute(
        select(Conversation.id).where(Conversation.session_id == recipient.session_id)
    )
    conversation_id = conv_result.scalar_one_or_none()
    detail = (
        await analytics_service.get_conversation_detail(db, current_user.id, conversation_id)
        if conversation_id else None
    )
    return {
        "recipient": _serialize_recipient(recipient),
        "conversation": detail,
    }
