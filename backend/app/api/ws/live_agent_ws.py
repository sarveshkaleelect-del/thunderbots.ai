"""
ThunderBots Live Agent — Dashboard WebSocket (NEW)

Push channel for the Live Agent dashboard: new waiting conversations,
assignment changes, and new messages on any conversation in the workspace.
Read-only from the client's perspective — sending messages/taking over/etc
still goes through the REST endpoints in api/v1/live_agent.py, which is what
actually mutates state and triggers the broadcast this socket delivers.
"""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.auth import verify_token
from app.models.team import Team, TeamMember
from app.services import live_agent_ws_manager as ws_manager

router = APIRouter()
logger = logging.getLogger(__name__)


async def _authorized_owner_id(user_id: str, requested_owner_id: str | None) -> str | None:
    if not requested_owner_id or requested_owner_id == user_id:
        return user_id
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TeamMember).join(Team, Team.id == TeamMember.team_id)
            .where(Team.created_by == requested_owner_id, TeamMember.user_id == user_id)
        )
        return requested_owner_id if result.scalar_one_or_none() else None


@router.websocket("/agent-dashboard")
async def agent_dashboard_ws(websocket: WebSocket, token: str = Query(...), owner_id: str = Query(None)):
    await websocket.accept()

    user_id = verify_token(token)
    if not user_id:
        await websocket.send_json({"type": "error", "content": "Unauthorized"})
        await websocket.close(code=4001)
        return

    scoped_owner_id = await _authorized_owner_id(user_id, owner_id)
    if not scoped_owner_id:
        await websocket.send_json({"type": "error", "content": "Not authorized for this workspace"})
        await websocket.close(code=4003)
        return

    ws_manager.register_agent_dashboard(scoped_owner_id, websocket)
    await websocket.send_json({"type": "connected", "owner_id": scoped_owner_id})

    try:
        while True:
            # Client never needs to send anything meaningful; just keep the
            # connection alive and tolerate pings.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Live Agent dashboard WS error: {e}")
    finally:
        ws_manager.unregister_agent_dashboard(scoped_owner_id, websocket)
