"""
ThunderBots Live Agent Service (NEW)

Core business logic for the Human Handoff / Live Agent module. Reuses the
existing `conversations` / `messages` tables (models/analytics.py) as the
single shared chat thread — a human agent's replies are written as ordinary
Message rows (role="agent"), interleaved with the AI's own role="bot" rows
and the visitor's role="user" rows, so conversation history is always one
consistent, chronological thread regardless of who answered.

This module never imports from or modifies app/engine/* (Workflow Runtime)
or app/services/ai_engine.py (AI Providers) — it only reads/writes its own
tables plus the pre-existing Conversation/Message tables.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.analytics import Conversation, Message
from app.models.live_agent import AgentProfile, LiveAgentHandoff
from app.models.user import User
from app.services import live_agent_ws_manager as ws_manager

logger = logging.getLogger(__name__)

ACTIVE_AGENT_STATUSES = ("waiting", "active")


def _now():
    return datetime.now(timezone.utc)


async def _get_or_create_conversation(db: AsyncSession, *, session_id: str, workflow_id: str, owner_id: str,
                                       channel: str) -> Conversation:
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if conv:
        return conv
    conv = Conversation(
        workflow_id=workflow_id, owner_id=owner_id, session_id=session_id,
        source=channel if channel in ("website", "embed_widget", "direct", "api", "whatsapp", "telegram") else "direct",
    )
    db.add(conv)
    await db.flush()
    return conv


async def _get_or_create_handoff(db: AsyncSession, *, conversation: Conversation, workflow_id: str, owner_id: str,
                                  session_id: str, channel: str) -> LiveAgentHandoff:
    result = await db.execute(
        select(LiveAgentHandoff).where(LiveAgentHandoff.conversation_id == conversation.id)
    )
    handoff = result.scalar_one_or_none()
    if handoff:
        return handoff
    handoff = LiveAgentHandoff(
        conversation_id=conversation.id, workflow_id=workflow_id, owner_id=owner_id,
        session_id=session_id, channel=channel, status="ai", last_message_at=_now(),
    )
    db.add(handoff)
    await db.flush()
    return handoff


async def _add_message(db: AsyncSession, *, conversation: Conversation, workflow_id: str, owner_id: str,
                        role: str, content: str, node_type: Optional[str] = None) -> Message:
    msg = Message(
        conversation_id=conversation.id, workflow_id=workflow_id, owner_id=owner_id,
        role=role, content=content, node_type=node_type,
    )
    db.add(msg)
    conversation.message_count = (conversation.message_count or 0) + 1
    conversation.last_activity_at = _now()
    await db.flush()
    return msg


def _serialize_handoff(h: LiveAgentHandoff, conv: Optional[Conversation] = None,
                        agent: Optional[User] = None) -> dict:
    return {
        "id": h.id,
        "conversation_id": h.conversation_id,
        "workflow_id": h.workflow_id,
        "session_id": h.session_id,
        "status": h.status,
        "channel": h.channel,
        "requested_by": h.requested_by,
        "handoff_reason": h.handoff_reason,
        "assigned_agent_id": h.assigned_agent_id,
        "assigned_agent_name": agent.name if agent else None,
        "priority": h.priority,
        "visitor_label": h.visitor_label or "Website visitor",
        "last_message_preview": h.last_message_preview,
        "last_message_at": h.last_message_at.isoformat() if h.last_message_at else None,
        "requested_at": h.requested_at.isoformat() if h.requested_at else None,
        "assigned_at": h.assigned_at.isoformat() if h.assigned_at else None,
        "closed_at": h.closed_at.isoformat() if h.closed_at else None,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "message_count": conv.message_count if conv else None,
    }


def _serialize_message(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "node_type": m.node_type,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ── Agent status ─────────────────────────────────────────────────────────

async def set_agent_status(db: AsyncSession, *, owner_id: str, user_id: str, status: str,
                            max_concurrent_chats: Optional[int] = None) -> AgentProfile:
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.owner_id == owner_id, AgentProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = AgentProfile(owner_id=owner_id, user_id=user_id, status="offline")
        db.add(profile)
    profile.status = status
    profile.last_seen_at = _now()
    if max_concurrent_chats is not None:
        profile.max_concurrent_chats = max_concurrent_chats
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_agents(db: AsyncSession, *, owner_id: str) -> list[dict]:
    result = await db.execute(
        select(AgentProfile, User).join(User, User.id == AgentProfile.user_id)
        .where(AgentProfile.owner_id == owner_id)
        .order_by(AgentProfile.status.asc(), User.name.asc())
    )
    rows = result.all()
    return [{
        "id": p.id, "user_id": p.user_id, "name": u.name, "email": u.email,
        "status": p.status, "active_chat_count": p.active_chat_count,
        "max_concurrent_chats": p.max_concurrent_chats,
        "last_seen_at": p.last_seen_at.isoformat() if p.last_seen_at else None,
    } for p, u in rows]


async def _pick_available_agent(db: AsyncSession, *, owner_id: str) -> Optional[AgentProfile]:
    result = await db.execute(
        select(AgentProfile)
        .where(AgentProfile.owner_id == owner_id, AgentProfile.status == "online",
               AgentProfile.active_chat_count < AgentProfile.max_concurrent_chats)
        .order_by(AgentProfile.active_chat_count.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Handoff lifecycle (called from chat_ws.py hooks, best-effort) ─────────

async def request_handoff(*, session_id: str, workflow_id: str, owner_id: str, channel: str = "web_chat",
                           reason: Optional[str] = None, requested_by: str = "visitor",
                           visitor_label: Optional[str] = None) -> dict:
    """Queues a conversation for a human agent, auto-assigning one if
    available. Owns its own DB session (fire-and-forget from the WS layer,
    mirroring services/analytics_service.record_turn)."""
    async with AsyncSessionLocal() as db:
        try:
            conv = await _get_or_create_conversation(
                db, session_id=session_id, workflow_id=workflow_id, owner_id=owner_id, channel=channel
            )
            handoff = await _get_or_create_handoff(
                db, conversation=conv, workflow_id=workflow_id, owner_id=owner_id,
                session_id=session_id, channel=channel,
            )
            if handoff.status in ("waiting", "active"):
                await db.commit()
                return _serialize_handoff(handoff, conv)

            handoff.status = "waiting"
            handoff.requested_by = requested_by
            handoff.handoff_reason = reason
            handoff.requested_at = _now()
            handoff.visitor_label = visitor_label or handoff.visitor_label
            await _add_message(
                db, conversation=conv, workflow_id=workflow_id, owner_id=owner_id,
                role="system", content="Handoff requested — waiting for a human agent.",
                node_type="handoff_requested",
            )

            agent = await _pick_available_agent(db, owner_id=owner_id)
            await db.commit()
            await db.refresh(handoff)

            await ws_manager.broadcast_to_owner_agents(owner_id, {
                "type": "handoff_waiting", "handoff": _serialize_handoff(handoff, conv),
            })

            if agent:
                return await take_over(handoff_id=handoff.id, agent_user_id=agent.user_id, owner_id=owner_id)

            return _serialize_handoff(handoff, conv)
        except Exception as e:
            logger.error(f"Live Agent: request_handoff failed: {e}", exc_info=True)
            await db.rollback()
            raise


async def take_over(*, handoff_id: str, agent_user_id: str, owner_id: str) -> dict:
    """Manual 'Take Over' — also used for auto-assignment out of the queue."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LiveAgentHandoff).where(LiveAgentHandoff.id == handoff_id, LiveAgentHandoff.owner_id == owner_id)
        )
        handoff = result.scalar_one_or_none()
        if not handoff:
            raise ValueError("Conversation not found")

        conv_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conv = conv_result.scalar_one_or_none()

        agent_result = await db.execute(select(User).where(User.id == agent_user_id))
        agent = agent_result.scalar_one_or_none()
        if not agent:
            raise ValueError("Agent not found")

        was_active = handoff.status == "active" and handoff.assigned_agent_id == agent_user_id
        if not was_active:
            handoff.status = "active"
            handoff.assigned_agent_id = agent_user_id
            handoff.assigned_at = _now()

            profile_result = await db.execute(
                select(AgentProfile).where(AgentProfile.owner_id == owner_id, AgentProfile.user_id == agent_user_id)
            )
            profile = profile_result.scalar_one_or_none()
            if not profile:
                profile = AgentProfile(owner_id=owner_id, user_id=agent_user_id, status="online")
                db.add(profile)
            profile.active_chat_count = (profile.active_chat_count or 0) + 1
            if profile.status == "offline":
                profile.status = "online"

            await _add_message(
                db, conversation=conv, workflow_id=handoff.workflow_id, owner_id=owner_id,
                role="system", content=f"{agent.name} joined the conversation.", node_type="human_joined",
            )

        await db.commit()
        await db.refresh(handoff)
        payload = _serialize_handoff(handoff, conv, agent)

        await ws_manager.send_to_visitor(handoff.session_id, {
            "type": "human_joined", "agent_name": agent.name,
        })
        await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "handoff_updated", "handoff": payload})
        return payload


