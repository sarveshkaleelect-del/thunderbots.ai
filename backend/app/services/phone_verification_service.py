"""
ThunderBots AI Call Agent — Phone Verification Service (NEW, Voice AI Part 2)

Purely additive module. Does not import from or modify app/engine/*
(Workflow Runtime), app/services/ai_engine.py's provider-completion logic,
app/knowledge/*, or any existing channel service (whatsapp_service.py,
telegram/instagram equivalents). This module only generates, delivers, and
checks phone verification codes for phone number *setup* — no call
placement, no telephony session handling, no workflow binding. That is
explicitly out of scope for this part and left for a future Voice AI phase.

── Providers ────────────────────────────────────────────────────────────
Follows the exact provider-abstraction convention already established by
services/email_service.py. PHONE_VERIFICATION_PROVIDER (see app/config.py)
selects the transport at runtime:
  - "console" (default) logs the code instead of sending it. Zero
               configuration required — nothing breaks in local dev or on
               a fresh deploy that hasn't set up SMS delivery yet.
  - "twilio"   sends OTP/SMS codes via Twilio's HTTP API using httpx
               (already a dependency of this project — used for Ollama/
               SendGrid), no Twilio SDK required.
If the selected provider is missing required credentials, this module logs
a warning and safely falls back to "console" rather than raising.

"call" is accepted as a requested delivery method so the API/UI contract is
complete ("Call verification if supported"), but placing an actual outbound
call is real call automation and is intentionally NOT implemented here — it
degrades to the same console logging as an unconfigured SMS provider would.
Wiring a real telephony call is left for a future part.

── Security ────────────────────────────────────────────────────────────
Codes are never stored in plaintext — only a SHA-256 hash, identical
convention to PasswordResetToken/EmailVerificationToken (api/v1/auth.py)
and TOTP backup codes (services/totp_service.py). This is a distinct,
purpose-built hash/generate pair (not a re-use of services/totp_service.py,
which implements the very different RFC 6238 time-step algorithm) — kept
here as the single place phone verification codes are generated, hashed,
and checked, so no other module duplicates this logic.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
VALID_METHODS = ("otp", "sms", "call")


class DeliveryError(Exception):
    """Raised only when a *configured* provider actively failed to deliver
    a code (e.g. Twilio returned an error). Never raised for the routine
    "no provider configured yet" case — that degrades to console logging."""


def generate_code() -> str:
    """A fresh, cryptographically random numeric code. Never persisted in
    the clear — callers must run it through hash_code before saving."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def verify_code_hash(code: str, stored_hash: str) -> bool:
    """Constant-time comparison, same convention as webhook signature
    checks elsewhere in this codebase (security audit fix)."""
    if not code or not stored_hash:
        return False
    return secrets.compare_digest(hash_code(code), stored_hash)


def code_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.PHONE_VERIFICATION_CODE_EXPIRE_MINUTES)


async def send_verification_code(phone_number: str, code: str, method: str) -> None:
    """Delivers `code` to `phone_number` via `method`. Degrades to logging
    the code (console) whenever no real provider is configured for that
    method — only raises DeliveryError when a *configured* provider's API
    call itself fails."""
    if method not in VALID_METHODS:
        raise ValueError(f"Unsupported verification method: {method}")

    provider = (settings.PHONE_VERIFICATION_PROVIDER or "console").lower()
    twilio_configured = bool(
        settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER
    )

    if method in ("otp", "sms") and provider == "twilio" and twilio_configured:
        await _send_via_twilio(phone_number, code)
        return

    if method == "call":
        # Real outbound call verification is out of scope for this part —
        # always degrades to console, regardless of provider config.
        logger.info(
            f"[PHONE VERIFICATION - CALL] Call-based delivery is not yet "
            f"implemented (Voice AI Part 2 scope); code for {phone_number} "
            f"would be read aloud here. Logging instead: {code}"
        )
        return

    # Default / graceful fallback for otp|sms with no provider configured.
    logger.info(
        f"[PHONE VERIFICATION - {method.upper()}] Code for {phone_number}: "
        f"{code} (expires in {settings.PHONE_VERIFICATION_CODE_EXPIRE_MINUTES} min)"
    )


async def _send_via_twilio(phone_number: str, code: str) -> None:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    body = (
        f"Your ThunderBots verification code is {code}. "
        f"It expires in {settings.PHONE_VERIFICATION_CODE_EXPIRE_MINUTES} minutes."
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={"To": phone_number, "From": settings.TWILIO_FROM_NUMBER, "Body": body},
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
        if resp.status_code >= 400:
            logger.warning(f"Twilio send failed ({resp.status_code}): {resp.text[:300]}")
            raise DeliveryError("The SMS provider could not deliver the code. Please try again.")
    except httpx.HTTPError as e:
        logger.warning(f"Twilio request error: {type(e).__name__}: {e}")
        raise DeliveryError("The SMS provider could not be reached. Please try again.")
