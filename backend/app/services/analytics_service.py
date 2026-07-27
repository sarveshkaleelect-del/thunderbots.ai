"""
ThunderBots Analytics Service
NEW (Analytics Dashboard).

Two responsibilities, kept strictly separate:

1. RECORDING — `record_turn(...)` is called (best-effort, fire-and-forget)
   from the chat API/WS layer after a turn completes. It NEVER raises: any
   failure is logged and swallowed so analytics can never break live chat.
   It uses its OWN short-lived DB session, independent of whatever session
   the caller used for the actual chat turn, so it cannot interfere with
   or roll back Workflow Runtime state.

2. QUERYING — a set of read-only aggregation functions powering every
   endpoint in api/v1/analytics.py. All are scoped by `owner_id` (the
   authenticated dashboard user), matching the ownership model already
   used by workflows/history/knowledge.

This module does not import from, call into, or modify anything in
app/engine/* (Workflow Runtime), app/knowledge/* (Knowledge Base engine),
app/services/ai_engine.py (AI Providers), or app/api/v1/deploy.py
(Deployment) — it only reads their already-persisted, public data
(workflow name/status, KB document filenames) for display purposes.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.analytics import Conversation, Message
from app.models.workflow import Workflow
from app.models.knowledge import KBDocument, KnowledgeBase

logger = logging.getLogger(__name__)


def hash_visitor(ip: Optional[str], user_agent: Optional[str]) -> Optional[str]:
    """One-way fingerprint used only to distinguish 'active' vs 'returning'
    visitors. Never stores the raw IP/UA anywhere."""
    if not ip:
        return None
    raw = f"{ip}::{user_agent or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def resolve_streamed_provider(
    workflow: dict, turn_node_type: Optional[str], pre_turn_node_id: Optional[str]
) -> Optional[str]:
    """Best-effort AI-provider attribution for the two *streaming* chat paths
    (WS + SSE). Unlike WorkflowRunner.run(), stream_run()'s 'done' chunk does
    not include a 'provider' field, and by the time the stream ends
    context.current_node_id has already advanced to the *next* node — so it
    can't be used directly to look the node back up.

    Strategy (does not require touching app/engine/*):
    - If the workflow has exactly one ai_agent node (the overwhelming common
      case — one bot, one LLM step), attribute the turn to it directly.
    - Otherwise, fall back to whatever node the session was pointing to
      *before* this turn started — correct whenever that node IS the
      ai_agent node (e.g. multi-agent graphs where each agent hands off
      directly to the next), best-effort otherwise.
    """
    if turn_node_type != "ai_agent":
        return None
    nodes = workflow.get("nodes") or []
    agent_nodes = [n for n in nodes if n.get("type") == "ai_agent"]
    if len(agent_nodes) == 1:
        return (agent_nodes[0].get("data") or {}).get("provider")
    match = next((n for n in nodes if n.get("id") == pre_turn_node_id), None)
    if match and match.get("type") == "ai_agent":
        return (match.get("data") or {}).get("provider")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# RECORDING
# ─────────────────────────────────────────────────────────────────────────────

async def get_or_create_conversation(
    db: AsyncSession,
    *,
    session_id: str,
    workflow_id: str,
    owner_id: str,
    source: str = "direct",
    visitor_key: Optional[str] = None,
    meta: Optional[dict] = None,
) -> Conversation:
    result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = result.scalar_one_or_none()
    if conv:
        return conv

    is_returning = False
    if visitor_key:
        prior = await db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.owner_id == owner_id,
                Conversation.visitor_key == visitor_key,
            )
        )
        is_returning = (prior.scalar() or 0) > 0

    conv = Conversation(
        session_id=session_id,
        workflow_id=workflow_id,
        owner_id=owner_id,
        source=source,
        visitor_key=visitor_key,
        is_returning=is_returning,
        meta=meta or {},
    )
    db.add(conv)
    await db.flush()
    return conv


async def record_turn(
    *,
    session_id: str,
    workflow_id: str,
    owner_id: str,
    user_message: Optional[str],
    bot_response: Optional[str],
    node_id: Optional[str] = None,
    node_type: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    latency_ms: Optional[int] = None,
    is_error: bool = False,
    error_message: Optional[str] = None,
    citations: Optional[list] = None,
    source: str = "direct",
    visitor_key: Optional[str] = None,
    meta: Optional[dict] = None,
    ended: bool = False,
) -> None:
    """Best-effort recorder — never raises. Called from chat.py / chat_ws.py
    after a turn finishes, using its own isolated DB session."""
    try:
        async with AsyncSessionLocal() as db:
            conv = await get_or_create_conversation(
                db,
                session_id=session_id,
                workflow_id=workflow_id,
                owner_id=owner_id,
                source=source,
                visitor_key=visitor_key,
                meta=meta,
            )

            now = datetime.now(timezone.utc)
            conv.last_activity_at = now
            if ended:
                conv.status = "ended"
                conv.ended_at = now

            if user_message:
                db.add(Message(
                    conversation_id=conv.id, workflow_id=workflow_id, owner_id=owner_id,
                    role="user", content=user_message[:8000],
                ))
                conv.message_count += 1
                conv.user_message_count += 1

            if bot_response is not None or is_error:
                db.add(Message(
                    conversation_id=conv.id, workflow_id=workflow_id, owner_id=owner_id,
                    role="bot", content=(bot_response or "")[:8000],
                    node_id=node_id, node_type=node_type, provider=provider, model=model,
                    latency_ms=latency_ms, is_error=is_error, error_message=error_message,
                    citations=citations or [],
                ))
                conv.message_count += 1
                conv.bot_message_count += 1
                if is_error:
                    conv.error_count += 1

                if latency_ms is not None:
                    if conv.first_response_time_ms is None:
                        conv.first_response_time_ms = latency_ms
                    prior_n = max(conv.bot_message_count - 1, 0)
                    prior_avg = conv.avg_response_time_ms or 0.0
                    conv.avg_response_time_ms = (
                        ((prior_avg * prior_n) + latency_ms) / (prior_n + 1)
                        if (prior_n + 1) > 0 else latency_ms
                    )

            await db.commit()
    except Exception as e:  # noqa: BLE001 — analytics must never break chat
        logger.warning(f"Analytics record_turn failed (non-fatal): {e}")


async def record_rating(session_id: str, rating: int) -> bool:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
            conv = result.scalar_one_or_none()
            if not conv:
                return False
            conv.satisfaction_rating = max(1, min(5, rating))
            await db.commit()
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Analytics record_rating failed (non-fatal): {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# QUERYING
# ─────────────────────────────────────────────────────────────────────────────

def _range_bounds(range_key: str, start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if range_key == "custom" and start and end:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return s, e
    days = {"today": 1, "7d": 7, "30d": 30, "90d": 90}.get(range_key, 7)
    if range_key == "today":
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return s, now
    return now - timedelta(days=days), now


async def get_overview(db: AsyncSession, owner_id: str, range_key: str = "7d",
                        start: Optional[str] = None, end: Optional[str] = None) -> dict:
    s, e = _range_bounds(range_key, start, end)

    total_bots = (await db.execute(
        select(func.count(Workflow.id)).where(Workflow.user_id == owner_id)
    )).scalar() or 0
    live_bots = (await db.execute(
        select(func.count(Workflow.id)).where(Workflow.user_id == owner_id, Workflow.status == "published")
    )).scalar() or 0

    conv_q = select(func.count(Conversation.id)).where(
        Conversation.owner_id == owner_id, Conversation.started_at.between(s, e)
    )
    total_conversations = (await db.execute(conv_q)).scalar() or 0

    msg_q = select(func.count(Message.id)).where(
        Message.owner_id == owner_id, Message.created_at.between(s, e)
    )
    total_messages = (await db.execute(msg_q)).scalar() or 0

    active_users = (await db.execute(
        select(func.count(func.distinct(Conversation.visitor_key))).where(
            Conversation.owner_id == owner_id,
            Conversation.started_at.between(s, e),
            Conversation.visitor_key.isnot(None),
        )
    )).scalar() or 0

    returning_users = (await db.execute(
        select(func.count(func.distinct(Conversation.visitor_key))).where(
            Conversation.owner_id == owner_id,
            Conversation.started_at.between(s, e),
            Conversation.is_returning.is_(True),
            Conversation.visitor_key.isnot(None),
        )
    )).scalar() or 0

    avg_latency = (await db.execute(
        select(func.avg(Message.latency_ms)).where(
            Message.owner_id == owner_id, Message.role == "bot",
            Message.latency_ms.isnot(None), Message.created_at.between(s, e),
        )
    )).scalar()

    avg_conv_len = (await db.execute(
        select(func.avg(Conversation.message_count)).where(
            Conversation.owner_id == owner_id, Conversation.started_at.between(s, e),
        )
    )).scalar()

    avg_satisfaction = (await db.execute(
        select(func.avg(Conversation.satisfaction_rating)).where(
            Conversation.owner_id == owner_id, Conversation.started_at.between(s, e),
            Conversation.satisfaction_rating.isnot(None),
        )
    )).scalar()
    rated_count = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.owner_id == owner_id, Conversation.started_at.between(s, e),
            Conversation.satisfaction_rating.isnot(None),
        )
    )).scalar() or 0

    return {
        "total_chatbots": total_bots,
        "live_chatbots": live_bots,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "active_users": active_users,
        "returning_users": returning_users,
        "avg_response_time_ms": round(avg_latency, 0) if avg_latency else 0,
        "avg_conversation_length": round(avg_conv_len, 1) if avg_conv_len else 0,
        "avg_satisfaction": round(avg_satisfaction, 2) if avg_satisfaction else None,
        "satisfaction_sample_size": rated_count,
        "range": {"start": s.isoformat(), "end": e.isoformat(), "key": range_key},
    }


async def get_timeseries(db: AsyncSession, owner_id: str, metric: str, range_key: str = "7d",
                          start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    """metric: conversations | messages | active_users | response_time"""
    s, e = _range_bounds(range_key, start, end)

    if metric == "conversations":
        q = (
            select(cast(Conversation.started_at, Date).label("d"), func.count(Conversation.id).label("v"))
            .where(Conversation.owner_id == owner_id, Conversation.started_at.between(s, e))
            .group_by("d").order_by("d")
        )
    elif metric == "messages":
        q = (
            select(cast(Message.created_at, Date).label("d"), func.count(Message.id).label("v"))
            .where(Message.owner_id == owner_id, Message.created_at.between(s, e))
            .group_by("d").order_by("d")
        )
    elif metric == "active_users":
        q = (
            select(cast(Conversation.started_at, Date).label("d"),
                   func.count(func.distinct(Conversation.visitor_key)).label("v"))
            .where(Conversation.owner_id == owner_id, Conversation.started_at.between(s, e),
                   Conversation.visitor_key.isnot(None))
            .group_by("d").order_by("d")
        )
    elif metric == "response_time":
        q = (
            select(cast(Message.created_at, Date).label("d"), func.avg(Message.latency_ms).label("v"))
            .where(Message.owner_id == owner_id, Message.role == "bot",
                   Message.latency_ms.isnot(None), Message.created_at.between(s, e))
            .group_by("d").order_by("d")
        )
    else:
        return []

    rows = (await db.execute(q)).all()
    return [{"date": r.d.isoformat(), "value": round(float(r.v), 2) if r.v is not None else 0} for r in rows]


async def get_traffic_sources(db: AsyncSession, owner_id: str, range_key: str = "7d",
                               start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    s, e = _range_bounds(range_key, start, end)
    q = (
        select(Conversation.source, func.count(Conversation.id).label("count"))
        .where(Conversation.owner_id == owner_id, Conversation.started_at.between(s, e))
        .group_by(Conversation.source).order_by(func.count(Conversation.id).desc())
    )
    rows = (await db.execute(q)).all()
    total = sum(r.count for r in rows) or 1
    known = {"website", "embed_widget", "direct", "api", "whatsapp", "telegram"}
    result = [
        {"source": r.source, "count": r.count, "percentage": round(r.count / total * 100, 1)}
        for r in rows
    ]
    present = {r["source"] for r in result}
    for k in known - present:
        result.append({"source": k, "count": 0, "percentage": 0.0})
    order = {k: i for i, k in enumerate(["website", "embed_widget", "direct", "api", "whatsapp", "telegram"])}
    result.sort(key=lambda x: order.get(x["source"], 99))
    return result


async def get_top_bots(db: AsyncSession, owner_id: str, range_key: str = "7d",
                        start: Optional[str] = None, end: Optional[str] = None, limit: int = 10) -> list[dict]:
    s, e = _range_bounds(range_key, start, end)
    q = (
        select(
            Workflow.id, Workflow.name, Workflow.status,
            func.count(func.distinct(Conversation.id)).label("conversations"),
            func.count(Message.id).label("messages"),
            func.avg(Message.latency_ms).label("avg_latency"),
        )
        .select_from(Workflow)
        .outerjoin(Conversation, and_(
            Conversation.workflow_id == Workflow.id,
            Conversation.started_at.between(s, e),
        ))
        .outerjoin(Message, and_(
            Message.conversation_id == Conversation.id,
            Message.role == "bot",
        ))
        .where(Workflow.user_id == owner_id)
        .group_by(Workflow.id, Workflow.name, Workflow.status)
        .order_by(func.count(func.distinct(Conversation.id)).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "workflow_id": r.id, "name": r.name, "status": r.status,
            "conversations": r.conversations or 0, "messages": r.messages or 0,
            "avg_latency_ms": round(r.avg_latency, 0) if r.avg_latency else 0,
        }
        for r in rows
    ]


async def get_top_documents(db: AsyncSession, owner_id: str, limit: int = 10) -> list[dict]:
    """Ranks KB documents by how often they appear in stored message citations."""
    q = (
        select(Message.citations)
        .where(Message.owner_id == owner_id, func.jsonb_array_length(Message.citations) > 0)
        .order_by(Message.created_at.desc())
        .limit(2000)
    )
    rows = (await db.execute(q)).scalars().all()
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for citations in rows:
        for c in (citations or []):
            doc_id = c.get("document_id") or c.get("id") or c.get("source")
            if not doc_id:
                continue
            counts[doc_id] = counts.get(doc_id, 0) + 1
            names[doc_id] = c.get("document") or c.get("name") or c.get("source") or doc_id

    if not counts:
        return []

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    doc_ids = [d for d, _ in ranked if len(d) == 36]
    doc_lookup: dict[str, str] = {}
    if doc_ids:
        result = await db.execute(
            select(KBDocument.id, KBDocument.filename).where(KBDocument.id.in_(doc_ids))
        )
        doc_lookup = {r.id: r.filename for r in result.all()}

    return [
        {"document": doc_lookup.get(doc_id, names.get(doc_id, doc_id)), "uses": count}
        for doc_id, count in ranked
    ]


async def get_kb_usage(db: AsyncSession, owner_id: str, range_key: str = "7d",
                        start: Optional[str] = None, end: Optional[str] = None) -> dict:
    s, e = _range_bounds(range_key, start, end)

    kb_total = (await db.execute(
        select(func.count(KnowledgeBase.id)).where(KnowledgeBase.user_id == owner_id)
    )).scalar() or 0
    doc_total = (await db.execute(
        select(func.count(KBDocument.id))
        .join(KnowledgeBase, KBDocument.knowledge_base_id == KnowledgeBase.id)
        .where(KnowledgeBase.user_id == owner_id)
    )).scalar() or 0

    grounded_msgs = (await db.execute(
        select(func.count(Message.id)).where(
            Message.owner_id == owner_id, Message.created_at.between(s, e),
            func.jsonb_array_length(Message.citations) > 0,
        )
    )).scalar() or 0
    bot_msgs = (await db.execute(
        select(func.count(Message.id)).where(
            Message.owner_id == owner_id, Message.created_at.between(s, e), Message.role == "bot",
        )
    )).scalar() or 0

    return {
        "knowledge_bases": kb_total,
        "documents": doc_total,
        "grounded_responses": grounded_msgs,
        "total_bot_responses": bot_msgs,
        "grounding_rate": round(grounded_msgs / bot_msgs * 100, 1) if bot_msgs else 0,
    }


async def get_provider_usage(db: AsyncSession, owner_id: str, range_key: str = "7d",
                              start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    s, e = _range_bounds(range_key, start, end)
    q = (
        select(Message.provider, func.count(Message.id).label("count"),
               func.avg(Message.latency_ms).label("avg_latency"))
        .where(Message.owner_id == owner_id, Message.created_at.between(s, e), Message.provider.isnot(None))
        .group_by(Message.provider).order_by(func.count(Message.id).desc())
    )
    rows = (await db.execute(q)).all()
    total = sum(r.count for r in rows) or 1
    result = [
        {
            "provider": r.provider, "requests": r.count,
            "percentage": round(r.count / total * 100, 1),
            "avg_latency_ms": round(r.avg_latency, 0) if r.avg_latency else 0,
        }
        for r in rows
    ]
    present = {r["provider"] for r in result}
    for p in {"gemini"} - present:
        result.append({"provider": p, "requests": 0, "percentage": 0.0, "avg_latency_ms": 0})
    order = {"gemini": 0}
    result.sort(key=lambda x: order.get(x["provider"], 99))
    return result


async def get_performance(db: AsyncSession, owner_id: str, range_key: str = "7d",
                           start: Optional[str] = None, end: Optional[str] = None) -> dict:
    s, e = _range_bounds(range_key, start, end)

    avg_latency = (await db.execute(
        select(func.avg(Message.latency_ms)).where(
            Message.owner_id == owner_id, Message.role == "bot",
            Message.latency_ms.isnot(None), Message.created_at.between(s, e),
        )
    )).scalar()

    p95_rows = (await db.execute(
        select(Message.latency_ms).where(
            Message.owner_id == owner_id, Message.role == "bot",
            Message.latency_ms.isnot(None), Message.created_at.between(s, e),
        ).order_by(Message.latency_ms)
    )).scalars().all()
    p95 = None
    if p95_rows:
        idx = max(0, int(len(p95_rows) * 0.95) - 1)
        p95 = p95_rows[idx]

    slow_requests = (await db.execute(
        select(func.count(Message.id)).where(
            Message.owner_id == owner_id, Message.role == "bot",
            Message.latency_ms.isnot(None), Message.latency_ms > 5000,
            Message.created_at.between(s, e),
        )
    )).scalar() or 0

    total_bot = (await db.execute(
        select(func.count(Message.id)).where(
            Message.owner_id == owner_id, Message.role == "bot", Message.created_at.between(s, e),
        )
    )).scalar() or 0

    errors = (await db.execute(
        select(func.count(Message.id)).where(
            Message.owner_id == owner_id, Message.is_error.is_(True), Message.created_at.between(s, e),
        )
    )).scalar() or 0

    return {
        "avg_latency_ms": round(avg_latency, 0) if avg_latency else 0,
        "p95_latency_ms": p95 or 0,
        "slow_requests": slow_requests,
        "slow_request_threshold_ms": 5000,
        "total_requests": total_bot,
        "errors": errors,
        "error_rate": round(errors / total_bot * 100, 2) if total_bot else 0,
        "failed_requests": errors,
    }


async def get_realtime(db: AsyncSession, owner_id: str) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=5)

    live_conversations = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.owner_id == owner_id, Conversation.last_activity_at >= since,
            Conversation.status == "active",
        )
    )).scalar() or 0

    msgs_last_5m = (await db.execute(
        select(func.count(Message.id)).where(
            Message.owner_id == owner_id, Message.created_at >= since,
        )
    )).scalar() or 0

    recent = (await db.execute(
        select(Message.id, Message.role, Message.content, Message.created_at, Message.workflow_id,
               Message.is_error, Message.node_type, Workflow.name.label("workflow_name"))
        .join(Workflow, Workflow.id == Message.workflow_id)
        .where(Message.owner_id == owner_id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )).all()

    return {
        "live_conversations": live_conversations,
        "messages_last_5m": msgs_last_5m,
        "generated_at": now.isoformat(),
        "recent_activity": [
            {
                "id": r.id, "role": r.role, "preview": (r.content or "")[:120],
                "workflow_name": r.workflow_name, "is_error": r.is_error,
                "node_type": r.node_type, "created_at": r.created_at.isoformat(),
            }
            for r in recent
        ],
    }


async def list_conversations(
    db: AsyncSession, owner_id: str, *,
    search: Optional[str] = None, workflow_id: Optional[str] = None,
    source: Optional[str] = None, status: Optional[str] = None,
    start: Optional[str] = None, end: Optional[str] = None,
    page: int = 1, page_size: int = 25,
) -> dict:
    conditions = [Conversation.owner_id == owner_id]
    if workflow_id:
        conditions.append(Conversation.workflow_id == workflow_id)
    if source:
        conditions.append(Conversation.source == source)
    if status:
        conditions.append(Conversation.status == status)
    if start:
        conditions.append(Conversation.started_at >= datetime.fromisoformat(start.replace("Z", "+00:00")))
    if end:
        conditions.append(Conversation.started_at <= datetime.fromisoformat(end.replace("Z", "+00:00")))
    if search:
        subq = select(Message.conversation_id).where(
            Message.owner_id == owner_id, Message.content.ilike(f"%{search}%")
        )
        conditions.append(or_(Conversation.session_id.ilike(f"%{search}%"), Conversation.id.in_(subq)))

    base_q = select(Conversation, Workflow.name.label("workflow_name")).join(
        Workflow, Workflow.id == Conversation.workflow_id
    ).where(and_(*conditions))

    total = (await db.execute(
        select(func.count()).select_from(base_q.subquery())
    )).scalar() or 0

    rows = (await db.execute(
        base_q.order_by(Conversation.started_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()

    items = [
        {
            "id": conv.id, "session_id": conv.session_id, "workflow_id": conv.workflow_id,
            "workflow_name": wf_name, "source": conv.source, "status": conv.status,
            "message_count": conv.message_count, "user_message_count": conv.user_message_count,
            "bot_message_count": conv.bot_message_count, "error_count": conv.error_count,
            "avg_response_time_ms": round(conv.avg_response_time_ms, 0) if conv.avg_response_time_ms else 0,
            "satisfaction_rating": conv.satisfaction_rating, "is_returning": conv.is_returning,
            "started_at": conv.started_at.isoformat(), "last_activity_at": conv.last_activity_at.isoformat(),
            "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
        }
        for conv, wf_name in rows
    ]

    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size)}


async def get_conversation_detail(db: AsyncSession, owner_id: str, conversation_id: str) -> Optional[dict]:
    result = await db.execute(
        select(Conversation, Workflow.name.label("workflow_name"))
        .join(Workflow, Workflow.id == Conversation.workflow_id)
        .where(Conversation.id == conversation_id, Conversation.owner_id == owner_id)
    )
    row = result.first()
    if not row:
        return None
    conv, wf_name = row

    msgs = (await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )).scalars().all()

    # NEW (Part 3, additive): surface the EXISTING Live Agent handoff status
    # (ai | waiting | active | paused | closed) alongside the conversation so
    # channel UIs (e.g. the Telegram conversation timeline) can show AI vs.
    # human-handoff status without a second round trip. Purely additive —
    # every existing field/behavior above is unchanged, and this import is
    # local to avoid a module-level dependency between analytics_service and
    # the Live Agent module.
    handoff_status = "ai"
    assigned_agent_name = None
    try:
        from app.models.live_agent import LiveAgentHandoff
        from app.models.user import User
        handoff_result = await db.execute(
            select(LiveAgentHandoff, User.name).outerjoin(
                User, User.id == LiveAgentHandoff.assigned_agent_id
            ).where(LiveAgentHandoff.conversation_id == conversation_id)
        )
        handoff_row = handoff_result.first()
        if handoff_row:
            handoff_status = handoff_row[0].status
            assigned_agent_name = handoff_row[1]
    except Exception as e:  # noqa: BLE001 — status enrichment must never break the detail view
        logger.warning(f"Conversation handoff-status lookup failed for {conversation_id}: {e}")

    return {
        "id": conv.id, "session_id": conv.session_id, "workflow_id": conv.workflow_id,
        "workflow_name": wf_name, "source": conv.source, "status": conv.status,
        "satisfaction_rating": conv.satisfaction_rating, "is_returning": conv.is_returning,
        "started_at": conv.started_at.isoformat(), "last_activity_at": conv.last_activity_at.isoformat(),
        "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
        "handoff_status": handoff_status,
        "assigned_agent_name": assigned_agent_name,
        "messages": [
            {
                "id": m.id, "role": m.role, "content": m.content, "node_type": m.node_type,
                "provider": m.provider, "model": m.model, "latency_ms": m.latency_ms,
                "is_error": m.is_error, "citations": m.citations, "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }
