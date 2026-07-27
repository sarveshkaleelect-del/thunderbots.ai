"""
ThunderBots AI Call Agent — Phone Number Models (NEW, Voice AI Part 2)

Purely additive — no existing table, model, or relationship is touched.
This is phone number *connection and verification* only: there is no
workflow binding, no call session, no telephony state here. That is
explicitly out of scope for this part (see api/v1/call_agent.py docstring)
and left for a future Voice AI phase.

Two tables:

- PhoneNumber: one row per phone number a user has added. Tracks the
  verification lifecycle (pending -> verified | failed | expired) and the
  connection lifecycle (connected/disconnected, plus an `is_enabled` flag
  gating "AI Call Agent" features — set only once a number is verified).

- PhoneVerificationCode: one row per code sent for a given phone number.
  Only a SHA-256 hash of the code is ever stored, never the plaintext code
  itself — identical convention to PasswordResetToken/EmailVerificationToken
  (models/notification.py) and TOTP backup codes (services/totp_service.py).

Follows the exact same conventions already established in models/user.py,
models/whatsapp.py, models/telegram.py: ondelete="CASCADE" on every FK,
passive_deletes=True on every relationship, JSONB-free simple columns,
String(36) UUID primary keys.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PhoneNumber(Base):
    """A phone number a user has added for AI Call Agent features."""
    __tablename__ = "phone_numbers"

    __table_args__ = (
        UniqueConstraint("user_id", "phone_number", name="uq_phone_number_user_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # E.164-normalized (e.g. "+14155551234"), same free-text-but-normalized
    # convention as WhatsAppChannel.display_phone_number.
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(100), default="")

    # pending | verified | failed | expired
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    # otp | sms | call — the method most recently used to (re)verify.
    verification_method: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Connection state, independent of verification status — a verified
    # number can still be disconnected (paused) and reconnected without
    # having to re-verify, as long as it hasn't expired/failed.
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Gates AI Call Agent features (real call automation is NOT implemented
    # in this part — this flag is purely a readiness toggle for a future
    # phase to key off of). Can only be set True while verified+connected.
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Voice AI Part 3 (NEW) ────────────────────────────────────────────
    # The Workflow whose AI Agent/Knowledge Base/Workflow Runtime answers
    # calls on this number. Nullable — a verified number with is_enabled
    # can still have no workflow bound yet, in which case inbound calls are
    # answered with a short "not configured" message and hung up, and
    # outbound calls cannot be placed (see call_agent_calls.py).
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # NEW (Voice AI Part 5): preferred binding — an independent VoiceAgent
    # (own provider/model/instructions/Knowledge Base, nothing shared with
    # the chatbot Workflow). Nullable and additive alongside workflow_id
    # above, which is left completely untouched for any number still bound
    # the old way. When both are set, voice_agent_id wins (see
    # api/ws/call_stream_ws.py) — a number should only ever be bound to one
    # or the other in practice, the UI only ever sets one at a time.
    voice_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("voice_agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # { voice_provider, voice_id, speed (0.5-2.0), language ("en-US" etc.),
    #   recording_enabled }. Same "small JSONB settings blob" convention as
    # Workflow.chat_settings (Deploy Experience / Voice Responses Part 1).
    call_settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    verification_codes: Mapped[list["PhoneVerificationCode"]] = relationship(
        "PhoneVerificationCode", back_populates="phone_number_row",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="PhoneVerificationCode.created_at.desc()",
    )


class PhoneVerificationCode(Base):
    """A single sent verification code. Never stores the raw code."""
    __tablename__ = "phone_verification_codes"

    __table_args__ = (
        Index("idx_phone_verification_phone_id", "phone_number_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("phone_numbers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # otp | sms | call
    method: Mapped[str] = mapped_column(String(10), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    phone_number_row: Mapped["PhoneNumber"] = relationship(
        "PhoneNumber", back_populates="verification_codes", passive_deletes=True
    )