async def return_to_ai(*, handoff_id: str, owner_id: str, actor_user_id: Optional[str] = None) -> dict:
    """Manual 'Return to AI'."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LiveAgentHandoff).where(LiveAgentHandoff.id == handoff_id, LiveAgentHandoff.owner_id == owner_id)
        )
        handoff = result.scalar_one_or_none()
        if not handoff:
            raise ValueError("Conversation not found")

        conv_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conv = conv_result.scalar_one_or_none()

        prev_agent_id = handoff.assigned_agent_id
        agent_name = None
        if prev_agent_id:
            agent_result = await db.execute(select(User).where(User.id == prev_agent_id))
            prev_agent = agent_result.scalar_one_or_none()
            agent_name = prev_agent.name if prev_agent else None

            profile_result = await db.execute(
                select(AgentProfile).where(AgentProfile.owner_id == owner_id, AgentProfile.user_id == prev_agent_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile and profile.active_chat_count > 0:
                profile.active_chat_count -= 1

        handoff.status = "ai"
        handoff.assigned_agent_id = None

        await _add_message(
            db, conversation=conv, workflow_id=handoff.workflow_id, owner_id=owner_id,
            role="system", content=f"{agent_name or 'The agent'} returned the conversation to the AI Agent.",
            node_type="human_left",
        )

        await db.commit()
        await db.refresh(handoff)
        payload = _serialize_handoff(handoff, conv)

        await ws_manager.send_to_visitor(handoff.session_id, {"type": "human_left"})
        await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "handoff_updated", "handoff": payload})
        return payload


async def close_conversation(*, handoff_id: str, owner_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LiveAgentHandoff).where(LiveAgentHandoff.id == handoff_id, LiveAgentHandoff.owner_id == owner_id)
        )
        handoff = result.scalar_one_or_none()
        if not handoff:
            raise ValueError("Conversation not found")

        if handoff.assigned_agent_id:
            profile_result = await db.execute(
                select(AgentProfile).where(
                    AgentProfile.owner_id == owner_id, AgentProfile.user_id == handoff.assigned_agent_id
                )
            )
            profile = profile_result.scalar_one_or_none()
            if profile and profile.active_chat_count > 0:
                profile.active_chat_count -= 1

        handoff.status = "closed"
        handoff.closed_at = _now()
        await db.commit()
        await db.refresh(handoff)
        payload = _serialize_handoff(handoff)

        await ws_manager.send_to_visitor(handoff.session_id, {"type": "human_left", "closed": True})
        await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "handoff_updated", "handoff": payload})
        return payload


async def send_agent_message(*, handoff_id: str, owner_id: str, agent_user_id: str, content: str) -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LiveAgentHandoff).where(LiveAgentHandoff.id == handoff_id, LiveAgentHandoff.owner_id == owner_id)
        )
        handoff = result.scalar_one_or_none()
        if not handoff:
            raise ValueError("Conversation not found")

        conv_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conv = conv_result.scalar_one_or_none()

        agent_result = await db.execute(select(User).where(User.id == agent_user_id))
        agent = agent_result.scalar_one_or_none()

        msg = await _add_message(
            db, conversation=conv, workflow_id=handoff.workflow_id, owner_id=owner_id,
            role="agent", content=content, node_type="human_agent",
        )
        handoff.last_message_preview = content[:200]
        handoff.last_message_at = _now()
        await db.commit()

        await ws_manager.send_to_visitor(handoff.session_id, {
            "type": "agent_message", "content": content,
            "agent_name": agent.name if agent else "Agent",
        })
        await ws_manager.broadcast_to_owner_agents(owner_id, {
            "type": "handoff_message", "handoff_id": handoff.id, "message": _serialize_message(msg),
        })

        # NEW (Telegram Integration — Part 3): a handoff that originated on
        # Telegram has no visitor WebSocket to push to (the call above is a
        # no-op for that session) — the human agent's reply must instead go
        # through the Telegram Bot API. Delegated to its own best-effort,
        # never-raising helper so behavior for every other channel is
        # completely unchanged.
        if handoff.channel == "telegram":
            try:
                from app.services import telegram_delivery
                await telegram_delivery.deliver_agent_reply(handoff.session_id, content)
            except Exception as e:  # noqa: BLE001 — must never break the dashboard reply flow
                logger.warning(f"Telegram delivery hook failed for handoff={handoff.id}: {e}")

        return _serialize_message(msg)


async def record_visitor_message(*, session_id: str, workflow_id: str, owner_id: str, content: str) -> None:
    """Called from chat_ws.py when a conversation is under active human
    handling — persists the visitor's message and notifies the dashboard.
    Never raises (best-effort, mirrors analytics_service.record_turn)."""
    async with AsyncSessionLocal() as db:
        try:
            conv = await _get_or_create_conversation(
                db, session_id=session_id, workflow_id=workflow_id, owner_id=owner_id, channel="web_chat"
            )
            handoff = await _get_or_create_handoff(
                db, conversation=conv, workflow_id=workflow_id, owner_id=owner_id,
                session_id=session_id, channel=conv.source,
            )
            msg = await _add_message(
                db, conversation=conv, workflow_id=workflow_id, owner_id=owner_id, role="user", content=content,
            )
            conv.user_message_count = (conv.user_message_count or 0) + 1
            handoff.last_message_preview = content[:200]
            handoff.last_message_at = _now()
            await db.commit()

            await ws_manager.broadcast_to_owner_agents(owner_id, {
                "type": "handoff_message", "handoff_id": handoff.id, "message": _serialize_message(msg),
            })
        except Exception as e:
            logger.error(f"Live Agent: record_visitor_message failed: {e}", exc_info=True)
            await db.rollback()


async def get_or_create_handoff_for_conversation(db: AsyncSession, *, conversation_id: str,
                                                  owner_id: str) -> Optional[LiveAgentHandoff]:
    """Public accessor (NEW, additive — no existing function body changed)
    used by the AI Supervisor module (services/ai_supervisor_service.py) so
    its interaction controls (pause/resume/take-over/return-to-AI/manual
    message) can resolve or lazily create the same 1:1 handoff overlay row
    this module already uses everywhere else, keyed off the Conversation the
    Supervisor page already has loaded instead of a handoff_id. Returns None
    if the conversation doesn't belong to owner_id."""
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        return None
    return await _get_or_create_handoff(
        db, conversation=conv, workflow_id=conv.workflow_id, owner_id=owner_id,
        session_id=conv.session_id, channel=conv.source,
    )


