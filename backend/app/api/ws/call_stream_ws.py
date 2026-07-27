"""
ThunderBots AI Call Agent — Twilio Media Stream WebSocket (NEW, Voice AI Part 3)

Speaks Twilio's Media Streams protocol (base64 mu-law/8000 frames over a
plain WebSocket) and delegates ALL AI/telephony-audio logic to
services/call_session_service.py — this file is purely protocol
translation: Twilio JSON frames in, CallSession calls out, Twilio JSON
frames back out. No AI Engine, Knowledge Base, or Workflow Runtime code
lives here, mirroring exactly how api/ws/chat_ws.py is the thin protocol
layer over the same Workflow Runtime.

Protocol reference (Twilio Media Streams):
  connected -> start (has streamSid, callSid, customParameters.call_id)
  -> media* (inbound audio) -> stop
Outbound: {"event":"media", streamSid, media:{payload: b64}}
          {"event":"clear", streamSid}   (used for barge-in)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.ws.chat_ws import get_deployed_workflow_data
from app.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import CacheService
from app.models.call import Call
from app.models.phone_number import PhoneNumber
from app.models.voice_agent import VoiceAgent
from app.services import call_summary_service
from app.services.call_session_service import CallSession

router = APIRouter()
logger = logging.getLogger(__name__)


# ── NEW (Voice AI Part 5) — standalone Voice Agent call runtime ────────────
# A Voice Agent has no Workflow graph of its own, so instead of teaching
# WorkflowRunner a second execution model, we hand it the smallest possible
# valid graph: a "start" node auto-advancing into exactly one "ai_agent"
# node built from the agent's own provider/model/instructions. This reuses
# every existing AI Agent node code path (provider resolution, streaming,
# error fallback — see engine/node_handlers/__init__.py:AIAgentNodeHandler)
# completely unmodified. The Workflow Runtime, Builder, and every
# Workflow-bound call are untouched by this — see PhoneNumber.voice_agent_id
# docstring for why both binding styles coexist.
def _compose_voice_agent_instructions(agent: VoiceAgent) -> str:
    instructions = agent.instructions or {}
    sections = [
        ("Role", instructions.get("role")),
        ("Behaviour", instructions.get("behaviour")),
        ("Tone", instructions.get("tone")),
        ("Rules", instructions.get("rules")),
        ("Business policies", instructions.get("business_policies")),
        ("Sales instructions", instructions.get("sales_instructions")),
        ("Appointment booking rules", instructions.get("appointment_booking_rules")),
        ("Escalation rules", instructions.get("escalation_rules")),
        ("Response restrictions", instructions.get("response_restrictions")),
    ]
    parts = [f"{label}: {value.strip()}" for label, value in sections if value and value.strip()]
    if agent.personality and agent.personality.strip():
        parts.append(f"Personality: {agent.personality.strip()}")
    if agent.goals and agent.goals.strip():
        parts.append(f"Goals: {agent.goals.strip()}")
    return "\n".join(parts)


def build_synthetic_voice_agent_workflow(agent: VoiceAgent) -> dict:
    return {
        "id": f"voice-agent-{agent.id}",
        "owner_id": str(agent.user_id),
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {
                "id": "voice-agent-node",
                "type": "ai_agent",
                "data": {
                    "provider": agent.ai_provider or None,
                    "model": agent.ai_model or "",
                    "systemPrompt": _compose_voice_agent_instructions(agent),
                    "instructions": "",
                    "temperature": agent.temperature,
                    "maxTokens": 1000,
                    "stayOnNode": True,
                },
            },
        ],
        "edges": [
            {"source": "start", "target": "voice-agent-node", "sourceHandle": "output_0"},
        ],
    }


async def _load_call(call_id: str) -> Call | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Call).where(Call.id == call_id))
        return result.scalar_one_or_none()


async def _mark_active(call_id: str, provider_call_sid: str | None) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call:
            return
        call.status = "active"
        call.answered_at = datetime.now(timezone.utc)
        if provider_call_sid and not call.provider_call_sid:
            call.provider_call_sid = provider_call_sid
        await db.commit()


async def _mark_ended(call_id: str, *, interrupted_count: int, fallback_triggered: bool,
                       handed_off: bool, reason: str = "completed") -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if not call:
            return
        now = datetime.now(timezone.utc)
        call.ended_at = now
        call.status = "completed" if call.status not in ("failed", "missed") else call.status
        call.end_reason = reason
        call.interrupted_count = interrupted_count
        call.fallback_triggered = fallback_triggered
        call.handed_off_to_human = handed_off
        if call.answered_at:
            call.duration_seconds = max(int((now - call.answered_at).total_seconds()), 0)
        await db.commit()


@router.websocket("/call-agent/stream/{call_id}")
async def call_media_stream(websocket: WebSocket, call_id: str):
    await websocket.accept()

    call = await _load_call(call_id)
    if not call:
        await websocket.close(code=4004)
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PhoneNumber).where(PhoneNumber.id == call.phone_number_id))
        phone_number = result.scalar_one_or_none()

    if not phone_number or not (phone_number.workflow_id or phone_number.voice_agent_id):
        logger.warning(f"call={call_id} has no bound workflow or Voice Agent — cannot run AI Call Agent")
        await websocket.close(code=4004)
        return

    cache = CacheService()
    call_settings = phone_number.call_settings or {}
    voice_agent: VoiceAgent | None = None
    extra_kb_collection: dict | None = None

    # NEW (Voice AI Part 5): a standalone Voice Agent takes priority over a
    # Workflow binding when both happen to be set (the UI only ever sets
    # one). Everything below the branch — audio pipeline, transcript
    # saving, summaries — is identical for both paths.
    if phone_number.voice_agent_id:
        async with AsyncSessionLocal() as db:
            va_result = await db.execute(select(VoiceAgent).where(VoiceAgent.id == phone_number.voice_agent_id))
            voice_agent = va_result.scalar_one_or_none()
        if not voice_agent or not voice_agent.is_enabled:
            logger.warning(f"call={call_id} voice_agent={phone_number.voice_agent_id} is missing or disabled")
            await websocket.close(code=4004)
            return
        workflow = build_synthetic_voice_agent_workflow(voice_agent)
        extra_kb_collection = {
            "kb_id": voice_agent.id,
            "collection": voice_agent.chroma_collection,
            "name": voice_agent.name,
            "embedding_provider": voice_agent.embedding_provider,
            "embedding_model": voice_agent.embedding_model,
        }
    else:
        workflow = await get_deployed_workflow_data(phone_number.workflow_id, cache)
        if not workflow:
            logger.warning(f"call={call_id} workflow={phone_number.workflow_id} is not published")
            await websocket.close(code=4004)
            return

    if voice_agent:
        voice_provider = voice_agent.voice_provider or call_settings.get("voice_provider", settings.VOICE_CALL_DEFAULT_VOICE_PROVIDER)
        voice_id = voice_agent.voice_id or call_settings.get("voice_id", settings.VOICE_CALL_DEFAULT_VOICE_ID)
        voice_speed = float(voice_agent.speaking_speed or call_settings.get("speed", settings.VOICE_CALL_DEFAULT_SPEED))
        language = voice_agent.language or call_settings.get("language", settings.VOICE_CALL_DEFAULT_LANGUAGE)
    else:
        voice_provider = call_settings.get("voice_provider", settings.VOICE_CALL_DEFAULT_VOICE_PROVIDER)
        voice_id = call_settings.get("voice_id", settings.VOICE_CALL_DEFAULT_VOICE_ID)
        voice_speed = float(call_settings.get("speed", settings.VOICE_CALL_DEFAULT_SPEED))
        language = call_settings.get("language", settings.VOICE_CALL_DEFAULT_LANGUAGE)

    stream_sid: str | None = None

    async def send_audio_frames(mulaw_frame: bytes) -> None:
        if not stream_sid:
            return
        await websocket.send_json({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(mulaw_frame).decode("ascii")},
        })

    async def send_clear() -> None:
        if not stream_sid:
            return
        await websocket.send_json({"event": "clear", "streamSid": stream_sid})

    session = CallSession(
        call_id=call_id,
        session_id=call.session_id,
        owner_id=str(workflow["owner_id"]),
        workflow=workflow,
        voice_provider=voice_provider,
        voice_id=voice_id,
        voice_speed=voice_speed,
        language=language,
        send_audio_frames=send_audio_frames,
        send_clear=send_clear,
        # NEW (Part 4) — admin controls read straight from the same
        # PhoneNumber.call_settings blob (no new columns needed).
        greeting_message=(voice_agent.welcome_message if voice_agent and voice_agent.welcome_message else call_settings.get("greeting_message")),
        fallback_message=(voice_agent.fallback_message if voice_agent and voice_agent.fallback_message else call_settings.get("fallback_prompt")),
        knowledge_base_ids=call_settings.get("knowledge_base_ids"),
        system_prompt=call_settings.get("system_prompt"),
        prompt_scope=call_settings.get("prompt_scope", settings.VOICE_CALL_DEFAULT_PROMPT_SCOPE),
        interrupt_behavior=(
            call_settings.get("interrupt_behavior", settings.VOICE_CALL_DEFAULT_INTERRUPT_BEHAVIOR)
            if not voice_agent else
            ("interrupt" if voice_agent.interrupt_enabled else "queue")
        ),
        extra_kb_collection=extra_kb_collection,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = data.get("event")
            if event == "start":
                stream_sid = data.get("streamSid")
                provider_call_sid = data.get("start", {}).get("callSid")
                await _mark_active(call_id, provider_call_sid)
                await session.start()
            elif event == "media":
                payload = data.get("media", {}).get("payload")
                if payload:
                    await session.push_inbound_audio(base64.b64decode(payload))
            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001 — never let a protocol error skip cleanup below
        logger.error(f"call={call_id} media stream error: {e}", exc_info=True)
    finally:
        await session.close()
        await _mark_ended(
            call_id,
            interrupted_count=session.interrupted_count,
            fallback_triggered=session.fallback_triggered,
            handed_off=session.handed_off,
        )
        # NEW (Part 4): call recording summary — fire-and-forget, same
        # pattern as services/analytics_service.record_turn. Never awaited
        # inline: it must not delay the WebSocket from closing, and its own
        # failures are already swallowed internally (see
        # call_summary_service.generate_and_store_summary docstring).
        asyncio.create_task(
            call_summary_service.generate_and_store_summary(call_id, str(session.owner_id))
        )
