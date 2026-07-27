"""
ThunderBots AI Call Agent — Calls API
(NEW, Voice AI Part 3; extended in Part 4 — production-ready admin
controls, analytics, recording summary, and human handoff)

Builds directly on top of api/v1/call_agent.py (Part 2 — phone number
connection/verification only, unchanged, not touched by this file).
This module adds exactly what Part 2's docstring left out for a future
phase:
  - Binding a verified/connected phone number to a Workflow + call
    voice/speed/language/recording settings.
  - Placing outbound AI calls and receiving inbound ones (Twilio REST +
    TwiML webhooks).
  - The call dashboard (active/missed/completed/failed/interrupted
    counts), call history, and per-call transcript.

NEW (Part 4) additions, all additive/backward-compatible:
  - Admin controls on CallSettingsPayload: business_hours, greeting_message,
    fallback_prompt, knowledge_base_ids, system_prompt, prompt_scope,
    interrupt_behavior — all stored in the existing PhoneNumber.call_settings
    JSONB blob (no schema change needed for the number itself), read by
    services/call_session_service.py at call time.
  - Extended dashboard analytics (total/avg duration/avg response time/
    resolution rate) and search/date filters on call history.
  - Call recording summary (services/call_summary_service.py).
  - Human handoff endpoints, reusing services/live_agent_service.py exactly
    as api/v1/live_agent.py already does for chat — a call is registered
    under live_agent_service with channel="voice_call" and the same
    request_handoff/take_over/return_to_ai functions apply.
  - Business-hours gating on the inbound Twilio webhook.

Registered as its own router (see app/main.py) rather than added into
call_agent.py, so Part 2's file is never modified by this part.

Twilio webhook routes (/twilio/*) are intentionally NOT behind
get_current_user — Twilio calls them directly. They're instead protected
by verify_twilio_signature() (services/call_telephony_service.py).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.call import Call, CallTranscriptEntry
from app.models.knowledge import KnowledgeBase
from app.models.live_agent import LiveAgentHandoff
from app.models.phone_number import PhoneNumber
from app.models.user import User, UserAPIKey
from app.models.workflow import Workflow
from app.services import audit_service, call_summary_service, call_telephony_service, live_agent_service, tts_engine
from app.services.audit_service import Action
from app.services.call_telephony_service import TelephonyError

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class BusinessHoursDay(BaseModel):
    open:  str  # "HH:MM", 24h
    close: str  # "HH:MM", 24h


class BusinessHours(BaseModel):
    enabled:  bool = False
    timezone: str  = "UTC"
    # keys: "mon".."sun" — a day with no entry is treated as closed all day
    days: dict[str, BusinessHoursDay] = Field(default_factory=dict)


class CallSettingsPayload(BaseModel):
    workflow_id: Optional[str] = None
    # NEW (Voice AI Part 5): bind this number to a standalone Voice Agent
    # instead of a chatbot Workflow. Additive alongside workflow_id above
    # (untouched) — see models/phone_number.py:PhoneNumber.voice_agent_id
    # and api/ws/call_stream_ws.py for how the two are resolved at call time.
    voice_agent_id: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    speed: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    language: Optional[str] = None
    recording_enabled: Optional[bool] = None

    # NEW (Part 4) — admin controls
    greeting_message: Optional[str] = Field(default=None, max_length=1000)
    fallback_prompt: Optional[str] = Field(default=None, max_length=1000)
    system_prompt: Optional[str] = Field(default=None, max_length=4000)
    knowledge_base_ids: Optional[list[str]] = None
    prompt_scope: Optional[str] = None       # "strict" | "open"
    interrupt_behavior: Optional[str] = None  # "interrupt" | "queue" | "ignore"
    business_hours: Optional[BusinessHours] = None


class OutboundCallPayload(BaseModel):
    phone_number_id: str
    to_number: str = Field(..., min_length=8, max_length=20)


class AgentMessagePayload(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_owned_number(number_id: str, db: AsyncSession, current_user: User) -> PhoneNumber:
    result = await db.execute(select(PhoneNumber).where(PhoneNumber.id == number_id))
    number = result.scalar_one_or_none()
    if not number:
        raise HTTPException(status_code=404, detail="Phone number not found")
    if str(number.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this phone number")
    return number


async def _get_owned_call(call_id: str, db: AsyncSession, current_user: User) -> Call:
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if str(call.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this call")
    return call


def _serialize_call(call: Call) -> dict:
    return {
        "id": call.id,
        "phone_number_id": call.phone_number_id,
        "workflow_id": call.workflow_id,
        "direction": call.direction,
        "from_number": call.from_number,
        "to_number": call.to_number,
        "status": call.status,
        "end_reason": call.end_reason,
        "error_message": call.error_message,
        "ai_voice_provider": call.ai_voice_provider,
        "ai_voice_id": call.ai_voice_id,
        "voice_speed": call.voice_speed,
        "language": call.language,
        "recording_enabled": call.recording_enabled,
        "recording_url": call.recording_url,
        "interrupted_count": call.interrupted_count,
        "fallback_triggered": call.fallback_triggered,
        "handed_off_to_human": call.handed_off_to_human,
        "summary": call.summary,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "answered_at": call.answered_at.isoformat() if call.answered_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": call.duration_seconds,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


def _serialize_transcript(entry: CallTranscriptEntry) -> dict:
    return {
        "id": entry.id,
        "role": entry.role,
        "content": entry.content,
        "sequence": entry.sequence,
        "was_interrupted": entry.was_interrupted,
        "response_time_ms": entry.response_time_ms,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


# NEW (Part 4): "Business hours" admin control. Checked once, on the
# inbound Twilio webhook, before a call is ever connected to the AI/Media
# Stream — an out-of-hours call never reaches the AI at all, it's told the
# business is closed and the call is logged with status="missed" /
# end_reason="outside_business_hours" so it still shows up in analytics.
_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _is_within_business_hours(business_hours: Optional[dict]) -> bool:
    if not business_hours or not business_hours.get("enabled"):
        return True  # not configured / disabled -> always open, unchanged Part 3 behavior
    try:
        tz = ZoneInfo(business_hours.get("timezone") or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = datetime.now(tz)
    day_key = _WEEKDAY_KEYS[now_local.weekday()]
    day_hours = (business_hours.get("days") or {}).get(day_key)
    if not day_hours:
        return False  # no hours configured for today -> closed all day
    try:
        open_h, open_m = (int(x) for x in day_hours["open"].split(":"))
        close_h, close_m = (int(x) for x in day_hours["close"].split(":"))
    except (KeyError, ValueError):
        return True  # malformed config -> fail open rather than block all calls
    now_minutes = now_local.hour * 60 + now_local.minute
    return (open_h * 60 + open_m) <= now_minutes <= (close_h * 60 + close_m)


# ─────────────────────────────────────────────────────────────────────────────
# Voice catalog (reuses tts_engine.py — no second voice engine)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/voices")
async def list_call_voices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserAPIKey.provider).where(UserAPIKey.user_id == current_user.id)
    )
    user_provider_ids = {r[0] for r in result.all()}
    providers = []
    for entry in tts_engine.list_provider_catalog():
        providers.append({**entry, "configured": entry["credential_provider"] in user_provider_ids})
    return providers


# ─────────────────────────────────────────────────────────────────────────────
# Phone number -> Workflow binding + call settings
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/phone-numbers/{number_id}/call-settings")
async def update_call_settings(
    number_id: str,
    payload: CallSettingsPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    if not number.is_enabled:
        raise HTTPException(
            status_code=400,
            detail="Enable AI Call Agent for this number before configuring call settings.",
        )

    if payload.workflow_id is not None:
        if payload.workflow_id:
            wf_result = await db.execute(
                select(Workflow).where(Workflow.id == payload.workflow_id, Workflow.user_id == current_user.id)
            )
            if not wf_result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Workflow not found")
        number.workflow_id = payload.workflow_id or None

    # NEW (Voice AI Part 5): validate + bind a standalone Voice Agent.
    if payload.voice_agent_id is not None:
        if payload.voice_agent_id:
            from app.models.voice_agent import VoiceAgent
            agent_result = await db.execute(
                select(VoiceAgent).where(VoiceAgent.id == payload.voice_agent_id, VoiceAgent.user_id == current_user.id)
            )
            if not agent_result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="Voice Agent not found")
        number.voice_agent_id = payload.voice_agent_id or None

    # NEW (Part 4): validate every bound KB (Text and/or File/PDF) is owned
    # by this user before persisting — a stale/foreign id would otherwise
    # silently retrieve nothing at call time.
    if payload.knowledge_base_ids is not None:
        if payload.knowledge_base_ids:
            kb_result = await db.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.id.in_(payload.knowledge_base_ids),
                    KnowledgeBase.user_id == current_user.id,
                )
            )
            found_ids = {str(r[0]) for r in kb_result.all()}
            missing = set(payload.knowledge_base_ids) - found_ids
            if missing:
                raise HTTPException(status_code=404, detail=f"Knowledge base(s) not found: {', '.join(missing)}")

    if payload.prompt_scope is not None and payload.prompt_scope not in ("strict", "open"):
        raise HTTPException(status_code=400, detail="prompt_scope must be 'strict' or 'open'")
    if payload.interrupt_behavior is not None and payload.interrupt_behavior not in ("interrupt", "queue", "ignore"):
        raise HTTPException(status_code=400, detail="interrupt_behavior must be 'interrupt', 'queue', or 'ignore'")

    settings_blob = dict(number.call_settings or {})
    for field in ("voice_provider", "voice_id", "speed", "language", "recording_enabled",
                  "greeting_message", "fallback_prompt", "system_prompt",
                  "knowledge_base_ids", "prompt_scope", "interrupt_behavior"):
        value = getattr(payload, field)
        if value is not None:
            settings_blob[field] = value
    if payload.business_hours is not None:
        settings_blob["business_hours"] = payload.business_hours.model_dump()
    number.call_settings = settings_blob

    await db.commit()
    await db.refresh(number)
    await audit_service.record(
        db, Action.CALL_AGENT_SETTINGS_UPDATE, actor=current_user, request=request,
        target_type="call_agent", target_id=str(number.id), target_label=number.phone_number,
    )
    return {
        "id": number.id,
        "workflow_id": number.workflow_id,
        "voice_agent_id": number.voice_agent_id,
        "call_settings": number.call_settings,
    }


@router.get("/phone-numbers/{number_id}/call-settings")
async def get_call_settings(
    number_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(number_id, db, current_user)
    return {
        "id": number.id,
        "workflow_id": number.workflow_id,
        "voice_agent_id": number.voice_agent_id,
        "call_settings": number.call_settings or {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Outbound calls
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/calls/outbound", status_code=status.HTTP_201_CREATED)
async def place_outbound_call(
    payload: OutboundCallPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    number = await _get_owned_number(payload.phone_number_id, db, current_user)
    if not number.is_enabled or not number.is_connected or number.status != "verified":
        raise HTTPException(status_code=400, detail="This number is not ready for AI Call Agent calls.")
    if not number.workflow_id:
        raise HTTPException(status_code=400, detail="Bind a Workflow to this number before placing calls.")
    if not call_telephony_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Calling is not configured on this server (Twilio credentials / BACKEND_PUBLIC_URL missing).",
        )

    call_settings = number.call_settings or {}
    call = Call(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        phone_number_id=number.id,
        workflow_id=number.workflow_id,
        direction="outbound",
        from_number=number.phone_number,
        to_number=payload.to_number,
        status="queued",
        session_id=str(uuid.uuid4()),
        ai_voice_provider=call_settings.get("voice_provider"),
        ai_voice_id=call_settings.get("voice_id"),
        voice_speed=float(call_settings.get("speed", 1.0)),
        language=call_settings.get("language", "en-US"),
        recording_enabled=bool(call_settings.get("recording_enabled", False)),
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    try:
        provider_sid = await call_telephony_service.place_outbound_call(
            call_id=call.id, to_number=payload.to_number, from_number=number.phone_number,
        )
        call.provider_call_sid = provider_sid
        call.status = "ringing"
    except TelephonyError as e:
        call.status = "failed"
        call.end_reason = "telephony_error"
        call.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))

    await db.commit()
    await db.refresh(call)
    return _serialize_call(call)


@router.post("/calls/{call_id}/hangup")
async def hangup_call(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    call = await _get_owned_call(call_id, db, current_user)
    if call.provider_call_sid:
        await call_telephony_service.hangup_call(call.provider_call_sid)
    if call.status in ("queued", "ringing", "active"):
        call.status = "completed"
        call.end_reason = "hung_up_by_owner"
        call.ended_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(call)
    return _serialize_call(call)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard + history + transcript
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/calls/dashboard")
async def call_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Counts backing the dashboard cards: Total, Active, Missed, Completed,
    Failed, Interrupted, plus (NEW, Part 4) average duration, average
    response time, total interrupt count, and resolution rate.
    "Interrupted" is completed calls that had at least one barge-in — not
    a separate terminal status."""
    result = await db.execute(
        select(Call.status, func.count(Call.id))
        .where(Call.user_id == current_user.id)
        .group_by(Call.status)
    )
    by_status = {status_: count for status_, count in result.all()}
    total_calls = sum(by_status.values())

    interrupted_result = await db.execute(
        select(func.count(Call.id), func.coalesce(func.sum(Call.interrupted_count), 0)).where(
            Call.user_id == current_user.id,
            Call.status == "completed",
            Call.interrupted_count > 0,
        )
    )
    interrupted_calls, interrupt_count_total = interrupted_result.one()

    # NEW (Part 4): average call duration, over calls that actually have one.
    avg_duration_result = await db.execute(
        select(func.avg(Call.duration_seconds)).where(
            Call.user_id == current_user.id, Call.duration_seconds.isnot(None),
        )
    )
    avg_duration = avg_duration_result.scalar_one()

    # NEW (Part 4): average AI response time, from call_transcript_entries
    # (see CallTranscriptEntry.response_time_ms / call_session_service._speak).
    avg_response_result = await db.execute(
        select(func.avg(CallTranscriptEntry.response_time_ms))
        .join(Call, Call.id == CallTranscriptEntry.call_id)
        .where(Call.user_id == current_user.id, CallTranscriptEntry.response_time_ms.isnot(None))
    )
    avg_response_ms = avg_response_result.scalar_one()

    completed = by_status.get("completed", 0)
    handed_off_result = await db.execute(
        select(func.count(Call.id)).where(
            Call.user_id == current_user.id, Call.status == "completed", Call.handed_off_to_human.is_(True),
        )
    )
    handed_off_completed = handed_off_result.scalar_one()
    # "Resolved" = completed by the AI without needing a human handoff.
    resolution_rate = round((completed - handed_off_completed) / completed, 4) if completed else None

    return {
        "total_calls": total_calls,
        "active": by_status.get("active", 0) + by_status.get("ringing", 0) + by_status.get("queued", 0),
        "missed": by_status.get("missed", 0) + by_status.get("no_answer", 0),
        "completed": completed,
        "failed": by_status.get("failed", 0),
        "interrupted": interrupted_calls,
        "interrupt_count": int(interrupt_count_total or 0),
        "avg_duration_seconds": round(avg_duration, 1) if avg_duration is not None else None,
        "avg_response_time_ms": round(avg_response_ms, 0) if avg_response_ms is not None else None,
        "resolution_rate": resolution_rate,
    }


