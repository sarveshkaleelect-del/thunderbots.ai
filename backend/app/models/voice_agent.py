"""
ThunderBots AI Call Agent — Voice Agent Models (NEW, Voice AI Part 5)

Standalone, independent from the chatbot Workflow/Builder module. A
VoiceAgent is its own first-class entity — its own AI provider/model,
personality, goals, instructions, voice, and Knowledge Base — with no
dependency on Workflow, Deployment, or the generic KnowledgeBase/KBDocument
tables the Builder's Knowledge Base panel uses. A PhoneNumber (Part 2/3)
and the Web Voice Bubble can each be bound to a VoiceAgent instead of a
Workflow (see PhoneNumber.voice_agent_id, added alongside the existing
workflow_id for backward compatibility — nothing about the Workflow-bound
path is removed or altered).

VoiceAgentKBDocument mirrors models/knowledge.py's KBDocument shape closely
(so it can reuse app/knowledge/pipeline.py's extract/chunk/embed/index
functions unmodified — those are collection-name/text driven and know
nothing about which table owns a document) but is an entirely separate
table with its own ChromaDB collection per agent
(`voice_agent_kb_{agent_id}`), so nothing here can ever appear in, or be
touched by, the chatbot's own Knowledge Base listings.

Follows the exact same conventions as every other model in this project:
String(36) UUID PKs, ondelete="CASCADE", passive_deletes=True.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class VoiceAgent(Base):
    """A standalone AI Call Agent persona — usable by a phone number (real
    calls) and/or the Web Voice Bubble (browser calls), independently of
    any chatbot Workflow."""
    __tablename__ = "voice_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # Empty string/None == "use my default provider", same convention the
    # Builder's AI Agent node already uses (resolve_agent_provider).
    ai_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Instructions (own system-prompt surface, separate from any
    # Workflow's AI Agent node prompt) ──────────────────────────────────
    # Structured admin controls: behaviour, role, rules, business_policies,
    # tone, sales_instructions, appointment_booking_rules,
    # escalation_rules, response_restrictions. Composed into one system
    # prompt at call time (see services/call_session_service.py).
    instructions: Mapped[dict] = mapped_column(JSONB, default=dict)

    personality: Mapped[str] = mapped_column(Text, default="")
    goals: Mapped[str] = mapped_column(Text, default="")
    welcome_message: Mapped[str] = mapped_column(Text, default="")
    fallback_message: Mapped[str] = mapped_column(Text, default="")

    voice_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en-US", nullable=False)
    speaking_speed: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)

    silence_timeout_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    interrupt_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    conversation_history_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # NEW — Publish/Unpublish lifecycle status, independent of is_enabled
    # (is_enabled is the existing On/Off runtime toggle; status is a
    # separate draft-vs-published gate a builder flips explicitly once
    # they're ready to make the agent live). "draft" | "published".
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    # Pinned once the agent's Knowledge Base gets its first successful
    # ingest — same convention as KnowledgeBase.embedding_provider/model.
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    knowledge_documents: Mapped[list["VoiceAgentKBDocument"]] = relationship(
        "VoiceAgentKBDocument", back_populates="agent",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="VoiceAgentKBDocument.created_at.desc()",
    )

    @property
    def chroma_collection(self) -> str:
        return f"voice_agent_kb_{self.id}"


class VoiceAgentKBDocument(Base):
    """One Knowledge Base entry for a Voice Agent — pdf | text | faq | url.
    All source types share one ChromaDB collection per agent, mirroring
    KBDocument's "one table, several source_type values" convention."""
    __tablename__ = "voice_agent_kb_documents"

    __table_args__ = (
        Index("idx_voice_agent_kb_documents_agent_id", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("voice_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # pdf | text | faq | url
    kb_type: Mapped[str] = mapped_column(String(10), default="text", nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), default="txt", nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="processing", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    # Source of truth for text/faq entries (pdf entries only keep chunks —
    # the original file is not retained after ingest, same as KBDocument).
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Only used for kb_type="faq": [{ "question": ..., "answer": ... }, ...]
    faq_items: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Only used for kb_type="url" (future-ready — not fetched yet).
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent: Mapped["VoiceAgent"] = relationship(
        "VoiceAgent", back_populates="knowledge_documents", passive_deletes=True
    )
