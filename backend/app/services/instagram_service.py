"""
ThunderBots Instagram DM Service
NEW (Instagram Channel).

Everything needed to talk to Meta's Graph API for Instagram Messaging:
Facebook Login OAuth code/token exchange, long-lived token derivation and
refresh, an HTTP client for sending DM replies, webhook signature
validation, and Page/Instagram-account discovery for the connection
wizard. This module does not import from or modify app/engine/*
(Workflow Runtime), app/core/auth.py (Authentication), app/knowledge/*
(Knowledge Base), app/services/ai_engine.py beyond reusing its
already-existing, already-shared encrypt_key/decrypt_key Fernet helpers
(same pattern services/whatsapp_service.py already uses), or anything
under app/api/v1/deploy.py (Deployment).

Media/attachments: Meta's Instagram Send/webhook payloads carry a plain
CDN `url` for attachments (no separate download-URL-resolution round trip
like WhatsApp's media API). The normalizer in api/v1/instagram.py already
captures that URL into InstagramMessageLog.attachment_url today; actually
downloading/re-hosting it (mirroring
services/whatsapp_service.download_and_store_media) is intentionally not
implemented in this pass since only text is executed through the AI Agent
for now — the schema and log plumbing are ready so that a future change is
additive (a new `download_and_store_attachment` function plus a call site
in the webhook handler), not a redesign.

Retry policy: every outbound Graph API call goes through
`_request_with_retry`, identical in shape to whatsapp_service's helper —
retries transient failures (timeouts, 429, 5xx) up to 3 times with
exponential backoff (0.5s, 1s, 2s). 4xx errors other than 429 are not
retried.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.ai_engine import encrypt_key, decrypt_key  # reused as-is, not modified

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = settings.INSTAGRAM_GRAPH_API_VERSION
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FB_OAUTH_DIALOG_URL = "https://www.facebook.com/v21.0/dialog/oauth"

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.0, 2.0)

# Scopes required to discover the Page's linked Instagram Business account
# and to send/receive Instagram DMs via the Send API.
OAUTH_SCOPES = [
    "instagram_basic",
    "instagram_manage_messages",
    "pages_show_list",
    "pages_manage_metadata",
    "pages_messaging",
]


class InstagramAPIError(RuntimeError):
    """Raised when the Graph API returns an error after exhausting retries,
    or an OAuth exchange fails. `error_type` is one of: invalid_token,
    expired_token, missing_permissions, rate_limited, verification_failed,
    or None for an otherwise-uncategorized failure — set by
    `_extract_graph_error` so callers/UI can react appropriately without
    string-matching the message."""

    def __init__(
        self, message: str, status_code: Optional[int] = None,
        payload: Optional[dict] = None, error_type: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.error_type = error_type


class InstagramNotConfiguredError(RuntimeError):
    """Raised when INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET aren't set."""


# ─────────────────────────────────────────────────────────────────────────────
# Encryption — thin, purpose-named wrappers over the shared Fernet helpers
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_credential(plaintext: str) -> str:
    return encrypt_key(plaintext) if plaintext else ""


def decrypt_credential(ciphertext: str) -> str:
    return decrypt_key(ciphertext) if ciphertext else ""


# ─────────────────────────────────────────────────────────────────────────────
# Webhook signature validation (app-wide secret — same HMAC scheme as
# WhatsApp's per-connection App Secret, but Instagram/Messenger webhooks are
# registered once per Meta App, so this always uses INSTAGRAM_APP_SECRET)
# ─────────────────────────────────────────────────────────────────────────────

def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
    app_secret = settings.INSTAGRAM_APP_SECRET
    if not app_secret:
        # No app secret configured — best-effort, matches whatsapp_service's
        # posture of not hard-failing an intentionally-unconfigured field.
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, provided)


def verify_webhook_token(token: Optional[str]) -> bool:
    """Constant-time comparison for the GET verification handshake."""
    expected = settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


# ─────────────────────────────────────────────────────────────────────────────
# Retry helper — identical shape to whatsapp_service._request_with_retry
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
                    f"Instagram API {method} {url} returned {resp.status_code}, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            last_exc = e
            if attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    f"Instagram API {method} {url} network error: {e}, "
                    f"retrying (attempt {attempt + 1}/{_MAX_ATTEMPTS})"
                )
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                continue
            raise
    if last_exc:
        raise last_exc
    raise InstagramAPIError(f"Exhausted retries for {method} {url}")


