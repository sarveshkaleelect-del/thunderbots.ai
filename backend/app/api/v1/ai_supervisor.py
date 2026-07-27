"""
ThunderBots AI Supervisor Dashboard — API (foundation + final phase)

Every route requires an authenticated User (get_current_user — identical to
analytics.py and live_agent.py) and is scoped to that user's own
conversations/workspace. Foundation routes (list/detail/pause/resume/take
over/return-to-AI/reply-as-human/notes/review) compose existing
Conversation/Message/LiveAgentHandoff/Workflow data. Final-phase routes add
assign/reassign, close/reopen, tags, priority, pin, export, activity
history, team activity, and bulk actions via
app/services/ai_supervisor_service.py.

Does not touch Builder, Runtime, Workflow Engine, AI Engine, Auth, or any
existing channel integration route/service.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.ai_supervisor import PRIORITY_LEVELS
from app.services import ai_supervisor_service as svc

router = APIRouter()
logger = logging.getLogger(__name__)


class ManualMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class NoteRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ReviewRequest(BaseModel):
    verdict: str = Field(pattern="^(correct|incorrect)$")


class AssignRequest(BaseModel):
    agent_id: str


class PriorityRequest(BaseModel):
    priority: str = Field(pattern="^(low|medium|high|critical)$")


class TagRequest(BaseModel):
    tag: str = Field(min_length=1, max_length=50)


class PinRequest(BaseModel):
    pinned: bool = True


class BulkCloseRequest(BaseModel):
    conversation_ids: list[str] = Field(min_length=1, max_length=200)


class BulkAssignRequest(BaseModel):
    conversation_ids: list[str] = Field(min_length=1, max_length=200)
    agent_id: str


class BulkTagRequest(BaseModel):
    conversation_ids: list[str] = Field(min_length=1, max_length=200)
    tag: str = Field(min_length=1, max_length=50)


class BulkExportRequest(BaseModel):
    conversation_ids: list[str] = Field(min_length=1, max_length=200)


@router.get("/stats")
async def get_stats(
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.get_stats(db, str(current_user.id), start=start, end=end)


@router.get("/conversations")
async def get_conversations(
    state: Optional[str] = Query(None, pattern="^(active|closed)$"),
    mode: Optional[str] = Query(None, pattern="^(human|ai_only)$"),
    channel: Optional[str] = None,
    search: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    priority: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    tag: Optional[str] = None,
    pinned_only: bool = False,
    assigned_agent_id: Optional[str] = None,
    supervisor_closed: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.list_conversations(
        db, str(current_user.id), state=state, mode=mode, channel=channel,
        search=search, start=start, end=end, priority=priority, tag=tag,
        pinned_only=pinned_only, assigned_agent_id=assigned_agent_id,
        supervisor_closed=supervisor_closed, page=page, page_size=page_size,
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = await svc.get_conversation_detail(db, str(current_user.id), conversation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


# ── Interaction controls (NEW) ────────────────────────────────────────────
# All routes below write state and therefore call services/ai_supervisor_
# service.py's action wrappers, which in turn delegate to the existing
# services/live_agent_service.py handoff state machine wherever possible
# (pause/resume/take-over/return-to-AI/manual message). Auth and ownership
# scoping follow the exact same get_current_user + owner_id convention as
# every read route above and as api/v1/live_agent.py.

@router.post("/conversations/{conversation_id}/pause")
async def pause_ai_replies(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.pause_ai_replies(db, str(current_user.id), conversation_id, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/resume")
async def resume_ai_replies(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.resume_ai_replies(db, str(current_user.id), conversation_id, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/take-over")
async def take_over_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.take_over_conversation(db, str(current_user.id), conversation_id, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/return-to-ai")
async def return_conversation_to_ai(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.return_conversation_to_ai(db, str(current_user.id), conversation_id, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/messages")
async def send_manual_message(
    conversation_id: str,
    body: ManualMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message manually while the owner has taken over — requires
    the conversation to already be (or become) handoff-owned; mirrors
    api/v1/live_agent.py's send_message route exactly."""
    try:
        return await svc.send_manual_message(db, str(current_user.id), conversation_id, str(current_user.id), body.content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/conversations/{conversation_id}/notes")
async def get_notes(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"items": await svc.list_notes(db, str(current_user.id), conversation_id)}


@router.post("/conversations/{conversation_id}/notes")
async def add_note(
    conversation_id: str,
    body: NoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Internal, team-only note — never sent to the visitor/customer or
    through any channel; only ever read back via the routes above."""
    try:
        return await svc.add_note(db, str(current_user.id), conversation_id, str(current_user.id), body.content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/messages/{message_id}/review")
async def review_message(
    message_id: str,
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single AI reply Correct/Incorrect for QA. Upsert — re-marking
    a reply updates the existing verdict instead of stacking rows."""
    try:
        return await svc.set_message_review(db, str(current_user.id), message_id, str(current_user.id), body.verdict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Final phase: assign/reassign, close/reopen, tags, priority, pin,
# export, activity history, team activity, bulk actions (NEW) ────────────
# Every route below follows the exact same auth (get_current_user) +
# ownership scoping (owner_id == current_user.id) convention as every
# route above. None of these touch Builder, Runtime, Workflow Engine, AI
# Engine, Auth, or any existing channel integration.

@router.get("/agents")
async def get_assignable_agents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Everyone assignable to a conversation: the workspace owner plus every
    team member — not only agents who already have presence data."""
    return {"items": await svc.list_assignable_agents(db, str(current_user.id))}


@router.post("/conversations/{conversation_id}/assign")
async def assign_conversation(
    conversation_id: str,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign or reassign a conversation to any workspace agent."""
    try:
        return await svc.assign_conversation(db, str(current_user.id), conversation_id, str(current_user.id), body.agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.close_conversation(db, str(current_user.id), conversation_id, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{conversation_id}/reopen")
async def reopen_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.reopen_conversation(db, str(current_user.id), conversation_id, str(current_user.id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/conversations/{conversation_id}/priority")
async def set_priority(
    conversation_id: str,
    body: PriorityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.set_priority(db, str(current_user.id), conversation_id, str(current_user.id), body.priority)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/conversations/{conversation_id}/tags")
async def add_tag(
    conversation_id: str,
    body: TagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.add_tag(db, str(current_user.id), conversation_id, str(current_user.id), body.tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/conversations/{conversation_id}/tags/{tag}")
async def remove_tag(
    conversation_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.remove_tag(db, str(current_user.id), conversation_id, str(current_user.id), tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/conversations/{conversation_id}/pin")
async def set_pinned(
    conversation_id: str,
    body: PinRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await svc.set_pinned(db, str(current_user.id), conversation_id, str(current_user.id), body.pinned)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/conversations/{conversation_id}/activity")
async def get_activity(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete activity history for one conversation — every supervisor
    action (assign/reassign, close/reopen, tags, priority, pin, export),
    distinct from the chat-thread timeline returned by GET /conversations/{id}."""
    try:
        return {"items": await svc.list_activity(db, str(current_user.id), conversation_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/team-activity")
async def get_team_activity(
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Team activity panel: agent presence/load + the most recent
    supervisor actions across the whole workspace."""
    return await svc.team_activity(db, str(current_user.id), limit=limit)


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("json", pattern="^(json|html|pdf)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """format=json returns the structured transcript as a downloadable
    JSON file. format=html|pdf renders the same payload into a print-ready
    HTML document (open it, then browser Print ➜ Save as PDF) — see
    services/ai_supervisor_service.render_export_html for the PDF-ready
    architecture note."""
    try:
        payload = await svc.export_conversation(db, str(current_user.id), conversation_id, str(current_user.id), fmt=format)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if format in ("html", "pdf"):
        html = svc.render_export_html(payload)
        return Response(content=html, media_type="text/html")
    return payload


@router.post("/conversations/bulk-close")
async def bulk_close(
    body: BulkCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.bulk_close(db, str(current_user.id), str(current_user.id), body.conversation_ids)


@router.post("/conversations/bulk-assign")
async def bulk_assign(
    body: BulkAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.bulk_assign(db, str(current_user.id), str(current_user.id), body.conversation_ids, body.agent_id)


@router.post("/conversations/bulk-tags")
async def bulk_tag(
    body: BulkTagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.bulk_tag(db, str(current_user.id), str(current_user.id), body.conversation_ids, body.tag)


@router.post("/conversations/bulk-export")
async def bulk_export(
    body: BulkExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await svc.bulk_export(db, str(current_user.id), str(current_user.id), body.conversation_ids)
