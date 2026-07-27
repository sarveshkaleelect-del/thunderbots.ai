"""
ThunderBots Live Agent / Human Handoff Models (NEW)

Purely additive module — does not alter Conversation, Message, Workflow, or
any Runtime/AI Engine table. A LiveAgentHandoff row is a 1:1 overlay on an
existing `conversations` row (via conversation_id) that tracks *who owns
this conversation right now* (AI vs a specific human agent) and its queue
state. All actual chat content — from the AI, from the visitor, and from
human agents — continues to be written to the existing `messages` table
(role="user" | "bot" | "agent" | "system"), so the AI and a human share
literally the same conversation thread/history with no duplication.

AgentProfile is presence/status for a human agent (an existing User) scoped
to a bot owner's workspace (owner_id — same scoping convention as
Conversation.owner_id / Message.owner_id elsewhere in the codebase). This
lets a team (see models/team.py) have several members act as live agents
for the same workspace.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

AGENT_STATUSES = ("online", "busy", "offline")
HANDOFF_STATUSES = ("ai", "waiting", "active", "closed")


class AgentProfile(Base):
    """Live-agent presence/status for one (owner workspace, user) pair."""
    __tablename__ = "agent_profiles"

    __table_args__ = (
        UniqueConstraint("owner_id", "user_id", name="uq_agent_profile_owner_user"),
        Index("idx_agent_owner_status", "owner_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # The bot-owning workspace this agent serves (matches Conversation.owner_id).
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The human agent (a platform User — the owner themself or a team member).
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(20), default="offline", index=True)  # online|busy|offline
    max_concurrent_chats: Mapped[int] = mapped_column(Integer, default=5)
    active_chat_count: Mapped[int] = mapped_column(Integer, default=0)

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id], passive_deletes=True)  # noqa: F821
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], passive_deletes=True)  # noqa: F821


class LiveAgentHandoff(Base):
    """1:1 handoff-state overlay on a `conversations` row."""
    __tablename__ = "live_agent_handoffs"

    __table_args__ = (
        Index("idx_handoff_owner_status", "owner_id", "status"),
        Index("idx_handoff_owner_agent", "owner_id", "assigned_agent_id"),
        Index("idx_handoff_owner_updated", "owner_id", "last_message_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # ai      — AI Agent is handling the conversation (default/normal state)
    # waiting — handoff requested, queued, not yet claimed by an agent
    # active  — a human agent has taken over
    # closed  — conversation resolved/closed out of the live-agent queue
    status: Mapped[str] = mapped_column(String(20), default="ai", index=True)

    # website | embed_widget | direct | api | whatsapp | telegram | instagram —
    # mirrors Conversation.source, denormalized here for filter/query speed
    # and so future channels (WhatsApp/Instagram/Telegram/Web Chat) need no
    # schema change, only a new value.
    channel: Mapped[str] = mapped_column(String(20), default="web_chat", index=True)

    requested_by: Mapped[str | None] = mapped_column(String(20))  # ai | visitor | agent
    handoff_reason: Mapped[str | None] = mapped_column(Text)

    assigned_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    priority: Mapped[int] = mapped_column(Integer, default=0)  # higher = served first out of the queue

    visitor_label: Mapped[str | None] = mapped_column(String(255))  # best-effort display name for the queue
    last_message_preview: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", passive_deletes=True)  # noqa: F821
    assigned_agent: Mapped["User"] = relationship(
        "User", foreign_keys=[assigned_agent_id], passive_deletes=True
    )  # noqa: F821
