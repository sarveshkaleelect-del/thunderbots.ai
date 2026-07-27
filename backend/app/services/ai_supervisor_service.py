"""
ThunderBots AI Supervisor Dashboard — Service (NEW, foundation)

Read-only aggregation layer for the "AI Supervisor" page. This module does
NOT introduce any new tables and does NOT touch the Builder, Workflow
Engine, Runtime, AI Engine, Authentication, or any existing channel
integration code. It only *reads* data that those systems already write:

- app/models/analytics.py  (Conversation, Message)      — unchanged
- app/models/live_agent.py (LiveAgentHandoff)            — unchanged
- app/models/workflow.py   (Workflow)                    — unchanged
- app/models/whatsapp.py   (WhatsAppContact)             — unchanged
- app/models/instagram.py  (InstagramContact)            — unchanged

Every query is scoped to `owner_id` (the authenticated dashboard user),
matching the ownership convention already used by analytics_service.py
and live_agent_service.py.

Design notes / known limitations (documented rather than worked around by
touching restricted systems):

- "AI confidence" is not tracked anywhere in the AI Engine today (Message
  has no confidence column, and no node emits one). Where a bot reply was
  produced with Knowledge Base retrieval, Message.citations already stores
  a per-source relevance `score` (0-1) — see knowledge/pipeline.py
  format_citations(). We surface the AVERAGE of those scores as
  `ai_confidence` ONLY when citations are present, clearly labeled as a
  retrieval-relevance estimate, and `None` otherwise ("if available", per
  the requirement). This is a read of already-persisted data — no AI
  Engine change.
- "Customer name/email/phone" search: the platform does not collect a
  customer email anywhere for chat visitors. Name/phone are available for
  channels that already capture an identity — WhatsAppContact.profile_name
  / wa_id and InstagramContact.username, both keyed by the same session_id
  as Conversation. Web-chat visitors fall back to
  LiveAgentHandoff.visitor_label (used identically on the Live Agent page)
  or the raw session_id.
- "Human takeover" vs "AI only" reuses LiveAgentHandoff.status /
  assigned_agent_id exactly as already modeled for the Live Agent module —
  no new state machine is introduced.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, or_, and_, Text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import Conversation, Message
from app.models.live_agent import LiveAgentHandoff, AgentProfile
from app.models.workflow import Workflow
from app.models.whatsapp import WhatsAppContact
from app.models.instagram import InstagramContact
from app.models.ai_supervisor import (
    SupervisorNote, MessageReview, SupervisorConversationMeta, SupervisorActivityLog,
    PRIORITY_LEVELS,
)
from app.models.user import User
from app.models.team import Team, TeamMember
from app.services import live_agent_service

STATE_TO_CONV_STATUS = {"active": "active", "closed": "ended"}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


async def _contact_lookup(db: AsyncSession, *, owner_id: str, session_ids: list[str]) -> dict[str, dict]:
    """session_id -> {"name": str|None, "handle": str|None} best-effort
    identity, sourced from the existing WhatsApp/Instagram contact tables.
    Purely additive read; never writes."""
    if not session_ids:
        return {}
    lookup: dict[str, dict] = {}

    wa_rows = (await db.execute(
        select(WhatsAppContact.session_id, WhatsAppContact.profile_name, WhatsAppContact.wa_id)
        .join(Workflow, Workflow.id == WhatsAppContact.workflow_id)
        .where(Workflow.user_id == owner_id, WhatsAppContact.session_id.in_(session_ids))
    )).all()
    for session_id, profile_name, wa_id in wa_rows:
        lookup[session_id] = {"name": profile_name or wa_id, "handle": wa_id}

    ig_rows = (await db.execute(
        select(InstagramContact.session_id, InstagramContact.username)
        .join(Workflow, Workflow.id == InstagramContact.workflow_id)
        .where(Workflow.user_id == owner_id, InstagramContact.session_id.in_(session_ids))
    )).all()
    for session_id, username in ig_rows:
        lookup[session_id] = {"name": username or "Instagram user", "handle": username}

    return lookup


def _confidence_from_citations(citations: Optional[list]) -> Optional[float]:
    if not citations:
        return None
    scores = [c.get("score") for c in citations if isinstance(c, dict) and isinstance(c.get("score"), (int, float))]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


async def _last_messages_by_role(db: AsyncSession, *, conversation_ids: list[str], role: str) -> dict[str, Message]:
    """Latest message of a given role per conversation, from the ids given.
    Small per-page fan-out query — mirrors the Python-side grouping pattern
    already used elsewhere in this codebase (e.g. live_agent_service)."""
    if not conversation_ids:
        return {}
    rows = (await db.execute(
        select(Message).where(Message.conversation_id.in_(conversation_ids), Message.role == role)
        .order_by(Message.created_at.desc())
    )).scalars().all()
    out: dict[str, Message] = {}
    for m in rows:
        if m.conversation_id not in out:
            out[m.conversation_id] = m
    return out


async def _meta_lookup(db: AsyncSession, *, owner_id: str, conversation_ids: list[str]) -> dict[str, SupervisorConversationMeta]:
    """conversation_id -> SupervisorConversationMeta, batched (no N+1),
    same fan-out-then-dict pattern as _last_messages_by_role/_contact_lookup."""
    if not conversation_ids:
        return {}
    rows = (await db.execute(
        select(SupervisorConversationMeta).where(
            SupervisorConversationMeta.owner_id == owner_id,
            SupervisorConversationMeta.conversation_id.in_(conversation_ids),
        )
    )).scalars().all()
    return {m.conversation_id: m for m in rows}


def _meta_defaults() -> dict:
    return {"priority": "medium", "tags": [], "is_pinned": False, "is_closed": False}


def _serialize_meta(meta: Optional[SupervisorConversationMeta]) -> dict:
    if not meta:
        return _meta_defaults()
    return {
        "priority": meta.priority, "tags": meta.tags or [],
        "is_pinned": meta.is_pinned, "is_closed": meta.is_closed,
    }


async def list_conversations(
    db: AsyncSession, owner_id: str, *,
    state: Optional[str] = None,          # 'active' | 'closed'
    mode: Optional[str] = None,           # 'human' | 'ai_only'
    channel: Optional[str] = None,
    search: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    priority: Optional[str] = None,       # low | medium | high | critical (NEW)
    tag: Optional[str] = None,            # NEW — filter by a single tag
    pinned_only: bool = False,            # NEW
    assigned_agent_id: Optional[str] = None,  # NEW
    supervisor_closed: Optional[bool] = None,  # NEW — supervisor close/reopen state
    page: int = 1,
    page_size: int = 25,
) -> dict:
    conditions = [Conversation.owner_id == owner_id]

    if state:
        conv_status = STATE_TO_CONV_STATUS.get(state)
        if conv_status:
            conditions.append(Conversation.status == conv_status)
    if channel:
        conditions.append(Conversation.source == channel)
    if start:
        conditions.append(Conversation.started_at >= datetime.fromisoformat(start.replace("Z", "+00:00")))
    if end:
        conditions.append(Conversation.started_at <= datetime.fromisoformat(end.replace("Z", "+00:00")))
    if assigned_agent_id:
        conditions.append(LiveAgentHandoff.assigned_agent_id == assigned_agent_id)

    base_q = (
        select(Conversation, Workflow.name.label("workflow_name"), LiveAgentHandoff)
        .join(Workflow, Workflow.id == Conversation.workflow_id)
        .outerjoin(LiveAgentHandoff, LiveAgentHandoff.conversation_id == Conversation.id)
        .where(and_(*conditions))
    )

    if mode == "human":
        base_q = base_q.where(or_(
            LiveAgentHandoff.status.in_(("waiting", "active")),
            and_(LiveAgentHandoff.status == "closed", LiveAgentHandoff.assigned_agent_id.isnot(None)),
        ))
    elif mode == "ai_only":
        base_q = base_q.where(or_(
            LiveAgentHandoff.id.is_(None),
            LiveAgentHandoff.status == "ai",
            and_(LiveAgentHandoff.status == "closed", LiveAgentHandoff.assigned_agent_id.is_(None)),
        ))

    # ── Priority / tag / pinned / supervisor-closed filters (NEW) ────────
    # All read from supervisor_conversation_meta — an unmatched conversation
    # (no meta row yet) is treated as its default: priority="medium",
    # tags=[], is_pinned=False, is_closed=False.
    if priority or tag or pinned_only or supervisor_closed is not None:
        meta_conditions = [SupervisorConversationMeta.owner_id == owner_id]
        if priority:
            meta_conditions.append(SupervisorConversationMeta.priority == priority)
        if tag:
            meta_conditions.append(SupervisorConversationMeta.tags.contains([tag]))
        if pinned_only:
            meta_conditions.append(SupervisorConversationMeta.is_pinned.is_(True))
        if supervisor_closed is not None:
            meta_conditions.append(SupervisorConversationMeta.is_closed.is_(supervisor_closed))
        matching_conv_ids = select(SupervisorConversationMeta.conversation_id).where(*meta_conditions)
        base_q = base_q.where(Conversation.id.in_(matching_conv_ids))

    # ── Advanced search (NEW) ─────────────────────────────────────────────
    # Broadened beyond the foundation phase to also match: tags, assigned
    # agent name, and message content (customer/AI/human replies) — not
    # just customer identity/session id.
    if search and search.strip():
        like = f"%{search.strip()}%"
        contact_session_ids_wa = select(WhatsAppContact.session_id).where(
            or_(WhatsAppContact.profile_name.ilike(like), WhatsAppContact.wa_id.ilike(like))
        )
        contact_session_ids_ig = select(InstagramContact.session_id).where(
            InstagramContact.username.ilike(like)
        )
        tag_conv_ids = select(SupervisorConversationMeta.conversation_id).where(
            SupervisorConversationMeta.owner_id == owner_id,
            func.cast(SupervisorConversationMeta.tags, Text).ilike(like),
        )
        agent_conv_ids = select(LiveAgentHandoff.conversation_id).where(
            LiveAgentHandoff.assigned_agent_id.in_(
                select(User.id).where(User.name.ilike(like))
            )
        )
        message_conv_ids = select(Message.conversation_id).where(
            Message.owner_id == owner_id, Message.content.ilike(like),
        )
        base_q = base_q.where(or_(
            Conversation.session_id.ilike(like),
            LiveAgentHandoff.visitor_label.ilike(like),
            Conversation.session_id.in_(contact_session_ids_wa),
            Conversation.session_id.in_(contact_session_ids_ig),
            Conversation.id.in_(tag_conv_ids),
            Conversation.id.in_(agent_conv_ids),
            Conversation.id.in_(message_conv_ids),
        ))

    total = (await db.execute(select(func.count()).select_from(base_q.subquery()))).scalar() or 0

    # Pinned conversations surface first, then most recently active —
    # requires a left join to the meta table purely for ordering (kept
    # separate from the filter join above so unpinned/no-meta rows still
    # sort, just last).
    order_q = base_q.outerjoin(
        SupervisorConversationMeta, SupervisorConversationMeta.conversation_id == Conversation.id
    ).order_by(
        SupervisorConversationMeta.is_pinned.is_(True).desc(),
        Conversation.last_activity_at.desc(),
    )

    rows = (await db.execute(
        order_q.offset((page - 1) * page_size).limit(page_size)
    )).all()

    conv_ids = [conv.id for conv, _wf, _h in rows]
    session_ids = [conv.session_id for conv, _wf, _h in rows]
    last_user = await _last_messages_by_role(db, conversation_ids=conv_ids, role="user")
    last_bot = await _last_messages_by_role(db, conversation_ids=conv_ids, role="bot")
    contacts = await _contact_lookup(db, owner_id=owner_id, session_ids=session_ids)
    metas = await _meta_lookup(db, owner_id=owner_id, conversation_ids=conv_ids)

    agent_ids = {h.assigned_agent_id for _c, _wf, h in rows if h and h.assigned_agent_id}
    agents_by_id: dict[str, User] = {}
    if agent_ids:
        agents_result = await db.execute(select(User).where(User.id.in_(agent_ids)))
        agents_by_id = {u.id: u for u in agents_result.scalars().all()}

    items = []
    for conv, wf_name, handoff in rows:
        contact = contacts.get(conv.session_id)
        um = last_user.get(conv.id)
        bm = last_bot.get(conv.id)
        meta = metas.get(conv.id)
        is_human = bool(handoff and (
            handoff.status in ("waiting", "active")
            or (handoff.status == "closed" and handoff.assigned_agent_id)
        ))
        assigned_agent = agents_by_id.get(handoff.assigned_agent_id) if handoff and handoff.assigned_agent_id else None
        items.append({
            "id": conv.id,
            "session_id": conv.session_id,
            "workflow_id": conv.workflow_id,
            "workflow_name": wf_name,
            "channel": conv.source,
            "status": conv.status,
            "handoff_status": handoff.status if handoff else "ai",
            "is_human_takeover": is_human,
            "is_paused": bool(handoff and handoff.status == "paused"),
            "customer_display": (contact or {}).get("name") or (handoff.visitor_label if handoff else None) or f"Visitor {conv.session_id[:8]}",
            "customer_handle": (contact or {}).get("handle"),
            "assigned_agent_id": handoff.assigned_agent_id if handoff else None,
            "assigned_agent_name": assigned_agent.name if assigned_agent else None,
            "last_customer_message": um.content if um else None,
            "last_customer_message_at": _iso(um.created_at) if um else None,
            "last_ai_reply": bm.content if bm else None,
            "last_ai_reply_at": _iso(bm.created_at) if bm else None,
            "ai_confidence": _confidence_from_citations(bm.citations) if bm else None,
            "message_count": conv.message_count,
            "avg_response_time_ms": round(conv.avg_response_time_ms, 0) if conv.avg_response_time_ms else None,
            "started_at": _iso(conv.started_at),
            "last_activity_at": _iso(conv.last_activity_at),
            "ended_at": _iso(conv.ended_at),
            **_serialize_meta(meta),
        })

    return {
        "items": items, "total": total, "page": page, "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


async def get_conversation_detail(db: AsyncSession, owner_id: str, conversation_id: str) -> Optional[dict]:
    result = await db.execute(
        select(Conversation, Workflow.name.label("workflow_name"), LiveAgentHandoff)
        .join(Workflow, Workflow.id == Conversation.workflow_id)
        .outerjoin(LiveAgentHandoff, LiveAgentHandoff.conversation_id == Conversation.id)
        .where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
    )
    row = result.first()
    if not row:
        return None
    conv, wf_name, handoff = row

    contacts = await _contact_lookup(db, owner_id=owner_id, session_ids=[conv.session_id])
    contact = contacts.get(conv.session_id)

    msgs = (await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )).scalars().all()

    is_human = bool(handoff and (
        handoff.status in ("waiting", "active")
        or (handoff.status == "closed" and handoff.assigned_agent_id)
    ))
    is_paused = bool(handoff and handoff.status == "paused")

    assigned_agent_name = None
    if handoff and handoff.assigned_agent_id:
        agent_result = await db.execute(select(User).where(User.id == handoff.assigned_agent_id))
        agent = agent_result.scalar_one_or_none()
        assigned_agent_name = agent.name if agent else None

    reviews = await _reviews_by_message(db, message_ids=[m.id for m in msgs])
    notes = await list_notes(db, owner_id, conversation_id)
    meta_result = await db.execute(
        select(SupervisorConversationMeta).where(
            SupervisorConversationMeta.owner_id == owner_id,
            SupervisorConversationMeta.conversation_id == conversation_id,
        )
    )
    meta = meta_result.scalar_one_or_none()

    return {
        "id": conv.id, "session_id": conv.session_id, "workflow_id": conv.workflow_id,
        "workflow_name": wf_name, "channel": conv.source, "status": conv.status,
        "handoff_status": handoff.status if handoff else "ai",
        "is_human_takeover": is_human,
        "is_paused": is_paused,
        "assigned_agent_id": handoff.assigned_agent_id if handoff else None,
        "assigned_agent_name": assigned_agent_name,
        "customer_display": (contact or {}).get("name") or (handoff.visitor_label if handoff else None) or f"Visitor {conv.session_id[:8]}",
        "customer_handle": (contact or {}).get("handle"),
        "started_at": _iso(conv.started_at), "last_activity_at": _iso(conv.last_activity_at),
        "ended_at": _iso(conv.ended_at),
        "avg_response_time_ms": round(conv.avg_response_time_ms, 0) if conv.avg_response_time_ms else None,
        "messages": [
            {
                "id": m.id, "role": m.role, "content": m.content, "node_type": m.node_type,
                "provider": m.provider, "model": m.model, "latency_ms": m.latency_ms,
                "is_error": m.is_error,
                "ai_confidence": _confidence_from_citations(m.citations) if m.role == "bot" else None,
                "review": reviews.get(m.id),
                "created_at": _iso(m.created_at),
            }
            for m in msgs
        ],
        "notes": notes,
        **_serialize_meta(meta),
    }


async def get_stats(db: AsyncSession, owner_id: str, *, start: Optional[str] = None,
                     end: Optional[str] = None) -> dict:
    conditions = [Conversation.owner_id == owner_id]
    if start:
        conditions.append(Conversation.started_at >= datetime.fromisoformat(start.replace("Z", "+00:00")))
    if end:
        conditions.append(Conversation.started_at <= datetime.fromisoformat(end.replace("Z", "+00:00")))

    active_chats = (await db.execute(
        select(func.count(Conversation.id)).where(*conditions, Conversation.status == "active")
    )).scalar() or 0

    ended_q = (
        select(Conversation.id, LiveAgentHandoff.assigned_agent_id)
        .outerjoin(LiveAgentHandoff, LiveAgentHandoff.conversation_id == Conversation.id)
        .where(*conditions, Conversation.status == "ended")
    )
    ended_rows = (await db.execute(ended_q)).all()
    human_resolved = sum(1 for _id, agent_id in ended_rows if agent_id)
    ai_resolved = len(ended_rows) - human_resolved

    avg_resp = (await db.execute(
        select(func.avg(Conversation.avg_response_time_ms)).where(
            *conditions, Conversation.avg_response_time_ms.isnot(None)
        )
    )).scalar()

    return {
        "active_chats": active_chats,
        "ai_resolved": ai_resolved,
        "human_resolved": human_resolved,
        "avg_response_time_ms": round(avg_resp, 0) if avg_resp else 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Interaction controls (NEW) ────────────────────────────────────────────
# View: get_conversation_detail above (also powers the live-updating detail
# panel — see api/v1/ai_supervisor.py get_conversation).
# Pause / Resume / Take-over / Return-to-AI / manual message: thin wrappers
# delegating to services/live_agent_service.py, which already owns the
# shared handoff state machine and its WebSocket broadcast to the dashboard
# socket both this page and the Live Agent page subscribe to.


async def _assert_owned_conversation(db: AsyncSession, owner_id: str, conversation_id: str) -> Conversation:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise ValueError("Conversation not found")
    return conv


async def pause_ai_replies(db: AsyncSession, owner_id: str, conversation_id: str, actor_user_id: str) -> dict:
    result = await live_agent_service.pause_ai(
        conversation_id=conversation_id, owner_id=owner_id, actor_user_id=actor_user_id,
    )
    actor_name = await _user_name(db, actor_user_id)
    await _log_activity(db, owner_id, conversation_id, actor_user_id, "paused")
    await _notify(owner_id, "ai_paused", conversation_id, f"AI replies paused by {actor_name or 'a supervisor'}", severity="warning")
    return result


async def resume_ai_replies(db: AsyncSession, owner_id: str, conversation_id: str, actor_user_id: str) -> dict:
    result = await live_agent_service.resume_ai(
        conversation_id=conversation_id, owner_id=owner_id, actor_user_id=actor_user_id,
    )
    await _log_activity(db, owner_id, conversation_id, actor_user_id, "resumed")
    return result


async def take_over_conversation(db: AsyncSession, owner_id: str, conversation_id: str, agent_user_id: str) -> dict:
    handoff = await live_agent_service.get_or_create_handoff_for_conversation(
        db, conversation_id=conversation_id, owner_id=owner_id,
    )
    if not handoff:
        raise ValueError("Conversation not found")
    await db.commit()
    result = await live_agent_service.take_over(handoff_id=handoff.id, agent_user_id=agent_user_id, owner_id=owner_id)
    actor_name = await _user_name(db, agent_user_id)
    await _log_activity(db, owner_id, conversation_id, agent_user_id, "take_over")
    await _notify(owner_id, "human_takeover", conversation_id, f"{actor_name or 'A supervisor'} took over the conversation")
    return result


async def return_conversation_to_ai(db: AsyncSession, owner_id: str, conversation_id: str, actor_user_id: str) -> dict:
    handoff = await live_agent_service.get_or_create_handoff_for_conversation(
        db, conversation_id=conversation_id, owner_id=owner_id,
    )
    if not handoff:
        raise ValueError("Conversation not found")
    await db.commit()
    result = await live_agent_service.return_to_ai(handoff_id=handoff.id, owner_id=owner_id, actor_user_id=actor_user_id)
    await _log_activity(db, owner_id, conversation_id, actor_user_id, "return_to_ai")
    return result


# ── Assign / Reassign (NEW) ───────────────────────────────────────────────

async def assign_conversation(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str,
                               agent_id: str) -> dict:
    """Assign (or reassign) a conversation to any workspace agent — not
    necessarily the caller, unlike take_over_conversation above. Reuses
    live_agent_service.take_over for the actual handoff/message-count/
    broadcast bookkeeping (it already supports assigning an arbitrary
    agent_user_id); this wrapper additionally decrements the *previous*
    agent's active_chat_count on reassignment, which take_over alone does
    not do (it only ever increments the newly-assigned agent)."""
    handoff = await live_agent_service.get_or_create_handoff_for_conversation(
        db, conversation_id=conversation_id, owner_id=owner_id,
    )
    if not handoff:
        raise ValueError("Conversation not found")
    agent_result = await db.execute(select(User).where(User.id == agent_id))
    if not agent_result.scalar_one_or_none():
        raise ValueError("Agent not found")

    previous_agent_id = handoff.assigned_agent_id
    is_reassign = bool(previous_agent_id and previous_agent_id != agent_id)
    if is_reassign:
        profile_result = await db.execute(
            select(AgentProfile).where(AgentProfile.owner_id == owner_id, AgentProfile.user_id == previous_agent_id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile and profile.active_chat_count > 0:
            profile.active_chat_count -= 1
    await db.commit()

    result = await live_agent_service.take_over(handoff_id=handoff.id, agent_user_id=agent_id, owner_id=owner_id)
    event_type = "reassigned" if is_reassign else "assigned"
    await _log_activity(db, owner_id, conversation_id, actor_id, event_type, {
        "agent_id": agent_id, "agent_name": result.get("assigned_agent_name"), "previous_agent_id": previous_agent_id,
    })
    await _notify(
        owner_id, "human_takeover", conversation_id,
        f"Conversation {'reassigned' if is_reassign else 'assigned'} to {result.get('assigned_agent_name') or 'an agent'}",
    )
    return result


async def list_assignable_agents(db: AsyncSession, owner_id: str) -> list[dict]:
    """Owner + every team member of any team owner_id created (same
    Team/TeamMember scoping convention as api/v1/live_agent.py's
    resolve_owner_scope and api/v1/teams.py) — so every teammate who could
    act as a live agent is assignable here, not only those who already have
    an AgentProfile presence row from having gone online at least once."""
    owner_result = await db.execute(select(User.id, User.name, User.email).where(User.id == owner_id))
    owner_row = owner_result.first()

    member_rows = (await db.execute(
        select(User.id, User.name, User.email)
        .join(TeamMember, TeamMember.user_id == User.id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.created_by == owner_id, TeamMember.user_id != owner_id)
    )).all()

    all_rows = ([owner_row] if owner_row else []) + list(member_rows)
    user_ids = [r[0] for r in all_rows]
    profiles: dict[str, AgentProfile] = {}
    if user_ids:
        prof_rows = (await db.execute(
            select(AgentProfile).where(AgentProfile.owner_id == owner_id, AgentProfile.user_id.in_(user_ids))
        )).scalars().all()
        profiles = {p.user_id: p for p in prof_rows}

    out, seen = [], set()
    for uid, name, email in all_rows:
        if uid in seen:
            continue
        seen.add(uid)
        p = profiles.get(uid)
        out.append({
            "user_id": uid, "name": name, "email": email,
            "status": p.status if p else "offline",
            "active_chat_count": p.active_chat_count if p else 0,
            "max_concurrent_chats": p.max_concurrent_chats if p else 5,
        })
    return out


# ── Close / Reopen (NEW) ──────────────────────────────────────────────────
# Deliberately a distinct concept from Conversation.status alone (which
# already tracks "active"/"ended" session state elsewhere in the app) — a
# supervisor "Close" also drops the conversation out of the live-agent
# queue and is independently reversible via "Reopen", so it is tracked in
# its own supervisor_conversation_meta.is_closed flag as well.

async def close_conversation(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str) -> dict:
    conv = await _assert_owned_conversation(db, owner_id, conversation_id)
    meta = await _get_or_create_meta(db, owner_id, conversation_id)
    now = datetime.now(timezone.utc)
    actor_name = await _user_name(db, actor_id)

    conv.status = "ended"
    conv.ended_at = conv.ended_at or now
    meta.is_closed = True
    meta.closed_at = now

    await _add_system_message(
        db, conversation=conv, owner_id=owner_id,
        content=f"Conversation closed by {actor_name or 'a supervisor'}.", node_type="conversation_closed",
    )

    handoff_result = await db.execute(select(LiveAgentHandoff).where(LiveAgentHandoff.conversation_id == conversation_id))
    handoff = handoff_result.scalar_one_or_none()
    if handoff and handoff.status != "closed":
        handoff.status = "closed"
        handoff.closed_at = now

    await db.commit()
    await db.refresh(meta)

    await _log_activity(db, owner_id, conversation_id, actor_id, "closed")
    await _notify(owner_id, "conversation_closed", conversation_id, f"Conversation closed by {actor_name or 'a supervisor'}")

    payload = {"id": conversation_id, "status": conv.status, "is_closed": True, "closed_at": _iso(meta.closed_at)}
    from app.services import live_agent_ws_manager as ws_manager
    await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "supervisor_conversation_closed", "conversation": payload})
    return payload


async def reopen_conversation(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str) -> dict:
    conv = await _assert_owned_conversation(db, owner_id, conversation_id)
    meta = await _get_or_create_meta(db, owner_id, conversation_id)
    now = datetime.now(timezone.utc)
    actor_name = await _user_name(db, actor_id)

    conv.status = "active"
    conv.ended_at = None
    meta.is_closed = False
    meta.reopened_at = now

    await _add_system_message(
        db, conversation=conv, owner_id=owner_id,
        content=f"Conversation reopened by {actor_name or 'a supervisor'}.", node_type="conversation_reopened",
    )

    handoff_result = await db.execute(select(LiveAgentHandoff).where(LiveAgentHandoff.conversation_id == conversation_id))
    handoff = handoff_result.scalar_one_or_none()
    if handoff and handoff.status == "closed":
        handoff.status = "ai"
        handoff.assigned_agent_id = None

    await db.commit()
    await db.refresh(meta)

    await _log_activity(db, owner_id, conversation_id, actor_id, "reopened")
    await _notify(owner_id, "conversation_reopened", conversation_id, f"Conversation reopened by {actor_name or 'a supervisor'}")

    payload = {"id": conversation_id, "status": conv.status, "is_closed": False, "closed_at": None}
    from app.services import live_agent_ws_manager as ws_manager
    await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "supervisor_conversation_reopened", "conversation": payload})
    return payload


# ── Tags / Priority / Pin (NEW) ───────────────────────────────────────────

async def _get_or_create_meta(db: AsyncSession, owner_id: str, conversation_id: str) -> SupervisorConversationMeta:
    result = await db.execute(
        select(SupervisorConversationMeta).where(
            SupervisorConversationMeta.owner_id == owner_id,
            SupervisorConversationMeta.conversation_id == conversation_id,
        )
    )
    meta = result.scalar_one_or_none()
    if meta:
        return meta
    await _assert_owned_conversation(db, owner_id, conversation_id)
    meta = SupervisorConversationMeta(conversation_id=conversation_id, owner_id=owner_id)
    db.add(meta)
    await db.flush()
    return meta


async def set_priority(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str, priority: str) -> dict:
    if priority not in PRIORITY_LEVELS:
        raise ValueError(f"priority must be one of {PRIORITY_LEVELS}")
    meta = await _get_or_create_meta(db, owner_id, conversation_id)
    old_priority = meta.priority
    meta.priority = priority
    await db.commit()
    await db.refresh(meta)

    await _log_activity(db, owner_id, conversation_id, actor_id, "priority_changed", {"from": old_priority, "to": priority})
    if priority in ("high", "critical") and old_priority not in ("high", "critical"):
        await _notify(
            owner_id, "high_priority", conversation_id, f"Conversation marked {priority} priority",
            severity="critical" if priority == "critical" else "warning",
        )
    return _serialize_meta(meta)


async def add_tag(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str, tag: str) -> dict:
    tag = (tag or "").strip()
    if not tag:
        raise ValueError("Tag cannot be empty")
    meta = await _get_or_create_meta(db, owner_id, conversation_id)
    tags = list(meta.tags or [])
    if tag not in tags:
        tags.append(tag)
        meta.tags = tags
        await db.commit()
        await db.refresh(meta)
        await _log_activity(db, owner_id, conversation_id, actor_id, "tag_added", {"tag": tag})
    return _serialize_meta(meta)


async def remove_tag(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str, tag: str) -> dict:
    meta = await _get_or_create_meta(db, owner_id, conversation_id)
    before = meta.tags or []
    tags = [t for t in before if t != tag]
    if len(tags) != len(before):
        meta.tags = tags
        await db.commit()
        await db.refresh(meta)
        await _log_activity(db, owner_id, conversation_id, actor_id, "tag_removed", {"tag": tag})
    return _serialize_meta(meta)


async def set_pinned(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str, pinned: bool) -> dict:
    meta = await _get_or_create_meta(db, owner_id, conversation_id)
    if meta.is_pinned == pinned:
        return _serialize_meta(meta)
    meta.is_pinned = pinned
    meta.pinned_at = datetime.now(timezone.utc) if pinned else None
    await db.commit()
    await db.refresh(meta)
    await _log_activity(db, owner_id, conversation_id, actor_id, "pinned" if pinned else "unpinned")
    return _serialize_meta(meta)


# ── Activity log / team activity panel (NEW) ──────────────────────────────

async def _user_name(db: AsyncSession, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    result = await db.execute(select(User.name).where(User.id == user_id))
    row = result.first()
    return row[0] if row else None


async def _add_system_message(db: AsyncSession, *, conversation: Conversation, owner_id: str, content: str,
                               node_type: str) -> Message:
    """Writes a role="system" Message row into the same shared chat thread
    conversations already use for take-over/return/pause/resume system
    events (see live_agent_service._add_message) — this is what makes
    Close/Reopen show up in the conversation timeline alongside customer,
    AI, and human replies with no separate timeline table required."""
    msg = Message(
        conversation_id=conversation.id, workflow_id=conversation.workflow_id, owner_id=owner_id,
        role="system", content=content, node_type=node_type,
    )
    db.add(msg)
    conversation.message_count = (conversation.message_count or 0) + 1
    conversation.last_activity_at = datetime.now(timezone.utc)
    await db.flush()
    return msg


async def _log_activity(db: AsyncSession, owner_id: str, conversation_id: Optional[str], actor_id: Optional[str],
                         event_type: str, detail: Optional[dict] = None) -> dict:
    entry = SupervisorActivityLog(
        owner_id=owner_id, conversation_id=conversation_id, actor_id=actor_id,
        event_type=event_type, detail=detail or {},
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    actor_name = await _user_name(db, actor_id)
    payload = {
        "id": entry.id, "conversation_id": entry.conversation_id, "actor_id": entry.actor_id,
        "actor_name": actor_name, "event_type": entry.event_type, "detail": entry.detail,
        "created_at": _iso(entry.created_at),
    }
    from app.services import live_agent_ws_manager as ws_manager
    await ws_manager.broadcast_to_owner_agents(owner_id, {"type": "supervisor_activity", "activity": payload})
    return payload


async def _notify(owner_id: str, kind: str, conversation_id: Optional[str], title: str, *,
                   severity: str = "info", detail: Optional[dict] = None) -> None:
    """Real-time notification push — reuses the existing agent-dashboard
    WebSocket broadcast (services/live_agent_ws_manager.py) already wired
    up for handoff/message events; the frontend distinguishes notification
    toasts from data-refresh events by `type == "supervisor_notification"`.
    kind: new_conversation | human_takeover | high_priority | ai_paused |
    conversation_closed | conversation_reopened."""
    from app.services import live_agent_ws_manager as ws_manager
    await ws_manager.broadcast_to_owner_agents(owner_id, {
        "type": "supervisor_notification", "kind": kind, "conversation_id": conversation_id,
        "title": title, "severity": severity, "detail": detail or {},
        "created_at": _iso(datetime.now(timezone.utc)),
    })


async def list_activity(db: AsyncSession, owner_id: str, conversation_id: str) -> list[dict]:
    await _assert_owned_conversation(db, owner_id, conversation_id)
    rows = (await db.execute(
        select(SupervisorActivityLog, User).outerjoin(User, User.id == SupervisorActivityLog.actor_id)
        .where(SupervisorActivityLog.owner_id == owner_id, SupervisorActivityLog.conversation_id == conversation_id)
        .order_by(SupervisorActivityLog.created_at.asc())
    )).all()
    return [{
        "id": a.id, "actor_id": a.actor_id, "actor_name": u.name if u else None,
        "event_type": a.event_type, "detail": a.detail, "created_at": _iso(a.created_at),
    } for a, u in rows]


async def team_activity(db: AsyncSession, owner_id: str, limit: int = 30) -> dict:
    """Powers the Team Activity panel: who's online/busy/offline and how
    many chats they're handling (reuses live_agent_service.list_agents'
    underlying AgentProfile data via list_assignable_agents above) plus the
    most recent supervisor actions across the whole workspace."""
    agents = await list_assignable_agents(db, owner_id)
    rows = (await db.execute(
        select(SupervisorActivityLog, User).outerjoin(User, User.id == SupervisorActivityLog.actor_id)
        .where(SupervisorActivityLog.owner_id == owner_id)
        .order_by(SupervisorActivityLog.created_at.desc())
        .limit(limit)
    )).all()
    recent = [{
        "id": a.id, "conversation_id": a.conversation_id, "actor_id": a.actor_id,
        "actor_name": u.name if u else None, "event_type": a.event_type, "detail": a.detail,
        "created_at": _iso(a.created_at),
    } for a, u in rows]
    return {"agents": agents, "recent_activity": recent}


# ── Export (NEW, JSON now / PDF-ready architecture) ───────────────────────
# `export_conversation` returns one structured, format-agnostic payload
# (conversation metadata + full message timeline + notes + activity log).
# For `format="json"` the API returns it directly as a downloadable file.
# For `format="html"` (or "pdf") `render_export_html` renders the exact
# same payload into a print-styled HTML document — no new template engine
# dependency, jinja2 is already a backend requirement (email templating) —
# which the frontend opens in a new tab; the browser's native "Print ➜ Save
# as PDF" produces the PDF. This keeps the architecture ready to swap in a
# server-side PDF renderer (e.g. weasyprint) later with zero change to the
# payload shape or calling code, without adding an unapproved new
# dependency now.

async def export_conversation(db: AsyncSession, owner_id: str, conversation_id: str, actor_id: str,
                               fmt: str = "json") -> dict:
    detail = await get_conversation_detail(db, owner_id, conversation_id)
    if not detail:
        raise ValueError("Conversation not found")
    activity = await list_activity(db, owner_id, conversation_id)
    payload = {
        "conversation": {k: v for k, v in detail.items() if k not in ("messages", "notes")},
        "messages": detail["messages"],
        "notes": detail["notes"],
        "activity": activity,
        "exported_at": _iso(datetime.now(timezone.utc)),
        "format": fmt,
    }
    await _log_activity(db, owner_id, conversation_id, actor_id, "exported", {"format": fmt})
    return payload


_EXPORT_HTML_TEMPLATE = None


def render_export_html(payload: dict) -> str:
    global _EXPORT_HTML_TEMPLATE
    if _EXPORT_HTML_TEMPLATE is None:
        from jinja2 import Template
        _EXPORT_HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Conversation export — {{ conv.session_id }}</title>
<style>
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; color:#111; padding:32px; max-width:820px; margin:0 auto; }
  h1 { font-size:18px; margin-bottom:4px; }
  .meta { color:#666; font-size:12px; margin-bottom:24px; line-height:1.6; }
  .msg { margin-bottom:12px; padding:10px 14px; border-radius:10px; max-width:80%; }
  .user { background:#f2f2f2; margin-right:auto; }
  .bot { background:#eef0ff; margin-left:auto; }
  .agent { background:#fff4e0; margin-left:auto; }
  .system { background:none; color:#999; font-style:italic; text-align:center; max-width:100%; font-size:11px; }
  .role { font-size:10px; text-transform:uppercase; color:#888; margin-bottom:2px; }
  .activity { font-size:11px; color:#555; border-top:1px solid #ddd; margin-top:24px; padding-top:12px; }
  @media print { body { padding:0; } }
</style></head>
<body>
  <h1>Conversation — {{ conv.customer_display }}</h1>
  <div class="meta">
    {{ conv.workflow_name }} · {{ conv.channel }} · Session {{ conv.session_id }}<br>
    Status: {{ conv.status }} · Priority: {{ conv.priority }} · Tags: {{ (conv.tags|join(', ')) if conv.tags else '—' }}<br>
    Started {{ conv.started_at }} · Exported {{ payload.exported_at }}
  </div>
  {% for m in messages %}
  <div class="msg {{ m.role }}">
    <div class="role">{{ m.role }}{% if m.created_at %} · {{ m.created_at }}{% endif %}</div>
    {{ m.content }}
  </div>
  {% endfor %}
  {% if activity %}
  <div class="activity">
    <strong>Activity history</strong>
    {% for a in activity %}
    <div>{{ a.created_at }} — {{ a.event_type }}{% if a.actor_name %} by {{ a.actor_name }}{% endif %}</div>
    {% endfor %}
  </div>
  {% endif %}
</body></html>""")
    return _EXPORT_HTML_TEMPLATE.render(
        conv=payload["conversation"], messages=payload["messages"], activity=payload["activity"], payload=payload,
    )


