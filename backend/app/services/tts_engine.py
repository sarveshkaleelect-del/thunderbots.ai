"""
ThunderBots Voice Responses — TTS Engine v1

Independent, optional module. This file is never imported by ai_engine.py,
app/engine/* (workflow runtime), or any node handler — Voice Responses read
the *final* bot response text after the workflow has already produced it,
so this module has no way to affect, delay, or block workflow execution.

All premium providers are called over plain HTTPS with `httpx` (already a
dependency, used by the Ollama provider) rather than each vendor's SDK, so:
  - no additional heavy dependency is added to requirements.txt
  - API keys never leave the backend — the frontend only ever receives
    already-synthesized audio bytes, never a provider credential
  - nothing here is loaded/executed unless a premium provider is actually
    selected and used (mirrors the "lazy-load" requirement on the frontend)

Every public function raises TTSError (never a raw SDK/HTTP exception) so
callers (app/api/v1/voice.py) can always degrade to "voice unavailable,
keep showing text" without ever crashing the chatbot.
"""
from __future__ import annotations

import base64
import logging
import struct
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 2000  # guardrail — never send unbounded text to a paid API


class TTSError(RuntimeError):
    """User-facing voice failure. Callers must catch this and continue
    showing text only — a voice failure must never crash the chatbot."""


# ── Static voice catalogs ────────────────────────────────────────────────────
# Hand-picked and small so "Voice" selection in the UI is instant and never
# requires a network round trip per provider just to populate a dropdown.

GEMINI_VOICES = [
    {"id": "Puck",   "name": "Puck",   "gender": "male"},
    {"id": "Charon", "name": "Charon", "gender": "male"},
    {"id": "Kore",   "name": "Kore",   "gender": "female"},
    {"id": "Fenrir", "name": "Fenrir", "gender": "male"},
    {"id": "Aoede",  "name": "Aoede",  "gender": "female"},
]

ELEVENLABS_VOICES = [
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "gender": "female"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi",   "gender": "female"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella",  "gender": "female"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "gender": "male"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli",   "gender": "female"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh",   "gender": "male"},
]

