"""
ThunderBots Telegram Service
NEW (Telegram Channel — Part 1).

Everything needed to talk to Telegram's Bot API for the connection
lifecycle: an HTTP client wrapping getMe / setWebhook / deleteWebhook /
getWebhookInfo / sendMessage, webhook secret-token validation, and bot
token format pre-validation. This module does not import from or modify
app/engine/* (Workflow Runtime), app/core/auth.py (Authentication),
app/knowledge/* (Knowledge Base), or app/services/ai_engine.py beyond
reusing its already-existing, already-shared encrypt_key/decrypt_key
Fernet helpers — the exact same pattern app/services/whatsapp_service.py
and app/services/instagram_service.py already use.

Retry policy: every outbound Bot API call goes through
`_request_with_retry`, which retries transient failures (timeouts, 429,
5xx) up to 3 times with exponential backoff (0.5s, 1s, 2s). 4xx errors
other than 429 are not retried — they indicate a bad request (invalid
token, chat not found, bot blocked by user, etc.) that retrying cannot fix.
"""
from __future__ import annotations

import hmac
import logging
import re
import secrets
from typing import Optional

import httpx

from app.services.ai_engine import encrypt_key, decrypt_key  # reused as-is, not modified

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)

# Telegram Bot API tokens look like "123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# — a numeric bot id, a colon, then a 35-char base64-ish secret. Used only as
# a cheap, fast pre-check so obviously-malformed input never even reaches
# Telegram's API; the definitive check is always the live getMe() call.
_TOKEN_SHAPE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,45}$")


class TelegramAPIError(RuntimeError):
    """Raised when the Bot API returns an error after exhausting retries."""

    def __init__(self, message: str, error_code: Optional[int] = None, description: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code
        self.description = description


# ─────────────────────────────────────────────────────────────────────────────
# Encryption — thin, purpose-named wrappers over the shared Fernet helpers
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_credential(plaintext: str) -> str:
    return encrypt_key(plaintext) if plaintext else ""


def decrypt_credential(ciphertext: str) -> str:
    return decrypt_key(ciphertext) if ciphertext else ""


def looks_like_bot_token(token: str) -> bool:
    """Fast format pre-check — does NOT confirm the token is live/valid."""
    return bool(token and _TOKEN_SHAPE.match(token.strip()))


def generate_webhook_secret() -> str:
    """A per-channel random secret handed to Telegram's setWebhook as
    `secret_token`; Telegram echoes it back on every webhook call as the
    X-Telegram-Bot-Api-Secret-Token header. Must be 1-256 chars of
    A-Z, a-z, 0-9, _ and - per Telegram's own constraint."""
    return secrets.token_urlsafe(32)[:64]


def verify_webhook_secret(expected_secret: str, header_value: Optional[str]) -> bool:
    """Constant-time comparison of the secret Telegram echoes back on every
    webhook POST against the one we registered via setWebhook. Always False
    if no header is present, so a channel can never be driven without the
    secret it was configured with."""
    if not expected_secret or not header_value:
        return False
    return hmac.compare_digest(expected_secret, header_value)


# ─────────────────────────────────────────────────────────────────────────────
# Retry helper
# ─────────────────────────────────────────────────────────────────────────────

async def _request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    import asyncio

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    f"Telegram API {method} {url} returned {resp.status_code}, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            last_exc = e
            if attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    f"Telegram API {method} {url} network error: {e}, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise
    if last_exc:
        raise last_exc
    raise TelegramAPIError(f"Exhausted retries for {method} {url}")


def _extract_telegram_error(resp: httpx.Response) -> tuple[str, Optional[int]]:
    try:
        body = resp.json()
        desc = body.get("description") or str(body)
        code = body.get("error_code")
        return desc, code
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code


# ─────────────────────────────────────────────────────────────────────────────
# Bot API client
# ─────────────────────────────────────────────────────────────────────────────

class TelegramBotClient:
    """Thin, typed wrapper around the pieces of the Telegram Bot API this
    integration needs: identity/token validation, webhook management, and
    sending text replies."""

    def __init__(self, bot_token: str, timeout: float = 20.0):
        self.bot_token = bot_token
        self.timeout = timeout
        self._base_url = f"{TELEGRAM_API_BASE}/bot{bot_token}"

    async def _call(self, method: str, payload: Optional[dict] = None) -> dict:
        url = f"{self._base_url}/{method}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(client, "POST", url, json=payload or {})

        try:
            body = resp.json()
        except Exception:
            raise TelegramAPIError(f"Telegram returned a non-JSON response (HTTP {resp.status_code})")

        if resp.status_code >= 400 or not body.get("ok", False):
            desc, code = _extract_telegram_error(resp)
            raise TelegramAPIError(desc, error_code=code or body.get("error_code"), description=desc)

        return body.get("result", {})

    # ── Identity / token validation (Connect, Test, Reconnect) ──────────────
    async def get_me(self) -> dict:
        """Returns {id, is_bot, first_name, username, ...}. Raises
        TelegramAPIError with error_code=401 for a definitively invalid/
        revoked token — the caller uses that to set status='invalid_token'
        rather than a generic 'error'."""
        return await self._call("getMe")

    # ── Webhook management ───────────────────────────────────────────────────
    async def set_webhook(self, url: str, secret_token: str) -> bool:
        result = await self._call("setWebhook", {
            "url": url,
            "secret_token": secret_token,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        })
        return bool(result) or result == {}

    async def delete_webhook(self) -> bool:
        result = await self._call("deleteWebhook", {"drop_pending_updates": False})
        return bool(result) or result == {}

    async def get_webhook_info(self) -> dict:
        return await self._call("getWebhookInfo")

    # ── Send: text (only ever called for chat_ids that have messaged the
    # bot first — Telegram itself enforces this: sendMessage to a chat_id
    # that has never started the bot fails with "chat not found") ──────────
    async def send_message(self, chat_id: str, text: str) -> dict:
        return await self._call("sendMessage", {
            "chat_id": chat_id,
            "text": text[:4096],
        })


def client_from_channel(channel) -> TelegramBotClient:
    """Build a TelegramBotClient from a TelegramChannel ORM row."""
    return TelegramBotClient(bot_token=decrypt_credential(channel.encrypted_bot_token))
