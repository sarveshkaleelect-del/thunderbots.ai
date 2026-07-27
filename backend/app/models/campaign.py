"""
ThunderBots AI Campaign Manager Models

NEW: Purely additive tables backing the Campaign Management System
(frontend/app/campaigns). Does not touch Workflow, Deployment, WhatsApp,
Analytics, or any other existing model.

- campaigns          One row per marketing campaign a business owner builds.
                      analytics counters (sent/delivered/failed/replied) are
                      incremented by services/campaign_dispatch_service.py as
                      messages are actually sent and their delivery/read/reply
                      status is confirmed (see also campaign_recipients in
                      models/campaign_broadcast.py for the per-contact ledger
                      backing these aggregates).
- campaign_history   Append-only audit trail of what happened to a campaign
                      (created, edited, duplicated, paused, resumed, deleted,
                      AI-rewrite applied, ...), independent of the app-wide
                      AuditLog table so campaign history can be shown inline
                      in the Campaigns UI without joining across features.

Same conventions as app/models/workflow.py: string UUID PKs, ondelete=CASCADE
on every FK with passive_deletes=True on the ORM side so async deletes never
trigger a MissingGreenlet lazy-load.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    __table_args__ = (
        Index("idx_campaigns_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # NEW (Broadcast & Auto-Reply Engine): which bot sends this campaign —
    # its WhatsAppChannel (or future Telegram/Instagram/Email connection)
    # is what's actually used to dispatch. Nullable + resolved automatically
    # at send-time when the user has exactly one connected channel for the
    # campaign's channel type, so existing campaigns/clients that never set
    # this keep working unchanged. See services/campaign_dispatch_service.py.
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)


    # Target Channel — WhatsApp today, Instagram/Telegram/Email are
    # future-ready values the UI already offers; nothing downstream
    # branches on channel yet since sending is out of scope.
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="whatsapp", index=True)

    # Optional starting template id (see CAMPAIGN_TEMPLATES in the API layer).
    # "custom" (or null) means the user wrote the campaign from scratch.
    template: Mapped[str | None] = mapped_column(String(50), nullable=True)

    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NEW (AI Broadcast Campaigns — Audience Selection):
    # "contacts" (all/filtered opted-in WhatsApp contacts, the original
    # behavior — default so pre-existing campaigns keep working unchanged),
    # "tags", "groups", or "manual" (typed numbers or CSV import — the
    # frontend parses the CSV client-side into the same manual_entries
    # shape). See app/services/audience_service.py for resolution and
    # app/services/campaign_dispatch_service.py for how this feeds the send
    # pipeline's recipient ledger.
    audience_type: Mapped[str] = mapped_column(String(20), nullable=False, default="contacts")
    audience_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Schedule: "now" or "later". scheduled_at is only meaningful when
    # schedule_type == "later".
    schedule_type: Mapped[str] = mapped_column(String(10), nullable=False, default="now")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # draft -> scheduled|active -> paused <-> active -> completed
    #                                    -> cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)

    # Analytics counters. Always 0 today — see module docstring. Kept as
    # plain integers (not derived) so a future send-pipeline can increment
    # them directly without a schema change.
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replied_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    history: Mapped[list["CampaignHistoryEntry"]] = relationship(
        "CampaignHistoryEntry",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CampaignHistoryEntry.created_at.desc()",
    )

    recipients: Mapped[list["CampaignRecipient"]] = relationship(  # noqa: F821
        "CampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CampaignHistoryEntry(Base):
    __tablename__ = "campaign_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # created | updated | duplicated | paused | resumed | deleted |
    # ai_rewrite | status_change
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    campaign: Mapped["Campaign"] = relationship(
        "Campaign", back_populates="history", passive_deletes=True
    )
