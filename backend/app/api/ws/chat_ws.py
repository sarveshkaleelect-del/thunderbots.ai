"""
ThunderBots WebSocket Chat Handler v5
FIX: Removed the WS-side context.current_node_id write that duplicated the
     runner's own write — this was the root cause of "sometimes follows the
     wrong branch" and inconsistent multiple-choice behavior. The runner is
     now the SOLE owner of context.current_node_id during a turn.
FIX: Added a per-session asyncio.Lock so concurrent messages (e.g. rapid
     double-click) on the same session are processed strictly in order
     instead of racing against each other — this was the root cause of
     "sometimes requires double click" and "responses sometimes duplicated".
FIX: Idempotency guard — identical message sent twice within 400ms on the
     same session is treated as a duplicate click and ignored.
FIX: json.loads protected against malformed messages.
"""
import json
import time
import uuid
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.auth import verify_token
from app.core.redis import CacheService
from app.engine.runner import WorkflowRunner
from app.engine.context import ExecutionContext
from app.models.workflow import Workflow
from app.config import settings
from app.services import analytics_service
from app.services import live_agent_service
from app.services import live_agent_ws_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# FIX v5: per-session locks live in-process. For multi-worker deployments this
# should move to a Redis-based distributed lock, but for a single-worker
# deployment (the default here) this is sufficient and removes the race.
_session_locks: dict[str, asyncio.Lock] = {}


def _get_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


async def get_workflow_data(workflow_id: str, cache: CacheService) -> dict | None:
    """Fetch the LIVE DRAFT workflow from Redis cache or DB.

    This is the workflow as it currently exists in the builder — including any
    unsaved-to-publish edits. It must only ever be served to the workflow's
    own authenticated owner (see chat_websocket's access-control branch below).
    """
    cached = await cache.get(f"workflow:{workflow_id}")
    if cached:
        return cached

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
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
                    "embedding_provider": kb.embedding_provider,
                    "embedding_model": kb.embedding_model,
                }, ttl=settings.KB_CACHE_TTL)

        await cache.set(f"workflow:{workflow_id}", data, ttl=settings.WORKFLOW_CACHE_TTL)
        return data


async def get_deployed_workflow_data(workflow_id: str, cache: CacheService) -> dict | None:
    """
    Fetch the PUBLISHED SNAPSHOT for a workflow — what public/anonymous chat
    visitors should run, as opposed to get_workflow_data's live draft.

    FIX: previously the WS endpoint always served the live draft to every
    caller regardless of authentication, which meant (a) any unpublished or
    since-edited-but-not-republished draft was reachable by anyone who knew
    the workflow_id, bypassing the publish gate entirely, and (b) editing a
    published bot's draft would instantly change the live public bot before
    the owner clicked "Publish". This resolver enforces that public/anonymous
    sessions only ever see the snapshot captured at the most recent publish,
    and only when the deployment is currently active.

    Uses its own cache key (deployment:{workflow_id}) so it never collides
    with the existing workflow:{id} live-draft cache invalidated elsewhere
    (workflows.py, history.py, chat.py REST endpoint).
    """
    cached = await cache.get(f"deployment:{workflow_id}")
    if cached:
        return cached

    async with AsyncSessionLocal() as db:
        from app.models.workflow import Deployment

        result = await db.execute(
            select(Deployment).where(
                Deployment.workflow_id == workflow_id,
                Deployment.is_active == True,  # noqa: E712
            )
        )
        dep = result.scalar_one_or_none()
        if not dep:
            return None

        wf_result = await db.execute(
            select(Workflow.name, Workflow.knowledge_base_id).where(Workflow.id == workflow_id)
        )
        wf_row = wf_result.first()
        name = wf_row.name if wf_row else "Chatbot"
        kb_id = wf_row.knowledge_base_id if wf_row else None

        data = {
            "id": str(workflow_id),
            "name": name,
            "nodes": dep.deployed_nodes or [],
            "edges": dep.deployed_edges or [],
            "settings": dep.deployed_settings or {},
            "knowledge_base_id": str(kb_id) if kb_id else None,
            "owner_id": str(dep.user_id),
        }

        if kb_id:
            from app.models.knowledge import KnowledgeBase
            kb_result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            kb = kb_result.scalar_one_or_none()
            if kb:
                await cache.set(f"kb:{kb_id}", {
                    "id": str(kb.id),
                    "name": kb.name,
                    "chroma_collection": kb.chroma_collection,
                    "embedding_provider": kb.embedding_provider,
                    "embedding_model": kb.embedding_model,
                }, ttl=settings.KB_CACHE_TTL)

        await cache.set(f"deployment:{workflow_id}", data, ttl=settings.WORKFLOW_CACHE_TTL)
        return data