def _extract_graph_error(resp: httpx.Response) -> InstagramAPIError:
    try:
        body = resp.json()
        err = body.get("error", {})
        msg = err.get("message") or str(body)
        code = err.get("code")
        subcode = err.get("error_subcode")
        error_type: Optional[str] = None
        # Meta's OAuthException codes for invalid/expired tokens and
        # missing permissions — mapped so callers can branch on
        # e.error_type instead of parsing prose.
        if code in (190,):
            error_type = "expired_token" if subcode in (463, 467) else "invalid_token"
        elif code in (10, 200, 299) or (isinstance(code, int) and 200 <= code < 300):
            error_type = "missing_permissions"
        elif code == 4 or resp.status_code == 429:
            error_type = "rate_limited"
        text = f"{msg}" + (f" (code {code}{f'/{subcode}' if subcode else ''})" if code else "")
        return InstagramAPIError(text, status_code=resp.status_code, payload=body, error_type=error_type)
    except Exception:
        return InstagramAPIError(
            f"HTTP {resp.status_code}: {resp.text[:300]}", status_code=resp.status_code,
        )


# ─────────────────────────────────────────────────────────────────────────────
# OAuth — Facebook Login flow used to connect a Page's Instagram account
# ─────────────────────────────────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(settings.INSTAGRAM_APP_ID and settings.INSTAGRAM_APP_SECRET)


def redirect_uri() -> str:
    return settings.INSTAGRAM_REDIRECT_URI or f"{settings.APP_API_URL}/api/v1/instagram/oauth/callback"


def build_authorize_url(state: str) -> str:
    """Builds the Meta/Facebook Login OAuth dialog URL. `state` is a signed,
    short-lived JWT (see api/v1/instagram.py) carrying workflow_id + user_id
    so the callback can't be replayed against a different bot or account."""
    if not is_configured():
        raise InstagramNotConfiguredError(
            "Instagram integration is not configured (INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET missing)"
        )
    from urllib.parse import urlencode
    params = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": ",".join(OAUTH_SCOPES),
        "response_type": "code",
    }
    return f"{FB_OAUTH_DIALOG_URL}?{urlencode(params)}"


async def exchange_code_for_user_token(code: str) -> dict:
    """Step 1: authorization code -> short-lived user access token."""
    url = f"{GRAPH_BASE_URL}/oauth/access_token"
    params = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "client_secret": settings.INSTAGRAM_APP_SECRET,
        "redirect_uri": redirect_uri(),
        "code": code,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await _request_with_retry(client, "GET", url, params=params)
    if resp.status_code >= 400:
        raise _extract_graph_error(resp)
    return resp.json()


async def get_long_lived_user_token(short_lived_token: str) -> dict:
    """Step 2: short-lived (~1-2h) user token -> long-lived (~60 day) user
    token. Returns {"access_token": ..., "expires_in": <seconds>}."""
    url = f"{GRAPH_BASE_URL}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": settings.INSTAGRAM_APP_ID,
        "client_secret": settings.INSTAGRAM_APP_SECRET,
        "fb_exchange_token": short_lived_token,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await _request_with_retry(client, "GET", url, params=params)
    if resp.status_code >= 400:
        raise _extract_graph_error(resp)
    return resp.json()


