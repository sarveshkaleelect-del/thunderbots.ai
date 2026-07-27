"""
ThunderBots WhatsApp Integration Models
NEW (WhatsApp Channel).

Three tables, purely additive — no existing table, model, or relationship
is touched:

- WhatsAppChannel: one row per workflow (one WhatsApp Business number per
  chatbot). Holds the Meta WhatsApp Cloud API connection (Phone Number ID,
  Business Account ID, encrypted Access Token, encrypted Verify Token, an
  optional encrypted App Secret used for webhook signature validation),
  plus live health/status/stat fields surfaced in the Settings UI.

- WhatsAppContact: maps a WhatsApp end-user (wa_id, i.e. their phone number
  in E.164-ish format as sent by Meta) to the stable `session_id` used by
  the existing Workflow Runtime's ExecutionContext (Redis-cached, exactly
  like the WebSocket/REST chat paths) — this is what lets a WhatsApp
  conversation resume correctly across multiple incoming messages/webhook
  deliveries ("Session Management").

- WhatsAppMediaAsset: records of incoming media (image/document/audio/
  video/sticker) downloaded from Meta's Graph API and stored locally under
  settings.UPLOAD_DIR, so downloads are auditable and never re-fetched.

Follows the exact same conventions already established in models/user.py,
models/workflow.py, models/analytics.py: ondelete="CASCADE" on every FK,
passive_deletes=True on every relationship (so async session.delete(...)
never triggers a lazy-load / MissingGreenlet), server-default-free JSONB
default=dict/list handled Python-side, and String(36) UUID primary keys.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class WhatsAppChannel(Base):
    """One WhatsApp Business connection per chatbot (workflow)."""
    __tablename__ = "whatsapp_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Meta WhatsApp Cloud API connection ────────────────────────────────────
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    business_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Verify Token — the shared secret Meta echoes back on GET webhook verification.
    encrypted_verify_token: Mapped[str] = mapped_column(Text, nullable=False)
    # App Secret — optional, used to validate the X-Hub-Signature-256 header on
    # every inbound webhook POST. Not one of the fields Meta strictly requires
    # to *send* messages, but without it webhook payloads cannot be
    # cryptographically verified as originating from Meta, so it's offered as
    # an optional-but-recommended field in the connection wizard.
    encrypted_app_secret: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Populated by Test Connection / Reconnect (read from Graph API) ────────
    display_phone_number: Mapped[str | None] = mapped_column(String(32))
    verified_name: Mapped[str | None] = mapped_column(String(255))
    quality_rating: Mapped[str | None] = mapped_column(String(32))

    # connecting | connected | error | disconnected
    status: Mapped[str] = mapped_column(String(20), default="disconnected", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # healthy | degraded | error | unknown — surfaced as the Settings UI health dot
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages_received_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_failed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Free-form bag for forward-compatible settings (e.g. default greeting,
    # 24h-session-window opt-outs) without another migration.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contacts: Mapped[list["WhatsAppContact"]] = relationship(
        "WhatsAppContact", back_populates="channel", cascade="all, delete-orphan", passive_deletes=True
    )
    media_assets: Mapped[list["WhatsAppMediaAsset"]] = relationship(
        "WhatsAppMediaAsset", back_populates="channel", cascade="all, delete-orphan", passive_deletes=True
    )


class WhatsAppContact(Base):
    """Maps a WhatsApp end-user to the Workflow Runtime session that carries
    their ExecutionContext (current_node_id, variables, message history)."""
    __tablename__ = "whatsapp_contacts"

    __table_args__ = (
        UniqueConstraint("channel_id", "wa_id", name="uq_whatsapp_contact_channel_wa_id"),
        Index("idx_wa_contact_channel_wa", "channel_id", "wa_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("whatsapp_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    wa_id: Mapped[str] = mapped_column(String(32), nullable=False)  # WhatsApp phone number (E.164-ish, no '+')
    profile_name: Mapped[str | None] = mapped_column(String(255))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    # NEW (AI Broadcast Campaigns): optional personalization fields + free-form
    # tags, editable from the Campaign Manager's audience picker so a
    # "WhatsApp contacts" audience can be filtered by tag and campaign
    # messages can use {{city}}/{{company}} alongside {{name}}. Additive,
    # nullable/defaulted — every pre-existing contact keeps working unchanged.
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)

    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    channel: Mapped["WhatsAppChannel"] = relationship(
        "WhatsAppChannel", back_populates="contacts", passive_deletes=True
    )


class WhatsAppMediaAsset(Base):
    """Metadata for incoming media downloaded securely from the Graph API."""
    __tablename__ = "whatsapp_media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("whatsapp_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    wa_media_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)  # image|document|audio|video|sticker
    mime_type: Mapped[str | None] = mapped_column(String(100))
    filename: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # relative to settings.UPLOAD_DIR
    file_size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    channel: Mapped["WhatsAppChannel"] = relationship(
        "WhatsAppChannel", back_populates="media_assets", passive_deletes=True
    )