@router.get("/calls")
async def list_calls(
    status_filter: Optional[str] = None,
    phone_number_id: Optional[str] = None,
    search: Optional[str] = None,          # NEW (Part 4): matches from/to number
    date_from: Optional[datetime] = None,  # NEW (Part 4)
    date_to: Optional[datetime] = None,    # NEW (Part 4)
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Call).where(Call.user_id == current_user.id)
    if phone_number_id:
        query = query.where(Call.phone_number_id == phone_number_id)

    if status_filter == "active":
        query = query.where(Call.status.in_(["active", "ringing", "queued"]))
    elif status_filter == "missed":
        query = query.where(Call.status.in_(["missed", "no_answer"]))
    elif status_filter == "interrupted":
        query = query.where(Call.status == "completed", Call.interrupted_count > 0)
    elif status_filter:
        query = query.where(Call.status == status_filter)

    if search:
        like = f"%{search.strip()}%"
        query = query.where((Call.from_number.ilike(like)) | (Call.to_number.ilike(like)))
    if date_from:
        query = query.where(Call.created_at >= date_from)
    if date_to:
        query = query.where(Call.created_at <= date_to)

    query = query.order_by(Call.created_at.desc()).limit(min(limit, 200)).offset(max(offset, 0))
    result = await db.execute(query)
    calls = result.scalars().all()
    return [_serialize_call(c) for c in calls]


