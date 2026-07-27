"""
ThunderBots AI Call Agent — Call Session Orchestrator
(NEW, Voice AI Part 3; extended in Part 4)

This is the "brain" that turns one phone call into a sequence of Workflow
Runtime turns, reusing every existing piece exactly the way chat_ws.py and
api/v1/whatsapp.py already do for their own channels:

  - app.engine.runner.WorkflowRunner + app.engine.context.ExecutionContext
    for the AI Agent / Knowledge Base / Memory / Workflow Runtime turn.
    SAME session_id, SAME Redis-cached context, SAME `stream_run()` used by
    the web chat WebSocket — a call is just another channel, not a second
    runtime.
  - services.tts_engine.synthesize() for text-to-speech (Voice Responses,
    Part 1) — NOT a second voice engine. This module only adds
    call_audio_utils.tts_audio_to_mulaw8k() on top of its output to get
    telephony-format audio.
  - services.call_stt_service for realtime speech-to-text.
  - services.live_agent_service — reused for BOTH the "fast fallback"
    escalation (Part 3, unchanged) AND, NEW in Part 4, the call-specific
    "Human Handoff" admin control: request_handoff/take_over/return_to_ai/
    get_handoff_status/record_visitor_message/send_agent_message are the
    exact same generic, channel-agnostic functions chat_ws.py already uses
    for web chat (channel="voice_call" is just another value of the same
    `channel` column) — no second handoff/queue system for calls.

Barge-in: the instant a `speech_started` STT event arrives while the AI is
speaking, `_barge_in()` cancels the in-flight LLM-stream task AND the
in-flight TTS-synthesis task, sends Twilio a `clear` event (flushes any
audio Twilio has buffered but not yet played), and the new caller utterance
is handled as soon as its `final` transcript arrives — no queueing behind
the old turn. NEW (Part 4): this is now gated by a per-call
`interrupt_behavior` setting rather than only the global feature flag —
"queue" lets the AI finish its sentence before addressing the caller's new
utterance, "ignore" disables barge-in entirely for that number.

NEW (Part 4) — Knowledge Base combination + scope control: before each turn
is handed to the Workflow Runtime, `_build_augmented_message()` retrieves
relevant chunks from every Knowledge Base (Text and/or PDF/file — same
KnowledgeBase rows, same retrieval_engine.retrieve(), no duplicate
retrieval logic) bound to the phone number's call_settings, and combines
them with an optional call-specific `system_prompt` into one instruction
block prepended to the caller's message. The Workflow's own AI Agent
node/system prompt is completely untouched — this only changes what user
message reaches it, exactly like a human dictating extra context before
asking their question. `prompt_scope="strict"` skips the LLM turn entirely
and speaks the configured fallback prompt when nothing relevant is found in
the bound Knowledge Bases, which is the literal, deterministic form of "if
the answer is not in the knowledge base, return a clear fallback".
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Awaitable, Callable, Optional

from sqlalchemy import select

from app.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis import CacheService
from app.engine.context import ExecutionContext
from app.engine.runner import WorkflowRunner
from app.knowledge.pipeline import retrieval_engine
from app.models.call import Call, CallTranscriptEntry
from app.models.knowledge import KnowledgeBase
from app.models.user import UserAPIKey
from app.services import call_audio_utils, call_stt_service, live_agent_service, live_agent_ws_manager, tts_engine
from app.services.ai_engine import decrypt_key

logger = logging.getLogger(__name__)

# Splits accumulated LLM tokens into speakable chunks at sentence
# boundaries so TTS can start on the first sentence while the model is
# still generating the rest — this is the "streaming response" requirement,
# built on top of the existing non-streaming-per-sentence tts_engine call.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_MAX_CHUNK_CHARS = 240  # don't let one TTS call run away on unpunctuated text

# NEW (Part 4): how many chunks to retrieve per bound Knowledge Base per
# turn — kept small since several KBs may be bound at once and the combined
# context still has to fit comfortably in the augmented message.
_KB_RESULTS_PER_KB = 3
_KB_SCORE_THRESHOLD = 0.3


async def _get_user_key(db, user_id: str, credential_provider: str) -> Optional[UserAPIKey]:
    result = await db.execute(
        select(UserAPIKey).where(
            UserAPIKey.user_id == user_id, UserAPIKey.provider == credential_provider,
        )
    )
    return result.scalar_one_or_none()


class _LiveAgentSocketAdapter:
    """NEW (Part 4). Satisfies the same tiny interface
    live_agent_ws_manager expects of a "visitor socket" (an object with an
    async `send_json(payload)`) so a phone call can be registered exactly
    like a chat_ws.py WebSocket connection — no changes to
    live_agent_ws_manager/live_agent_service needed. A human agent's typed
    dashboard reply (`type: "agent_message"`) is spoken to the caller via
    TTS; `human_joined`/`human_left` are recorded into the call transcript
    so the transcript reads as one consistent timeline regardless of who
    was actually talking.
    """

    def __init__(self, session: "CallSession"):
        self._session = session

    async def send_json(self, payload: dict) -> None:
        ptype = payload.get("type")
        if ptype == "agent_message":
            agent_name = payload.get("agent_name") or "Agent"
            content = payload.get("content") or ""
            if content.strip():
                await self._session._record_transcript("system", f"[{agent_name}]: {content}")
                await self._session._speak(content)
        elif ptype == "human_joined":
            await self._session._record_transcript(
                "system", f"[{payload.get('agent_name') or 'A human agent'} joined the call]"
            )
        elif ptype in ("human_left",):
            await self._session._record_transcript("system", "[Human agent returned the call to the AI]")


class CallSession:
    def __init__(
        self,
        *,
        call_id: str,
        session_id: str,
        owner_id: str,
        workflow: dict,
        voice_provider: str,
        voice_id: str,
        voice_speed: float,
        language: str,
        send_audio_frames: Callable[[bytes], Awaitable[None]],
        send_clear: Callable[[], Awaitable[None]],
        # NEW (Part 4) — admin controls, all optional/backward-compatible.
        greeting_message: Optional[str] = None,
        fallback_message: Optional[str] = None,
        knowledge_base_ids: Optional[list[str]] = None,
        system_prompt: Optional[str] = None,
        prompt_scope: str = "open",           # "strict" | "open"
        interrupt_behavior: str = "interrupt",  # "interrupt" | "queue" | "ignore"
        # NEW (Voice AI Part 5): a standalone Voice Agent's OWN Knowledge
        # Base — a completely separate table/collection from the
        # KnowledgeBase rows `knowledge_base_ids` above points at (see
        # models/voice_agent.py:VoiceAgentKBDocument). Optional dict:
        # {"kb_id", "collection", "name", "embedding_provider", "embedding_model"}.
        # Retrieved in `_retrieve_kb_context` exactly like a bound
        # KnowledgeBase, just from a different table — additive, never
        # required, never touches the workflow_id KB path above.
        extra_kb_collection: Optional[dict] = None,
    ):
        self.call_id = call_id
        self.session_id = session_id
        self.owner_id = owner_id
        self.workflow = workflow
        self.voice_provider = voice_provider
        self.voice_id = voice_id
        self.voice_speed = voice_speed
        self.language = language
        self._send_audio_frames = send_audio_frames
        self._send_clear = send_clear

        self.greeting_message = (greeting_message or "").strip() or None
        self.fallback_message = (fallback_message or "").strip() or settings.VOICE_CALL_FALLBACK_MESSAGE
        self.knowledge_base_ids = [kb_id for kb_id in (knowledge_base_ids or []) if kb_id]
        self.system_prompt = (system_prompt or "").strip() or None
        self.prompt_scope = prompt_scope if prompt_scope in ("strict", "open") else "open"
        self.interrupt_behavior = interrupt_behavior if interrupt_behavior in ("interrupt", "queue", "ignore") else "interrupt"
        self.extra_kb_collection = extra_kb_collection or None

        self.cache = CacheService()
        self.runner = WorkflowRunner(workflow, user_id=owner_id)
        self.stt = call_stt_service.create_session(language=language)

        self.ai_speaking = False
        self._turn_task: Optional[asyncio.Task] = None
        self._sequence = 0
        self._closed = False
        self.interrupted_count = 0
        self.fallback_triggered = False
        self.handed_off = False
        self._partial_buffer = ""
        # NEW (Part 4): timestamp of the caller's utterance finishing, and
        # the latency computed from it — used to record per-turn AI
        # response time for analytics (see _speak/_record_transcript).
        self._turn_started_at: Optional[float] = None
        self._pending_response_time_ms: Optional[int] = None

        self._kb_cache: Optional[list[KnowledgeBase]] = None
        self._live_agent_adapter = _LiveAgentSocketAdapter(self)

    # ── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        # NEW (Part 4): register this call so a human agent's dashboard
        # reply (send_agent_message -> ws_manager.send_to_visitor) reaches
        # this call and gets spoken over the phone — same registry
        # chat_ws.py already uses for web chat visitors.
        live_agent_ws_manager.register_visitor(self.session_id, self._live_agent_adapter)

        await self.stt.connect()
        asyncio.create_task(self._consume_stt_events())

        if self.greeting_message:
            await self._speak(self.greeting_message)
            await self._record_transcript("ai", self.greeting_message)

    async def close(self) -> None:
        self._closed = True
        live_agent_ws_manager.unregister_visitor(self.session_id)
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        await self.stt.close()

    # ── inbound audio from Twilio ────────────────────────────────────────

    async def push_inbound_audio(self, mulaw_bytes: bytes) -> None:
        await self.stt.send_audio(mulaw_bytes)

    # ── STT event loop ───────────────────────────────────────────────────

    async def _consume_stt_events(self) -> None:
        try:
            async for event in self.stt.events():
                if self._closed:
                    break
                etype = event.get("type")
                if etype == "speech_started":
                    # NEW (Part 4): barge-in is now gated by the per-call
                    # interrupt_behavior in addition to the existing global
                    # kill switch — "queue" and "ignore" both leave the AI
                    # speaking uninterrupted; "queue" still lets the
                    # caller's new utterance be handled as soon as the AI
                    # finishes (it's simply the next turn), "ignore" is a
                    # straight barge-in-disabled call.
                    if (
                        settings.VOICE_CALL_BARGE_IN_ENABLED
                        and self.interrupt_behavior == "interrupt"
                        and self.ai_speaking
                    ):
                        await self._barge_in()
                elif etype == "final":
                    await self._handle_user_utterance(event["text"])
                elif etype == "unavailable":
                    await self._handle_stt_unavailable()
        except Exception as e:  # noqa: BLE001 — never let the STT loop crash the call
            logger.error(f"call={self.call_id} STT event loop error: {e}", exc_info=True)

    async def _barge_in(self) -> None:
        """Instantly stops AI speech: cancels the in-flight turn task (which
        owns both the LLM stream and any in-flight TTS synthesis) and tells
        Twilio to drop any audio it has buffered but hasn't played yet."""
        self.interrupted_count += 1
        self.ai_speaking = False
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        await self._send_clear()
        await self._record_transcript("system", "[caller interrupted the AI]", was_interrupted=True)
        logger.info(f"call={self.call_id} barge-in #{self.interrupted_count}")

    # ── turn execution ───────────────────────────────────────────────────

    async def _handle_user_utterance(self, text: str) -> None:
        if not text.strip():
            return
        await self._record_transcript("caller", text)
        self._turn_started_at = time.monotonic()

        # NEW (Part 4) — Human Handoff: once this call has been queued for
        # or taken over by a human agent (same status values chat_ws.py's
        # equivalent gate already checks: waiting|active|paused), the AI
        # Agent/Workflow Runtime is skipped entirely — the caller's speech
        # is only transcribed and pushed to the agent dashboard. This is
        # the ONLY place call turn execution is ever skipped, mirroring
        # chat_ws.py's own single gate for the same reason.
        handoff_status = await live_agent_service.get_handoff_status(session_id=self.session_id)
        if handoff_status in ("waiting", "active", "paused"):
            await live_agent_service.record_visitor_message(
                session_id=self.session_id, workflow_id=self.workflow.get("id", ""),
                owner_id=self.owner_id, content=text,
            )
            return

        # Serialize turns: if a previous turn task is somehow still running
        # (shouldn't normally happen — barge-in already cancels it) wait for
        # it to actually finish cancelling before starting the next one.
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
            try:
                await self._turn_task
            except (asyncio.CancelledError, Exception):
                pass
        self._turn_task = asyncio.create_task(self._run_turn(text))

    # ── NEW (Part 4): Knowledge Base combination + scope control ──────────

    async def _load_bound_knowledge_bases(self) -> list[KnowledgeBase]:
        """Loads (and caches for the lifetime of the call) the
        KnowledgeBase rows bound to this call — Text and/or File/PDF KBs
        alike, since both are the same KnowledgeBase model (see
        models/knowledge.py:KnowledgeBase.kb_type). Rows the owner no
        longer has (deleted mid-call) are silently skipped rather than
        failing the turn."""
        if self._kb_cache is not None:
            return self._kb_cache
        if not self.knowledge_base_ids:
            self._kb_cache = []
            return self._kb_cache
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id.in_(self.knowledge_base_ids),
                    KnowledgeBase.user_id == self.owner_id,
                )
            )
            self._kb_cache = list(result.scalars().all())
        return self._kb_cache

    async def _retrieve_kb_context(self, query: str) -> tuple[str, bool]:
        """Retrieves relevant chunks from every bound Knowledge Base for
        this turn's query. Returns (formatted_context, any_results_found).
        Never raises — a single KB's retrieval failure (e.g. its embedding
        key was removed mid-call) is logged and skipped so one bad KB never
        breaks a call that has other working ones bound."""
        kbs = await self._load_bound_knowledge_bases()
        if not kbs:
            return "", False

        blocks: list[str] = []
        any_hits = False
        for kb in kbs:
            try:
                results = await retrieval_engine.retrieve(
                    query=query,
                    collection_name=kb.chroma_collection,
                    kb_id=kb.id,
                    n_results=_KB_RESULTS_PER_KB,
                    score_threshold=_KB_SCORE_THRESHOLD,
                    user_id=self.owner_id,
                    embedding_provider=kb.embedding_provider,
                    embedding_model=kb.embedding_model,
                )
            except Exception as e:  # noqa: BLE001 — one bad KB must not break the call
                logger.warning(f"call={self.call_id} KB retrieval failed for kb={kb.id} ('{kb.name}'): {e}")
                continue
            if results:
                any_hits = True
                label = "Text Knowledge Base" if kb.kb_type == "text" else "Knowledge Base"
                blocks.append(
                    f"[{label}: {kb.name}]\n" + retrieval_engine.format_context(results)
                )

        # NEW (Voice AI Part 5): a standalone Voice Agent's own Knowledge
        # Base, retrieved from its own table/collection alongside any
        # Workflow-bound KnowledgeBase rows above. Failure here is just as
        # non-fatal as any other KB's.
        if self.extra_kb_collection:
            try:
                extra_results = await retrieval_engine.retrieve(
                    query=query,
                    collection_name=self.extra_kb_collection["collection"],
                    kb_id=self.extra_kb_collection["kb_id"],
                    n_results=_KB_RESULTS_PER_KB,
                    score_threshold=_KB_SCORE_THRESHOLD,
                    user_id=self.owner_id,
                    embedding_provider=self.extra_kb_collection.get("embedding_provider"),
                    embedding_model=self.extra_kb_collection.get("embedding_model"),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"call={self.call_id} Voice Agent KB retrieval failed: {e}")
                extra_results = []
            if extra_results:
                any_hits = True
                blocks.append(
                    f"[Knowledge Base: {self.extra_kb_collection.get('name', 'Voice Agent')}]\n"
                    + retrieval_engine.format_context(extra_results)
                )

        return "\n\n---\n\n".join(blocks), any_hits

    async def _build_augmented_message(self, user_message: str) -> Optional[str]:
        """Combines Text KB + PDF/File KB + call-specific system prompt with
        the caller's message and a scope instruction, WITHOUT touching the
        Workflow's own AI Agent node/system prompt (that continues to run
        completely unchanged inside runner.stream_run — this only changes
        what user message reaches it, the same as a human prepending extra
        context before their question).

        Returns None when prompt_scope="strict", at least one Knowledge
        Base is bound, and nothing relevant was found — the caller of this
        method treats None as "skip the LLM turn entirely, speak the
        fallback prompt instead", which is the deterministic, literal
        implementation of "if the answer is not in the knowledge base,
        return a clear fallback".
        """
        kb_context, any_hits = await self._retrieve_kb_context(user_message)

        if self.prompt_scope == "strict" and (self.knowledge_base_ids or self.extra_kb_collection) and not any_hits:
            return None

        if not kb_context and not self.system_prompt:
            return user_message  # nothing to combine — behave exactly like Part 3

        parts = []
        if self.system_prompt:
            parts.append(f"[Call agent instructions]\n{self.system_prompt}")
        if kb_context:
            parts.append(f"[Reference material]\n{kb_context}")
            scope_note = (
                "Answer ONLY using the reference material above. If it doesn't contain "
                "the answer, say so plainly rather than guessing."
                if self.prompt_scope == "strict" else
                "Use the reference material above when it's relevant; otherwise answer normally."
            )
            parts.append(scope_note)
        parts.append(f"[Caller says]\n{user_message}")
        return "\n\n".join(parts)

    async def _run_turn(self, user_message: str) -> None:
        # NEW (Part 4): resolve KB context / scope before touching the
        # Workflow Runtime at all, so a strict-scope miss never spends an
        # LLM call.
        try:
            augmented_message = await self._build_augmented_message(user_message)
        except Exception as e:  # noqa: BLE001 — KB combination must never break the call
            logger.warning(f"call={self.call_id} KB combination failed, continuing without it: {e}")
            augmented_message = user_message

        if augmented_message is None:
            await self._trigger_fallback("out_of_scope")
            return

        context = await self._load_context()
        started = time.monotonic()
        sentence_buffer = ""
        full_response = ""
        got_first_chunk = False
        turn_error = False
        node_type = None

        try:
            stream = self.runner.stream_run(augmented_message, context)
            while True:
                remaining = max(settings.VOICE_CALL_MAX_THINKING_SECONDS - (time.monotonic() - started), 0.1) \
                    if not got_first_chunk else None
                try:
                    chunk = await (asyncio.wait_for(stream.__anext__(), timeout=remaining)
                                   if remaining is not None else stream.__anext__())
                except StopAsyncIteration:
                    break

                got_first_chunk = True
                ctype = chunk.get("type")
                if ctype in ("token", "message"):
                    piece = chunk.get("content") or ""
                    full_response += piece
                    sentence_buffer += piece
                    node_type = chunk.get("node_type") or node_type
                    sentence_buffer = await self._flush_complete_sentences(sentence_buffer)
                elif ctype == "done":
                    node_type = chunk.get("node_type") or node_type
                elif ctype == "error":
                    turn_error = True

                if ctype in ("ended", "error"):
                    break

            # Speak whatever's left in the buffer (the final, possibly
            # unpunctuated, trailing fragment).
            if sentence_buffer.strip():
                await self._speak(sentence_buffer.strip())

            await self._save_context(context)

        except asyncio.TimeoutError:
            logger.warning(f"call={self.call_id} AI Engine exceeded {settings.VOICE_CALL_MAX_THINKING_SECONDS}s")
            await self._trigger_fallback("timeout")
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"call={self.call_id} turn execution error: {e}", exc_info=True)
            turn_error = True

        if turn_error or not full_response.strip():
            await self._trigger_fallback("ai_error")
            return

        await self._record_transcript("ai", full_response.strip())

    async def _flush_complete_sentences(self, buffer: str) -> str:
        """Speaks every complete sentence currently in `buffer`, returning
        whatever trailing partial fragment is left to keep accumulating —
        this is what makes TTS start on sentence 1 while the LLM is still
        generating sentence 2+ (streaming response support)."""
        parts = _SENTENCE_BOUNDARY.split(buffer)
        if len(parts) <= 1:
            if len(buffer) > _MAX_CHUNK_CHARS:
                await self._speak(buffer.strip())
                return ""
            return buffer
        *complete, trailing = parts
        for sentence in complete:
            if sentence.strip():
                await self._speak(sentence.strip())
        return trailing

    # ── speech synthesis + playback ──────────────────────────────────────

    async def _speak(self, text: str) -> None:
        if not text:
            return
        self.ai_speaking = True
        try:
            # NEW (Part 4): capture response latency the first time this
            # call session speaks after a caller utterance — i.e. time from
            # end-of-caller-speech to first audio out, backing the
            # "Average response time" analytics card. Only the FIRST _speak
            # call of a turn carries a fresh value (subsequent sentence
            # chunks in the same turn must not overwrite it with None).
            if self._turn_started_at is not None:
                self._pending_response_time_ms = int((time.monotonic() - self._turn_started_at) * 1000)
                self._turn_started_at = None

            async with AsyncSessionLocal() as db:
                key_row = await _get_user_key(
                    db, self.owner_id, tts_engine.PROVIDER_CATALOG[self.voice_provider]["credential_provider"]
                )
            if not key_row or not key_row.encrypted_key:
                logger.warning(f"call={self.call_id} no TTS key configured for provider={self.voice_provider}")
                return
            api_key = decrypt_key(key_row.encrypted_key)
            audio_bytes, content_type = await tts_engine.synthesize(
                self.voice_provider, api_key, text, self.voice_id,
                base_url=key_row.base_url,
                personality={"rate": self.voice_speed} if self.voice_speed != 1.0 else None,
            )
            mulaw = call_audio_utils.tts_audio_to_mulaw8k(audio_bytes, content_type)
            for frame in call_audio_utils.chunk_mulaw_frames(mulaw):
                if self._closed:
                    return
                await self._send_audio_frames(frame)
                # Pace frames roughly at real-time playback so Twilio's own
                # buffer stays small — a smaller Twilio-side buffer is what
                # makes the `clear` event on barge-in actually feel instant.
                await asyncio.sleep(call_audio_utils.TWILIO_FRAME_MS / 1000)
        except (tts_engine.TTSError, call_audio_utils.AudioConversionError) as e:
            logger.warning(f"call={self.call_id} TTS/audio failure: {e}")
        finally:
            self.ai_speaking = False

    # ── fast fallback (AI Engine error / can't answer / thinking too long) ──

    async def _trigger_fallback(self, reason: str) -> None:
        self.fallback_triggered = True
        await self._record_transcript("system", f"[fallback triggered: {reason}]")
        # NEW (Part 4): speaks the call/number's own configured fallback
        # prompt when one is set, instead of always the global default.
        await self._speak(self.fallback_message)
        try:
            await live_agent_service.request_handoff(
                session_id=self.session_id, workflow_id=self.workflow.get("id", ""),
                owner_id=self.owner_id, channel="voice_call",
                reason=f"AI Call Agent fallback ({reason})", requested_by="ai",
            )
            self.handed_off = True
        except Exception as e:  # noqa: BLE001 — handoff is best-effort
            logger.warning(f"call={self.call_id} live-agent handoff failed: {e}")

    async def _handle_stt_unavailable(self) -> None:
        await self._speak(
            "I'm sorry, speech recognition isn't configured for this number yet. "
            "Please try again later."
        )
        self.fallback_triggered = True

    # ── persistence: transcript + shared Workflow Runtime session ───────────

    async def _record_transcript(self, role: str, content: str, was_interrupted: bool = False) -> None:
        self._sequence += 1
        seq = self._sequence
        response_time_ms = None
        if role == "ai":
            response_time_ms = self._pending_response_time_ms
            self._pending_response_time_ms = None
        try:
            async with AsyncSessionLocal() as db:
                db.add(CallTranscriptEntry(
                    id=str(uuid.uuid4()), call_id=self.call_id, role=role,
                    content=content, sequence=seq, was_interrupted=was_interrupted,
                    response_time_ms=response_time_ms,
                ))
                await db.commit()
        except Exception as e:  # noqa: BLE001 — never let transcript logging break the call
            logger.warning(f"call={self.call_id} failed to persist transcript entry: {e}")

    async def _load_context(self) -> ExecutionContext:
        data = await self.cache.get(f"session:{self.session_id}")
        if data:
            return ExecutionContext.from_dict(data)
        return ExecutionContext(session_id=self.session_id, workflow_id=self.workflow.get("id"))

    async def _save_context(self, context: ExecutionContext) -> None:
        await self.cache.set(f"session:{self.session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)
