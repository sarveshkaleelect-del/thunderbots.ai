"""
ThunderBots Audit Log — models (NEW, v58)

Purely additive module — no existing table, column, or relationship is
touched. Same conventions as models/session.py: UUID string PKs,
ForeignKey(..., ondelete="SET NULL") so a deleted user's history still
survives as an audit trail with actor_email captured verbatim at write time.

Design notes:
- Append-only / tamper-resistant by convention: nothing in this codebase
  ever UPDATEs or DELETEs an AuditLog row after insert (see
  services/audit_service.py — only `insert` statements are issued). There
  is deliberately no PATCH/PUT route for audit logs anywhere in
  api/v1/audit.py — only GET (list/export) is exposed, all gated
  get_current_admin_user. Retention/pruning (if configured) is the only
  code path that ever deletes rows, and it deletes by age, never by
  content.
- actor_id is nullable + ON DELETE SET NULL: deleting a user (admin
  "Delete user") must not cascade-delete that user's own audit history,
  or an account could erase the record of its own actions on its way out.
  actor_email/actor_name are captured as plain strings at write time so
  the log stays human-readable even after the actor row is gone.
- target_type/target_id describe *what* was acted on (e.g.
  target_type="workflow", target_id=<workflow.id>) without a hard FK —
  targets span many tables (workflows, knowledge_bases, teams, users,
  api_keys, ...) and, like actor rows, may be deleted later; the log must
  keep the pointer regardless.
- metadata_json carries action-specific structured detail (e.g. which
  fields changed, provider name, invite email) as JSONB — kept generic on
  purpose so new action types never require a schema migration.
- Indexes mirror the filters the list/export API actually supports:
  actor, action, resource/target_type, status, and created_at (range
  queries + default sort), plus a composite (action, created_at) for the
  common "all logins in the last 7 days" style query.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # ── Actor ──────────────────────────────────────────────────────────────
    # Nullable + SET NULL: a deleted user's past actions remain in the log.
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "user" | "admin" | "system" — system covers background/scheduled
    # actions (e.g. retention pruning itself) with no human actor.
    actor_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)

    # ── Action ─────────────────────────────────────────────────────────────
    # Dotted, namespaced action names, e.g. "auth.login", "workflow.delete",
    # "team.invite.create", "admin.user.disable" — see audit_service.Action
    # for the canonical list. Free-text (not an enum column) so new action
    # types never require a migration.
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Coarse grouping used for the frontend's resource filter dropdown, e.g.
    # "auth", "workflow", "knowledge_base", "team", "api_key", "billing",
    # "admin". Derived once at write time from `action`.
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # ── Target ─────────────────────────────────────────────────────────────
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Outcome ────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False, index=True)  # success | failure
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Request context ───────────────────────────────────────────────────
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), nullable=False)

    # ── Extra structured detail (action-specific) ─────────────────────────
    audit_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    actor: Mapped["User"] = relationship("User", passive_deletes=True)  # noqa: F821

    __table_args__ = (
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_resource_created", "resource_type", "created_at"),
    )
