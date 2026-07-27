"""
ThunderBots AI Call Agent — Call Audio Utilities (NEW, Voice AI Part 3)

Twilio Media Streams send/receive raw 8kHz mono mu-law (G.711) audio in
20ms frames, base64-encoded over a WebSocket. Nothing else in this project
speaks that format, so this module is the ONLY place audio is transcoded:

  - Inbound (caller -> STT): Twilio's mu-law/8000 frames are forwarded to
    Deepgram AS-IS (Deepgram accepts mulaw/8000 natively) — no decoding
    needed on this side at all, see services/call_stt_service.py.

  - Outbound (AI -> caller): the EXISTING services/tts_engine.py (Voice
    Responses, Part 1) is reused as-is — this module only takes its output
    bytes (mp3/wav, whatever the provider returned) and converts them to
    8kHz mu-law frames Twilio can play. This is intentionally NOT a second
    voice engine: tts_engine.py still owns every provider call, API key,
    and voice/personality preset; this module only handles the *telephony
    audio format* at the very end of the pipeline.

Uses pydub (+ system ffmpeg, see Dockerfile) to decode arbitrary
mp3/wav/pcm into raw PCM, then the stdlib `audioop` module to resample to
8kHz and mu-law encode — no numpy/scipy dependency needed for that step.
"""
from __future__ import annotations

import audioop
import io
import logging
from typing import Iterator

from pydub import AudioSegment

logger = logging.getLogger(__name__)

TWILIO_SAMPLE_RATE = 8000
TWILIO_FRAME_MS = 20
# 8kHz * 0.02s * 1 byte/sample (mu-law is 8-bit) = 160 bytes/frame
TWILIO_FRAME_BYTES = int(TWILIO_SAMPLE_RATE * (TWILIO_FRAME_MS / 1000))


class AudioConversionError(RuntimeError):
    """Raised when TTS output can't be converted to telephony audio. The
    caller (call_session_service.py) must treat this exactly like a TTS
    failure — skip this utterance, never crash the call."""


def tts_audio_to_mulaw8k(audio_bytes: bytes, content_type: str) -> bytes:
    """Converts an arbitrary TTS provider audio blob (mp3/wav — whatever
    tts_engine.synthesize() returned) into raw 8kHz mono 8-bit mu-law PCM,
    ready to be chunked into Twilio Media Stream frames."""
    fmt = "wav" if "wav" in (content_type or "") else "mp3"
    try:
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
        segment = segment.set_channels(1).set_frame_rate(TWILIO_SAMPLE_RATE).set_sample_width(2)
        pcm16 = segment.raw_data
        mulaw = audioop.lin2ulaw(pcm16, 2)
        return mulaw
    except Exception as e:  # noqa: BLE001 — any decode failure degrades the same way
        logger.warning(f"Call audio conversion failed (content_type={content_type}): {e}")
        raise AudioConversionError(str(e)) from e


def chunk_mulaw_frames(mulaw_bytes: bytes) -> Iterator[bytes]:
    """Splits raw mu-law audio into Twilio's expected 20ms (160-byte)
    frames. The last partial frame (if any) is zero-padded (mu-law silence
    byte 0xFF) rather than dropped, so no audio is ever lost."""
    for i in range(0, len(mulaw_bytes), TWILIO_FRAME_BYTES):
        frame = mulaw_bytes[i:i + TWILIO_FRAME_BYTES]
        if len(frame) < TWILIO_FRAME_BYTES:
            frame = frame + b"\xff" * (TWILIO_FRAME_BYTES - len(frame))
        yield frame


def mulaw8k_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Inverse direction — used only if a provider ever needs linear PCM
    from Twilio's inbound audio (e.g. a non-streaming STT fallback)."""
    return audioop.ulaw2lin(mulaw_bytes, 2)
