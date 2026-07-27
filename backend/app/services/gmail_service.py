"""
ThunderBots Personal Email AI Assistant — Gmail Service (NEW — Part 1)

Everything needed to talk to Google for the user's OWN personal Gmail
inbox: the OAuth 2.0 authorization-code flow (distinct from
services/google_oauth.py, which only verifies a client-side Sign-In-With-
Google ID token and never obtains a refresh token or Gmail scope), token
refresh, and a thin Gmail REST API client (list/get messages, star/unstar,
mark read). This module does not import from or modify app/engine/*
(Workflow Runtime), app/core/auth.py (Authentication), app/knowledge/*
(Knowledge Base), or app/services/email_service.py (the transactional
Email & Notification Service) — it reuses only the already-shared
encrypt_key/decrypt_key Fernet helpers from app/services/ai_engine.py,
same pattern as services/whatsapp_service.py and services/instagram_service.py.

Provider-agnostic design (future-ready for Outlook / Microsoft 365):
every function here is named/shaped around what api/v1/personal_email.py
and services/personal_email_sync_service.py actually need
(is_configured, build_authorize_url, exchange_code_for_tokens,
refresh_access_token, get_user_email, list_message_ids, get_message,
modify_message_labels, EmailMessage normalized dataclass) — a future
services/outlook_service.py implementing the same function names against
Microsoft Graph would let personal_email_sync_service.py dispatch on
PersonalEmailAccount.provider without changing its own logic. Nothing in
this module hardcodes "gmail" outside of this file itself.

Retry policy: transient failures (timeouts, 429, 5xx) are retried up to 3
times with exponential backoff (0.5s, 1s, 2s), matching
services/instagram_service.py's `_request_with_retry` shape.

Part 2 additions (NEW — additive only): `gmail.send` is now requested
alongside the Part 1 read/modify scopes (OAUTH_SCOPES), plus
`build_mime_message` / `send_message` (one-click Send + Schedule Send both
land here), `get_attachment` (download one attachment's raw bytes on
demand, used by the download-attachment API route), and attachment
metadata extraction in `parse_message`/`_walk_parts` (`EmailMessage.
attachments`, additive field with a safe default, so any Part 1 caller
that doesn't know about it is unaffected). Accounts connected before Part 2
shipped will not have `gmail.send` in their granted `scopes` string until
they reconnect — callers must check `has_send_scope(account.scopes)`
before attempting to send and surface a clear "please reconnect" error
otherwise, exactly like an expired token.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.ai_engine import encrypt_key, decrypt_key  # reused as-is, not modified

logger = logging.getLogger(__name__)

GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Read + label-modify (star, mark read, archive) + send (Part 2: one-click
# Send, Schedule Send, Bulk Reply, auto-reply rules). Deliberately NOT
# gmail.compose (which would also allow editing/deleting the user's other
# drafts in the Gmail UI itself — not needed here).
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def has_send_scope(scopes: Optional[str]) -> bool:
    """True if a previously-granted `scopes` string includes gmail.send.
    Accounts connected before Part 2 shipped won't have it until they
    reconnect via the normal OAuth flow (which always re-requests the
    current OAUTH_SCOPES list)."""
    return bool(scopes) and _SEND_SCOPE in scopes.split()

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)

FOLDER_LABEL = {
    "inbox": "INBOX",
    "sent": "SENT",
    "drafts": "DRAFT",
}


class GmailAPIError(RuntimeError):
    """Raised when the Gmail/Google API returns an error after exhausting
    retries, or an OAuth exchange fails. `error_type` is one of:
    invalid_token, expired_token, rate_limited, or None."""

    def __init__(self, message: str, status_code: Optional[int] = None, error_type: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class GmailNotConfiguredError(RuntimeError):
    """Raised when GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET aren't set."""


# ─────────────────────────────────────────────────────────────────────────────
# Encryption — thin, purpose-named wrappers over the shared Fernet helpers
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_credential(plaintext: str) -> str:
    return encrypt_key(plaintext) if plaintext else ""


def decrypt_credential(ciphertext: str) -> str:
    return decrypt_key(ciphertext) if ciphertext else ""


# ─────────────────────────────────────────────────────────────────────────────
# Config / OAuth
# ─────────────────────────────────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET)


def _redirect_uri() -> str:
    return settings.GMAIL_REDIRECT_URI or f"{settings.APP_API_URL}/api/v1/personal-email/oauth/callback"


