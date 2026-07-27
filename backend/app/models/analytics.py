"""
ThunderBots Analytics Models
NEW (Analytics Dashboard): Conversation & Message are the two tables backing
every metric on the Analytics Dashboard — overview cards, time-series charts,
conversation history/search/export, traffic sources, top bots, KB usage,
AI provider usage and performance (latency/errors).

Design notes:
- Both tables denormalize `owner_id` (the workflow's owner) alongside the
  proper `workflow_id` / `conversation_id` foreign keys. Every analytics
  query is scoped to "the current user's bots", and querying/filtering
  directly on owner_id avoids a join through `workflows` on every single
  dashboard request.
- All FKs use ondelete="CASCADE" + passive_deletes=True on relationships,
  matching the pattern already established in models/workflow.py and
  models/user.py — so deleting a user or workflow cleanly cascades into
  analytics data with no Python-side lazy-load required.
- This module is purely additive: it does not alter any existing table,
  model, or relationship. `User.workflows` / `Workflow.*` etc. are untouched.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Conversation(Base):
    """One conversation = one chat session (session_id) against one workflow."""
    __tablename__ = "conversations"

    __table_args__ = (
        Index("idx_conv_owner_started", "owner_id", "started_at"),
        Index("idx_conv_workflow_started", "workflow_id", "started_at"),
        Index("idx_conv_owner_source", "owner_id", "source"),
        Index("idx_conv_visitor", "owner_id", "visitor_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Unique per chat session (matches ExecutionContext.session_id / WS session_id)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # website | embed_widget | direct | api | whatsapp | telegram
    source: Mapped[str] = mapped_column(String(20), default="direct", index=True)

    # Best-effort visitor fingerprint (hashed IP+UA) used only to compute
    # "Active Users" / "Returning Users" — never stores raw PII.
    visitor_key: Mapped[str | None] = mapped_column(String(64), index=True)
    is_returning: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active | ended

    message_count: Mapped[int] = mapped_column(Integer, default=0)
    user_message_count: Mapped[int] = mapped_column(Integer, default=0)
    bot_message_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    first_response_time_ms: Mapped[int | None] = mapped_column(Integer)
    avg_response_time_ms: Mapped[float | None] = mapped_column(Float)

    # 1-5 star rating — ready for future ratings collection; null until then.
    satisfaction_rating: Mapped[int | None] = mapped_column(Integer)

    meta: Mapped[dict] = mapped_column(JSONB, default=dict)  # user_agent, referrer, ip_country, etc.

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workflow: Mapped["Workflow"] = relationship("Workflow", passive_deletes=True)  # noqa: F821
    owner: Mapped["User"] = relationship("User", passive_deletes=True)  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        passive_deletes=True, order_by="Message.created_at",
    )


class Message(Base):
    """One row per chat turn side (a user message OR a bot response)."""
    __tablename__ = "messages"

    __table_args__ = (
        Index("idx_msg_owner_created", "owner_id", "created_at"),
        Index("idx_msg_workflow_created", "workflow_id", "created_at"),
        Index("idx_msg_owner_role", "owner_id", "role"),
        Index("idx_msg_owner_provider", "owner_id", "provider"),
        Index("idx_msg_owner_error", "owner_id", "is_error"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | bot | system
    content: Mapped[str] = mapped_column(Text, default="")

    node_id: Mapped[str | None] = mapped_column(String(100))
    node_type: Mapped[str | None] = mapped_column(String(50), index=True)

    # Populated only for bot messages produced by an AI Agent node.
    provider: Mapped[str | None] = mapped_column(String(30), index=True)  # openai | gemini | claude
    model: Mapped[str | None] = mapped_column(String(100))

    # End-to-end turn latency in milliseconds, measured at the API boundary.
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    is_error: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    citations: Mapped[list] = mapped_column(JSONB, default=list)  # [{source, document, score}, ...]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages", passive_deletes=True
    )
