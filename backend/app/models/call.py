"""
ThunderBots AI Call Agent — Call Session Models (NEW, Voice AI Part 3)

Builds on top of models/phone_number.py (Part 2 — connection/verification
only). This part adds the actual call session: one row per inbound or
outbound phone call, plus a transcript entry table for realtime STT/AI
turns. Follows the exact same conventions as every other model in this
project (String(36) UUID PKs, ondelete="CASCADE", passive_deletes=True).

Call state does NOT duplicate the Workflow Runtime's own session state —
`session_id` is the same Redis-cached ExecutionContext session id used by
chat_ws.py/whatsapp.py, so a call is just another "channel" driving the
existing Workflow Runtime, AI Agent, and Knowledge Base exactly like
WhatsApp/Telegram/Instagram already do.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, Index, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


# Every terminal/active state the call dashboard groups calls into.
CALL_STATUSES = (
    "queued", "ringing", "active", "completed", "failed", "missed", "no_answer",
)


class Call(Base):
    """One inbound or outbound AI phone call."""
    __tablename__ = "calls"

    __table_args__ = (
        Index("idx_calls_user_status", "user_id", "status"),
        Index("idx_calls_phone_number_id", "phone_number_id"),
        Index("idx_calls_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone_number_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("phone_numbers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # inbound | outbound
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    from_number: Mapped[str] = mapped_column(String(20), nullable=False)
    to_number: Mapped[str] = mapped_column(String(20), nullable=False)

    # queued | ringing | active | completed | failed | missed | no_answer
    # "interrupted" is NOT a terminal status — it is tracked via
    # `interrupted_count` on an otherwise-completed call (a call that had
    # one or more barge-ins is still a completed call), matching the
    # dashboard's "Interrupted" bucket = completed calls where count > 0.
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    end_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provider (Twilio) identifiers — needed to correlate status callbacks,
    # fetch recordings, and to hang up an in-progress call from the API.
    provider: Mapped[str] = mapped_column(String(20), default="twilio", nullable=False)
    provider_call_sid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Same session id the ExecutionContext is cached under in Redis
    # (see services/call_session_service.py) — reuses the Workflow Runtime
    # exactly the way chat_ws.py / whatsapp.py already do.
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Voice/speed/language actually used for this call (snapshot at call
    # start, so changing defaults later never rewrites history).
    ai_voice_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ai_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_speed: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en-US", nullable=False)

    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_provider_sid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # NEW (Voice AI Part 4): short AI-generated summary of the call,
    # generated from the transcript once the call ends (see
    # services/call_summary_service.py). Nullable — a call with no
    # transcript (e.g. missed/failed) never gets one.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # How many times the caller successfully interrupted (barged-in on) the
    # AI while it was speaking during this call.
    interrupted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Set true the moment AI Engine/Knowledge Base fails to answer and the
    # fast-fallback message is played (see call_session_service.py).
    fallback_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    handed_off_to_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    transcript_entries: Mapped[list["CallTranscriptEntry"]] = relationship(
        "CallTranscriptEntry", back_populates="call",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="CallTranscriptEntry.sequence.asc()",
    )


class CallTranscriptEntry(Base):
    """One realtime transcript line — either what the caller said (STT
    final result) or what the AI said (the sentence chunk actually sent to
    TTS), in strict chronological order via `sequence`."""
    __tablename__ = "call_transcript_entries"

    __table_args__ = (
        Index("idx_call_transcript_call_id", "call_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # caller | ai | system — "system" covers barge-in markers, fallback
    # notices, and handoff notices so the transcript reads as one timeline.
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # True for an AI sentence that was cut off mid-utterance by a barge-in
    # (kept in the transcript, but visually distinguishable in the UI).
    was_interrupted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # NEW (Voice AI Part 4): only set on role="ai" entries — milliseconds
    # from the caller's utterance finishing (STT `final` event) to the
    # first audio frame of the AI's spoken reply. Backs the "Average
    # response time" analytics card. Null for caller/system entries and
    # for any AI entry produced before this was added.
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    call: Mapped["Call"] = relationship("Call", back_populates="transcript_entries", passive_deletes=True)