async def _save_context(cache: CacheService, session_id: str, context: ExecutionContext) -> None:
    await cache.set(
        f"session:{session_id}",
        context.to_dict(),
        ttl=settings.SESSION_CACHE_TTL,
    )


async def _load_context(cache: CacheService, session_id: str) -> ExecutionContext | None:
    data = await cache.get(f"session:{session_id}")
    if data:
        return ExecutionContext.from_dict(data)
    return None


@router.websocket("/chat/{workflow_id}")
async def chat_websocket(
    websocket: WebSocket,
    workflow_id: str,
    token: str = Query(None),
    session_id: str = Query(None),
):
    await websocket.accept()
    cache = CacheService()

    # NEW (Analytics): best-effort visitor fingerprint + traffic-source guess.
    # Read-only inspection of the handshake — never affects auth, routing, or
    # the runner. Falls back gracefully to "direct" when signals are absent.
    client_host = websocket.client.host if websocket.client else None
    user_agent = websocket.headers.get("user-agent")
    referer = (websocket.headers.get("referer") or websocket.headers.get("origin") or "").lower()
    visitor_key = analytics_service.hash_visitor(client_host, user_agent)
    inferred_source = "embed_widget" if "/embed/" in referer or "/api/v1/deploy/embed" in referer \
        else ("website" if referer else "direct")

    # Auth — unchanged from prior behavior: a present token must be valid,
    # absence of a token is allowed (anonymous/public callers), DEBUG mode
    # tolerates invalid tokens for local development convenience.
    user_id: str | None = None
    if token:
        user_id = verify_token(token)
        if not user_id and not settings.DEBUG:
            await websocket.send_json({"type": "error", "content": "Unauthorized: invalid or expired token"})
            await websocket.close(code=4001)
            return

    # Load workflow.
    #
    # FIX (security/correctness): the live draft (get_workflow_data) must only
    # ever be handed to the workflow's own owner — that's what the authenticated
    # in-builder Chat Tester relies on, and that behavior is preserved exactly.
    # Every other caller (no token, or a token belonging to someone else) is
    # treated as a public visitor and is routed to the published deployment
    # snapshot instead. This closes a gap where any caller who knew or guessed
    # a workflow_id could chat against an unpublished, unreviewed, or
    # since-edited-but-not-republished draft with no authorization check at all.
    try:
        workflow = await get_workflow_data(workflow_id, cache)
        is_owner = bool(workflow and user_id and workflow.get("owner_id") == user_id)
        is_owner_attempt = bool(user_id)  # a real, validated token was presented

        if not is_owner:
            workflow = await get_deployed_workflow_data(workflow_id, cache)
    except Exception as e:
        logger.error(f"Failed to load workflow {workflow_id}: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "content": f"Failed to load workflow: {str(e)}"})
        await websocket.close(code=1011)
        return

    if not workflow:
        msg = (
            "Workflow not found. It may have been deleted."
            if is_owner_attempt
            else "This bot is not published. Ask the owner to publish it from the Deploy panel."
        )
        await websocket.send_json({"type": "error", "content": msg})
        await websocket.close(code=4004)
        return

    if not workflow.get("nodes"):
        await websocket.send_json({"type": "error", "content": "This workflow has no nodes. Add a Start node to begin."})
        await websocket.close(code=4004)
        return

    new_session_id = session_id or str(uuid.uuid4())
    chat_source = "direct" if is_owner else inferred_source
    owner_id = workflow.get("owner_id")
    if session_id:
        context = await _load_context(cache, session_id) or ExecutionContext(
            session_id=new_session_id,
            workflow_id=workflow_id,
        )
        resumed = context.turn_count > 0
    else:
        context = ExecutionContext(session_id=new_session_id, workflow_id=workflow_id)
        resumed = False

    # ROOT CAUSE FIX (production-only "model not found" bug): this used to be
    # WorkflowRunner(workflow, user_id=user_id) — i.e. the CALLER's identity.
    # For the authenticated in-builder Chat Tester that's fine, since the
    # caller *is* the workflow owner (user_id == owner_id there). But every
    # public/anonymous embed-widget visitor has no token, so user_id is None,
    # and AI Agent nodes resolve their provider/model/API-key entirely
    # through app.services.ai_engine.get_provider_for_user(provider, user_id):
    # with user_id=None that function skips the per-user DB key lookup
    # entirely (see `if user_id:` there) and falls back to whatever
    # environment-level provider happens to be configured on the server —
    # frequently a *different* provider than the one the workflow owner
    # actually configured for this node (e.g. only GEMINI_API_KEY is set at
    # the environment level while the owner's own OpenAI key lives in the
    # DB). The node's `model` field (e.g. "gpt-4o-mini") is provider-specific
    # and never gets revalidated against whichever provider ends up
    # resolved, so it was silently sent to the wrong SDK — producing exactly
    # this class of error ("models/gpt-4o-mini is not found for API version
    # v1beta", i.e. an OpenAI model name sent to Gemini).
    #
    # The correct identity for AI-provider/key resolution during a chatbot
    # turn is always the workflow OWNER's — a visitor's own auth state (or
    # lack of it) must never affect which of the *owner's* provider keys run
    # the *owner's* bot. This mirrors what the WhatsApp channel webhook
    # already does correctly (WorkflowRunner(workflow, user_id=channel.user_id)
    # in app/api/v1/whatsapp.py) and what the authenticated Chat Tester does
    # implicitly (owner_id == user_id there). Using owner_id unconditionally
    # makes all three execution paths identical for provider resolution.
    runner = WorkflowRunner(workflow, user_id=owner_id)

    await websocket.send_json({
        "type": "connected",
        "session_id": new_session_id,
        "workflow": workflow["name"],
        "resumed": resumed,
    })

    # NEW (Live Agent): register this visitor's socket so a human agent's
    # messages / join-leave notices (services/live_agent_service.py, pushed
    # via live_agent_ws_manager) can be delivered on this same connection —
    # no second socket, no protocol change for the widget.
    if owner_id:
        live_agent_ws_manager.register_visitor(new_session_id, websocket)

    # FIX v5: idempotency guard state
    last_message_text: str | None = None
    last_message_time: float = 0.0
    DEDUPE_WINDOW_SECONDS = 0.4

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid message format (not valid JSON)"})
                continue

            msg_type = data.get("type", "message")
            user_message = data.get("message", "").strip()

            # NEW (Live Agent): visitor-initiated "Talk to a human" — queues
            # the conversation for a live agent without touching the AI
            # Engine/Runtime at all. Best-effort: a failure here never breaks
            # the underlying AI chat.
            if msg_type == "request_human":
                if owner_id:
                    try:
                        await live_agent_service.request_handoff(
                            session_id=new_session_id, workflow_id=workflow_id, owner_id=owner_id,
                            channel="embed_widget" if chat_source == "embed_widget" else "web_chat",
                            reason=user_message or None, requested_by="visitor",
                        )
                        await websocket.send_json({"type": "handoff_queued"})
                    except Exception as e:
                        logger.error(f"Live Agent handoff request failed: {e}", exc_info=True)
                continue

            if msg_type == "reset":
                lock = _get_lock(new_session_id)
                async with lock:
                    context.reset()
                    context.session_id = new_session_id
                    context.workflow_id = workflow_id
                    await cache.delete(f"session:{new_session_id}")
                    last_message_text = None
                    last_message_time = 0.0
                await websocket.send_json({"type": "reset", "session_id": new_session_id})
                continue

            if not user_message:
                continue

            # NEW (Live Agent): once a conversation is queued for or being
            # handled by a human, incoming visitor messages are persisted to
            # the shared conversation thread and pushed to the agent
            # dashboard instead of being run through the AI Agent/Workflow
            # Runtime. This is the only place chat_ws.py's normal AI
            # execution path is skipped, and only for sessions that were
            # explicitly handed off (see msg_type == "request_human" above
            # or an AI Agent node's own handoff trigger) — every other
            # session runs exactly as before.
            if owner_id:
                handoff_status = await live_agent_service.get_handoff_status(session_id=new_session_id)
                # NEW (AI Supervisor): "paused" is added to this exact,
                # pre-existing gate — the only place chat_ws.py ever skips
                # the AI Agent/Workflow Runtime for a session — so a
                # supervisor's "Pause AI replies" action stops AI responses
                # the same way a human take-over already does, without any
                # change to the Runtime/AI Engine itself.
                if handoff_status in ("waiting", "active", "paused"):
                    await live_agent_service.record_visitor_message(
                        session_id=new_session_id, workflow_id=workflow_id, owner_id=owner_id,
                        content=user_message,
                    )
                    continue

            # FIX v5: ignore exact-duplicate rapid sends (double-click protection)
            now = time.monotonic()
            if (
                user_message == last_message_text
                and (now - last_message_time) < DEDUPE_WINDOW_SECONDS
            ):
                logger.debug(f"Ignored duplicate message within dedupe window: {user_message!r}")
                continue
            last_message_text = user_message
            last_message_time = now

            # FIX v5: serialize all turns for this session through a lock so
            # rapid double-sends are processed one at a time against a
            # consistent context, never interleaved.
            lock = _get_lock(new_session_id)
            async with lock:
                turn_started = time.monotonic()
                pre_turn_node_id = context.current_node_id
                full_text = ""
                turn_node_type = None
                turn_citations: list = []
                turn_error = False
                turn_error_content = None
                try:
                    async for chunk in runner.stream_run(user_message, context):
                        await websocket.send_json(chunk)

                        ctype = chunk.get("type")
                        if ctype == "token":
                            full_text += chunk.get("content") or ""
                        elif ctype == "message":
                            full_text += chunk.get("content") or ""
                            turn_node_type = chunk.get("node_type") or turn_node_type
                        elif ctype == "done":
                            turn_node_type = chunk.get("node_type") or turn_node_type
                            turn_citations = chunk.get("citations") or turn_citations
                        elif ctype == "error":
                            turn_error = True
                            turn_error_content = chunk.get("content")

                        if chunk.get("type") in ("ended", "error"):
                            break

                    # Context is now solely owned/updated by the runner —
                    # no second write happens here (FIX: removed duplicate
                    # context.current_node_id assignment that used to live here).
                    await _save_context(cache, new_session_id, context)

                except Exception as e:
                    error_msg = str(e) or f"{type(e).__name__} during workflow execution"
                    logger.error(f"WS execution error workflow={workflow_id}: {error_msg}", exc_info=True)
                    turn_error = True
                    turn_error_content = error_msg
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Execution error: {error_msg}",
                    })
                finally:
                    if owner_id:
                        turn_latency_ms = int((time.monotonic() - turn_started) * 1000)
                        turn_provider = analytics_service.resolve_streamed_provider(
                            workflow, turn_node_type, pre_turn_node_id
                        )
                        await analytics_service.record_turn(
                            session_id=new_session_id, workflow_id=workflow_id, owner_id=owner_id,
                            user_message=user_message, bot_response=None if turn_error else full_text,
                            node_type=turn_node_type, provider=turn_provider, latency_ms=turn_latency_ms,
                            is_error=turn_error, error_message=turn_error_content, citations=turn_citations,
                            source=chat_source, visitor_key=visitor_key, ended=bool(context.completed),
                        )

    except WebSocketDisconnect:
        logger.debug(f"WS disconnect session={new_session_id}")
        live_agent_ws_manager.unregister_visitor(new_session_id)
    except Exception as e:
        logger.error(f"WS unexpected error: {e}", exc_info=True)
        live_agent_ws_manager.unregister_visitor(new_session_id)
        try:
            await websocket.send_json({"type": "error", "content": f"Unexpected error: {str(e)}"})
        except Exception:
            pass
    finally:
        # MEMORY-LEAK FIX (v107): previously only the WebSocketDisconnect
        # branch popped `_session_locks[new_session_id]`. Any other
        # exception (execution errors, network resets surfaced as generic
        # Exceptions, etc.) left the per-session asyncio.Lock in the dict
        # forever — under 1,000+ concurrent visitors with a nonzero error
        # rate, this dict only ever grows, tying up memory for the life of
        # the process. Moved to `finally` so every exit path — clean
        # disconnect, handled error, or unexpected error — releases it.
        _session_locks.pop(new_session_id, None)
