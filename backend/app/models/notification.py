"""
ThunderBots Email & Notification Service — models (NEW)

Purely additive module — no existing table, column, or relationship is
touched. Same conventions as models/team.py: UUID string PKs,
ForeignKey(..., ondelete="CASCADE"), relationship(..., passive_deletes=True).

- PasswordResetToken: one row per issued "forgot password" request. The
  raw token is never stored — only its SHA-256 hash — so a leaked database
  cannot be used to reset accounts (same reasoning as storing bcrypt
  password hashes, not plaintext passwords). A token is single-use
  (used_at) and time-boxed (expires_at).
- EmailLog: a lightweight audit trail of every email the platform attempted
  to send (welcome, password reset, team invite, usage/error notification),
  regardless of outcome. Used for debugging delivery issues and basic
  abuse/volume monitoring — not a queue, and not required for the send path
  to function (see services/email_service.py — logging failures never block
  or fail an actual send).
- EmailVerificationToken (NEW — Email Verification): one row per issued
  signup-verification link, same shape and same "hash only, never store the
  raw token" principle as PasswordResetToken. Single-use (used_at) and
  time-boxed (expires_at).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", passive_deletes=True)  # noqa: F821


class EmailVerificationToken(Base):
    """NEW (Email Verification): issued on register (and on
    /auth/resend-verification) and consumed by /auth/verify-email. Mirrors
    PasswordResetToken exactly — only a SHA-256 hash of the raw token is
    persisted, single-use, time-boxed."""
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", passive_deletes=True)  # noqa: F821


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # "sent" | "failed"
    provider: Mapped[str] = mapped_column(String(50), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