def build_authorize_url(state: str) -> str:
    if not is_configured():
        raise GmailNotConfiguredError("Gmail integration is not configured on this server")
    params = {
        "client_id": settings.GMAIL_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",   # required to receive a refresh_token
        "prompt": "consent",        # ensures a refresh_token is returned even on reconnect
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


async def _request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    last_exc: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                return resp
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exc = e
                if attempt < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
    raise GmailAPIError(f"Network error contacting Google: {last_exc}")


def _extract_google_error(resp: httpx.Response) -> GmailAPIError:
    error_type = None
    message = f"Google API error (HTTP {resp.status_code})"
    try:
        payload = resp.json()
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message", message)
        elif isinstance(err, str):
            message = payload.get("error_description", err)
    except Exception:  # noqa: BLE001
        pass
    if resp.status_code == 401:
        error_type = "invalid_token"
    elif resp.status_code == 403 and "invalid_grant" in message.lower():
        error_type = "expired_token"
    elif resp.status_code == 429:
        error_type = "rate_limited"
    return GmailAPIError(message, status_code=resp.status_code, error_type=error_type)


async def exchange_code_for_tokens(code: str) -> dict:
    if not is_configured():
        raise GmailNotConfiguredError("Gmail integration is not configured on this server")
    resp = await _request_with_retry(
        "POST", GOOGLE_OAUTH_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
        },
    )
    if resp.status_code >= 400:
        raise _extract_google_error(resp)
    return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    if not is_configured():
        raise GmailNotConfiguredError("Gmail integration is not configured on this server")
    resp = await _request_with_retry(
        "POST", GOOGLE_OAUTH_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": settings.GMAIL_CLIENT_ID,
            "client_secret": settings.GMAIL_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
    )
    if resp.status_code >= 400:
        err = _extract_google_error(resp)
        err.error_type = err.error_type or "expired_token"
        raise err
    return resp.json()


def token_expiry_from_expires_in(expires_in: Optional[int]) -> Optional[datetime]:
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 30)  # 30s safety margin


async def get_user_email(access_token: str) -> dict:
    resp = await _request_with_retry(
        "GET", GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"},
    )
    if resp.status_code >= 400:
        raise _extract_google_error(resp)
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Gmail REST API
# ─────────────────────────────────────────────────────────────────────────────

async def _gmail_get(access_token: str, path: str, params: Optional[dict] = None) -> dict:
    resp = await _request_with_retry(
        "GET", f"{GMAIL_API_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"}, params=params or {},
    )
    if resp.status_code >= 400:
        raise _extract_google_error(resp)
    return resp.json()


async def _gmail_post(access_token: str, path: str, json_body: Optional[dict] = None) -> dict:
    resp = await _request_with_retry(
        "POST", f"{GMAIL_API_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"}, json=json_body or {},
    )
    if resp.status_code >= 400:
        raise _extract_google_error(resp)
    return resp.json() if resp.content else {}


async def list_message_ids(
    access_token: str, *, folder: str, query: Optional[str] = None,
    max_results: int = 25, page_token: Optional[str] = None,
) -> dict:
    """Returns {"ids": [...], "next_page_token": str | None}. `folder` is
    inbox|sent|drafts|starred (starred is layered as an extra label filter
    on top of inbox, since Gmail treats STARRED as a label, not a folder)."""
    label_ids = []
    if folder == "starred":
        label_ids = ["STARRED"]
    else:
        label_ids = [FOLDER_LABEL.get(folder, "INBOX")]

    params: dict[str, Any] = {"maxResults": max_results, "labelIds": label_ids}
    if query:
        params["q"] = query
    if page_token:
        params["pageToken"] = page_token

    data = await _gmail_get(access_token, "/messages", params=params)
    return {
        "ids": [m["id"] for m in data.get("messages", [])],
        "next_page_token": data.get("nextPageToken"),
    }


@dataclass
class EmailMessage:
    provider_message_id: str
    provider_thread_id: Optional[str]
    sender_name: Optional[str]
    sender_email: Optional[str]
    to_addresses: Optional[str]
    subject: Optional[str]
    snippet: Optional[str]
    body_text: Optional[str]
    body_html: Optional[str]
    received_at: Optional[datetime]
    is_starred: bool
    is_read: bool
    label_ids: list = field(default_factory=list)
    attachments: list = field(default_factory=list)
    # list[{"attachment_id": str, "filename": str, "mime_type": str, "size": int}]


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _walk_parts(part: dict, text_out: list, html_out: list, attachments_out: Optional[list] = None) -> None:
    mime_type = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")
    filename = part.get("filename") or ""
    # A part is an attachment if it has a filename and either an
    # attachmentId (too large to inline) or is not text/plain|text/html.
    if filename and attachments_out is not None and (body.get("attachmentId") or mime_type not in ("text/plain", "text/html")):
        attachments_out.append({
            "attachment_id": body.get("attachmentId"),
            "filename": filename,
            "mime_type": mime_type or "application/octet-stream",
            "size": body.get("size") or 0,
        })
    elif mime_type == "text/plain" and data:
        text_out.append(_decode_b64url(data))
    elif mime_type == "text/html" and data:
        html_out.append(_decode_b64url(data))
    for sub in part.get("parts", []) or []:
        _walk_parts(sub, text_out, html_out, attachments_out)


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", html)
    text = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_address_header(value: str) -> tuple[Optional[str], Optional[str]]:
    """'Jane Doe <jane@example.com>' -> ('Jane Doe', 'jane@example.com')."""
    if not value:
        return None, None
    match = re.match(r"^\s*(.*?)\s*<([^<>]+)>\s*$", value)
    if match:
        name = match.group(1).strip().strip('"') or None
        return name, match.group(2).strip()
    return None, value.strip()


