"""
ThunderBots Instagram DM API
NEW (Instagram Channel).

Three groups of routes:

1. Management (authenticated, owner-scoped) — connection status, enable/
   disable/reconnect/disconnect, test connection, webhook info, stats, logs.

2. OAuth (mixed) — GET .../oauth/authorize/{workflow_id} is authenticated
   and returns the Meta/Facebook Login dialog URL for the frontend to
   redirect the browser to; GET .../oauth/callback is PUBLIC (Meta redirects
   the user's browser here directly, with no Authorization header) and is
   protected instead by a signed, short-lived state JWT minted by the
   authorize step (see _build_oauth_state / _read_oauth_state).

3. Webhook (public, no auth — this IS Meta's callback endpoint). Unlike
   WhatsApp's per-connection webhook URL, Instagram/Messenger webhooks are
   registered once per Meta App, so there is a single app-wide
   GET/POST /webhook rather than /webhook/{account_id} — the POST handler
   routes each entry to the right InstagramAccount by matching the
   Instagram-scoped account id Meta includes in `entry[].id`.

Every inbound message is executed through the EXISTING Workflow Runtime
(app.engine.runner.WorkflowRunner) using the exact same
run()/ExecutionContext/Redis-session pattern already used by the REST chat
endpoint, the WebSocket endpoint, and api/v1/whatsapp.py — none of which are
modified by this module, only imported from (get_workflow_data /
get_deployed_workflow_data). Every turn is recorded via the existing
app.services.analytics_service with source="instagram".
"""
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.exc import IntegrityError
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.database import get_db, AsyncSessionLocal
from app.core.auth import get_current_user
from app.core.redis import CacheService
from app.engine.runner import WorkflowRunner
from app.engine.context import ExecutionContext
from app.models.user import User
from app.models.workflow import Workflow
from app.models.instagram import (
    InstagramAccount, InstagramContact, InstagramMessageLog, InstagramWebhookLog,
)
from app.config import settings
from app.services import analytics_service
from app.services import instagram_service as ig
from app.services import live_agent_service
from app.api.ws.chat_ws import get_workflow_data, get_deployed_workflow_data

router = APIRouter()
logger = logging.getLogger(__name__)

