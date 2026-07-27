"""
ThunderBots Audit Log API (NEW — v58)

Every route in this module is gated by get_current_admin_user (same
dependency api/v1/admin.py uses — is_admin=True AND is_active=True). This
module is read-only by design: GET /audit-logs (list, filtered/paginated),
GET /audit-logs/{id} (single entry detail), GET /audit-logs/export (CSV
export of the current filter set), and GET /audit-logs/actions +
/audit-logs/resource-types (distinct-value lookups that back the frontend's
filter dropdowns). There is no POST/PUT/PATCH/DELETE here — audit rows are
written only via services/audit_service.record()/record_bg() from the
action's own endpoint, and are never edited or removed through this API,
which is what keeps the log tamper-resistant/append-only from the API
surface's perspective.
"""
import csv
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_admin_user
from app.models.user import User
from app.models.audit_log import AuditLog

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_EXPORT_ROWS = 20_000  # hard ceiling so an unbounded export can't take down the DB/response


def _serialize(entry: AuditLog) -> dict:
    return {
        "id": entry.id,
        "actor_id": entry.actor_id,
        "actor_email": entry.actor_email,
        "actor_name": entry.actor_name,
        "actor_type": entry.actor_type,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "target_label": entry.target_label,
        "status": entry.status,
        "status_detail": entry.status_detail,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "request_id": entry.request_id,
        "metadata": entry.audit_metadata or {},
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def _apply_filters(
    stmt,
    *,
    search: str,
    actor_id: Optional[str],
    action: Optional[str],
    resource_type: Optional[str],
    status_filter: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
):
    if search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.actor_email.ilike(like),
                AuditLog.actor_name.ilike(like),
                AuditLog.action.ilike(like),
                AuditLog.target_label.ilike(like),
                AuditLog.target_id.ilike(like),
                AuditLog.ip_address.ilike(like),
            )
        )
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if status_filter:
        stmt = stmt.where(AuditLog.status == status_filter)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return stmt


# ── List / filter / search / paginate ───────────────────────────────────────

@router.get("")
@router.get("/")
async def list_audit_logs(
    search: str = Query("", max_length=255),
    actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    base_filters = dict(
        search=search, actor_id=actor_id, action=action, resource_type=resource_type,
        status_filter=status_filter, date_from=date_from, date_to=date_to,
    )

    count_stmt = _apply_filters(select(func.count()).select_from(AuditLog), **base_filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = _apply_filters(select(AuditLog), **base_filters)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    entries = (await db.execute(stmt)).scalars().all()

    return {
        "logs": [_serialize(e) for e in entries],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{log_id}")
async def get_audit_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    entry = await db.get(AuditLog, log_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit log entry not found")
    return _serialize(entry)


# ── Filter dropdown helpers ──────────────────────────────────────────────

@router.get("/meta/actions")
async def list_distinct_actions(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))
    return {"actions": [row[0] for row in result.all()]}


@router.get("/meta/resource-types")
async def list_distinct_resource_types(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(AuditLog.resource_type).distinct().order_by(AuditLog.resource_type))
    return {"resource_types": [row[0] for row in result.all()]}


# ── Export (CSV) ───────────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_audit_logs_csv(
    search: str = Query("", max_length=255),
    actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    base_filters = dict(
        search=search, actor_id=actor_id, action=action, resource_type=resource_type,
        status_filter=status_filter, date_from=date_from, date_to=date_to,
    )
    stmt = _apply_filters(select(AuditLog), **base_filters)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(MAX_EXPORT_ROWS)
    entries = (await db.execute(stmt)).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "created_at", "actor_email", "actor_name", "actor_type", "action",
        "resource_type", "target_type", "target_id", "target_label", "status",
        "status_detail", "ip_address", "user_agent", "request_id",
    ])
    for e in entries:
        writer.writerow([
            e.id,
            e.created_at.isoformat() if e.created_at else "",
            e.actor_email or "", e.actor_name or "", e.actor_type, e.action,
            e.resource_type, e.target_type or "", e.target_id or "", e.target_label or "",
            e.status, e.status_detail or "", e.ip_address or "", e.user_agent or "", e.request_id,
        ])
    buffer.seek(0)

    logger.info(f"Admin {admin.email} exported {len(entries)} audit log row(s) to CSV")
    filename = f"audit-log-export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
