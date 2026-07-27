"""
ThunderBots AI Call Agent — Realtime Speech-to-Text (NEW, Voice AI Part 3)

Streams inbound call audio (Twilio Media Streams: raw mu-law/8000, no
transcoding needed — see call_audio_utils.py's docstring) to Deepgram's
realtime WebSocket API and yields transcript events as they arrive:
  - {"type": "partial", "text": ...}  interim, not yet final
  - {"type": "final", "text": ...}    an utterance boundary — this is what
                                       triggers a Workflow Runtime turn
  - {"type": "speech_started"}        caller began talking — this is the
                                       barge-in trigger (see
                                       call_session_service.py), fired
                                       BEFORE the final transcript is
                                       available so the AI can stop
                                       speaking instantly rather than
                                       waiting for STT to finish.

If DEEPGRAM_API_KEY isn't configured, `is_configured()` is False and the
caller (call_session_service.py) never opens this connection at all — the
call still connects but degrades to the "speech recognition not
configured" fallback, exactly like an unconfigured TTS/SMS provider
elsewhere in this project.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import websockets

from app.config import settings

logger = logging.getLogger(__name__)

DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw&sample_rate=8000&channels=1"
    "&interim_results=true&endpointing=300&vad_events=true"
    "&punctuate=true&smart_format=true"
)


class STTError(Exception):
    """Raised only for a configured provider's connection/protocol
    failure. Callers must fall back to the fast-fallback message, never
    crash the call."""


def is_configured() -> bool:
    return settings.VOICE_CALL_STT_PROVIDER == "deepgram" and bool(settings.DEEPGRAM_API_KEY)


class RealtimeSTTSession:
    """One Deepgram connection for the lifetime of a single call. Usage:

        stt = RealtimeSTTSession(language="en-US")
        await stt.connect()
        ...
        await stt.send_audio(mulaw_bytes)   # called for every inbound Twilio frame
        async for event in stt.events():
            ...
        await stt.close()
    """

    def __init__(self, language: str = "en-US"):
        self.language = language
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._closed = False

    async def connect(self) -> None:
        if not is_configured():
            raise STTError("Deepgram is not configured (DEEPGRAM_API_KEY unset)")
        url = f"{DEEPGRAM_WS_URL}&language={self.language}"
        try:
            self._ws = await websockets.connect(
                url,
                extra_headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"},
                ping_interval=5,
                ping_timeout=10,
            )
        except Exception as e:
            raise STTError(f"Could not connect to Deepgram: {e}") from e

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        if self._ws is None or self._closed:
            return
        try:
            await self._ws.send(mulaw_bytes)
        except Exception as e:
            logger.warning(f"Deepgram send failed: {e}")

    async def events(self) -> AsyncIterator[dict]:
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = msg.get("type")
                if msg_type == "SpeechStarted":
                    yield {"type": "speech_started"}
                    continue
                if msg_type != "Results":
                    continue

                alt = (msg.get("channel", {}).get("alternatives") or [{}])[0]
                text = (alt.get("transcript") or "").strip()
                if not text:
                    continue
                if msg.get("is_final"):
                    yield {"type": "final", "text": text}
                else:
                    yield {"type": "partial", "text": text}
        except websockets.exceptions.ConnectionClosed:
            return
        except Exception as e:
            logger.warning(f"Deepgram event stream error: {e}")
            return

    async def close(self) -> None:
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass


class UnavailableSTTSession:
    """Drop-in stand-in used when no STT provider is configured, so
    call_session_service.py never has to branch on "is STT configured" at
    every call site — it just gets an events() stream that immediately
    signals unavailability once, then stays silent for the rest of the
    call (audio is still accepted and discarded, never raising)."""

    def __init__(self, *_, **__):
        self._reported = False

    async def connect(self) -> None:
        return

    async def send_audio(self, mulaw_bytes: bytes) -> None:
        return

    async def events(self) -> AsyncIterator[dict]:
        if not self._reported:
            self._reported = True
            yield {"type": "unavailable"}
        # Keep the generator alive without busy-looping; call_session_service
        # cancels this task when the call ends.
        while True:
            await asyncio.sleep(3600)

    async def close(self) -> None:
        return


def create_session(language: str = "en-US"):
    if is_configured():
        return RealtimeSTTSession(language=language)
    return UnavailableSTTSession(language=language)