_OAUTH_STATE_TOKEN_TYPE = "ig_oauth_state"
_OAUTH_STATE_EXPIRE_MINUTES = 10


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_owned_workflow(workflow_id: str, db: AsyncSession, current_user: User) -> Workflow:
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if str(workflow.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this workflow")
    return workflow


async def _get_account(workflow_id: str, db: AsyncSession) -> Optional[InstagramAccount]:
    result = await db.execute(select(InstagramAccount).where(InstagramAccount.workflow_id == workflow_id))
    return result.scalar_one_or_none()


async def _get_account_by_ig_user_id(ig_user_id: str, db: AsyncSession) -> Optional[InstagramAccount]:
    result = await db.execute(select(InstagramAccount).where(InstagramAccount.ig_user_id == ig_user_id))
    return result.scalar_one_or_none()


def _build_oauth_state(user_id: str, workflow_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES)
    return jwt.encode(
        {"uid": user_id, "wid": workflow_id, "exp": expire, "type": _OAUTH_STATE_TOKEN_TYPE},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _read_oauth_state(state: str) -> tuple[str, str]:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=400, detail=f"Invalid or expired OAuth state: {e}")
    if payload.get("type") != _OAUTH_STATE_TOKEN_TYPE:
        raise HTTPException(status_code=400, detail="Invalid OAuth state token")
    return payload["uid"], payload["wid"]


async def _log_event(
    db: AsyncSession, account_id: Optional[str], event_type: str, message: str,
    level: str = "info", detail: Optional[dict] = None,
) -> None:
    """Best-effort connection/webhook delivery log entry. Never raises —
    logging must not break the connection flow or the webhook."""
    try:
        db.add(InstagramWebhookLog(
            account_id=account_id, event_type=event_type, level=level,
            message=message[:2000], detail=detail or {},
        ))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Instagram log_event failed (non-fatal): {e}")


def _preview(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "••••••••"
    return secret[:4] + "•" * min(len(secret) - 8, 24) + secret[-4:]


def _serialize_account(account: Optional[InstagramAccount]) -> dict:
    if not account:
        return {"connected": False, "configured": ig.is_configured()}
    # Surface "expired" even if a background refresh hasn't run yet, so the
    # Settings UI never shows a stale "Connected" pill past the token's
    # actual expiry.
    display_status = account.status
    expiry_status = ig.compute_status_from_expiry(account.token_expires_at)
    if expiry_status and account.status not in ("disconnected",):
        display_status = expiry_status

    return {
        "connected": True,
        "configured": ig.is_configured(),
        "id": account.id,
        "workflow_id": account.workflow_id,
        "platform": account.platform,
        "ig_user_id": account.ig_user_id,
        "ig_username": account.ig_username,
        "facebook_page_id": account.facebook_page_id,
        "facebook_page_name": account.facebook_page_name,
        "token_preview": _preview(ig.decrypt_credential(account.encrypted_page_access_token)),
        "token_expires_at": account.token_expires_at.isoformat() if account.token_expires_at else None,
        "status": display_status,
        "is_enabled": account.is_enabled,
        "health_status": account.health_status,
        "last_error": account.last_error,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "last_webhook_at": account.last_webhook_at.isoformat() if account.last_webhook_at else None,
        "last_tested_at": account.last_tested_at.isoformat() if account.last_tested_at else None,
        "last_token_refresh_at": account.last_token_refresh_at.isoformat() if account.last_token_refresh_at else None,
        "messages_received_count": account.messages_received_count,
        "messages_sent_count": account.messages_sent_count,
        "messages_failed_count": account.messages_failed_count,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Management API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/accounts/{workflow_id}")
async def get_account(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    return _serialize_account(account)


@router.get("/accounts")
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All Instagram accounts connected across the user's workspace —
    backs the Integrations/Channels overview ('multiple Instagram accounts
    per workspace')."""
    result = await db.execute(
        select(InstagramAccount).where(InstagramAccount.user_id == current_user.id)
        .order_by(desc(InstagramAccount.updated_at))
    )
    accounts = result.scalars().all()
    return {"accounts": [_serialize_account(a) for a in accounts]}


@router.get("/oauth/authorize/{workflow_id}")
async def oauth_authorize(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the Meta/Facebook Login dialog URL. The frontend redirects
    the full browser window to this URL (not an XHR/fetch) — Meta's OAuth
    dialog cannot be embedded via fetch/XHR."""
    await _get_owned_workflow(workflow_id, db, current_user)
    if not ig.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Instagram integration is not configured on this server (missing Meta App credentials)",
        )
    state = _build_oauth_state(str(current_user.id), workflow_id)
    return {"authorize_url": ig.build_authorize_url(state)}


@router.get("/oauth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """Public — Meta redirects the user's browser here after consent.
    Always ends in a redirect back to the frontend's per-workflow Instagram
    settings page, with a query param indicating success/failure, since
    there is no API caller here to return JSON to."""
    if not state:
        return RedirectResponse(f"{settings.APP_BASE_URL}/instagram?error=missing_state")

    user_id, workflow_id = _read_oauth_state(state)
    frontend_url = f"{settings.APP_BASE_URL}/instagram/{workflow_id}"

    if error:
        async with AsyncSessionLocal() as db:
            await _log_event(
                db, None, "oauth_error", f"Meta OAuth error: {error} — {error_description}",
                level="error", detail={"error": error, "error_description": error_description},
            )
            await db.commit()
        return RedirectResponse(f"{frontend_url}?ig_error={error}")

    if not code:
        return RedirectResponse(f"{frontend_url}?ig_error=missing_code")

    async with AsyncSessionLocal() as db:
        try:
            short_lived = await ig.exchange_code_for_user_token(code)
            long_lived = await ig.get_long_lived_user_token(short_lived["access_token"])
            user_token = long_lived["access_token"]
            expires_at = ig.token_expiry_from_expires_in(long_lived.get("expires_in"))

            pages = await ig.list_pages_with_instagram(user_token)
            if not pages:
                await _log_event(
                    db, None, "oauth_error",
                    "No Facebook Page with a linked Instagram Business account was found for this login",
                    level="error",
                )
                await db.commit()
                return RedirectResponse(f"{frontend_url}?ig_error=no_linked_instagram_account")

            # A workflow drives exactly one bot's worth of DMs — take the
            # first eligible Page. (Listing/choosing among several is a
            # frontend enhancement the API already supports via the
            # `pages` field returned here for future use.)
            page = pages[0]
            ig_account = page["instagram_business_account"]

            account = await _get_account(workflow_id, db)
            if account:
                account.ig_user_id = ig_account["id"]
                account.ig_username = ig_account.get("username")
                account.facebook_page_id = page["id"]
                account.facebook_page_name = page.get("name")
                account.encrypted_page_access_token = ig.encrypt_credential(page["access_token"])
                account.encrypted_user_access_token = ig.encrypt_credential(user_token)
                account.token_expires_at = expires_at
                account.status = "connected"
                account.health_status = "healthy"
                account.last_error = None
                account.last_sync_at = datetime.now(timezone.utc)
                account.last_tested_at = datetime.now(timezone.utc)
            else:
                account = InstagramAccount(
                    workflow_id=workflow_id,
                    user_id=user_id,
                    ig_user_id=ig_account["id"],
                    ig_username=ig_account.get("username"),
                    facebook_page_id=page["id"],
                    facebook_page_name=page.get("name"),
                    encrypted_page_access_token=ig.encrypt_credential(page["access_token"]),
                    encrypted_user_access_token=ig.encrypt_credential(user_token),
                    token_expires_at=expires_at,
                    status="connected",
                    health_status="healthy",
                    last_sync_at=datetime.now(timezone.utc),
                    last_tested_at=datetime.now(timezone.utc),
                )
                db.add(account)

            await db.flush()
            await _log_event(
                db, account.id, "oauth_connect",
                f"Connected Instagram @{ig_account.get('username', ig_account['id'])} via Page '{page.get('name', page['id'])}'",
            )
            await db.commit()
            return RedirectResponse(f"{frontend_url}?ig_connected=1")
        except ig.InstagramAPIError as e:
            await _log_event(db, None, "oauth_error", f"OAuth token/page exchange failed: {e}", level="error")
            await db.commit()
            return RedirectResponse(f"{frontend_url}?ig_error=oauth_exchange_failed")
        except Exception as e:  # noqa: BLE001 — never let an unhandled error strand the browser mid-redirect
            logger.error(f"Instagram OAuth callback error: {e}", exc_info=True)
            await _log_event(db, None, "oauth_error", f"Unexpected OAuth callback error: {e}", level="error")
            await db.commit()
            return RedirectResponse(f"{frontend_url}?ig_error=unexpected")


@router.post("/accounts/{workflow_id}/test")
async def test_connection(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="No Instagram connection configured for this bot")

    client = ig.client_from_account(account)
    started = time.monotonic()
    try:
        details = await client.get_page_and_ig_details()
        latency_ms = int((time.monotonic() - started) * 1000)
        ig_details = details.get("instagram_business_account") or {}
        result = {
            "ok": True, "latency_ms": latency_ms,
            "facebook_page_name": details.get("name"),
            "ig_username": ig_details.get("username"),
        }
    except ig.InstagramAPIError as e:
        result = {"ok": False, "error": str(e), "error_type": e.error_type,
                   "latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as e:
        result = {"ok": False, "error": str(e).strip() or f"{type(e).__name__}",
                   "latency_ms": int((time.monotonic() - started) * 1000)}

    account.last_tested_at = datetime.now(timezone.utc)
    if result["ok"]:
        account.status = "connected"
        account.health_status = "healthy"
        account.last_error = None
        account.facebook_page_name = result.get("facebook_page_name") or account.facebook_page_name
        account.ig_username = result.get("ig_username") or account.ig_username
        await _log_event(db, account.id, "webhook_verify", "Test Connection succeeded")
    else:
        error_type = result.get("error_type")
        account.status = "expired" if error_type in ("invalid_token", "expired_token") else "error"
        account.health_status = "error"
        account.last_error = result.get("error")
        await _log_event(db, account.id, "send_failed", f"Test Connection failed: {result.get('error')}", level="error")
    await db.commit()
    return result


@router.post("/accounts/{workflow_id}/enable")
async def enable_account(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="No Instagram connection configured for this bot")
    if account.status != "connected":
        raise HTTPException(status_code=400, detail="Run Test Connection successfully before enabling Instagram")
    account.is_enabled = True
    await db.commit()
    return {"is_enabled": True, "status": account.status}


@router.post("/accounts/{workflow_id}/disable")
async def disable_account(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="No Instagram connection configured for this bot")
    account.is_enabled = False
    await db.commit()
    return {"is_enabled": False, "status": account.status}


@router.post("/accounts/{workflow_id}/reconnect")
async def reconnect_account(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-validates the currently saved Page Access Token. If it has
    expired or been revoked, the response tells the frontend to send the
    owner back through OAuth (`needs_reauth: true`) rather than silently
    failing — a stored user token can extend a still-valid token, but
    cannot resurrect one Meta has already revoked."""
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="No Instagram connection configured for this bot")

    # First, try a no-op re-validate — cheapest path, no token churn.
    client = ig.client_from_account(account)
    try:
        details = await client.get_page_and_ig_details()
        ig_details = details.get("instagram_business_account") or {}
        account.status = "connected"
        account.health_status = "healthy"
        account.last_error = None
        account.facebook_page_name = details.get("name") or account.facebook_page_name
        account.ig_username = ig_details.get("username") or account.ig_username
        account.last_tested_at = datetime.now(timezone.utc)
        account.last_sync_at = datetime.now(timezone.utc)
        await _log_event(db, account.id, "webhook_verify", "Reconnect succeeded (token still valid)")
        await db.commit()
        return {"ok": True, "status": account.status, "needs_reauth": False}
    except ig.InstagramAPIError as e:
        if e.error_type not in ("invalid_token", "expired_token"):
            account.status = "error"
            account.health_status = "error"
            account.last_error = str(e)
            await db.commit()
            raise HTTPException(status_code=502, detail=f"Reconnect failed: {e}")

    # Token looks invalid/expired — attempt a silent long-lived refresh
    # using the stored user token before asking the owner to re-authenticate.
    user_token = ig.decrypt_credential(account.encrypted_user_access_token) if account.encrypted_user_access_token else None
    if user_token:
        try:
            refreshed = await ig.refresh_long_lived_token(user_token)
            new_user_token = refreshed["access_token"]
            pages = await ig.list_pages_with_instagram(new_user_token)
            page = next((p for p in pages if p["id"] == account.facebook_page_id), None) or (pages[0] if pages else None)
            if page:
                account.encrypted_page_access_token = ig.encrypt_credential(page["access_token"])
                account.encrypted_user_access_token = ig.encrypt_credential(new_user_token)
                account.token_expires_at = ig.token_expiry_from_expires_in(refreshed.get("expires_in"))
                account.status = "connected"
                account.health_status = "healthy"
                account.last_error = None
                account.last_token_refresh_at = datetime.now(timezone.utc)
                account.last_sync_at = datetime.now(timezone.utc)
                await _log_event(db, account.id, "token_refresh", "Access token refreshed successfully")
                await db.commit()
                return {"ok": True, "status": account.status, "needs_reauth": False, "token_refreshed": True}
        except Exception as e:  # noqa: BLE001 — fall through to needs_reauth
            logger.warning(f"Instagram token refresh failed for account={account.id}: {e}")

    account.status = "expired"
    account.health_status = "error"
    account.last_error = "Access token expired or was revoked — reconnect via Instagram OAuth"
    await _log_event(db, account.id, "oauth_error", "Token expired/revoked; owner must re-authenticate", level="warning")
    await db.commit()
    return {"ok": False, "status": account.status, "needs_reauth": True,
            "error": "Your Instagram connection has expired. Please reconnect."}


@router.post("/accounts/{workflow_id}/disconnect")
async def disconnect_account(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnects Instagram: clears stored tokens and disables the
    account. The row (and historical conversations already recorded in
    Analytics) is kept, so reconnecting doesn't lose history."""
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="No Instagram connection configured for this bot")

    account.is_enabled = False
    account.status = "disconnected"
    account.health_status = "unknown"
    account.last_error = None
    account.encrypted_page_access_token = ""
    account.encrypted_user_access_token = None
    account.token_expires_at = None
    await _log_event(db, account.id, "oauth_error", "Disconnected by owner", level="info")
    await db.commit()
    return {"disconnected": True}


@router.get("/accounts/{workflow_id}/webhook-info")
async def webhook_info(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        raise HTTPException(status_code=404, detail="Connect Instagram first to get webhook details")
    return {
        # App-wide — one webhook URL/verify-token pair covers every
        # Instagram account connected across the whole Meta App, unlike
        # WhatsApp's per-connection URL.
        "webhook_url": f"{settings.APP_API_URL}/api/v1/instagram/webhook",
        "verify_token_configured": bool(settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN),
        "app_secret_configured": bool(settings.INSTAGRAM_APP_SECRET),
        "subscribe_fields": ["messages", "messaging_postbacks"],
        "scope": "app-wide (registered once in the Meta App dashboard, shared by every connected account)",
    }


@router.get("/accounts/{workflow_id}/stats")
async def account_stats(
    workflow_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        return {"connected": False}

    conversations = await analytics_service.list_conversations(
        db, str(current_user.id), workflow_id=workflow_id, source="instagram",
        page=page, page_size=page_size,
    )
    contacts_result = await db.execute(
        select(InstagramContact)
        .where(InstagramContact.account_id == account.id)
        .order_by(InstagramContact.last_message_at.desc())
        .limit(50)
    )
    contacts = contacts_result.scalars().all()

    return {
        "connected": True,
        "status": account.status,
        "is_enabled": account.is_enabled,
        "health_status": account.health_status,
        "last_error": account.last_error,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "last_webhook_at": account.last_webhook_at.isoformat() if account.last_webhook_at else None,
        "messages_received_count": account.messages_received_count,
        "messages_sent_count": account.messages_sent_count,
        "messages_failed_count": account.messages_failed_count,
        "contact_count": len(contacts),
        "contacts": [
            {
                "igsid": c.igsid, "username": c.username,
                "message_count": c.message_count,
                "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            }
            for c in contacts
        ],
        "conversations": conversations,
    }


@router.get("/accounts/{workflow_id}/logs")
async def account_logs(
    workflow_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connection & webhook delivery logs for the Settings UI."""
    await _get_owned_workflow(workflow_id, db, current_user)
    account = await _get_account(workflow_id, db)
    if not account:
        return {"logs": []}

    result = await db.execute(
        select(InstagramWebhookLog)
        .where(InstagramWebhookLog.account_id == account.id)
        .order_by(desc(InstagramWebhookLog.created_at))
        .limit(limit)
    )
    logs = result.scalars().all()
    return {
        "logs": [
            {
                "id": l.id, "event_type": l.event_type, "level": l.level,
                "message": l.message, "detail": l.detail,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Webhook — public, called by Meta (app-wide, not per-account)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta's subscription handshake: GET with hub.mode=subscribe and
    hub.verify_token must match INSTAGRAM_WEBHOOK_VERIFY_TOKEN, echoing
    back hub.challenge verbatim as plain text — otherwise 403."""
    if hub_mode == "subscribe" and ig.verify_webhook_token(hub_verify_token):
        return PlainTextResponse(content=hub_challenge or "")

    async with AsyncSessionLocal() as db:
        await _log_event(
            db, None, "webhook_verify", "Webhook verification handshake failed",
            level="error", detail={"hub_mode": hub_mode},
        )
        await db.commit()
    raise HTTPException(status_code=403, detail="Webhook verification failed")


def _session_id_for(account_id: str, igsid: str) -> str:
    return f"ig_{account_id}_{igsid}"


def _normalize_incoming_message(message: dict) -> dict:
    """Turns a single Messaging entry's `message` object into a normalized
    dict: {text, attachment_type, attachment_url, message_type}. `text` is
    always populated with something safe to feed into the Workflow Runtime
    as user_message, even for non-text message types."""
    out = {"text": "", "attachment_type": None, "attachment_url": None, "message_type": "text"}

    text = message.get("text")
    attachments = message.get("attachments") or []

    if text:
        out["text"] = text
    elif attachments:
        att = attachments[0]
        atype = att.get("type", "attachment")
        url = (att.get("payload") or {}).get("url")
        out["attachment_type"] = atype
        out["attachment_url"] = url
        out["message_type"] = atype
        out["text"] = f"[{atype.capitalize()} received]"
    else:
        out["text"] = "[Unsupported message content]"

    quick_reply = message.get("quick_reply")
    if quick_reply and quick_reply.get("payload"):
        out["text"] = quick_reply["payload"]

    return out


async def _send_runner_result(client: ig.InstagramGraphClient, igsid: str, result: dict) -> tuple[int, int]:
    """Sends the WorkflowRunner result back to Instagram. Returns
    (sent_count, failed_count). Instagram's Send API has no native
    button/list message type outside the Messenger platform's generic
    templates, so multiple-choice responses are sent as plain numbered
    text — the Workflow Runtime's choice-parsing on the next turn already
    accepts a typed number/label back, same as any free-text channel."""
    sent, failed = 0, 0
    response_text = (result.get("response") or "").strip()
    choices = result.get("choices")
    image = result.get("image")

    try:
        if choices:
            options = "\n".join(
                f"{i + 1}. {c.get('label') or c.get('value') or f'Option {i + 1}'}"
                for i, c in enumerate(choices)
            )
            body = f"{response_text}\n\n{options}" if response_text else options
            await client.send_text(igsid, body)
            sent += 1
        elif response_text:
            await client.send_text(igsid, response_text)
            sent += 1

        if image:
            await client.send_image(igsid, image)
            sent += 1
    except Exception as e:
        logger.error(f"Instagram send failed to={igsid}: {e}", exc_info=True)
        failed += 1

    return sent, failed


@router.post("/webhook")
async def receive_webhook(request: Request):
    raw_body = await request.body()

    signature = request.headers.get("x-hub-signature-256")
    if not ig.verify_webhook_signature(raw_body, signature):
        logger.warning("Instagram webhook signature validation failed")
        async with AsyncSessionLocal() as db:
            await _log_event(db, None, "signature_invalid", "Webhook signature validation failed", level="error")
            await db.commit()
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        return {"status": "invalid_json"}

    if payload.get("object") not in ("instagram", "page"):
        return {"status": "ignored"}

    cache = CacheService()

    async with AsyncSessionLocal() as db:
        for entry in payload.get("entry", []):
            ig_recipient_id = entry.get("id")
            account = await _get_account_by_ig_user_id(ig_recipient_id, db) if ig_recipient_id else None
            if not account:
                # Unknown/unconnected account — ack quietly so Meta doesn't
                # hammer retries against an account we don't manage.
                continue

            await _log_event(db, account.id, "webhook_receive", "Webhook delivery received")

            if not account.is_enabled:
                await db.commit()
                continue

            workflow_id = account.workflow_id
            workflow = await get_deployed_workflow_data(workflow_id, cache)
            if not workflow:
                # Fall back to the live draft so a bot only ever used via
                # Instagram (never explicitly Published) still works — the
                # Instagram OAuth connection is already an owner-authorized,
                # explicit "go live" action, same trust level as Publish.
                workflow = await get_workflow_data(workflow_id, cache)

            if not workflow or not workflow.get("nodes"):
                account.last_error = "Workflow has no nodes / could not be loaded"
                account.health_status = "error"
                account.last_webhook_at = datetime.now(timezone.utc)
                await db.commit()
                continue

            client = ig.client_from_account(account)
            any_failed = False

            for messaging_event in entry.get("messaging", []):
                igsid = (messaging_event.get("sender") or {}).get("id")
                message = messaging_event.get("message")
                if not igsid or not message:
                    continue  # e.g. delivery/read receipts, postbacks not yet supported
                if message.get("is_echo"):
                    continue  # our own outbound message reflected back — never re-process

                mid = message.get("mid") or ""

                # ── Duplicate-webhook-processing guard ──────────────────
                if mid:
                    existing = await db.execute(
                        select(InstagramMessageLog).where(
                            InstagramMessageLog.account_id == account.id, InstagramMessageLog.mid == mid,
                        )
                    )
                    if existing.scalar_one_or_none():
                        logger.info(f"Instagram webhook: duplicate mid={mid} for account={account.id}, skipping")
                        continue

                normalized = _normalize_incoming_message(message)
                user_message = normalized["text"]
                session_id = _session_id_for(account.id, igsid)

                # ── Contact / session bookkeeping ───────────────────────
                contact_result = await db.execute(
                    select(InstagramContact).where(
                        InstagramContact.account_id == account.id, InstagramContact.igsid == igsid,
                    )
                )
                contact = contact_result.scalar_one_or_none()
                if not contact:
                    contact = InstagramContact(
                        account_id=account.id, workflow_id=workflow_id, igsid=igsid, session_id=session_id,
                    )
                    db.add(contact)
                contact.message_count += 1
                contact.last_message_at = datetime.now(timezone.utc)

                # ── Load ExecutionContext (same Redis session pattern
                # used by the REST + WS + WhatsApp chat paths) ───────────
                context_data = await cache.get(f"session:{session_id}")
                context = (
                    ExecutionContext.from_dict(context_data) if context_data
                    else ExecutionContext(session_id=session_id, workflow_id=workflow_id)
                )
                if not context.session_id:
                    context.session_id = session_id
                if not context.workflow_id:
                    context.workflow_id = workflow_id

                if normalized["attachment_url"]:
                    # Architecture kept ready for images/videos/attachments:
                    # the raw CDN URL is captured on the context and in the
                    # message log now; a future change can add a download/
                    # re-host step here (mirroring
                    # whatsapp_service.download_and_store_media) without
                    # touching anything else in this handler.
                    context.set_variable("last_attachment_url", normalized["attachment_url"])
                    context.set_variable("last_attachment_type", normalized["attachment_type"])

                # ── Execute the EXISTING Workflow Runtime ───────────────
                runner = WorkflowRunner(workflow, user_id=account.user_id)
                started = time.monotonic()
                turn_error = False
                turn_error_content = None
                try:
                    run_result = await runner.run(user_message, context)
                    context = ExecutionContext.from_dict(run_result["context"])
                except Exception as e:
                    turn_error = True
                    turn_error_content = str(e).strip() or f"{type(e).__name__} during workflow execution"
                    logger.error(
                        f"Instagram workflow execution error account={account.id}: {turn_error_content}",
                        exc_info=True,
                    )
                    run_result = {"response": None, "ended": False, "context": context.to_dict(),
                                  "node_type": "error", "choices": None, "image": None, "citations": []}

                # ROOT CAUSE FIX (Issue 2 — "generated chatbot sometimes
                # does not answer"): a Workflow Runtime execution error used
                # to leave run_result["response"] as None and, below, skip
                # sending anything back to Instagram entirely — the real
                # customer saw total silence. Mirrors the EXISTING, already-
                # correct Telegram behavior (api/v1/telegram.py): queue a
                # Live Agent handoff and always send a friendly fallback
                # message, so every inbound message gets some reply.
                if turn_error:
                    try:
                        await live_agent_service.request_handoff(
                            session_id=session_id, workflow_id=workflow_id, owner_id=account.user_id,
                            channel="instagram", reason="AI Agent could not process this message",
                            requested_by="ai",
                            visitor_label=f"@{contact.username}" if contact.username else f"Instagram {igsid}",
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Instagram auto-handoff-on-error failed account={account.id}: {e}", exc_info=True)
                    run_result["response"] = (
                        "I'm having trouble answering that right now — connecting you with a human agent."
                    )

                latency_ms = int((time.monotonic() - started) * 1000)
                await cache.set(f"session:{session_id}", context.to_dict(), ttl=settings.SESSION_CACHE_TTL)

                # ── Send reply back to Instagram (retried inside the client) ──
                # ROOT CAUSE FIX: previously gated on `not turn_error`, which
                # meant an execution error skipped sending anything at all.
                # Now always attempts to send whatever run_result["response"]
                # holds — the real answer on success, or the friendly
                # fallback message set above on failure.
                sent, failed = (0, 0)
                if run_result.get("response") or run_result.get("choices"):
                    sent, failed = await _send_runner_result(client, igsid, run_result)
                    if failed:
                        any_failed = True
                await client.mark_seen(igsid)

                account.messages_received_count += 1
                account.messages_sent_count += sent
                account.messages_failed_count += failed

                # ── Message log — dedup ledger + audit trail ────────────
                if mid:
                    db.add(InstagramMessageLog(
                        account_id=account.id, workflow_id=workflow_id, mid=mid, igsid=igsid,
                        direction="inbound", message_type=normalized["message_type"],
                        attachment_type=normalized["attachment_type"], attachment_url=normalized["attachment_url"],
                        status="failed" if turn_error else "processed",
                        error=turn_error_content,
                    ))

                # ── Analytics — same call shape as chat.py / whatsapp.py ──
                await analytics_service.record_turn(
                    session_id=session_id, workflow_id=workflow_id, owner_id=account.user_id,
                    user_message=user_message, bot_response=None if turn_error else run_result.get("response"),
                    node_type=run_result.get("node_type"), provider=run_result.get("provider"),
                    latency_ms=latency_ms, is_error=turn_error, error_message=turn_error_content,
                    citations=run_result.get("citations", []), source="instagram",
                    visitor_key=analytics_service.hash_visitor(igsid, "instagram"),
                    ended=bool(context.completed),
                )

                try:
                    await db.commit()
                except IntegrityError:
                    # Race: the same mid was processed by a concurrent
                    # redelivery between our existence check and this
                    # commit — the unique constraint on (account_id, mid)
                    # is the actual duplicate-processing guarantee; the
                    # pre-check above is just the fast path that avoids
                    # re-running the Workflow Runtime in the common case.
                    await db.rollback()
                    logger.info(f"Instagram webhook: duplicate mid={mid} caught at commit for account={account.id}")

            account.last_webhook_at = datetime.now(timezone.utc)
            account.last_sync_at = datetime.now(timezone.utc)
            account.health_status = "degraded" if any_failed else "healthy"
            if not any_failed:
                account.last_error = None
            await db.commit()

    return {"status": "ok"}