async def pause_ai(*, conversation_id: str, owner_id: str, actor_user_id: Optional[str] = None) -> dict:
    """AI Supervisor 'Pause AI replies' (NEW, additive). Sets the shared
    handoff overlay to a new `paused` status value — the same column
    `live_agent_handoffs.status` already used for ai|waiting|active|closed,
    with no schema change. api/ws/chat_ws.py's existing handoff-status gate
    (the single place AI/Workflow Runtime execution is ever skipped for a
    session) treats `paused` exactly like `active`: visitor messages are
    still recorded to the shared thread, but the AI Agent/Workflow Runtime
    does not run. A human can still send manual messages via take_over +
    send_agent_message while paused."""
    async with AsyncSessionLocal() as db:
        actor_name = None
        if actor_user_id:
            actor_result = await db.execute(select(User).where(User.id == actor_user_id))
            actor = actor_result.scalar_one_or_none()
            actor_name = actor.name if actor else None

        handoff = await get_or_create_handoff_for_conversation(db, conversation_id=conversation_id, owner_id=owner_id)
        if not handoff:
            raise ValueError("Conversation not found")
        conv_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conv = conv_result.scalar_one_or_none()

        if handoff.status != "paused":
            handoff.status = "paused"
            await _add_message(
                db, conversation=conv, workflow_id=handoff.workflow_id, owner_id=owner_id,
                role="system", content=f"AI replies paused by {actor_name or 'a supervisor'}.",
                node_type="ai_paused",
            )

        await db.commit()
        await db.refresh(handoff)
        payload = _serialize_handoff(handoff, conv)
        await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "handoff_updated", "handoff": payload})
        return payload


