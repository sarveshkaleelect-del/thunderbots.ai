"""
ThunderBots Chat REST API v4
FIX: WorkflowRunner receives user_id for AI key resolution.
FIX: _load_workflow returns None safely (type annotation corrected).
"""
import json
import time
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.engine.runner import WorkflowRunner
from app.engine.context import ExecutionContext
from app.models.user import User
from app.models.workflow import Workflow
from app.config import settings
from app.services import analytics_service

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None
    context: Optional[dict] = None
    stream: bool = False


async def _load_workflow(workflow_id: str, db: AsyncSession, owner_user_id: str) -> Optional[dict]:
    """SECURITY FIX: this REST endpoint requires auth (get_current_user) but
    was loading the LIVE DRAFT of *any* workflow_id regardless of who owns
    it — any logged-in platform user could run/inspect another user's
    private, unpublished workflow (including its Knowledge Base) simply by
    knowing or guessing its id. This mirrors the ownership check already
    enforced by the WebSocket chat handler (app/api/ws/chat_ws.py): the live
    draft is only ever returned to its owner."""
    cache = CacheService()
    cache_key = f"workflow:{workflow_id}"
    cached = await cache.get(cache_key)
    if cached:
        if cached.get("owner_id") != owner_user_id:
            return None
        return cached

    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == owner_user_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        return None

    data = {
        "id": str(workflow.id),
        "name": workflow.name,
        "nodes": workflow.nodes or [],
        "edges": workflow.edges or [],
        "settings": workflow.settings or {},
        "knowledge_base_id": str(workflow.knowledge_base_id) if workflow.knowledge_base_id else None,
        "owner_id": str(workflow.user_id),
    }

    if workflow.knowledge_base_id:
        from app.models.knowledge import KnowledgeBase
        kb_result = await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == workflow.knowledge_base_id)
        )
        kb = kb_result.scalar_one_or_none()
        if kb:
            await cache.set(f"kb:{kb.id}", {
                "id": str(kb.id),
                "name": kb.name,
                "chroma_collection": kb.chroma_collection,
                # ROOT CAUSE FIX: must match the shape node_handlers'
                # _get_kb_data writes on its own cache-miss path (both read
                # from the same "kb:{id}" key) — see app/knowledge/pipeline.py.
                "embedding_provider": kb.embedding_provider,
                "embedding_model": kb.embedding_model,
            }, ttl=settings.KB_CACHE_TTL)

    await cache.set(cache_key, data, ttl=settings.WORKFLOW_CACHE_TTL)
    return data


@router.post("/{workflow_id}/message")
async def chat_message(
    workflow_id: str,
    payload: ChatMessage,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _load_workflow(workflow_id, db, str(current_user.id))
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    owner_id = workflow.get("owner_id") or str(current_user.id)
    visitor_key = analytics_service.hash_visitor(
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )

    context = ExecutionContext.from_dict(payload.context or {})
    if not context.workflow_id:
        context.workflow_id = workflow_id
    if not context.session_id:
        context.session_id = payload.session_id or str(uuid.uuid4())

    # FIX: pass user_id for API key resolution
    runner = WorkflowRunner(workflow, user_id=str(current_user.id))

    if payload.stream:
        async def generate():
            started = time.monotonic()
            pre_turn_node_id = context.current_node_id
            full_text = ""
            node_type = None
            citations: list = []
            had_error = False
            error_content = None
            try:
                async for chunk in runner.stream_run(payload.message, context):
                    ctype = chunk.get("type")
                    if ctype == "token":
                        full_text += chunk.get("content") or ""
                    elif ctype == "message":
                        full_text += chunk.get("content") or ""
                        node_type = chunk.get("node_type") or node_type
                    elif ctype == "done":
                        node_type = chunk.get("node_type") or node_type
                        citations = chunk.get("citations") or citations
                    elif ctype == "error":
                        had_error = True
                        error_content = chunk.get("content")
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                error_msg = str(e).strip() or f"{type(e).__name__} during workflow execution"
                logger.error(f"SSE stream error: {error_msg}", exc_info=True)
                had_error = True
                error_content = error_msg
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
            finally:
                latency_ms = int((time.monotonic() - started) * 1000)
                provider = analytics_service.resolve_streamed_provider(workflow, node_type, pre_turn_node_id)
                await analytics_service.record_turn(
                    session_id=context.session_id, workflow_id=workflow_id, owner_id=owner_id,
                    user_message=payload.message, bot_response=None if had_error else full_text,
                    node_type=node_type, provider=provider, latency_ms=latency_ms,
                    is_error=had_error, error_message=error_content, citations=citations,
                    source="api", visitor_key=visitor_key, ended=bool(context.completed),
                )
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    started = time.monotonic()
    try:
        result = await runner.run(payload.message, context)
    except Exception as e:
        error_msg = str(e).strip() or f"{type(e).__name__} during workflow execution"
        logger.error(f"Chat message execution error workflow={workflow_id}: {error_msg}", exc_info=True)
        latency_ms = int((time.monotonic() - started) * 1000)
        await analytics_service.record_turn(
            session_id=context.session_id, workflow_id=workflow_id, owner_id=owner_id,
            user_message=payload.message, bot_response=None, latency_ms=latency_ms,
            is_error=True, error_message=error_msg, source="api", visitor_key=visitor_key,
        )
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {error_msg}")

    latency_ms = int((time.monotonic() - started) * 1000)
    await analytics_service.record_turn(
        session_id=context.session_id, workflow_id=workflow_id, owner_id=owner_id,
        user_message=payload.message, bot_response=result.get("response"),
        node_type=result.get("node_type"), provider=result.get("provider"),
        latency_ms=latency_ms, is_error=result.get("node_type") == "error",
        citations=result.get("citations", []), source="api", visitor_key=visitor_key,
        ended=result.get("ended", False),
    )

    return {
        "response": result["response"],
        "choices": result.get("choices"),
        "image": result.get("image"),
        "citations": result.get("citations", []),
        "ended": result.get("ended", False),
        "session_id": context.session_id,
        "context": result["context"],
        "node_type": result.get("node_type"),
    }