AZURE_VOICES = [
    {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "female"},
    {"id": "en-US-GuyNeural",   "name": "Guy",   "gender": "male"},
    {"id": "en-US-AriaNeural",  "name": "Aria",  "gender": "female"},
    {"id": "en-US-DavisNeural", "name": "Davis", "gender": "male"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia", "gender": "female"},
]

GOOGLE_TTS_VOICES = [
    {"id": "en-US-Neural2-C", "name": "Neural2-C", "gender": "female"},
    {"id": "en-US-Neural2-D", "name": "Neural2-D", "gender": "male"},
    {"id": "en-US-Neural2-F", "name": "Neural2-F", "gender": "female"},
    {"id": "en-US-Neural2-J", "name": "Neural2-J", "gender": "male"},
]

# credential_provider = the `UserAPIKey.provider` id this TTS provider's key
# is stored/looked up under. gemini reuses the same key already saved
# for the AI Agent (same vendor, same key) — no need to enter it twice.
PROVIDER_CATALOG: dict[str, dict] = {
    "gemini": {
        "name": "Gemini TTS", "credential_provider": "gemini",
        "requires_region": False, "voices": GEMINI_VOICES,
    },
    "elevenlabs": {
        "name": "ElevenLabs", "credential_provider": "elevenlabs",
        "requires_region": False, "voices": ELEVENLABS_VOICES,
    },
    "azure_speech": {
        "name": "Azure Speech", "credential_provider": "azure_speech",
        "requires_region": True, "voices": AZURE_VOICES,
    },
    "google_tts": {
        "name": "Google Cloud TTS", "credential_provider": "google_tts",
        "requires_region": False, "voices": GOOGLE_TTS_VOICES,
    },
}

DEFAULT_VOICE = {
    "gemini": "Kore",
    "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
    "azure_speech": "en-US-JennyNeural",
    "google_tts": "en-US-Neural2-C",
}

# ── Voice Personality presets ────────────────────────────────────────────────
# Playback-only tuning. Never touches the bot's text response. Each provider
# maps these onto whatever native parameter it supports (speed, SSML prosody,
# audioConfig, or voice_settings); providers with no such parameter simply
# ignore personality and synthesize with the default voice — no error.
DEFAULT_PERSONALITY = "friendly"

PERSONALITY_PRESETS: dict[str, dict] = {
    "friendly":     {"rate": 1.0,  "pitch_pct": 0,  "pitch_st": 1.0,  "eleven_stability": 0.45, "eleven_style": 0.35, "gemini_style": "warm and friendly"},
    "professional": {"rate": 1.0,  "pitch_pct": 0,  "pitch_st": 0.0,  "eleven_stability": 0.65, "eleven_style": 0.15, "gemini_style": "clear and professional"},
    "energetic":    {"rate": 1.15, "pitch_pct": 8,  "pitch_st": 2.0,  "eleven_stability": 0.30, "eleven_style": 0.55, "gemini_style": "upbeat and energetic"},
    "calm":         {"rate": 0.88, "pitch_pct": -6, "pitch_st": -1.5, "eleven_stability": 0.75, "eleven_style": 0.10, "gemini_style": "calm and soothing"},
    "formal":       {"rate": 0.95, "pitch_pct": -3, "pitch_st": -0.5, "eleven_stability": 0.70, "eleven_style": 0.05, "gemini_style": "formal and measured"},
}


def _personality_preset(personality: Optional[str]) -> dict:
    """Never raises — unknown/None personality safely falls back to the
    default preset so a bad value can never break voice synthesis."""
    return PERSONALITY_PRESETS.get((personality or DEFAULT_PERSONALITY).lower(), PERSONALITY_PRESETS[DEFAULT_PERSONALITY])


def list_provider_catalog() -> list[dict]:
    """Provider metadata for the /voice/providers endpoint (Browser is
    added separately by the route — it needs no credential/catalog entry)."""
    return [
        {
            "id": pid,
            "name": meta["name"],
            "requires_key": True,
            "requires_region": meta["requires_region"],
            "credential_provider": meta["credential_provider"],
            "voices": meta["voices"],
        }
        for pid, meta in PROVIDER_CATALOG.items()
    ]


def _truncate(text: str) -> str:
    return (text or "").strip()[:MAX_TEXT_LENGTH]


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM (as returned by Gemini's TTS API) in a minimal WAV
    header so browsers can play it directly via <audio>/HTMLAudioElement
    without needing a separate PCM decoder."""
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = len(pcm)
    header = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, sample_width * 8)
    header += b"data" + struct.pack("<I", data_size)
    return header + pcm


async def synthesize(
    provider: str,
    api_key: str,
    text: str,
    voice: Optional[str] = None,
    base_url: Optional[str] = None,
    personality: Optional[str] = None,
) -> tuple[bytes, str]:
    """Returns (audio_bytes, content_type). Always raises TTSError on
    failure — never a raw httpx/SDK exception — so every caller can safely
    catch just this one type and fall back to text-only.

    `personality` is playback styling only (rate/pitch/tone). If applying it
    for a given provider fails for any reason, synthesis silently continues
    without it rather than raising — Voice Personality must never be able to
    break voice playback."""
    if provider not in PROVIDER_CATALOG:
        raise TTSError(f"Unknown voice provider: {provider}")

    text = _truncate(text)
    if not text:
        raise TTSError("No text to synthesize")
    if not api_key:
        raise TTSError(f"No API key configured for {PROVIDER_CATALOG[provider]['name']}")

    voice = voice or DEFAULT_VOICE[provider]
    preset = _personality_preset(personality)

    try:
        if provider == "gemini":
            return await _gemini_tts(api_key, text, voice, preset)
        if provider == "elevenlabs":
            return await _elevenlabs_tts(api_key, text, voice, preset)
        if provider == "azure_speech":
            return await _azure_tts(api_key, base_url, text, voice, preset)
        if provider == "google_tts":
            return await _google_tts(api_key, text, voice, preset)
        raise TTSError(f"Unsupported voice provider: {provider}")
    except TTSError:
        raise
    except httpx.HTTPStatusError as e:
        logger.warning(f"TTS provider {provider} returned HTTP {e.response.status_code}")
        raise TTSError(f"{PROVIDER_CATALOG[provider]['name']} rejected the request ({e.response.status_code})")
    except httpx.HTTPError as e:
        raise TTSError(f"Could not reach {PROVIDER_CATALOG[provider]['name']}: {type(e).__name__}")
    except Exception as e:
        logger.error(f"TTS synthesis failed for provider={provider}: {e}", exc_info=True)
        raise TTSError("Voice generation failed")


async def _gemini_tts(api_key: str, text: str, voice: str, preset: Optional[dict] = None) -> tuple[bytes, str]:
    # Gemini's TTS model has no explicit rate/pitch knob, but does respond to
    # a short natural-language style instruction prefixed onto the audio
    # prompt. This only shapes the *spoken delivery* of the same text — the
    # actual bot reply rendered in chat is untouched, only what's handed to
    # the audio model for this synthesis call.
    style = (preset or {}).get("gemini_style")
    prompt_text = f"Say in a {style} tone: {text}" if style else text
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash-preview-tts:generateContent?key={api_key}",
            json={
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
            b64 = part["data"]
        except (KeyError, IndexError, TypeError):
            raise TTSError("Gemini TTS returned an unexpected response")
        mime = part.get("mimeType", "audio/L16;rate=24000")
        rate = 24000
        if "rate=" in mime:
            try:
                rate = int(mime.split("rate=")[1].split(";")[0])
            except ValueError:
                pass
        pcm = base64.b64decode(b64)
        return _pcm_to_wav(pcm, sample_rate=rate), "audio/wav"


async def _elevenlabs_tts(api_key: str, text: str, voice: str, preset: Optional[dict] = None) -> tuple[bytes, str]:
    body = {"text": text, "model_id": "eleven_multilingual_v2"}
    if preset:
        body["voice_settings"] = {
            "stability": preset.get("eleven_stability", 0.5),
            "style": preset.get("eleven_style", 0.2),
            "use_speaker_boost": True,
        }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json=body,
        )
        resp.raise_for_status()
        return resp.content, "audio/mpeg"


async def _azure_tts(api_key: str, region: Optional[str], text: str, voice: str, preset: Optional[dict] = None) -> tuple[bytes, str]:
    if not region or not region.strip():
        raise TTSError(
            "Azure Speech requires a region — set it as the Base URL/Region "
            "field when saving the Azure Speech API key in Settings → API Keys."
        )
    rate_pct = int(round(((preset or {}).get("rate", 1.0) - 1.0) * 100))
    pitch_st = (preset or {}).get("pitch_st", 0.0)
    escaped = _xml_escape(text)
    inner = (
        f"<prosody rate='{rate_pct:+d}%' pitch='{pitch_st:+.1f}st'>{escaped}</prosody>"
        if preset else escaped
    )
    ssml = (
        "<speak version='1.0' xml:lang='en-US'>"
        f"<voice xml:lang='en-US' name='{voice}'>{inner}</voice></speak>"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://{region.strip()}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-64kbitrate-mono-mp3",
            },
            content=ssml.encode("utf-8"),
        )
        resp.raise_for_status()
        return resp.content, "audio/mpeg"


async def _google_tts(api_key: str, text: str, voice: str, preset: Optional[dict] = None) -> tuple[bytes, str]:
    lang = "-".join(voice.split("-")[:2]) if "-" in voice else "en-US"
    audio_config = {"audioEncoding": "MP3"}
    if preset:
        audio_config["speakingRate"] = max(0.25, min(4.0, preset.get("rate", 1.0)))
        audio_config["pitch"] = max(-20.0, min(20.0, preset.get("pitch_st", 0.0) * 2))
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}",
            json={
                "input": {"text": text},
                "voice": {"languageCode": lang, "name": voice},
                "audioConfig": audio_config,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        b64 = data.get("audioContent")
        if not b64:
            raise TTSError("Google Cloud TTS returned no audio")
        return base64.b64decode(b64), "audio/mpeg"