async def resume_ai(*, conversation_id: str, owner_id: str, actor_user_id: Optional[str] = None) -> dict:
    """AI Supervisor 'Resume AI replies' (NEW, additive). Only clears a
    `paused` status back to `ai` — resuming never overrides an active human
    take-over; use return_to_ai for that."""
    async with AsyncSessionLocal() as db:
        actor_name = None
        if actor_user_id:
            actor_result = await db.execute(select(User).where(User.id == actor_user_id))
            actor = actor_result.scalar_one_or_none()
            actor_name = actor.name if actor else None

        handoff = await get_or_create_handoff_for_conversation(db, conversation_id=conversation_id, owner_id=owner_id)
        if not handoff:
            raise ValueError("Conversation not found")
        conv_result = await db.execute(select(Conversation).where(Conversation.id == handoff.conversation_id))
        conv = conv_result.scalar_one_or_none()

        if handoff.status == "paused":
            handoff.status = "ai"
            await _add_message(
                db, conversation=conv, workflow_id=handoff.workflow_id, owner_id=owner_id,
                role="system", content=f"AI replies resumed by {actor_name or 'a supervisor'}.",
                node_type="ai_resumed",
            )

        await db.commit()
        await db.refresh(handoff)
        payload = _serialize_handoff(handoff, conv)
        await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "handoff_updated", "handoff": payload})
        return payload


