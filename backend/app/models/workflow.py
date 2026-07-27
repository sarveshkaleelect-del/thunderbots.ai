"""
ThunderBots Workflow Models
FIX v4:
- All relationships use passive_deletes=True to avoid MissingGreenlet in async delete
- ForeignKeys use ondelete="CASCADE" so the DB handles child deletion
- Added UniqueConstraint on (workflow_id, version_number) to prevent history race condition
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    canvas_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    nodes: Mapped[list] = mapped_column(JSONB, default=list)
    edges: Mapped[list] = mapped_column(JSONB, default=list)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="SET NULL"), nullable=True
    )

    # ── Deploy Experience (draft state, edited live in the Deploy panel) ──────
    # Copied into Deployment.* at publish-time, same pattern as nodes/edges/settings.
    branding: Mapped[dict] = mapped_column(JSONB, default=dict)
    design: Mapped[dict] = mapped_column(JSONB, default=dict)
    chat_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    widget_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # FIX: passive_deletes=True tells SQLAlchemy NOT to load children before delete.
    # The DB handles cascades via ondelete="CASCADE" on the ForeignKey.
    # Without this, async session.delete(workflow) raises MissingGreenlet when it
    # tries to lazy-load history/deployment to apply Python-side cascade logic.
    user: Mapped["User"] = relationship(
        "User", back_populates="workflows", passive_deletes=True
    )
    history: Mapped[list["WorkflowHistory"]] = relationship(
        "WorkflowHistory",
        back_populates="workflow",
        cascade="all, delete-orphan",
        passive_deletes=True,  # FIX: DB cascade handles delete, no lazy load needed
    )
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship(
        "KnowledgeBase", foreign_keys=[knowledge_base_id], passive_deletes=True
    )
    deployment: Mapped["Deployment | None"] = relationship(
        "Deployment",
        back_populates="workflow",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,  # FIX: same as above
    )


class WorkflowHistory(Base):
    __tablename__ = "workflow_history"

    # FIX: UniqueConstraint on (workflow_id, version_number) prevents duplicate
    # version numbers from concurrent saves hitting the same max(version_number).
    __table_args__ = (
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version"),
        Index("idx_wh_workflow_version", "workflow_id", "version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))

    canvas_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    nodes: Mapped[list] = mapped_column(JSONB, nullable=False)
    edges: Mapped[list] = mapped_column(JSONB, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    workflow: Mapped["Workflow"] = relationship(
        "Workflow", back_populates="history", passive_deletes=True
    )


class Deployment(Base):
    """Tracks published/deployed state of a workflow."""
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    deployed_nodes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    deployed_edges: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    deployed_settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    embed_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # ── Deploy Experience snapshot (copied from Workflow.* at publish-time) ───
    branding: Mapped[dict] = mapped_column(JSONB, default=dict)
    design: Mapped[dict] = mapped_column(JSONB, default=dict)
    chat_settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workflow: Mapped["Workflow"] = relationship(
        "Workflow", back_populates="deployment", passive_deletes=True
    )
