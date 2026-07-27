"""
ThunderBots AI Supervisor Dashboard — Write-side Models (NEW)

Purely additive module — does not alter Conversation, Message, Workflow,
LiveAgentHandoff, or any Runtime/AI Engine table. These tables back the
interaction controls on the AI Supervisor page (view/pause/resume/take
over/return-to-AI reuse the existing `live_agent_handoffs` state machine —
see services/ai_supervisor_service.py) plus the final-phase supervisor
controls (assign/reassign, close/reopen, tags, priority, pin, export,
activity history) added below:

- SupervisorNote            a free-text internal note on a conversation,
                            visible only to the team (never surfaced to the
                            visitor/customer or sent through any channel).
- MessageReview             a "Correct" / "Incorrect" verdict an owner/team
                            member attaches to one AI (`role="bot"`) reply,
                            for QA. One verdict per message (upsert), so
                            re-marking a reply just updates the existing
                            row instead of stacking rows.
- SupervisorConversationMeta a 1:1 overlay row per conversation holding the
                            genuinely-new supervisor-only fields that don't
                            belong on the shared `conversations` table:
                            tags, priority level, and pinned state. One row
                            per conversation (upsert), same overlay pattern
                            `live_agent_handoffs` already uses.
- SupervisorActivityLog     append-only audit trail of every supervisor
                            action (assign/reassign, close/reopen, tag and
                            priority changes, pin/unpin, export, bulk
                            actions) — powers "complete activity history"
                            and the team activity panel. Distinct from the
                            chat-thread timeline (Message rows), which
                            already carries customer/AI/human replies plus
                            take-over/return/pause/resume system events.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

REVIEW_VERDICTS = ("correct", "incorrect")
PRIORITY_LEVELS = ("low", "medium", "high", "critical")


class SupervisorNote(Base):
    """An internal, team-only note attached to a conversation."""
    __tablename__ = "supervisor_notes"

    __table_args__ = (
        Index("idx_supervisor_note_conv_created", "conversation_id", "created_at"),
        Index("idx_supervisor_note_owner", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized owner_id (dashboard-scoping convention shared with
    # Conversation.owner_id / LiveAgentHandoff.owner_id elsewhere).
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", passive_deletes=True)  # noqa: F821
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id], passive_deletes=True)  # noqa: F821


class MessageReview(Base):
    """A Correct/Incorrect QA verdict on a single AI reply (Message row)."""
    __tablename__ = "message_reviews"

    __table_args__ = (
        UniqueConstraint("message_id", name="uq_message_review_message"),
        Index("idx_message_review_conv", "conversation_id"),
        Index("idx_message_review_owner", "owner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    verdict: Mapped[str] = mapped_column(String(10), nullable=False)  # correct | incorrect

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    message: Mapped["Message"] = relationship("Message", passive_deletes=True)  # noqa: F821
    conversation: Mapped["Conversation"] = relationship("Conversation", passive_deletes=True)  # noqa: F821
    reviewer: Mapped["User"] = relationship("User", foreign_keys=[reviewer_id], passive_deletes=True)  # noqa: F821


class SupervisorConversationMeta(Base):
    """1:1 supervisor-only overlay row per conversation: tags, priority,
    pinned state. Created lazily on first write (get_or_create), same
    pattern `LiveAgentHandoff` uses for its own conversation overlay."""
    __tablename__ = "supervisor_conversation_meta"

    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_supervisor_meta_conversation"),
        Index("idx_supervisor_meta_owner_priority", "owner_id", "priority"),
        Index("idx_supervisor_meta_owner_pinned", "owner_id", "is_pinned"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # low | medium | high | critical — plain string, not a DB enum (same
    # convention as Team.role / Conversation.status elsewhere), so adding a
    # level later is a one-line change, not a migration.
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium", index=True)

    tags: Mapped[list] = mapped_column(JSONB, default=list)

    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Supervisor-level close/reopen is a distinct concept from a session
    # naturally ending (Conversation.status) — see services/
    # ai_supervisor_service.py close_conversation/reopen_conversation. Kept
    # here rather than overloading Conversation.status so existing
    # analytics/status semantics are never touched.
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", passive_deletes=True)  # noqa: F821


class SupervisorActivityLog(Base):
    """Append-only audit trail of every supervisor action — powers
    "complete activity history" on the conversation drawer and the team
    activity panel. Distinct from the chat-thread timeline (Message rows)."""
    __tablename__ = "supervisor_activity_log"

    __table_args__ = (
        Index("idx_supervisor_activity_conv_created", "conversation_id", "created_at"),
        Index("idx_supervisor_activity_owner_created", "owner_id", "created_at"),
        Index("idx_supervisor_activity_owner_actor", "owner_id", "actor_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # assigned | reassigned | closed | reopened | tag_added | tag_removed |
    # priority_changed | pinned | unpinned | exported | bulk_closed |
    # bulk_assigned | bulk_tagged | bulk_exported | note_added |
    # review_set | take_over | return_to_ai | paused | resumed
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", passive_deletes=True)  # noqa: F821
    actor: Mapped["User"] = relationship("User", foreign_keys=[actor_id], passive_deletes=True)  # noqa: F821
