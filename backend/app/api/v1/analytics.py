"""
ThunderBots Analytics API
NEW (Analytics Dashboard). Every endpoint here is read-only and scoped to
the authenticated user's own chatbots/conversations — same ownership model
as workflows.py/history.py/knowledge.py. Nothing here touches Auth,
Workflow Runtime, Knowledge Base, AI Providers, Deployment, or Builder code.
"""
import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services import analytics_service as svc

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/overview")
async def overview(
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.get_overview(db, str(current_user.id), range, start, end)


@router.get("/charts/{metric}")
async def chart(
    metric: str,
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if metric not in {"conversations", "messages", "active_users", "response_time"}:
        raise HTTPException(status_code=404, detail=f"Unknown chart metric: {metric}")
    return {"metric": metric, "series": await svc.get_timeseries(db, str(current_user.id), metric, range, start, end)}


@router.get("/traffic-sources")
async def traffic_sources(
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"sources": await svc.get_traffic_sources(db, str(current_user.id), range, start, end)}


@router.get("/top-bots")
async def top_bots(
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"bots": await svc.get_top_bots(db, str(current_user.id), range, start, end, limit)}


@router.get("/top-documents")
async def top_documents(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"documents": await svc.get_top_documents(db, str(current_user.id), limit)}


@router.get("/kb-usage")
async def kb_usage(
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.get_kb_usage(db, str(current_user.id), range, start, end)


@router.get("/provider-usage")
async def provider_usage(
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"providers": await svc.get_provider_usage(db, str(current_user.id), range, start, end)}


@router.get("/performance")
async def performance(
    range: str = Query("7d", pattern="^(today|7d|30d|90d|custom)$"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.get_performance(db, str(current_user.id), range, start, end)


@router.get("/realtime")
async def realtime(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.get_realtime(db, str(current_user.id))


@router.get("/conversations")
async def conversations(
    search: Optional[str] = None,
    workflow_id: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.list_conversations(
        db, str(current_user.id), search=search, workflow_id=workflow_id, source=source,
        status=status, start=start, end=end, page=page, page_size=page_size,
    )


@router.get("/conversations/export/csv")
async def export_csv(
    search: Optional[str] = None,
    workflow_id: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await svc.list_conversations(
        db, str(current_user.id), search=search, workflow_id=workflow_id, source=source,
        status=status, start=start, end=end, page=1, page_size=10000,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "session_id", "workflow_name", "source", "status", "message_count",
        "user_messages", "bot_messages", "errors", "avg_response_time_ms",
        "satisfaction_rating", "is_returning", "started_at", "last_activity_at", "ended_at",
    ])
    for c in result["items"]:
        writer.writerow([
            c["id"], c["session_id"], c["workflow_name"], c["source"], c["status"],
            c["message_count"], c["user_message_count"], c["bot_message_count"], c["error_count"],
            c["avg_response_time_ms"], c["satisfaction_rating"], c["is_returning"],
            c["started_at"], c["last_activity_at"], c["ended_at"],
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=conversations.csv"},
    )


@router.get("/conversations/export/json")
async def export_json(
    search: Optional[str] = None,
    workflow_id: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await svc.list_conversations(
        db, str(current_user.id), search=search, workflow_id=workflow_id, source=source,
        status=status, start=start, end=end, page=1, page_size=10000,
    )
    payload = json.dumps(result["items"], indent=2, default=str)
    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=conversations.json"},
    )


# NOTE: this catch-all-by-id route MUST be registered after the literal
# /conversations/export/* routes above — FastAPI matches path operations in
# declaration order, and {conversation_id} would otherwise swallow "export".
@router.get("/conversations/{conversation_id}")
async def conversation_detail(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = await svc.get_conversation_detail(db, str(current_user.id), conversation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


class SatisfactionRating(BaseModel):
    session_id: str
    rating: int


@router.post("/satisfaction")
async def submit_satisfaction(payload: SatisfactionRating):
    """Public endpoint (no auth) — called from the end-user chat widget/page
    to record a 1-5 satisfaction rating for their own session. Ready for
    future ratings collection; does not require the visitor to be logged in."""
    if not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=400, detail="rating must be between 1 and 5")
    ok = await svc.record_rating(payload.session_id, payload.rating)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}