# ── Bulk actions (NEW) ────────────────────────────────────────────────────

async def bulk_close(db: AsyncSession, owner_id: str, actor_id: str, conversation_ids: list[str]) -> dict:
    succeeded, failed = [], []
    for cid in conversation_ids:
        try:
            await close_conversation(db, owner_id, cid, actor_id)
            succeeded.append(cid)
        except ValueError as e:
            failed.append({"id": cid, "error": str(e)})
    await _log_activity(db, owner_id, None, actor_id, "bulk_closed", {"conversation_ids": conversation_ids, "count": len(succeeded)})
    return {"succeeded": succeeded, "failed": failed}


async def bulk_assign(db: AsyncSession, owner_id: str, actor_id: str, conversation_ids: list[str], agent_id: str) -> dict:
    succeeded, failed = [], []
    for cid in conversation_ids:
        try:
            await assign_conversation(db, owner_id, cid, actor_id, agent_id)
            succeeded.append(cid)
        except ValueError as e:
            failed.append({"id": cid, "error": str(e)})
    await _log_activity(db, owner_id, None, actor_id, "bulk_assigned", {
        "conversation_ids": conversation_ids, "agent_id": agent_id, "count": len(succeeded),
    })
    return {"succeeded": succeeded, "failed": failed}


async def bulk_tag(db: AsyncSession, owner_id: str, actor_id: str, conversation_ids: list[str], tag: str) -> dict:
    succeeded, failed = [], []
    for cid in conversation_ids:
        try:
            await add_tag(db, owner_id, cid, actor_id, tag)
            succeeded.append(cid)
        except ValueError as e:
            failed.append({"id": cid, "error": str(e)})
    await _log_activity(db, owner_id, None, actor_id, "bulk_tagged", {
        "conversation_ids": conversation_ids, "tag": tag, "count": len(succeeded),
    })
    return {"succeeded": succeeded, "failed": failed}