@router.get("/calls/{call_id}")
async def get_call(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    call = await _get_owned_call(call_id, db, current_user)
    return _serialize_call(call)


@router.get("/calls/{call_id}/transcript")
async def get_call_transcript(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    call = await _get_owned_call(call_id, db, current_user)
    result = await db.execute(
        select(CallTranscriptEntry)
        .where(CallTranscriptEntry.call_id == call.id)
        .order_by(CallTranscriptEntry.sequence.asc())
    )
    return [_serialize_transcript(e) for e in result.scalars().all()]


# ─────────────────────────────────────────────────────────────────────────────
# NEW (Part 4) — Call recording summary
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/calls/{call_id}/summary")
async def regenerate_call_summary(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """(Re)generates the AI summary of this call's transcript on demand —
    the same generation call_stream_ws.py already fires automatically once
    a call ends (see services/call_summary_service.py)."""
    call = await _get_owned_call(call_id, db, current_user)
    if call.status in ("active", "ringing", "queued"):
        raise HTTPException(status_code=400, detail="Call is still in progress")
    summary = await call_summary_service.generate_and_store_summary(call.id, str(current_user.id))
    if summary is None:
        raise HTTPException(status_code=422, detail="Not enough transcript content to summarize")
    return {"id": call.id, "summary": summary}


# ─────────────────────────────────────────────────────────────────────────────
# NEW (Part 4) — Human handoff during a call
#
# Reuses services/live_agent_service.py exactly as api/v1/live_agent.py
# does for chat: a call is just another `channel="voice_call"` conversation
# under the same handoff state machine (waiting -> active -> ai, with
# "paused" also supported). services/call_session_service.py's per-turn
# handoff-status check is what actually stops the AI from responding once
# a human has taken the call — these endpoints only move the shared
# handoff row's status; they never touch the Media Stream/audio directly.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/calls/{call_id}/handoff")
async def handoff_call_to_human(
    call_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Human agent takes over an in-progress (or already-escalated) call.
    From this point, the caller's speech is transcribed and shown to the
    agent, and anything the agent types in the Live Agent dashboard is
    spoken to the caller via TTS (see call_session_service._LiveAgentSocketAdapter) —
    reusing the exact same text-based takeover console already built for
    web chat, rather than a second real-time audio-conferencing system."""
    call = await _get_owned_call(call_id, db, current_user)
    if call.status not in ("active", "ringing", "queued"):
        raise HTTPException(status_code=400, detail="This call is not currently in progress")

    handoff_result = await db.execute(
        select(LiveAgentHandoff).where(LiveAgentHandoff.session_id == call.session_id)
    )
    handoff = handoff_result.scalar_one_or_none()

    if not handoff:
        # No prior AI-triggered escalation for this call — create one now
        # so the proactive "Take over" button works even on a call that's
        # going perfectly fine.
        await live_agent_service.request_handoff(
            session_id=call.session_id, workflow_id=call.workflow_id or "",
            owner_id=str(current_user.id), channel="voice_call",
            reason="Manually taken over by agent", requested_by="agent",
        )
        handoff_result = await db.execute(
            select(LiveAgentHandoff).where(LiveAgentHandoff.session_id == call.session_id)
        )
        handoff = handoff_result.scalar_one_or_none()
    if not handoff:
        raise HTTPException(status_code=500, detail="Could not set up handoff for this call")

    result = await live_agent_service.take_over(
        handoff_id=handoff.id, agent_user_id=str(current_user.id), owner_id=str(current_user.id),
    )

    call.handed_off_to_human = True
    await db.commit()
    await audit_service.record(
        db, Action.CALL_AGENT_HANDOFF_TO_HUMAN, actor=current_user, request=request,
        target_type="call", target_id=call.id, target_label=call.to_number or call.from_number,
    )
    return {"call_id": call.id, "handoff_status": result.get("status"), "handoff": result}


@router.post("/calls/{call_id}/resume-ai")
async def resume_ai_on_call(
    call_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Human agent hands the call back to the AI Call Agent."""
    call = await _get_owned_call(call_id, db, current_user)
    handoff_result = await db.execute(
        select(LiveAgentHandoff).where(LiveAgentHandoff.session_id == call.session_id)
    )
    handoff = handoff_result.scalar_one_or_none()
    if not handoff:
        raise HTTPException(status_code=404, detail="This call has no handoff to resume from")

    result = await live_agent_service.return_to_ai(
        handoff_id=handoff.id, owner_id=str(current_user.id), actor_user_id=str(current_user.id),
    )

    call.handed_off_to_human = False
    await db.commit()
    await audit_service.record(
        db, Action.CALL_AGENT_RESUME_AI, actor=current_user, request=request,
        target_type="call", target_id=call.id, target_label=call.to_number or call.from_number,
    )
    return {"call_id": call.id, "handoff_status": result.get("status"), "handoff": result}


@router.get("/calls/{call_id}/handoff-status")
async def get_call_handoff_status(
    call_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    call = await _get_owned_call(call_id, db, current_user)
    status_value = await live_agent_service.get_handoff_status(session_id=call.session_id)
    return {"call_id": call.id, "handoff_status": status_value or "ai"}


@router.post("/calls/{call_id}/agent-message")
async def send_agent_message_on_call(
    call_id: str,
    payload: AgentMessagePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """While a human has taken over (see handoff_call_to_human), sends the
    agent's typed message to be spoken to the caller over the phone."""
    call = await _get_owned_call(call_id, db, current_user)
    handoff_result = await db.execute(
        select(LiveAgentHandoff).where(LiveAgentHandoff.session_id == call.session_id)
    )
    handoff = handoff_result.scalar_one_or_none()
    if not handoff or handoff.status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="Take over this call before sending messages")

    result = await live_agent_service.send_agent_message(
        handoff_id=handoff.id, owner_id=str(current_user.id),
        agent_user_id=str(current_user.id), content=payload.content,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Twilio webhooks (NOT authenticated — verified via X-Twilio-Signature)
# ─────────────────────────────────────────────────────────────────────────────

async def _verify_request(request: Request) -> dict:
    form = await request.form()
    form_dict = {k: str(v) for k, v in form.items()}
    signature = request.headers.get("X-Twilio-Signature")
    url = str(request.url)
    if not call_telephony_service.verify_twilio_signature(url, form_dict, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    return form_dict


@router.post("/twilio/voice")
async def twilio_voice_webhook(
    request: Request,
    call_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """TwiML entry point for BOTH directions:
      - Outbound: Twilio requests this once the callee answers, call_id is
        the query param we set in place_outbound_call().
      - Inbound: Twilio requests this the moment a call arrives at one of
        our numbers — no call_id yet, so we create the Call row here,
        matched by the dialed `To` number."""
    form = await _verify_request(request)

    if call_id:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call:
            return Response(
                content=call_telephony_service.build_unavailable_twiml("This call could not be found."),
                media_type="application/xml",
            )
    else:
        to_number = form.get("To", "")
        from_number = form.get("From", "")
        provider_call_sid = form.get("CallSid", "")

        number_result = await db.execute(select(PhoneNumber).where(PhoneNumber.phone_number == to_number))
        number = number_result.scalar_one_or_none()

        if not number or not number.is_enabled or not number.is_connected:
            return Response(
                content=call_telephony_service.build_unavailable_twiml(
                    "This number is not set up to take AI calls right now."
                ),
                media_type="application/xml",
            )
        if not number.workflow_id:
            return Response(
                content=call_telephony_service.build_unavailable_twiml(
                    "This AI Call Agent has not been configured with a bot yet."
                ),
                media_type="application/xml",
            )

        call_settings = number.call_settings or {}

        # NEW (Part 4) — Business hours admin control: gate BEFORE the Call
        # row/Media Stream is ever created, so an out-of-hours call never
        # reaches the AI. Still logged (status="missed") so it shows up in
        # call history/analytics like any other missed call.
        if not _is_within_business_hours(call_settings.get("business_hours")):
            closed_call = Call(
                id=str(uuid.uuid4()), user_id=number.user_id, phone_number_id=number.id,
                workflow_id=number.workflow_id, direction="inbound", from_number=from_number,
                to_number=to_number, status="missed", end_reason="outside_business_hours",
                provider_call_sid=provider_call_sid, session_id=str(uuid.uuid4()),
                started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc),
            )
            db.add(closed_call)
            await db.commit()
            closed_message = (call_settings.get("fallback_prompt") or "").strip() or app_settings.VOICE_CALL_CLOSED_MESSAGE
            return Response(
                content=call_telephony_service.build_unavailable_twiml(closed_message),
                media_type="application/xml",
            )

        call = Call(
            id=str(uuid.uuid4()),
            user_id=number.user_id,
            phone_number_id=number.id,
            workflow_id=number.workflow_id,
            direction="inbound",
            from_number=from_number,
            to_number=to_number,
            status="ringing",
            provider_call_sid=provider_call_sid,
            session_id=str(uuid.uuid4()),
            ai_voice_provider=call_settings.get("voice_provider"),
            ai_voice_id=call_settings.get("voice_id"),
            voice_speed=float(call_settings.get("speed", 1.0)),
            language=call_settings.get("language", "en-US"),
            recording_enabled=bool(call_settings.get("recording_enabled", False)),
            started_at=datetime.now(timezone.utc),
        )
        db.add(call)
        await db.commit()
        await db.refresh(call)

    twiml = call_telephony_service.build_connect_stream_twiml(call.id, recording_enabled=call.recording_enabled)
    return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status_webhook(
    request: Request,
    call_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    form = await _verify_request(request)
    twilio_status = form.get("CallStatus", "")
    provider_call_sid = form.get("CallSid")

    query = select(Call).where(Call.id == call_id) if call_id else \
        select(Call).where(Call.provider_call_sid == provider_call_sid)
    result = await db.execute(query)
    call = result.scalar_one_or_none()
    if not call:
        return Response(status_code=204)

    if twilio_status == "ringing":
        call.status = "ringing"
    elif twilio_status == "in-progress":
        call.status = "active"
        if not call.answered_at:
            call.answered_at = datetime.now(timezone.utc)
    elif twilio_status in ("no-answer", "canceled"):
        call.status = "missed" if call.direction == "inbound" else "no_answer"
        call.end_reason = twilio_status
        call.ended_at = datetime.now(timezone.utc)
    elif twilio_status == "busy":
        call.status = "failed"
        call.end_reason = "busy"
        call.ended_at = datetime.now(timezone.utc)
    elif twilio_status == "failed":
        call.status = "failed"
        call.end_reason = "provider_failed"
        call.ended_at = datetime.now(timezone.utc)
    elif twilio_status == "completed":
        # Don't downgrade a status the Media Stream close handler already
        # set more precisely (e.g. "failed" mid-call) — only fill in
        # "completed" if nothing more specific has been recorded.
        if call.status not in ("failed", "missed", "no_answer", "completed"):
            call.status = "completed"
        call.ended_at = call.ended_at or datetime.now(timezone.utc)
        duration = form.get("CallDuration")
        if duration and duration.isdigit():
            call.duration_seconds = int(duration)

    await db.commit()
    return Response(status_code=204)


@router.post("/twilio/recording-status")
async def twilio_recording_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await _verify_request(request)
    provider_call_sid = form.get("CallSid")
    recording_sid = form.get("RecordingSid")
    recording_url = form.get("RecordingUrl")

    if not provider_call_sid:
        return Response(status_code=204)

    result = await db.execute(select(Call).where(Call.provider_call_sid == provider_call_sid))
    call = result.scalar_one_or_none()
    if call:
        call.recording_provider_sid = recording_sid
        call.recording_url = f"{recording_url}.mp3" if recording_url else None
        await db.commit()

    return Response(status_code=204)
