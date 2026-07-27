"""
ThunderBots AI Broadcast & Auto-Reply Engine — Models
NEW: Purely additive. Adds exactly one table (campaign_recipients) plus one
nullable column on the existing `campaigns` table (workflow_id). Does not
alter Conversation/Message (Analytics), WhatsAppChannel/Contact (WhatsApp),
or Workflow/Runtime in any way.

- campaign_recipients   One row per (campaign, contact) the campaign was, or
                        will be, sent to. This is the delivery ledger:
                        send status, provider message id (for delivery/read
                        webhook correlation), retry bookkeeping, and the
                        conversation outcome (replied / ai_resolved /
                        escalated / human_takeover).

                        `session_id` is deliberately the SAME session_id the
                        Workflow Runtime / Analytics already use for this
                        contact (see app/models/whatsapp.py:WhatsAppContact
                        and app/api/v1/whatsapp.py:_session_id_for). That's
                        what lets an inbound reply on the existing WhatsApp
                        webhook path — completely unmodified in its core
                        execution — land back on the same conversation this
                        campaign started, so the AI Agent continues the
                        conversation naturally using its normal history +
                        Knowledge Base, with zero special-casing inside the
                        Workflow Runtime itself.

Same conventions as app/models/campaign.py: string UUID PKs, ondelete=CASCADE
on every FK with passive_deletes=True on the ORM side.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# pending    — created, not yet attempted
# queued     — picked up by the dispatcher, about to be sent
# sent       — accepted by the channel provider (e.g. Graph API 200)
# delivered  — provider confirmed device delivery (webhook status callback)
# read       — provider confirmed the recipient read it (webhook status callback)
# failed     — provider rejected it, or all retries exhausted
# opted_out  — skipped: recipient has no valid opt-in / session on this channel
RECIPIENT_STATUSES = {
    "pending", "queued", "sent", "delivered", "read", "failed", "opted_out",
}

DEFAULT_MAX_RETRIES = 3


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_identifier", name="uq_campaign_recipient_contact"),
        Index("idx_campaign_recipients_campaign_status", "campaign_id", "status"),
        Index("idx_campaign_recipients_session", "session_id"),
        Index("idx_campaign_recipients_provider_msg", "provider_message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    channel: Mapped[str] = mapped_column(String(20), nullable=False)

    # Destination address on the channel: WhatsApp wa_id (phone, no '+'),
    # Telegram chat id, Instagram-scoped id, or email address. Future-ready:
    # the field is channel-agnostic on purpose.
    contact_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # NEW (AI Broadcast Campaigns — Audience Selection + Personalization):
    # snapshot of {{city}}/{{company}} at send time (from the resolved
    # audience — WhatsApp contact, contact group member, or manual/CSV row)
    # so re-sends/retries stay consistent even if the source contact is
    # edited later. `source` records which audience type produced this row:
    # contacts | tags | groups | manual.
    contact_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="contacts")

    # Same session_id the Workflow Runtime/Analytics use for this contact —
    # see module docstring. Unique because one contact -> one ongoing session.
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_MAX_RETRIES)

    # ── Conversation outcome (drives campaign analytics: Opened / Replied /
    # AI Resolved / Escalated) ─────────────────────────────────────────────
    opened: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)       # read receipt
    replied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)      # any inbound reply
    ai_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # AI reached a natural end
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)    # handed to a human

    # When true, the existing WhatsApp webhook still records the inbound
    # message but skips invoking the Workflow Runtime for THIS session —
    # the human is expected to reply manually from the WhatsApp Business
    # app / a future inbox UI. Toggled via
    # POST /campaigns/{id}/recipients/{recipient_id}/takeover.
    human_takeover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    campaign: Mapped["Campaign"] = relationship(  # noqa: F821
        "Campaign", back_populates="recipients", passive_deletes=True
    )
