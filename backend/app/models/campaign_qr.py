"""
ThunderBots Campaign QR Marketing Models — Part 1 (QR Acquisition)
NEW (Campaign QR Marketing System).

Purely additive — no existing table, model, or relationship is touched.
Follows the exact conventions already established by models/campaign.py and
models/telegram.py: String(36) UUID primary keys, ondelete="CASCADE" on
every FK with passive_deletes=True on the ORM side, JSONB default=dict/list
handled Python-side.

One table:

- CampaignQRCode: one row per QR code a business owner generates for a
  connected channel (Telegram or WhatsApp today; `channel` also accepts
  "facebook"/"instagram" so the same row shape already covers those two
  channels' QR codes once their acquisition links exist — architecture
  only for Part 1, see api/v1/campaigns.py's QR_ARCHITECTURE_ONLY_CHANNELS).

  Does NOT duplicate any contact/subscriber logic: the QR just carries the
  short_code that this table maps back to the channel's own existing
  deep-link (t.me/<bot_username> or wa.me/<phone>) so a scan lands on
  Telegram/WhatsApp itself. Everything after that — the customer pressing
  START or sending "Hi", subscriber/contact creation, welcome workflow,
  conversation history, tags — is unchanged, existing behavior already
  handled entirely by the untouched Telegram/WhatsApp webhook handlers
  (api/v1/telegram.py::receive_webhook, api/v1/whatsapp.py's webhook).

  `placement` is purely a business-facing label (Shop Entrance, Cash
  Counter, ...) so an owner can print/track a separate code per physical
  location; `scan_count`/`last_scanned_at` are incremented by the public
  redirect endpoint on every scan, independent of whether the scan ever
  turns into a subscriber.

  Regenerate (NEW) issues a fresh, unguessable short_code and archives the
  old one (is_active=False) rather than mutating it in place, so historical
  scan counts on a previously-printed code are never silently reattributed
  to a new one — printed QR images that still show the old code simply stop
  resolving (404) instead of quietly redirecting somewhere else.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# NEW (Campaign QR Marketing System — Part 3): per-scan log backing "Unique QR
# Scans" and the Daily/Weekly/Monthly growth timeseries. campaign_qr_codes.scan_count
# stays the simple lifetime total (untouched); this table is additive and never
# read by the existing redirect behavior — it only gets one extra INSERT.


PLACEMENT_CHOICES = (
    "shop_entrance", "cash_counter", "product_packaging", "bills",
    "visiting_card", "posters", "menu", "website", "other",
)

# Channels with a real, scannable customer-acquisition deep link today.
# Facebook/Instagram are intentionally excluded — see QR_ARCHITECTURE_ONLY_CHANNELS
# in api/v1/campaigns.py — until an equivalent deep link exists for them.
ACTIVE_QR_CHANNELS = ("telegram", "whatsapp")


class CampaignQRCode(Base):
    """One generated QR code, scoped to a single connected channel + a
    business-chosen physical/print placement."""
    __tablename__ = "campaign_qr_codes"

    __table_args__ = (
        Index("idx_campaign_qr_user_workflow", "user_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Which bot/channel connection this QR resolves to. Nullable=False, but
    # ondelete=CASCADE so a deleted bot connection cleans up its QR codes
    # too, exactly like TelegramSubscriber/WhatsAppContact do for their
    # channel today.
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # telegram | whatsapp | facebook | instagram — the latter two are
    # architecture-only for Part 1 (no active deep link yet to encode).
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # shop_entrance | cash_counter | product_packaging | bills |
    # visiting_card | posters | menu | website | other
    placement: Mapped[str] = mapped_column(String(30), nullable=False, default="other")
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Random, unguessable public identifier embedded in the QR image's
    # target URL (…/api/v1/campaigns/qr/r/{short_code}). Never the raw
    # t.me/wa.me link itself, so scans can be counted per-placement and a
    # regenerate can invalidate a specific printed code without touching
    # the underlying bot connection.
    short_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    scan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # False once superseded by Regenerate — kept (not deleted) purely as a
    # historical scan-count record; the redirect endpoint 404s for it.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CampaignQRScan(Base):
    """One row per scan of a QR code (Part 3 — QR Marketing analytics).

    Purely additive event log alongside CampaignQRCode.scan_count/last_scanned_at
    (both untouched). `visitor_hash` is a SHA-256 of (short_code + client IP +
    User-Agent), never the raw IP — enough to de-duplicate repeat scans from the
    same device for "Unique QR Scans" without storing PII. `converted` flips to
    True the first time a subscriber created afterwards on the same channel is
    attributed back to this scan (best-effort, short attribution window) — see
    campaigns_analytics_overview's conversion_rate calculation.
    """
    __tablename__ = "campaign_qr_scans"

    __table_args__ = (
        Index("idx_campaign_qr_scans_qr_created", "qr_id", "created_at"),
        Index("idx_campaign_qr_scans_visitor", "qr_id", "visitor_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    qr_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaign_qr_codes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visitor_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    converted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
