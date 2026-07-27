"""
ThunderBots Owner Assistant — Part 2 (Campaign QR Marketing System)
NEW.

Purely additive — no existing table, model, or relationship is touched.
Follows the exact conventions already established by models/campaign_qr.py
and models/telegram.py: String(36) UUID primary keys, ondelete="CASCADE" on
every FK with passive_deletes=True on the ORM side.

One table:

- OwnerAssistantLink: maps a single Telegram chat_id or WhatsApp wa_id to
  the ThunderBots account (user) that owns the bot it messaged, once that
  owner has explicitly linked it (via the one-time /assistant <code> command
  handled in api/v1/telegram.py / api/v1/whatsapp.py's existing webhooks).
  Only a chat_id/wa_id with an active row here is ever routed to the Owner
  Assistant flow (app/services/owner_assistant_service.py) instead of the
  normal customer-facing Workflow Runtime — every other inbound message on
  every channel is completely unaffected.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OwnerAssistantLink(Base):
    """One row per business owner who has linked a Telegram chat or
    WhatsApp number to control their campaigns conversationally."""
    __tablename__ = "owner_assistant_links"

    __table_args__ = (
        UniqueConstraint("channel", "external_chat_id", name="uq_owner_assistant_channel_chat"),
        Index("idx_owner_assistant_user", "user_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Which of the owner's connected bots this link was created through —
    # informational only; the assistant flow itself operates across every
    # campaign/QR/analytics resource the owner has, not just this bot's.
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )

    # telegram | whatsapp
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # TelegramSubscriber.chat_id or WhatsAppContact.wa_id
    external_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
