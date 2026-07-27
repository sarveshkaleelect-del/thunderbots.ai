"""
ThunderBots Live Agent API (NEW)

Every route requires an authenticated User (get_current_user — same as the
rest of the app). Routes are scoped to a `owner_id` workspace: it defaults
to the caller's own user id (a solo bot owner acting as their own agent),
and also accepts an explicit `owner_id` query param for a *team* member
acting as an agent for another user's workspace — validated by reusing the
existing Team/TeamMember model (any role is enough to act as a live agent;
inviting/removing team members is unchanged, handled entirely by
api/v1/teams.py).

Does not touch Builder, Workflow Engine, Runtime, or AI Engine — reads/
writes only agent_profiles, live_agent_handoffs, and the pre-existing
conversations/messages tables.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.team import Team, TeamMember
from app.services import live_agent_service as svc

router = APIRouter()
logger = logging.getLogger(__name__)


async def resolve_owner_scope(
    owner_id: Optional[str] = Query(None, description="Workspace owner id; defaults to the caller"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> str:
    if not owner_id or owner_id == user.id:
        return user.id
    # Team member acting as a live agent for another user's workspace —
    # reuses the existing Team model; any membership role is sufficient.
    result = await db.execute(
        select(TeamMember).join(Team, Team.id == TeamMember.team_id)
        .where(Team.created_by == owner_id, TeamMember.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace's team")
    return owner_id


class AgentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(online|busy|offline)$")
    max_concurrent_chats: Optional[int] = Field(default=None, ge=1, le=50)


class TakeOverRequest(BaseModel):
    pass


class AgentMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class RequestHandoffBody(BaseModel):
    session_id: str
    workflow_id: str
    reason: Optional[str] = None
    channel: str = "web_chat"


# ── Agent status ─────────────────────────────────────────────────────────

@router.get("/agents")
async def get_agents(owner_id: str = Depends(resolve_owner_scope), db: AsyncSession = Depends(get_db)):
    return {"agents": await svc.list_agents(db, owner_id=owner_id)}


@router.put("/agents/me/status")
async def update_my_status(
    body: AgentStatusUpdate,
    owner_id: str = Depends(resolve_owner_scope),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await svc.set_agent_status(
        db, owner_id=owner_id, user_id=user.id, status=body.status,
        max_concurrent_chats=body.max_concurrent_chats,
    )
    return {
        "id": profile.id, "status": profile.status,
        "active_chat_count": profile.active_chat_count,
        "max_concurrent_chats": profile.max_concurrent_chats,
    }


# ── Dashboard ────────────────────────────────────────────────────────────

@router.get("/dashboard/stats")
async def get_dashboard_stats(owner_id: str = Depends(resolve_owner_scope), db: AsyncSession = Depends(get_db)):
    return await svc.dashboard_stats(db, owner_id=owner_id)


@router.get("/conversations")
async def get_conversations(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(ai|waiting|active|closed)$"),
    channel: Optional[str] = None,
    agent_id: Optional[str] = None,
    search: str = "",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    owner_id: str = Depends(resolve_owner_scope),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_conversations(
        db, owner_id=owner_id, status=status_filter, channel=channel, agent_id=agent_id,
        search=search, limit=limit, offset=offset,
    )


@router.get("/conversations/{handoff_id}")
async def get_conversation(
    handoff_id: str, owner_id: str = Depends(resolve_owner_scope), db: AsyncSession = Depends(get_db),
):
    try:
        return await svc.get_conversation_detail(db, handoff_id=handoff_id, owner_id=owner_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Handoff actions ──────────────────────────────────────────────────────

@router.post("/handoff/request")
async def request_handoff(
    body: RequestHandoffBody, owner_id: str = Depends(resolve_owner_scope),
):
    """Manual/API-triggered handoff request — the AI Agent node and the
    visitor-facing 'Talk to a human' button both ultimately call the same
    services.live_agent_service.request_handoff used here."""
    try:
        return await svc.request_handoff(
            session_id=body.session_id, workflow_id=body.workflow_id, owner_id=owner_id,
            channel=body.channel, reason=body.reason, requested_by="agent",
        )
    except Exception as e:
        logger.error(f"request_handoff failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to request handoff")


@router.post("/conversations/{handoff_id}/take-over")
async def take_over_conversation(
    handoff_id: str, owner_id: str = Depends(resolve_owner_scope), user: User = Depends(get_current_user),
):
    try:
        return await svc.take_over(handoff_id=handoff_id, agent_user_id=user.id, owner_id=owner_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{handoff_id}/return-to-ai")
async def return_conversation_to_ai(
    handoff_id: str, owner_id: str = Depends(resolve_owner_scope), user: User = Depends(get_current_user),
):
    try:
        return await svc.return_to_ai(handoff_id=handoff_id, owner_id=owner_id, actor_user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{handoff_id}/close")
async def close_conversation_route(
    handoff_id: str, owner_id: str = Depends(resolve_owner_scope),
):
    try:
        return await svc.close_conversation(handoff_id=handoff_id, owner_id=owner_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/conversations/{handoff_id}/messages")
async def send_message(
    handoff_id: str, body: AgentMessageRequest,
    owner_id: str = Depends(resolve_owner_scope), user: User = Depends(get_current_user),
):
    try:
        return await svc.send_agent_message(
            handoff_id=handoff_id, owner_id=owner_id, agent_user_id=user.id, content=body.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