async def list_pages_with_instagram(user_access_token: str) -> list[dict]:
    """Step 3: enumerate the Facebook Pages this user manages, each with its
    Page Access Token and (if linked) connected Instagram Business account.
    Only pages with a linked IG account are returned — that's the set the
    connection wizard can actually offer."""
    url = f"{GRAPH_BASE_URL}/me/accounts"
    params = {
        "fields": "id,name,access_token,instagram_business_account{id,username,profile_picture_url}",
        "access_token": user_access_token,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await _request_with_retry(client, "GET", url, params=params)
    if resp.status_code >= 400:
        raise _extract_graph_error(resp)
    data = resp.json().get("data", [])
    return [p for p in data if p.get("instagram_business_account")]


async def refresh_long_lived_token(current_token: str) -> dict:
    """Refreshes a not-yet-expired long-lived Page/User token for another
    ~60 days. Uses the same fb_exchange_token grant as the initial
    short->long exchange — Meta's supported way to extend a long-lived
    token's life without re-running the OAuth consent screen."""
    return await get_long_lived_user_token(current_token)


# ─────────────────────────────────────────────────────────────────────────────
# Send API client
# ─────────────────────────────────────────────────────────────────────────────

class InstagramGraphClient:
    """Thin, typed wrapper around the pieces of the Instagram Messaging API
    (via the Send API on the linked Facebook Page) this integration needs:
    sending text replies, marking-seen, and validating the token/page."""

    def __init__(self, page_id: str, page_access_token: str, timeout: float = 20.0):
        self.page_id = page_id
        self.page_access_token = page_access_token
        self.timeout = timeout

    async def _post_messages(self, payload: dict) -> dict:
        url = f"{GRAPH_BASE_URL}/{self.page_id}/messages"
        params = {"access_token": self.page_access_token}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(client, "POST", url, params=params, json=payload)
        if resp.status_code >= 400:
            raise _extract_graph_error(resp)
        return resp.json()

    async def send_text(self, igsid: str, text: str) -> dict:
        return await self._post_messages({
            "recipient": {"id": igsid},
            "message": {"text": text[:1000]},
            "messaging_type": "RESPONSE",
        })

    async def send_image(self, igsid: str, link: str) -> dict:
        return await self._post_messages({
            "recipient": {"id": igsid},
            "message": {"attachment": {"type": "image", "payload": {"url": link, "is_reusable": True}}},
            "messaging_type": "RESPONSE",
        })

    async def mark_seen(self, igsid: str) -> None:
        try:
            await self._post_messages({"recipient": {"id": igsid}, "sender_action": "mark_seen"})
        except Exception as e:  # noqa: BLE001 — read receipts are non-critical
            logger.debug(f"Instagram mark_seen failed (non-fatal): {e}")

    async def get_page_and_ig_details(self) -> dict:
        """Test Connection / Reconnect: re-reads Page name + linked IG
        account details using the currently stored Page Access Token."""
        url = f"{GRAPH_BASE_URL}/{self.page_id}"
        params = {
            "fields": "name,instagram_business_account{id,username,profile_picture_url}",
            "access_token": self.page_access_token,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await _request_with_retry(client, "GET", url, params=params)
        if resp.status_code >= 400:
            raise _extract_graph_error(resp)
        return resp.json()


def client_from_account(account) -> InstagramGraphClient:
    """Build an InstagramGraphClient from an InstagramAccount ORM row."""
    return InstagramGraphClient(
        page_id=account.facebook_page_id,
        page_access_token=decrypt_credential(account.encrypted_page_access_token),
    )


def token_expiry_from_expires_in(expires_in: Optional[int]) -> Optional[datetime]:
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))


def compute_status_from_expiry(token_expires_at: Optional[datetime]) -> Optional[str]:
    """Returns 'expired' if the stored expiry has already passed, else
    None (caller keeps whatever status Test Connection last set)."""
    if token_expires_at and datetime.now(timezone.utc) >= token_expires_at:
        return "expired"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Background token-refresh loop — automatically refreshes tokens nearing
# expiry so owners don't discover an "Expired" bot only after DMs stop
# being answered. Purely additive: started as its own asyncio task from
# main.py's lifespan (same pattern as campaign_dispatch_service's scheduler
# loop), never touches any existing startup behavior, and never raises out
# of its own loop.
# ─────────────────────────────────────────────────────────────────────────────

async def run_token_refresh_loop() -> None:
    import asyncio
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.instagram import InstagramAccount, InstagramWebhookLog

    interval = max(1, settings.INSTAGRAM_TOKEN_REFRESH_INTERVAL_MINUTES) * 60
    threshold = timedelta(days=max(1, settings.INSTAGRAM_TOKEN_REFRESH_THRESHOLD_DAYS))

    while True:
        try:
            if is_configured():
                cutoff = datetime.now(timezone.utc) + threshold
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(InstagramAccount).where(
                            InstagramAccount.status == "connected",
                            InstagramAccount.token_expires_at.isnot(None),
                            InstagramAccount.token_expires_at <= cutoff,
                        )
                    )
                    for account in result.scalars().all():
                        user_token = decrypt_credential(account.encrypted_user_access_token) \
                            if account.encrypted_user_access_token else None
                        if not user_token:
                            continue
                        try:
                            refreshed = await refresh_long_lived_token(user_token)
                            new_user_token = refreshed["access_token"]
                            pages = await list_pages_with_instagram(new_user_token)
                            page = next((p for p in pages if p["id"] == account.facebook_page_id), None)
                            if not page:
                                continue
                            account.encrypted_page_access_token = encrypt_credential(page["access_token"])
                            account.encrypted_user_access_token = encrypt_credential(new_user_token)
                            account.token_expires_at = token_expiry_from_expires_in(refreshed.get("expires_in"))
                            account.last_token_refresh_at = datetime.now(timezone.utc)
                            db.add(InstagramWebhookLog(
                                account_id=account.id, event_type="token_refresh", level="info",
                                message="Access token proactively refreshed before expiry", detail={},
                            ))
                            logger.info(f"Instagram: proactively refreshed token for account={account.id}")
                        except Exception as e:  # noqa: BLE001 — one account's failure must not stop the loop
                            logger.warning(f"Instagram: proactive token refresh failed for account={account.id}: {e}")
                    await db.commit()
        except Exception as e:  # noqa: BLE001 — the loop itself must never die
            logger.error(f"Instagram token-refresh loop error: {e}", exc_info=True)

        await asyncio.sleep(interval)
