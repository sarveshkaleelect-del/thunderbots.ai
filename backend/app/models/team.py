"""
ThunderBots Team Workspace Models (NEW)

Purely additive module — no existing table, column, or relationship is
touched. Personal Workspace (Workflow.user_id ownership) is completely
unaffected: a Workflow still belongs to exactly one User, exactly as before.
Team Workspace is a fully separate feature: a Team is its own container with
its own membership list. Nothing here changes Workflow, KnowledgeBase, or
any other existing model.

Same conventions as the rest of the codebase (see models/user.py,
models/workflow.py): UUID string PKs, ForeignKey(..., ondelete="CASCADE"),
relationship(..., passive_deletes=True) so async session.delete(...) never
triggers a lazy-load/MissingGreenlet.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Role hierarchy, most to least privileged. Stored as plain strings (not a DB
# enum) so adding a role later is a one-line change, not a migration —
# consistent with Workflow.status being String(20) rather than an enum.
TEAM_ROLES = ("owner", "admin", "editor", "viewer")

INVITE_STATUSES = ("pending", "accepted", "revoked")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The user who created the team. Kept even though the same relationship
    # is derivable from TeamMember(role="owner") — this column makes "who
    # created this team" a cheap indexed lookup with no join, and gives us a
    # stable owner reference even in the (disallowed by API, but DB-legal)
    # edge case of an owner membership row being removed some other way.
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan", passive_deletes=True
    )
    invites: Mapped[list["TeamInvite"]] = relationship(
        "TeamInvite", back_populates="team", cascade="all, delete-orphan", passive_deletes=True
    )


class TeamMember(Base):
    """One row per (team, user) membership. A user can belong to many teams —
    there is no uniqueness constraint across teams, only within one."""

    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        Index("ix_team_members_user_team", "user_id", "team_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    team: Mapped["Team"] = relationship("Team", back_populates="members", passive_deletes=True)
    user: Mapped["User"] = relationship("User", passive_deletes=True)


class TeamInvite(Base):
    """A pending (or resolved) invitation by email. Deliberately decoupled
    from User — the invited person may not have a ThunderBots account yet.
    Accepting an invite (by a logged-in user whose email matches) creates the
    TeamMember row and flips status to 'accepted'."""

    __tablename__ = "team_invites"
    __table_args__ = (
        Index("ix_team_invites_email_status", "email", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    invited_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    team: Mapped["Team"] = relationship("Team", back_populates="invites", passive_deletes=True)
