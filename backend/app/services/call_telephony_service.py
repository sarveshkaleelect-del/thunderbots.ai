"""
ThunderBots AI Call Agent — Telephony Provider Service (NEW, Voice AI Part 3)

Twilio Voice REST API + TwiML + Media Streams, over plain HTTPS via
httpx — same "no vendor SDK" convention already used by
services/phone_verification_service.py and services/tts_engine.py. Reuses
the EXACT SAME TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER
already configured for phone verification (Part 2) — no second Twilio
project, no new credential to set up.

Only one provider is implemented (Twilio) — "provider" is still stored on
every Call row so a second telephony provider could be added later without
a migration, exactly like Call.provider already anticipates.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TelephonyError(Exception):
    """Raised only when a configured provider actively failed (bad
    credentials, invalid number, Twilio-side error) — never for routine
    'not configured' cases, which callers check for explicitly via
    `is_configured()` before ever calling into this module."""


def is_configured() -> bool:
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_FROM_NUMBER
        and settings.BACKEND_PUBLIC_URL
    )


def _public_url(path: str) -> str:
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}{path}"


def _stream_ws_url(call_id: str) -> str:
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/ws/call-agent/stream/{call_id}"


# ── TwiML builders ───────────────────────────────────────────────────────────

def build_connect_stream_twiml(call_id: str, recording_enabled: bool = False) -> str:
    """TwiML returned for both inbound calls and outbound calls once
    answered: opens a bidirectional Media Stream to our WebSocket, which is
    where all realtime STT -> AI Engine -> TTS -> barge-in logic lives
    (services/call_session_service.py + api/ws/call_stream_ws.py)."""
    stream_url = escape(_stream_ws_url(call_id))
    record_tag = (
        f'<Record recordingStatusCallback="{escape(_public_url("/api/v1/call-agent/twilio/recording-status"))}" '
        f'recordingStatusCallbackEvent="completed" playBeep="false" trim="do-not-trim"/>'
        if recording_enabled else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{record_tag}"
        "<Connect>"
        f'<Stream url="{stream_url}" track="both_tracks">'
        f'<Parameter name="call_id" value="{escape(call_id)}"/>'
        "</Stream>"
        "</Connect>"
        "</Response>"
    )


def build_unavailable_twiml(message: str) -> str:
    """Used when a number is enabled but has no Workflow bound yet, or the
    telephony provider isn't configured — says a short message and hangs up
    instead of connecting silence or erroring at the carrier level."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="Polly.Joanna">{escape(message)}</Say>'
        "<Hangup/>"
        "</Response>"
    )


# ── REST calls ────────────────────────────────────────────────────────────────

async def place_outbound_call(*, call_id: str, to_number: str, from_number: Optional[str] = None) -> str:
    """Initiates an outbound call via Twilio. Returns the provider call SID.
    Twilio will fetch TwiML from our /twilio/voice webhook once the call is
    answered, which returns build_connect_stream_twiml for this call_id."""
    if not is_configured():
        raise TelephonyError(
            "Calling is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "TWILIO_FROM_NUMBER, and BACKEND_PUBLIC_URL."
        )
    sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
    payload = {
        "To": to_number,
        "From": from_number or settings.TWILIO_FROM_NUMBER,
        "Url": _public_url(f"/api/v1/call-agent/twilio/voice?call_id={call_id}"),
        "Method": "POST",
        "StatusCallback": _public_url(f"/api/v1/call-agent/twilio/status?call_id={call_id}"),
        "StatusCallbackEvent": "initiated ringing answered completed",
        "StatusCallbackMethod": "POST",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{TWILIO_API_BASE}/Accounts/{sid}/Calls.json",
                data=payload,
                auth=(sid, token),
            )
        except httpx.HTTPError as e:
            raise TelephonyError(f"Could not reach Twilio: {type(e).__name__}") from e

    if resp.status_code >= 400:
        detail = resp.json().get("message", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise TelephonyError(f"Twilio rejected the call request: {detail}")

    data = resp.json()
    return data["sid"]


async def hangup_call(provider_call_sid: str) -> None:
    """Best-effort — used when the owner ends a live call from the
    dashboard, or when the AI Call Agent itself needs to end the call
    (e.g. after the fallback message)."""
    if not is_configured():
        return
    sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(
                f"{TWILIO_API_BASE}/Accounts/{sid}/Calls/{provider_call_sid}.json",
                data={"Status": "completed"},
                auth=(sid, token),
            )
        except httpx.HTTPError as e:
            logger.warning(f"Failed to hang up call sid={provider_call_sid}: {e}")


async def fetch_recording_url(recording_sid: str) -> Optional[str]:
    if not is_configured() or not recording_sid:
        return None
    sid = settings.TWILIO_ACCOUNT_SID
    return f"{TWILIO_API_BASE}/Accounts/{sid}/Recordings/{recording_sid}.mp3"


def verify_twilio_signature(url: str, form_params: dict, signature_header: Optional[str]) -> bool:
    """Validates X-Twilio-Signature per Twilio's documented algorithm
    (HMAC-SHA1 of the URL + sorted POST params, using the auth token as
    key). If TWILIO_AUTH_TOKEN isn't set, verification is skipped (dev
    convenience — mirrors phone_verification_service's graceful
    degradation) but this should always be enabled in production."""
    token = settings.TWILIO_AUTH_TOKEN
    if not token:
        return True
    if not signature_header:
        return False
    data = url
    for key in sorted(form_params.keys()):
        data += key + form_params[key]
    computed = base64.b64encode(
        hmac.new(token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(computed, signature_header)
