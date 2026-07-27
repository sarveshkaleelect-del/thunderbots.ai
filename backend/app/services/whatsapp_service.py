"""
ThunderBots WhatsApp Service
NEW (WhatsApp Channel).

Everything needed to talk to Meta's WhatsApp Cloud API: an HTTP client for
sending messages (text/buttons/list/image/document), secure media download,
webhook signature validation, and connection testing. This module does not
import from or modify app/engine/* (Workflow Runtime), app/core/auth.py
(Authentication), app/knowledge/* (Knowledge Base), app/services/ai_engine.py
beyond reusing its already-existing, already-shared encrypt_key/decrypt_key
Fernet helpers (same pattern api/v1/settings.py already uses for provider
API keys), or anything under app/api/v1/deploy.py (Deployment).

Retry policy: every outbound Graph API call goes through `_request_with_retry`,
which retries transient failures (timeouts, 429, 5xx) up to 3 times with
exponential backoff (0.5s, 1s, 2s). 4xx errors other than 429 are not
retried — they indicate a bad request (invalid token, bad recipient, etc.)
that retrying cannot fix.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
import os
import uuid
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.ai_engine import encrypt_key, decrypt_key  # reused as-is, not modified

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)

WHATSAPP_MEDIA_SUBDIR = "whatsapp"


class WhatsAppAPIError(RuntimeError):
    """Raised when the Graph API returns an error after exhausting retries."""

    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


# ─────────────────────────────────────────────────────────────────────────────
# Encryption — thin, purpose-named wrappers over the shared Fernet helpers
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_credential(plaintext: str) -> str:
    return encrypt_key(plaintext) if plaintext else ""


def decrypt_credential(ciphertext: str) -> str:
    return decrypt_key(ciphertext) if ciphertext else ""


# ─────────────────────────────────────────────────────────────────────────────
# Webhook signature validation
# ─────────────────────────────────────────────────────────────────────────────

def verify_webhook_signature(app_secret: str, raw_body: bytes, signature_header: Optional[str]) -> bool:
    """
    Validates Meta's X-Hub-Signature-256 header: 'sha256=<hex hmac>' computed
    over the raw request body using the app's App Secret. Returns True when
    no app_secret is configured for the channel (signature validation is
    optional/best-effort here since the connection wizard only requires
    Phone Number ID / Business Account ID / Access Token / Verify Token —
    App Secret is an additional opt-in hardening field), but ALWAYS returns
    False for a present-but-wrong signature so a misconfigured or malicious
    sender can never be silently accepted once App Secret has been set.
    """
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, provided)


# ─────────────────────────────────────────────────────────────────────────────
# Retry helper
# ─────────────────────────────────────────────────────────────────────────────

async def _request_with_retry(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
) -> httpx.Response:
    import asyncio

    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    f"WhatsApp API {method} {url} returned {resp.status_code}, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            last_exc = e
            if attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    f"WhatsApp API {method} {url} network error: {e}, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise
    if last_exc:
        raise last_exc
    raise WhatsAppAPIError(f"Exhausted retries for {method} {url}")


# ─────────────────────────────────────────────────────────────────────────────
# Cloud API client
# ─────────────────────────────────────────────────────────────────────────────

class WhatsAppCloudClient:
    """Thin, typed wrapper around the pieces of the WhatsApp Cloud API this
    integration needs: sending messages, downloading media, and reading
    phone-number metadata for Test Connection / Reconnect."""

    def __init__(self, phone_number_id: str, access_token: str, timeout: float = 20.0):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _post_messages(self, payload: dict) -> dict:
        url = f"{GRAPH_BASE_URL}/{self.phone_number_id}/messages"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(
                client, "POST", url, json=payload, headers=self._headers()
            )
        if resp.status_code >= 400:
            err = _extract_graph_error(resp)
            raise WhatsAppAPIError(err, status_code=resp.status_code, payload=payload)
        return resp.json()

    # ── Send: Text ──────────────────────────────────────────────────────────
    async def send_text(self, to: str, body: str, preview_url: bool = False) -> dict:
        return await self._post_messages({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body[:4096], "preview_url": preview_url},
        })

    # ── Send: Interactive reply buttons (max 3) ────────────────────────────
    async def send_buttons(
        self, to: str, body_text: str, buttons: list[dict], footer: Optional[str] = None
    ) -> dict:
        """buttons: [{"id": str, "title": str}, ...] — max 3, title <= 20 chars."""
        interactive_buttons = [
            {"type": "reply", "reply": {"id": b["id"][:256], "title": b["title"][:20]}}
            for b in buttons[:3]
        ]
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text[:1024]},
                "action": {"buttons": interactive_buttons},
            },
        }
        if footer:
            payload["interactive"]["footer"] = {"text": footer[:60]}
        return await self._post_messages(payload)

    # ── Send: Interactive list (used when there are > 3 choices) ───────────
    async def send_list(
        self, to: str, body_text: str, button_text: str, rows: list[dict], footer: Optional[str] = None
    ) -> dict:
        """rows: [{"id": str, "title": str, "description": str|None}, ...] — max 10."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text[:1024]},
                "action": {
                    "button": button_text[:20],
                    "sections": [{
                        "title": "Options",
                        "rows": [
                            {
                                "id": r["id"][:200],
                                "title": r["title"][:24],
                                **({"description": r["description"][:72]} if r.get("description") else {}),
                            }
                            for r in rows[:10]
                        ],
                    }],
                },
            },
        }
        if footer:
            payload["interactive"]["footer"] = {"text": footer[:60]}
        return await self._post_messages(payload)

    # ── Send: quick replies (alias of buttons — WhatsApp's quick-reply UX
    # IS the interactive reply-button message type; kept as its own method
    # name so callers can express intent clearly) ──────────────────────────
    async def send_quick_replies(self, to: str, body_text: str, options: list[str]) -> dict:
        buttons = [{"id": f"qr_{i}", "title": opt} for i, opt in enumerate(options)]
        return await self.send_buttons(to, body_text, buttons)

    # ── Send: Image ─────────────────────────────────────────────────────────
    async def send_image(self, to: str, link: str, caption: Optional[str] = None) -> dict:
        image: dict[str, Any] = {"link": link}
        if caption:
            image["caption"] = caption[:1024]
        return await self._post_messages({
            "messaging_product": "whatsapp", "to": to, "type": "image", "image": image,
        })

    # ── Send: Document ──────────────────────────────────────────────────────
    async def send_document(
        self, to: str, link: str, filename: Optional[str] = None, caption: Optional[str] = None
    ) -> dict:
        document: dict[str, Any] = {"link": link}
        if filename:
            document["filename"] = filename
        if caption:
            document["caption"] = caption[:1024]
        return await self._post_messages({
            "messaging_product": "whatsapp", "to": to, "type": "document", "document": document,
        })

    # ── Mark a message as read (best-effort, never raises) ─────────────────
    async def mark_read(self, message_id: str) -> None:
        try:
            await self._post_messages({
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            })
        except Exception as e:  # noqa: BLE001 — read receipts are non-critical
            logger.debug(f"mark_read failed (non-fatal): {e}")

    # ── Media: resolve download URL, then download bytes ───────────────────
    async def get_media_url(self, media_id: str) -> tuple[str, Optional[str], Optional[int]]:
        url = f"{GRAPH_BASE_URL}/{media_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(client, "GET", url, headers=self._headers())
        if resp.status_code >= 400:
            raise WhatsAppAPIError(_extract_graph_error(resp), status_code=resp.status_code)
        data = resp.json()
        return data["url"], data.get("mime_type"), data.get("file_size")

    async def download_media_bytes(self, media_url: str) -> bytes:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(client, "GET", media_url, headers=self._headers())
        if resp.status_code >= 400:
            raise WhatsAppAPIError(f"Media download failed: HTTP {resp.status_code}", status_code=resp.status_code)
        return resp.content

    # ── Phone number metadata (Test Connection / Reconnect) ────────────────
    async def get_phone_number_details(self) -> dict:
        url = f"{GRAPH_BASE_URL}/{self.phone_number_id}"
        params = {"fields": "verified_name,display_phone_number,quality_rating,code_verification_status"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(client, "GET", url, params=params, headers=self._headers())
        if resp.status_code >= 400:
            raise WhatsAppAPIError(_extract_graph_error(resp), status_code=resp.status_code)
        return resp.json()


def _extract_graph_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", {})
        msg = err.get("message") or str(body)
        code = err.get("code")
        return f"{msg}" + (f" (code {code})" if code else "")
    except Exception:
        return f"HTTP {resp.status_code}: {resp.text[:300]}"


def client_from_channel(channel) -> WhatsAppCloudClient:
    """Build a WhatsAppCloudClient from a WhatsAppChannel ORM row."""
    return WhatsAppCloudClient(
        phone_number_id=channel.phone_number_id,
        access_token=decrypt_credential(channel.encrypted_access_token),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Secure media download to disk
# ─────────────────────────────────────────────────────────────────────────────

async def download_and_store_media(
    client: WhatsAppCloudClient, media_id: str, channel_id: str, media_type: str,
) -> dict:
    """
    Downloads incoming media securely: resolves the short-lived Graph media
    URL using the channel's own access token (required — the URL is useless
    without the bearer token), streams the bytes, verifies the declared
    file_size against what was actually received, computes a SHA-256 for
    integrity/audit, and writes it under
    {UPLOAD_DIR}/whatsapp/{channel_id}/{uuid}.{ext} — never using any
    attacker-controlled filename directly on disk.

    Returns a dict ready to persist as a WhatsAppMediaAsset row.
    """
    media_url, mime_type, declared_size = await client.get_media_url(media_id)
    content = await client.download_media_bytes(media_url)

    if declared_size is not None and len(content) != declared_size:
        logger.warning(
            f"WhatsApp media {media_id}: downloaded size {len(content)} "
            f"does not match declared size {declared_size}"
        )

    digest = hashlib.sha256(content).hexdigest()
    ext = mimetypes.guess_extension(mime_type or "") or ""
    safe_name = f"{uuid.uuid4().hex}{ext}"

    rel_dir = os.path.join(WHATSAPP_MEDIA_SUBDIR, channel_id)
    abs_dir = os.path.join(settings.UPLOAD_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    rel_path = os.path.join(rel_dir, safe_name)
    abs_path = os.path.join(settings.UPLOAD_DIR, rel_path)
    with open(abs_path, "wb") as f:
        f.write(content)

    return {
        "wa_media_id": media_id,
        "media_type": media_type,
        "mime_type": mime_type,
        "file_path": rel_path,
        "file_size": len(content),
        "sha256": digest,
    }


def media_asset_url(rel_path: str) -> str:
    """Public URL for a stored media asset, served by the existing
    /uploads static mount in main.py (same mount branding assets use)."""
    return f"{settings.APP_API_URL}/uploads/{rel_path}"
