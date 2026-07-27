"""
Live Agent — WebSocket connection registry

Two independent in-process registries (dict/set based):

1. Visitor sockets: session_id -> the visitor's already-open chat_ws.py
   WebSocket. Registered/unregistered by chat_ws.py itself (two extra lines
   at connect/disconnect). Used to push human-agent chat messages and
   join/leave notices into the *same* socket the visitor is already using —
   no second connection, no protocol change for the widget beyond a couple
   of new `type` values it already safely ignores today.

2. Agent dashboard sockets: owner_id -> set of open dashboard WebSockets
   (api/ws/live_agent_ws.py). Used to push live queue/assignment/message
   events to every agent watching that workspace's dashboard.

HORIZONTAL-SCALING FIX (v107)
──────────────────────────────
Previously these registries were purely in-process: correct only for a
single-worker deployment. Behind a load balancer with multiple app workers
or replicas — exactly the "1,000+ concurrent users" / horizontal-scaling
target this audit is for — a visitor's WebSocket and the agent's dashboard
WebSocket can land on *different* processes entirely, so a message sent to
"the visitor" or broadcast to "the owner's agents" would silently vanish
whenever the sender and the socket-holder aren't the same worker.

Fixed with a lightweight Redis pub/sub bridge, reusing the Redis instance
already required by CacheService — no new infra dependency:
  - Every send still delivers immediately to a *local* socket if this
    worker happens to hold it (zero added latency for the common
    single-worker/dev case).
  - Every send also publishes the payload to a Redis channel keyed by
    session_id / owner_id. All other workers are subscribed (via
    `start_cross_worker_bridge()`, started once at app startup) and
    re-deliver to their own local socket if they hold it.
  - Each published payload is tagged with this process's `_WORKER_ID` so a
    worker never re-delivers its own message a second time when its pub/sub
    subscription echoes it back.
  - Fails open exactly like CacheService/rate_limiter: if Redis is
    unavailable, cross-worker delivery is simply skipped — local, same-
    process delivery (the only thing that worked before this fix) still
    works unchanged.
"""
import asyncio
import json
import logging
import uuid
from typing import Any

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_visitor_sockets: dict[str, Any] = {}
_agent_sockets: dict[str, set] = {}

_WORKER_ID = uuid.uuid4().hex
_VISITOR_CHANNEL_PREFIX = "wsbridge:visitor:"
_OWNER_CHANNEL_PREFIX = "wsbridge:owner:"

_listener_task: "asyncio.Task | None" = None


def register_visitor(session_id: str, websocket: Any) -> None:
    _visitor_sockets[session_id] = websocket


def unregister_visitor(session_id: str) -> None:
    _visitor_sockets.pop(session_id, None)


async def _deliver_to_local_visitor(session_id: str, payload: dict) -> bool:
    ws = _visitor_sockets.get(session_id)
    if not ws:
        return False
    try:
        await ws.send_json(payload)
        return True
    except Exception as e:
        logger.debug(f"Live Agent: failed to push to visitor session={session_id}: {e}")
        return False


async def send_to_visitor(session_id: str, payload: dict) -> bool:
    delivered = await _deliver_to_local_visitor(session_id, payload)
    await _publish(_VISITOR_CHANNEL_PREFIX + session_id, payload)
    return delivered


def register_agent_dashboard(owner_id: str, websocket: Any) -> None:
    _agent_sockets.setdefault(owner_id, set()).add(websocket)


def unregister_agent_dashboard(owner_id: str, websocket: Any) -> None:
    sockets = _agent_sockets.get(owner_id)
    if sockets:
        sockets.discard(websocket)
        if not sockets:
            _agent_sockets.pop(owner_id, None)


async def _deliver_to_local_agents(owner_id: str, payload: dict) -> None:
    for ws in list(_agent_sockets.get(owner_id, ())):
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.debug(f"Live Agent: failed to push to agent dashboard owner={owner_id}: {e}")


async def broadcast_to_owner_agents(owner_id: str, payload: dict) -> None:
    await _deliver_to_local_agents(owner_id, payload)
    await _publish(_OWNER_CHANNEL_PREFIX + owner_id, payload)


async def _publish(channel: str, payload: dict) -> None:
    redis = get_redis()
    if not redis:
        return  # fail open — no Redis means single-worker-only delivery, not a crash
    try:
        envelope = json.dumps({"origin": _WORKER_ID, "payload": payload}, default=str)
        await redis.publish(channel, envelope)
    except Exception as e:
        logger.debug(f"Live Agent: pubsub publish failed for {channel}: {e}")


async def start_cross_worker_bridge() -> "asyncio.Task | None":
    """
    Call once at app startup (see main.py lifespan). Subscribes this worker
    to every visitor/owner channel and re-delivers a payload published by
    *another* worker to whichever local socket this worker happens to hold.
    No-ops (returns None) if Redis is unavailable — every other function in
    this module still works locally without it.
    """
    redis = get_redis()
    if not redis:
        logger.info("Live Agent cross-worker WS bridge disabled — Redis unavailable")
        return None

    pubsub = redis.pubsub()
    await pubsub.psubscribe(_VISITOR_CHANNEL_PREFIX + "*", _OWNER_CHANNEL_PREFIX + "*")

    async def _loop():
        try:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                try:
                    channel = message["channel"]
                    data = json.loads(message["data"])
                except Exception:
                    continue
                if data.get("origin") == _WORKER_ID:
                    continue  # this worker already delivered it locally in send_/broadcast_
                payload = data.get("payload")
                if payload is None:
                    continue
                if channel.startswith(_VISITOR_CHANNEL_PREFIX):
                    session_id = channel[len(_VISITOR_CHANNEL_PREFIX):]
                    if session_id in _visitor_sockets:
                        await _deliver_to_local_visitor(session_id, payload)
                elif channel.startswith(_OWNER_CHANNEL_PREFIX):
                    owner_id = channel[len(_OWNER_CHANNEL_PREFIX):]
                    if owner_id in _agent_sockets:
                        await _deliver_to_local_agents(owner_id, payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Live Agent cross-worker WS bridge listener stopped: {e}")

    global _listener_task
    _listener_task = asyncio.create_task(_loop())
    return _listener_task


async def stop_cross_worker_bridge() -> None:
    global _listener_task
    if _listener_task:
        _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass
        _listener_task = None
