"""
ThunderBots Audit Log — service (NEW, v58)

Centralized helper for writing AuditLog rows. Every call site across the
app (auth.py, workflows.py, knowledge.py, teams.py, settings.py, admin.py)
goes through `record()` (or its sync-friendly wrapper `record_bg()` for use
with FastAPI's BackgroundTasks) so the write shape, actor resolution, and
failure handling stay consistent in exactly one place.

Design notes:
- Never blocks or fails the caller's request: `record()` wraps its own
  commit in try/except and only logs a warning on failure — an audit-log
  write error must never turn a successful login/workflow-save/etc into a
  500. This mirrors the existing best-effort patterns in this codebase
  (session_service.geolocate_ip, core/auth's session activity heartbeat).
- Background by default: every call site that already has a
  BackgroundTasks dependency injected schedules the write with
  `record_bg()` so it runs after the response is sent, adding zero latency
  to the user-facing request. Call sites without BackgroundTasks (e.g.
  /auth/login, which must return the token whether or not 2FA short-
  circuits) call `record()` directly — a single indexed INSERT is cheap
  enough not to matter there, and login is exactly the action where the
  log entry existing before the response returns has the most value.
- Append-only / tamper-resistant by convention: this module exposes only
  `record()` / `record_bg()` (INSERT) and `purge_expired()` (age-based
  DELETE for retention). There is no update_audit_log or delete-by-id
  function anywhere in the codebase — nothing can edit or selectively
  remove a row short of direct DB access.
- Actor resolution accepts either a `User` object or raw id/email/name
  strings, so it can log actions where the acting user has already been
  deleted from the request's perspective (e.g. failed login for a
  since-deleted email) or where there is no user at all (system/background
  jobs use actor_type="system").
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.services import session_service

logger = logging.getLogger(__name__)


# ── Canonical action names ───────────────────────────────────────────────
# Dotted "<resource>.<verb>" convention. resource_type stored on the row is
# derived from the prefix (see _resource_type_for). Grouped here purely for
# discoverability/typo-safety at call sites — the column itself is a plain
# string, so a new action never requires a migration.
class Action:
    # Auth
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    LOGOUT_ALL = "auth.logout_all"
    REGISTER = "auth.register"
    GOOGLE_SSO_LOGIN = "auth.google_sso_login"
    GOOGLE_SSO_LINK = "auth.google_sso_link"
    TWO_FA_ENABLED = "auth.2fa_enabled"
    TWO_FA_DISABLED = "auth.2fa_disabled"
    TWO_FA_BACKUP_CODES_REGENERATED = "auth.2fa_backup_codes_regenerated"
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"
    EMAIL_VERIFICATION_SENT = "auth.email_verification_sent"
    EMAIL_VERIFIED = "auth.email_verified"
    SESSION_REVOKED = "auth.session_revoked"

    # Team
    TEAM_CREATE = "team.create"
    TEAM_DELETE = "team.delete"
    TEAM_MEMBER_ROLE_UPDATE = "team.member_role_update"
    TEAM_MEMBER_REMOVE = "team.member_remove"
    TEAM_INVITE_CREATE = "team.invite.create"
    TEAM_INVITE_REVOKE = "team.invite.revoke"
    TEAM_INVITE_ACCEPT = "team.invite.accept"

    # Workflow
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_UPDATE = "workflow.update"
    WORKFLOW_DELETE = "workflow.delete"

    # Knowledge base
    KNOWLEDGE_BASE_CREATE = "knowledge_base.create"
    KNOWLEDGE_BASE_DELETE = "knowledge_base.delete"
    KNOWLEDGE_BASE_UPLOAD = "knowledge_base.document_upload"
    KNOWLEDGE_BASE_DOCUMENT_DELETE = "knowledge_base.document_delete"

    # AI Call Agent (Voice AI Part 4) — text KB CRUD reuses the existing
    # KNOWLEDGE_BASE_* actions above (a pasted-text entry is an ordinary
    # KBDocument); these cover the call-specific human handoff actions that
    # have no chat/Live Agent equivalent action string yet.
    CALL_AGENT_HANDOFF_TO_HUMAN = "call_agent.handoff_to_human"
    CALL_AGENT_RESUME_AI = "call_agent.resume_ai"
    CALL_AGENT_SETTINGS_UPDATE = "call_agent.settings_update"

    # API keys
    API_KEY_CREATE = "api_key.create"
    API_KEY_DELETE = "api_key.delete"

    # Billing (future-ready — no billing routes exist yet, reserved for
    # when subscription/payment endpoints are added)
    BILLING_SUBSCRIPTION_CHANGE = "billing.subscription_change"
    BILLING_PAYMENT_METHOD_CHANGE = "billing.payment_method_change"

    # Admin
    ADMIN_USER_STATUS_CHANGE = "admin.user.status_change"
    ADMIN_USER_DELETE = "admin.user.delete"
    ADMIN_BOT_DELETE = "admin.bot.delete"

    # System
    RETENTION_PURGE = "system.audit_log_retention_purge"


_RESOURCE_PREFIX_MAP = {
    "auth": "auth",
    "team": "team",
    "workflow": "workflow",
    "knowledge_base": "knowledge_base",
    "call_agent": "call_agent",
    "api_key": "api_key",
    "billing": "billing",
    "admin": "admin",
    "system": "system",
}


def _resource_type_for(action: str) -> str:
    prefix = action.split(".", 1)[0]
    return _RESOURCE_PREFIX_MAP.get(prefix, prefix or "other")


async def record(
    db: AsyncSession,
    action: str,
    *,
    actor=None,
    actor_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    actor_name: Optional[str] = None,
    actor_type: str = "user",
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    target_label: Optional[str] = None,
    status: str = "success",
    status_detail: Optional[str] = None,
    request: Optional[Request] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Writes one AuditLog row on the given session and commits it.

    Never raises — a logging failure is swallowed (and logged at WARNING)
    so it can never turn a successful user action into a 500. Pass either
    `actor` (a User ORM object) or the individual actor_* fields directly.
    """
    if actor is not None:
        actor_id = actor_id or getattr(actor, "id", None)
        actor_email = actor_email or getattr(actor, "email", None)
        actor_name = actor_name or getattr(actor, "name", None)
        if getattr(actor, "is_admin", False) and actor_type == "user":
            actor_type = "admin"

    if request is not None:
        if ip_address is None:
            ip_address = session_service.get_client_ip(request)
        if user_agent is None:
            user_agent = request.headers.get("user-agent", "")[:2000]

    entry = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        actor_name=actor_name,
        actor_type=actor_type,
        action=action,
        resource_type=_resource_type_for(action),
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        status=status,
        status_detail=(status_detail or "")[:4000] or None,
        ip_address=ip_address,
        user_agent=user_agent,
        audit_metadata=metadata or {},
    )
    try:
        db.add(entry)
        await db.commit()
    except Exception as e:
        logger.warning(f"Audit log write failed (non-fatal) for action={action}: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


async def record_standalone(action: str, **kwargs) -> None:
    """Same as `record()` but opens and closes its own DB session — for use
    from BackgroundTasks, where the original request's AsyncSession has
    already been closed by the time the background task runs."""
    try:
        async with AsyncSessionLocal() as db:
            await record(db, action, **kwargs)
    except Exception as e:
        logger.warning(f"Audit log background write failed (non-fatal) for action={action}: {e}")


def record_bg(background_tasks, action: str, **kwargs) -> None:
    """Schedules `record_standalone()` on the given FastAPI BackgroundTasks
    so the write happens after the response is sent, at zero latency cost
    to the request. Preferred call style at every route that already
    injects `background_tasks: BackgroundTasks`."""
    background_tasks.add_task(record_standalone, action, **kwargs)


# ── Retention ──────────────────────────────────────────────────────────────
# Configurable via settings.AUDIT_LOG_RETENTION_DAYS (default 365, 0/None
# disables pruning entirely — logs are then kept forever). Purely additive:
# nothing calls this automatically unless a deployment wires it into a
# scheduled job; it is exposed here so one can be added (cron, Celery beat,
# etc.) without further backend changes.
async def purge_expired(db: AsyncSession) -> int:
    """Deletes AuditLog rows older than settings.AUDIT_LOG_RETENTION_DAYS.
    Returns the number of rows deleted. No-ops (returns 0) if retention is
    unset/disabled."""
    retention_days = settings.AUDIT_LOG_RETENTION_DAYS
    if not retention_days or retention_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(select(AuditLog.id).where(AuditLog.created_at < cutoff))
    ids = [row[0] for row in result.all()]
    if not ids:
        return 0

    await db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
    await db.commit()
    logger.info(f"Audit log retention purge: deleted {len(ids)} row(s) older than {retention_days} days")
    return len(ids)