async def bulk_export(db: AsyncSession, owner_id: str, actor_id: str, conversation_ids: list[str]) -> dict:
    items, failed = [], []
    for cid in conversation_ids:
        try:
            items.append(await export_conversation(db, owner_id, cid, actor_id, fmt="json"))
        except ValueError as e:
            failed.append({"id": cid, "error": str(e)})
    await _log_activity(db, owner_id, None, actor_id, "bulk_exported", {
        "conversation_ids": conversation_ids, "count": len(items),
    })
    return {"items": items, "failed": failed, "exported_at": _iso(datetime.now(timezone.utc))}


async def send_manual_message(db: AsyncSession, owner_id: str, conversation_id: str, agent_user_id: str,
                               content: str) -> dict:
    """Owner sends a message manually after taking over the conversation.
    Reuses live_agent_service.send_agent_message verbatim — the same call
    the Live Agent page's chat composer already makes."""
    handoff = await live_agent_service.get_or_create_handoff_for_conversation(
        db, conversation_id=conversation_id, owner_id=owner_id,
    )
    if not handoff:
        raise ValueError("Conversation not found")
    await db.commit()
    return await live_agent_service.send_agent_message(
        handoff_id=handoff.id, owner_id=owner_id, agent_user_id=agent_user_id, content=content,
    )


