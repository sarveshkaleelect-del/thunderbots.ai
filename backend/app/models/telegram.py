"""
ThunderBots Telegram Integration Models — Part 1 (Connect + Subscribers)
NEW (Telegram Channel).

Mirrors the exact conventions already established by models/whatsapp.py and
models/instagram.py: ondelete="CASCADE" on every FK, passive_deletes=True on
every relationship, JSONB default=dict handled Python-side, String(36) UUID
primary keys. Purely additive — no existing table, model, or relationship
is touched.

Two tables:

- TelegramChannel: one row per connected Telegram Bot, tied to a single
  workflow (one bot per chatbot, same shape as WhatsAppChannel/
  InstagramAccount). Holds the encrypted Bot API token obtained from
  @BotFather, an encrypted per-channel webhook secret (verified via
  Telegram's `X-Telegram-Bot-Api-Secret-Token` header on every inbound
  webhook call — Telegram's equivalent of Meta's signed-payload check),
  and the bot identity/health/stat fields surfaced in the Settings UI.

  `status` distinguishes "invalid_token" (the token was rejected by
  Telegram's own getMe call — i.e. definitively wrong/revoked) from a
  generic "error" (a transient network/API failure) so the Settings UI can
  show the specific, actionable state the requirements ask for:
  Connected / Disconnected / Invalid Token.

- TelegramSubscriber: maps a Telegram chat_id to the stable `session_id`
  used by the existing Workflow Runtime's ExecutionContext — identical role
  to WhatsAppContact / InstagramContact. A row is only ever created when an
  inbound webhook update actually arrives for that chat_id, which is itself
  proof the person has started a conversation with the bot: Telegram's own
  platform rules mean a bot can never message a chat_id that hasn't messaged
  it first (sendMessage fails with "chat not found" / 403 otherwise), so
  this table can never contain someone who hasn't opted in by messaging the
  bot. This is what "Future-ready architecture for campaigns" (Part 2)
  will read from as its opt-in audience, exactly like WhatsAppContact today.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TelegramChannel(Base):
    """One Telegram Bot connection per chatbot (workflow)."""
    __tablename__ = "telegram_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Telegram Bot API connection (token issued by @BotFather) ──────────────
    encrypted_bot_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Random per-channel secret we generate and hand to Telegram's setWebhook
    # `secret_token` param; Telegram echoes it back on every webhook POST as
    # X-Telegram-Bot-Api-Secret-Token so we can reject spoofed calls.
    encrypted_webhook_secret: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Populated by Connect / Test / Reconnect (read from Telegram getMe) ────
    bot_id: Mapped[str | None] = mapped_column(String(32))
    bot_username: Mapped[str | None] = mapped_column(String(255))
    bot_first_name: Mapped[str | None] = mapped_column(String(255))

    # connecting | connected | invalid_token | disconnected | error
    status: Mapped[str] = mapped_column(String(20), default="disconnected", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # healthy | degraded | error | unknown — surfaced as the Settings UI health dot
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text)

    webhook_registered: Mapped[bool] = mapped_column(Boolean, default=False)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages_received_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_failed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Free-form bag for forward-compatible settings without another migration.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    subscribers: Mapped[list["TelegramSubscriber"]] = relationship(
        "TelegramSubscriber", back_populates="channel", cascade="all, delete-orphan", passive_deletes=True
    )


class TelegramSubscriber(Base):
    """Maps a Telegram chat_id to the Workflow Runtime session that carries
    their ExecutionContext. Only ever created on an inbound webhook update —
    i.e. only for people who have started the bot conversation."""
    __tablename__ = "telegram_subscribers"

    __table_args__ = (
        UniqueConstraint("channel_id", "chat_id", name="uq_telegram_subscriber_channel_chat_id"),
        Index("idx_tg_subscriber_channel_chat", "channel_id", "chat_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("telegram_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)  # Telegram chat id
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    # Flips to False if a send ever comes back "bot was blocked by the user"
    # (Telegram 403) — kept instead of deleted so the historical session/
    # analytics trail and re-subscribe (unblock -> message again) both work.
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)

    message_count: Mapped[int] = mapped_column(Integer, default=0)
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    channel: Mapped["TelegramChannel"] = relationship(
        "TelegramChannel", back_populates="subscribers", passive_deletes=True
    )