async def get_handoff_status(*, session_id: str) -> Optional[str]:
    """Fast read used by chat_ws.py's per-message hook. Returns None if no
    handoff row exists yet for this session (i.e. plain AI conversation)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LiveAgentHandoff.status).where(LiveAgentHandoff.session_id == session_id)
        )
        row = result.first()
        return row[0] if row else None


# ── Dashboard queries (authenticated REST) ──────────────────────────────

async def list_conversations(db: AsyncSession, *, owner_id: str, status: Optional[str] = None,
                              channel: Optional[str] = None, agent_id: Optional[str] = None,
                              search: str = "", limit: int = 50, offset: int = 0) -> dict:
    stmt = select(LiveAgentHandoff, Conversation).join(
        Conversation, Conversation.id == LiveAgentHandoff.conversation_id
    ).where(LiveAgentHandoff.owner_id == owner_id)

    if status:
        stmt = stmt.where(LiveAgentHandoff.status == status)
    if channel:
        stmt = stmt.where(LiveAgentHandoff.channel == channel)
    if agent_id:
        stmt = stmt.where(LiveAgentHandoff.assigned_agent_id == agent_id)
    if search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            LiveAgentHandoff.visitor_label.ilike(like),
            LiveAgentHandoff.last_message_preview.ilike(like),
            LiveAgentHandoff.session_id.ilike(like),
        ))

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()

    stmt = stmt.order_by(LiveAgentHandoff.last_message_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.all()

    agent_ids = {h.assigned_agent_id for h, _ in rows if h.assigned_agent_id}
    agents_by_id: dict[str, User] = {}
    if agent_ids:
        agents_result = await db.execute(select(User).where(User.id.in_(agent_ids)))
        agents_by_id = {u.id: u for u in agents_result.scalars().all()}

    items = [_serialize_handoff(h, conv, agents_by_id.get(h.assigned_agent_id)) for h, conv in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def get_conversation_detail(db: AsyncSession, *, handoff_id: str, owner_id: str) -> dict:
    result = await db.execute(
        select(LiveAgentHandoff, Conversation).join(
            Conversation, Conversation.id == LiveAgentHandoff.conversation_id
        ).where(LiveAgentHandoff.id == handoff_id, LiveAgentHandoff.owner_id == owner_id)
    )
    row = result.first()
    if not row:
        raise ValueError("Conversation not found")
    handoff, conv = row

    agent = None
    if handoff.assigned_agent_id:
        agent_result = await db.execute(select(User).where(User.id == handoff.assigned_agent_id))
        agent = agent_result.scalar_one_or_none()

    messages_result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc())
    )
    messages = [_serialize_message(m) for m in messages_result.scalars().all()]

    return {"handoff": _serialize_handoff(handoff, conv, agent), "messages": messages}


async def dashboard_stats(db: AsyncSession, *, owner_id: str) -> dict:
    result = await db.execute(
        select(LiveAgentHandoff.status, func.count()).where(LiveAgentHandoff.owner_id == owner_id)
        .group_by(LiveAgentHandoff.status)
    )
    counts = {status: 0 for status in ("ai", "waiting", "active", "closed")}
    for status, count in result.all():
        counts[status] = count

    agents_result = await db.execute(
        select(AgentProfile.status, func.count()).where(AgentProfile.owner_id == owner_id)
        .group_by(AgentProfile.status)
    )
    agent_counts = {status: 0 for status in ("online", "busy", "offline")}
    for status, count in agents_result.all():
        agent_counts[status] = count

    return {
        "active_chats": counts["active"],
        "waiting_chats": counts["waiting"],
        "closed_chats": counts["closed"],
        "agents_online": agent_counts["online"],
        "agents_busy": agent_counts["busy"],
        "agents_offline": agent_counts["offline"],
    }