# ── Internal notes (NEW) ──────────────────────────────────────────────────

async def add_note(db: AsyncSession, owner_id: str, conversation_id: str, author_id: str, content: str) -> dict:
    await _assert_owned_conversation(db, owner_id, conversation_id)
    note = SupervisorNote(
        conversation_id=conversation_id, owner_id=owner_id, author_id=author_id, content=content.strip(),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    author_result = await db.execute(select(User).where(User.id == author_id))
    author = author_result.scalar_one_or_none()

    payload = {
        "id": note.id, "conversation_id": note.conversation_id, "author_id": note.author_id,
        "author_name": author.name if author else None, "content": note.content,
        "created_at": _iso(note.created_at),
    }
    from app.services import live_agent_ws_manager as ws_manager
    await ws_manager.broadcast_to_owner_agents(owner_id, {
        "type": "supervisor_note_added", "conversation_id": conversation_id, "note": payload,
    })
    return payload


async def list_notes(db: AsyncSession, owner_id: str, conversation_id: str) -> list[dict]:
    rows = (await db.execute(
        select(SupervisorNote, User).outerjoin(User, User.id == SupervisorNote.author_id)
        .where(SupervisorNote.owner_id == owner_id, SupervisorNote.conversation_id == conversation_id)
        .order_by(SupervisorNote.created_at.asc())
    )).all()
    return [{
        "id": n.id, "conversation_id": n.conversation_id, "author_id": n.author_id,
        "author_name": u.name if u else None, "content": n.content, "created_at": _iso(n.created_at),
    } for n, u in rows]


# ── Reply QA verdicts (NEW) ───────────────────────────────────────────────

async def _reviews_by_message(db: AsyncSession, *, message_ids: list[str]) -> dict[str, dict]:
    if not message_ids:
        return {}
    rows = (await db.execute(
        select(MessageReview, User).outerjoin(User, User.id == MessageReview.reviewer_id)
        .where(MessageReview.message_id.in_(message_ids))
    )).all()
    return {
        r.message_id: {
            "verdict": r.verdict, "reviewer_id": r.reviewer_id,
            "reviewer_name": u.name if u else None, "updated_at": _iso(r.updated_at),
        }
        for r, u in rows
    }


async def set_message_review(db: AsyncSession, owner_id: str, message_id: str, reviewer_id: str,
                              verdict: str) -> dict:
    if verdict not in ("correct", "incorrect"):
        raise ValueError("verdict must be 'correct' or 'incorrect'")

    msg_result = await db.execute(
        select(Message).where(Message.id == message_id, Message.owner_id == owner_id)
    )
    msg = msg_result.scalar_one_or_none()
    if not msg:
        raise ValueError("Message not found")
    if msg.role != "bot":
        raise ValueError("Only AI replies can be reviewed")

    existing_result = await db.execute(select(MessageReview).where(MessageReview.message_id == message_id))
    review = existing_result.scalar_one_or_none()
    if review:
        review.verdict = verdict
        review.reviewer_id = reviewer_id
    else:
        review = MessageReview(
            message_id=message_id, conversation_id=msg.conversation_id, owner_id=owner_id,
            reviewer_id=reviewer_id, verdict=verdict,
        )
        db.add(review)
    await db.commit()
    await db.refresh(review)

    reviewer_result = await db.execute(select(User).where(User.id == reviewer_id))
    reviewer = reviewer_result.scalar_one_or_none()

    payload = {
        "message_id": message_id, "conversation_id": review.conversation_id, "verdict": review.verdict,
        "reviewer_id": reviewer_id, "reviewer_name": reviewer.name if reviewer else None,
        "updated_at": _iso(review.updated_at),
    }
    from app.services import live_agent_ws_manager as ws_manager
    await ws_manager.broadcast_to_owner_agents(owner_id, {
        "type": "supervisor_review_updated", "conversation_id": review.conversation_id, "review": payload,
    })
    return payload