def parse_message(raw: dict) -> EmailMessage:
    payload = raw.get("payload", {}) or {}
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", []) or []}

    text_parts: list = []
    html_parts: list = []
    attachment_parts: list = []
    if payload.get("body", {}).get("data") and not payload.get("filename"):
        _walk_parts(payload, text_parts, html_parts, attachment_parts)
    else:
        for sub in payload.get("parts", []) or []:
            _walk_parts(sub, text_parts, html_parts, attachment_parts)

    body_html = "\n".join(html_parts) if html_parts else None
    body_text = "\n".join(text_parts) if text_parts else (_html_to_text(body_html) if body_html else None)

    sender_name, sender_email = _parse_address_header(headers.get("from", ""))

    received_at = None
    try:
        internal_date = raw.get("internalDate")
        if internal_date:
            received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
    except Exception:  # noqa: BLE001
        received_at = None

    label_ids = raw.get("labelIds", []) or []

    return EmailMessage(
        provider_message_id=raw["id"],
        provider_thread_id=raw.get("threadId"),
        sender_name=sender_name,
        sender_email=sender_email,
        to_addresses=headers.get("to"),
        subject=headers.get("subject"),
        snippet=raw.get("snippet"),
        body_text=body_text,
        body_html=body_html,
        received_at=received_at,
        is_starred="STARRED" in label_ids,
        is_read="UNREAD" not in label_ids,
        label_ids=label_ids,
        attachments=attachment_parts,
    )


async def get_message(access_token: str, message_id: str) -> EmailMessage:
    data = await _gmail_get(access_token, f"/messages/{message_id}", params={"format": "full"})
    return parse_message(data)


async def modify_message_labels(
    access_token: str, message_id: str, *, add: Optional[list] = None, remove: Optional[list] = None,
) -> None:
    await _gmail_post(
        access_token, f"/messages/{message_id}/modify",
        json_body={"addLabelIds": add or [], "removeLabelIds": remove or []},
    )


async def get_attachment(access_token: str, message_id: str, attachment_id: str) -> bytes:
    """Downloads one attachment's raw bytes for a given message."""
    data = await _gmail_get(access_token, f"/messages/{message_id}/attachments/{attachment_id}")
    b64 = data.get("data", "")
    padded = b64 + "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(padded)


# ─────────────────────────────────────────────────────────────────────────────
# Send (Part 2) — one-click Send, Schedule Send, Bulk Reply, auto-reply rules
# all funnel through send_message(). Nothing above this line (Part 1) can
# send; sending only ever happens via this explicit, separately-scoped path.
# ─────────────────────────────────────────────────────────────────────────────

def build_mime_message(
    *, to: str, subject: str, body_text: str, from_name: Optional[str] = None,
    cc: Optional[str] = None, bcc: Optional[str] = None,
    in_reply_to: Optional[str] = None, thread_references: Optional[str] = None,
    attachments: Optional[list] = None,
) -> str:
    """Builds a base64url-encoded RFC 2822 MIME message ready for Gmail's
    messages.send. `attachments` is a list of
    {"filename", "mime_type", "content_base64"} dicts (already base64,
    e.g. straight from the frontend's file upload) — decoded and
    re-encoded into the multipart body here."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    from email.header import Header
    from email.utils import formataddr

    attachments = attachments or []
    msg: Any = MIMEMultipart("mixed") if attachments else MIMEMultipart("alternative")

    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = str(Header(subject or "(no subject)", "utf-8"))
    if from_name:
        msg["From"] = formataddr((str(Header(from_name, "utf-8")), ""))
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = thread_references or in_reply_to

    body_part = MIMEMultipart("alternative") if attachments else msg
    body_part.attach(MIMEText(body_text or "", "plain", "utf-8"))
    if attachments and body_part is not msg:
        msg.attach(body_part)

    for att in attachments:
        try:
            raw = base64.b64decode(att.get("content_base64", ""))
        except Exception:  # noqa: BLE001 — skip an unparsable attachment rather than fail the whole send
            continue
        mime_type = att.get("mime_type") or "application/octet-stream"
        maintype, _, subtype = mime_type.partition("/")
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(raw)
        encoders.encode_base64(part)
        filename = att.get("filename") or "attachment"
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


async def send_message(
    access_token: str, *, raw_message: str, thread_id: Optional[str] = None,
) -> dict:
    """Sends an already-MIME-encoded (base64url) message via
    messages.send. Pass `thread_id` to keep a reply in the original Gmail
    thread. Returns Gmail's response dict (id, threadId, labelIds)."""
    body: dict[str, Any] = {"raw": raw_message}
    if thread_id:
        body["threadId"] = thread_id
    return await _gmail_post(access_token, "/messages/send", json_body=body)
