"""
ThunderBots Personal Email AI Assistant API (NEW — Part 1)

This is a completely separate module from api/v1/whatsapp.py /
api/v1/instagram.py (customer-support channels driving a workflow bot) and
from the existing Email & Notification Service (services/email_service.py,
transactional platform emails). It gives an authenticated user AI tools
over their OWN personal Gmail inbox. Nothing here sends email — there is
no send endpoint in Part 1.

Three route groups, mirroring api/v1/instagram.py's shape:

1. OAuth — GET .../oauth/authorize is authenticated and returns the Google
   consent-screen URL; GET .../oauth/callback is PUBLIC (Google redirects
   the browser here with no Authorization header) and is instead protected
   by a signed, short-lived state JWT minted by the authorize step.

2. Account management (authenticated, owner-scoped) — list/connect-status,
   disconnect, sync, enable/disable digest.

3. Messages / drafts / digest (authenticated, owner-scoped) — list by
   folder, get one, star/unstar, re-analyze, generate/edit/regenerate/
   translate reply drafts, generate/list digests, search.

`provider` is accepted on the OAuth-authorize route (default "gmail") so
the same route shape already supports a future `provider=outlook` without
a breaking change — see services/gmail_service.py module docstring for the
rest of the future-Outlook design.

Part 2 additions (NEW — additive only, no Part 1 route changed): four more
route groups — Send/Schedule (one-click Send, Schedule Send, cancel,
approve/reject), Bulk Reply, Auto-reply rules (CRUD + toggle), and
Automation/Analytics (unanswered list, follow-up suggestions, analytics,
attachment download, thread/conversation history, manual re-categorize).
Every Part 2 route reuses the same `_get_owned_account`/`_get_owned_message`
ownership checks as Part 1.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.database import get_db, AsyncSessionLocal
from app.core.auth import get_current_user
from app.models.user import User
from app.models.personal_email import (
    PersonalEmailAccount, PersonalEmailMessage, PersonalEmailDraft, PersonalEmailDigest,
    PersonalEmailAutoReplyRule, PersonalEmailAiFollowUp,
)
from app.config import settings
from app.services import gmail_service as gmail
from app.services import personal_email_sync_service as sync_service
from app.services import personal_email_ai_service as ai
from app.services import personal_email_send_service as send_service
from app.services import personal_email_automation_service as automation
from fastapi import Response

router = APIRouter()
logger = logging.getLogger(__name__)

_OAUTH_STATE_TOKEN_TYPE = "personal_email_oauth_state"
_OAUTH_STATE_EXPIRE_MINUTES = 10
_ANALYZED_FOLDERS = ("inbox",)  # AI classification is meaningful for inbound mail; sent/drafts are skipped by default


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_oauth_state(user_id: str, provider: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES)
    return jwt.encode(
        {"uid": user_id, "provider": provider, "exp": expire, "type": _OAUTH_STATE_TOKEN_TYPE},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )


def _read_oauth_state(state: str) -> tuple[str, str]:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=400, detail=f"Invalid or expired OAuth state: {e}")
    if payload.get("type") != _OAUTH_STATE_TOKEN_TYPE:
        raise HTTPException(status_code=400, detail="Invalid OAuth state token")
    return payload["uid"], payload.get("provider", "gmail")


async def _get_owned_account(account_id: str, db: AsyncSession, current_user: User) -> PersonalEmailAccount:
    result = await db.execute(select(PersonalEmailAccount).where(PersonalEmailAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Email account not found")
    if str(account.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not own this email account")
    return account


async def _get_owned_message(message_id: str, db: AsyncSession, current_user: User) -> PersonalEmailMessage:
    result = await db.execute(select(PersonalEmailMessage).where(PersonalEmailMessage.id == message_id))
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Email not found")
    await _get_owned_account(message.account_id, db, current_user)  # raises 403/404 if not owned
    return message


async def _get_owned_draft(
    draft_id: str, db: AsyncSession, current_user: User,
) -> tuple[PersonalEmailDraft, PersonalEmailMessage, PersonalEmailAccount]:
    result = await db.execute(select(PersonalEmailDraft).where(PersonalEmailDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    message = await _get_owned_message(draft.message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    return draft, message, account


def _serialize_account(account: PersonalEmailAccount) -> dict:
    return {
        "id": account.id,
        "provider": account.provider,
        "email_address": account.email_address,
        "display_name": account.display_name,
        "status": account.status,
        "last_error": account.last_error,
        "sync_enabled": account.sync_enabled,
        "digest_enabled": account.digest_enabled,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
        "last_sync_status": account.last_sync_status,
        "last_digest_at": account.last_digest_at.isoformat() if account.last_digest_at else None,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def _serialize_message(message: PersonalEmailMessage, *, include_body: bool = False) -> dict:
    data = {
        "id": message.id,
        "account_id": message.account_id,
        "provider_thread_id": message.provider_thread_id,
        "folder": message.folder,
        "is_starred": message.is_starred,
        "is_read": message.is_read,
        "sender_name": message.sender_name,
        "sender_email": message.sender_email,
        "to_addresses": message.to_addresses,
        "subject": message.subject,
        "snippet": message.snippet,
        "received_at": message.received_at.isoformat() if message.received_at else None,
        "ai_summary": message.ai_summary,
        "ai_priority": message.ai_priority,
        "ai_sentiment": message.ai_sentiment,
        "ai_deadline": message.ai_deadline,
        "ai_tasks": message.ai_tasks or [],
        "ai_action_required": message.ai_action_required,
        "ai_analyzed_at": message.ai_analyzed_at.isoformat() if message.ai_analyzed_at else None,
        "ai_analysis_error": message.ai_analysis_error,
        "category": message.category,
        "labels": message.labels or [],
        "is_spam": message.is_spam,
        "spam_score": message.spam_score,
        "spam_reason": message.spam_reason,
        "is_answered": message.is_answered,
        "answered_at": message.answered_at.isoformat() if message.answered_at else None,
        "has_attachments": message.has_attachments,
        "attachments": message.attachments or [],
    }
    if include_body:
        data["body_text"] = message.body_text
        data["body_html"] = message.body_html
    return data


def _serialize_draft(draft: PersonalEmailDraft) -> dict:
    return {
        "id": draft.id,
        "message_id": draft.message_id,
        "style": draft.style,
        "content": draft.content,
        "is_edited": draft.is_edited,
        "language": draft.language,
        "send_status": draft.send_status,
        "approval_status": draft.approval_status,
        "scheduled_at": draft.scheduled_at.isoformat() if draft.scheduled_at else None,
        "sent_at": draft.sent_at.isoformat() if draft.sent_at else None,
        "sent_provider_message_id": draft.sent_provider_message_id,
        "send_error": draft.send_error,
        "to_addresses": draft.to_addresses,
        "cc": draft.cc,
        "bcc": draft.bcc,
        "subject_override": draft.subject_override,
        "attachments": [
            {"filename": a.get("filename"), "mime_type": a.get("mime_type"), "size": a.get("size")}
            for a in (draft.attachments or [])
        ],
        "created_by_rule_id": draft.created_by_rule_id,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def _serialize_rule(rule: PersonalEmailAutoReplyRule) -> dict:
    return {
        "id": rule.id,
        "account_id": rule.account_id,
        "name": rule.name,
        "is_active": rule.is_active,
        "sender_contains": rule.sender_contains,
        "subject_contains": rule.subject_contains,
        "category": rule.category,
        "priority": rule.priority,
        "style": rule.style,
        "instructions": rule.instructions,
        "require_approval": rule.require_approval,
        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "trigger_count": rule.trigger_count,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _serialize_followup(row: PersonalEmailAiFollowUp) -> dict:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "suggested_content": row.suggested_content,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_digest(digest: PersonalEmailDigest) -> dict:
    return {
        "id": digest.id,
        "account_id": digest.account_id,
        "digest_date": digest.digest_date,
        "summary": digest.summary,
        "total_emails": digest.total_emails,
        "action_required_count": digest.action_required_count,
        "high_priority_count": digest.high_priority_count,
        "highlights": digest.highlights or [],
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# OAuth
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/oauth/authorize")
async def oauth_authorize(provider: str = Query("gmail"), current_user: User = Depends(get_current_user)):
    """Returns the Google consent-screen URL. The frontend redirects the
    full browser window to this URL (Google's OAuth dialog cannot be
    embedded via fetch/XHR)."""
    if provider != "gmail":
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' is not supported yet. Gmail is available today.")
    if not gmail.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Personal Gmail integration is not configured on this server (missing Google OAuth credentials).",
        )
    state = _build_oauth_state(str(current_user.id), provider)
    return {"authorize_url": gmail.build_authorize_url(state)}


@router.get("/oauth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None), state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Public — Google redirects the user's browser here after consent.
    Always ends in a redirect back to the frontend's Personal Email page."""
    frontend_url = f"{settings.APP_BASE_URL}/personal-email"
    if not state:
        return RedirectResponse(f"{frontend_url}?pe_error=missing_state")

    user_id, provider = _read_oauth_state(state)

    if error:
        return RedirectResponse(f"{frontend_url}?pe_error={error}")
    if not code:
        return RedirectResponse(f"{frontend_url}?pe_error=missing_code")

    async with AsyncSessionLocal() as db:
        try:
            token_data = await gmail.exchange_code_for_tokens(code)
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            identity = await gmail.get_user_email(access_token)
            email_address = identity.get("email")
            if not email_address:
                return RedirectResponse(f"{frontend_url}?pe_error=missing_email_scope")

            result = await db.execute(
                select(PersonalEmailAccount).where(
                    PersonalEmailAccount.user_id == user_id,
                    PersonalEmailAccount.provider == provider,
                    PersonalEmailAccount.email_address == email_address,
                )
            )
            account = result.scalar_one_or_none()

            if account:
                account.encrypted_access_token = gmail.encrypt_credential(access_token)
                if refresh_token:
                    account.encrypted_refresh_token = gmail.encrypt_credential(refresh_token)
                account.token_expires_at = gmail.token_expiry_from_expires_in(token_data.get("expires_in"))
                account.scopes = token_data.get("scope")
                account.status = "connected"
                account.last_error = None
            else:
                if not refresh_token:
                    # First-time connect with no refresh_token returned is
                    # unusual (access_type=offline + prompt=consent should
                    # always grant one) — surface it clearly rather than
                    # silently creating an account that can't be refreshed.
                    logger.warning(f"Gmail OAuth connect for user={user_id} returned no refresh_token")
                account = PersonalEmailAccount(
                    user_id=user_id, provider=provider, email_address=email_address,
                    display_name=identity.get("name"),
                    encrypted_access_token=gmail.encrypt_credential(access_token),
                    encrypted_refresh_token=gmail.encrypt_credential(refresh_token) if refresh_token else None,
                    token_expires_at=gmail.token_expiry_from_expires_in(token_data.get("expires_in")),
                    scopes=token_data.get("scope"),
                    status="connected",
                )
                db.add(account)

            await db.commit()
            return RedirectResponse(f"{frontend_url}?pe_connected=1")
        except gmail.GmailAPIError as e:
            logger.warning(f"Personal email OAuth callback failed: {e}")
            return RedirectResponse(f"{frontend_url}?pe_error=oauth_exchange_failed")
        except Exception as e:  # noqa: BLE001 — never strand the browser mid-redirect
            logger.error(f"Personal email OAuth callback error: {e}", exc_info=True)
            return RedirectResponse(f"{frontend_url}?pe_error=unexpected")


# ─────────────────────────────────────────────────────────────────────────────
# Account management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(PersonalEmailAccount).where(PersonalEmailAccount.user_id == current_user.id)
        .order_by(desc(PersonalEmailAccount.created_at))
    )
    accounts = result.scalars().all()
    return {"accounts": [_serialize_account(a) for a in accounts], "configured": gmail.is_configured()}


@router.post("/accounts/{account_id}/sync")
async def sync_account(
    account_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    if not account.sync_enabled:
        raise HTTPException(status_code=400, detail="Sync is disabled for this account")
    try:
        summary = await sync_service.sync_account(db, account)
    except sync_service.PersonalEmailSyncError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return summary


@router.post("/accounts/{account_id}/disconnect")
async def disconnect_account(
    account_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Securely disconnects the account: clears the encrypted tokens and
    marks it disconnected, but keeps already-synced messages/drafts/
    digests around (consistent with how other channels handle disconnect)
    so the user doesn't lose their AI-analyzed history. Delete via the
    account's own settings if full removal is desired."""
    account = await _get_owned_account(account_id, db, current_user)
    account.encrypted_access_token = ""
    account.encrypted_refresh_token = None
    account.token_expires_at = None
    account.status = "disconnected"
    account.sync_enabled = False
    await db.commit()
    return {"disconnected": True}


class ToggleRequest(BaseModel):
    enabled: bool


@router.post("/accounts/{account_id}/digest-toggle")
async def toggle_digest(
    account_id: str, payload: ToggleRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    account.digest_enabled = payload.enabled
    await db.commit()
    return {"digest_enabled": account.digest_enabled}


# ─────────────────────────────────────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/accounts/{account_id}/messages")
async def list_messages(
    account_id: str, folder: str = Query("inbox"), search: Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)

    query = select(PersonalEmailMessage).where(PersonalEmailMessage.account_id == account.id)
    if folder == "starred":
        query = query.where(PersonalEmailMessage.is_starred == True)  # noqa: E712
    elif folder in ("inbox", "sent", "drafts"):
        query = query.where(PersonalEmailMessage.folder == folder)
    else:
        raise HTTPException(status_code=400, detail="folder must be one of inbox, sent, drafts, starred")

    if search:
        like = f"%{search}%"
        query = query.where(
            or_(
                PersonalEmailMessage.subject.ilike(like),
                PersonalEmailMessage.snippet.ilike(like),
                PersonalEmailMessage.sender_name.ilike(like),
                PersonalEmailMessage.sender_email.ilike(like),
                PersonalEmailMessage.body_text.ilike(like),
            )
        )

    query = query.order_by(desc(PersonalEmailMessage.received_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    messages = result.scalars().all()
    return {"messages": [_serialize_message(m) for m in messages], "page": page, "page_size": page_size}


@router.get("/messages/{message_id}")
async def get_message_detail(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    message = await _get_owned_message(message_id, db, current_user)
    result = await db.execute(
        select(PersonalEmailDraft).where(PersonalEmailDraft.message_id == message.id)
        .order_by(desc(PersonalEmailDraft.created_at))
    )
    drafts = result.scalars().all()
    data = _serialize_message(message, include_body=True)
    data["drafts"] = [_serialize_draft(d) for d in drafts]
    return data


@router.post("/messages/{message_id}/star")
async def star_message(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    message = await _get_owned_message(message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    try:
        await sync_service.set_starred(db, account, message, True)
    except sync_service.PersonalEmailSyncError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"is_starred": True}


@router.post("/messages/{message_id}/unstar")
async def unstar_message(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    message = await _get_owned_message(message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    try:
        await sync_service.set_starred(db, account, message, False)
    except sync_service.PersonalEmailSyncError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"is_starred": False}


@router.post("/messages/{message_id}/analyze")
async def analyze_message(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    message = await _get_owned_message(message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    try:
        await sync_service.analyze_message(db, account, message)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {e}") from e
    return _serialize_message(message, include_body=True)


# ─────────────────────────────────────────────────────────────────────────────
# Drafts
# ─────────────────────────────────────────────────────────────────────────────

class GenerateDraftsRequest(BaseModel):
    styles: list[str] = ["professional", "friendly", "short"]
    instructions: Optional[str] = None


@router.post("/messages/{message_id}/drafts/generate")
async def generate_drafts(
    message_id: str, payload: GenerateDraftsRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    message = await _get_owned_message(message_id, db, current_user)
    styles = [s for s in payload.styles if s in ai.VALID_STYLES] or ["professional"]

    created = []
    for style in styles:
        try:
            content = await ai.generate_reply_draft(
                str(current_user.id), subject=message.subject or "", sender=message.sender_email or "",
                body=message.body_text or message.snippet or "", style=style, instructions=payload.instructions,
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Draft generation failed: {e}") from e
        draft = PersonalEmailDraft(message_id=message.id, style=style, content=content)
        db.add(draft)
        created.append(draft)

    await db.commit()
    for d in created:
        await db.refresh(d)
    return {"drafts": [_serialize_draft(d) for d in created]}


class EditDraftRequest(BaseModel):
    content: str


@router.patch("/drafts/{draft_id}")
async def edit_draft(
    draft_id: str, payload: EditDraftRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(PersonalEmailDraft).where(PersonalEmailDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _get_owned_message(draft.message_id, db, current_user)
    draft.content = payload.content
    draft.is_edited = True
    await db.commit()
    return _serialize_draft(draft)


class RegenerateDraftRequest(BaseModel):
    instructions: Optional[str] = None


@router.post("/drafts/{draft_id}/regenerate")
async def regenerate_draft(
    draft_id: str, payload: RegenerateDraftRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(PersonalEmailDraft).where(PersonalEmailDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    message = await _get_owned_message(draft.message_id, db, current_user)
    try:
        content = await ai.generate_reply_draft(
            str(current_user.id), subject=message.subject or "", sender=message.sender_email or "",
            body=message.body_text or message.snippet or "", style=draft.style,
            instructions=payload.instructions, previous_draft=draft.content,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Draft regeneration failed: {e}") from e
    draft.content = content
    draft.is_edited = False
    await db.commit()
    return _serialize_draft(draft)


class TranslateDraftRequest(BaseModel):
    target_language: str


@router.post("/drafts/{draft_id}/translate")
async def translate_draft(
    draft_id: str, payload: TranslateDraftRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(PersonalEmailDraft).where(PersonalEmailDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await _get_owned_message(draft.message_id, db, current_user)
    try:
        translated = await ai.translate_text(str(current_user.id), text=draft.content, target_language=payload.target_language)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Translation failed: {e}") from e
    draft.content = translated
    draft.language = payload.target_language[:10]
    draft.is_edited = True
    await db.commit()
    return _serialize_draft(draft)


# ─────────────────────────────────────────────────────────────────────────────
# Digest
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/digest/generate")
async def generate_digest_now(
    account_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    try:
        digest = await sync_service.generate_digest(db, account)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Digest generation failed: {e}") from e
    return _serialize_digest(digest)


@router.get("/accounts/{account_id}/digest/latest")
async def get_latest_digest(
    account_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    result = await db.execute(
        select(PersonalEmailDigest).where(PersonalEmailDigest.account_id == account.id)
        .order_by(desc(PersonalEmailDigest.digest_date)).limit(1)
    )
    digest = result.scalar_one_or_none()
    if not digest:
        return {"digest": None}
    return {"digest": _serialize_digest(digest)}


@router.get("/accounts/{account_id}/digest/history")
async def digest_history(
    account_id: str, limit: int = Query(14, ge=1, le=90),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    result = await db.execute(
        select(PersonalEmailDigest).where(PersonalEmailDigest.account_id == account.id)
        .order_by(desc(PersonalEmailDigest.digest_date)).limit(limit)
    )
    digests = result.scalars().all()
    return {"digests": [_serialize_digest(d) for d in digests]}


# ═════════════════════════════════════════════════════════════════════════
# Part 2 — Send, Schedule Send, Bulk Reply, Approval workflow (NEW)
# ═════════════════════════════════════════════════════════════════════════

class AttachmentIn(BaseModel):
    filename: str
    mime_type: str = "application/octet-stream"
    content_base64: str


class EditRecipientsRequest(BaseModel):
    to_addresses: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
    subject_override: Optional[str] = None


@router.patch("/drafts/{draft_id}/recipients")
async def edit_draft_recipients(
    draft_id: str, payload: EditRecipientsRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Override To/Cc/Bcc/Subject before sending — the reply otherwise
    defaults to the original sender and "Re: <subject>" at send time."""
    draft, _message, _account = await _get_owned_draft(draft_id, db, current_user)
    if payload.to_addresses is not None:
        draft.to_addresses = payload.to_addresses
    if payload.cc is not None:
        draft.cc = payload.cc
    if payload.bcc is not None:
        draft.bcc = payload.bcc
    if payload.subject_override is not None:
        draft.subject_override = payload.subject_override
    await db.commit()
    return _serialize_draft(draft)


class SetAttachmentsRequest(BaseModel):
    attachments: list[AttachmentIn] = []


@router.put("/drafts/{draft_id}/attachments")
async def set_draft_attachments(
    draft_id: str, payload: SetAttachmentsRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Replaces this draft's outgoing attachment list ("Support
    attachments"). Size is validated against
    settings.PERSONAL_EMAIL_MAX_ATTACHMENT_MB at send time."""
    draft, _message, _account = await _get_owned_draft(draft_id, db, current_user)
    attachments = [a.model_dump() for a in payload.attachments]
    try:
        send_service._validate_attachments(attachments)
    except send_service.PersonalEmailSendError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    for a in attachments:
        a["size"] = len(a.get("content_base64", "")) * 3 // 4
    draft.attachments = attachments
    await db.commit()
    return _serialize_draft(draft)


@router.post("/drafts/{draft_id}/send")
async def send_draft_now(
    draft_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """One-click Send."""
    draft, message, account = await _get_owned_draft(draft_id, db, current_user)
    try:
        await send_service.send_draft(db, account, message, draft)
    except send_service.PersonalEmailSendError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _serialize_draft(draft)


class ScheduleDraftRequest(BaseModel):
    scheduled_at: datetime


@router.post("/drafts/{draft_id}/schedule")
async def schedule_draft_send(
    draft_id: str, payload: ScheduleDraftRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Schedule Send — sent automatically once due by the background
    scheduler (services/personal_email_send_service.run_scheduled_send_loop)."""
    draft, _message, account = await _get_owned_draft(draft_id, db, current_user)
    scheduled_at = payload.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    try:
        await send_service.schedule_draft(db, account, draft, scheduled_at)
    except send_service.PersonalEmailSendError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _serialize_draft(draft)


@router.post("/drafts/{draft_id}/cancel-schedule")
async def cancel_draft_schedule(
    draft_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    draft, _message, _account = await _get_owned_draft(draft_id, db, current_user)
    try:
        await send_service.cancel_scheduled_send(db, draft)
    except send_service.PersonalEmailSendError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _serialize_draft(draft)


@router.post("/drafts/{draft_id}/approve")
async def approve_draft_route(
    draft_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Reply approval workflow — approves a draft created by an auto-reply
    rule with require_approval=True so it becomes sendable/schedulable."""
    draft, _message, _account = await _get_owned_draft(draft_id, db, current_user)
    await send_service.approve_draft(db, draft)
    return _serialize_draft(draft)


@router.post("/drafts/{draft_id}/reject")
async def reject_draft_route(
    draft_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    draft, _message, _account = await _get_owned_draft(draft_id, db, current_user)
    await send_service.reject_draft(db, draft)
    return _serialize_draft(draft)


class BulkReplyRequest(BaseModel):
    message_ids: list[str]
    style: str = "professional"
    instructions: Optional[str] = None
    auto_send: bool = False


@router.post("/accounts/{account_id}/messages/bulk-reply")
async def bulk_reply_messages(
    account_id: str, payload: BulkReplyRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    if not payload.message_ids:
        raise HTTPException(status_code=400, detail="message_ids must not be empty")
    if len(payload.message_ids) > 50:
        raise HTTPException(status_code=400, detail="Bulk Reply is limited to 50 messages at a time")

    result = await db.execute(
        select(PersonalEmailMessage).where(
            PersonalEmailMessage.id.in_(payload.message_ids),
            PersonalEmailMessage.account_id == account.id,
        )
    )
    messages = result.scalars().all()
    style = payload.style if payload.style in ai.VALID_STYLES else "professional"

    outcome = await send_service.bulk_reply(
        db, account, messages, style=style, instructions=payload.instructions, auto_send=payload.auto_send,
    )
    return {
        "drafts": [_serialize_draft(d) for d in outcome["drafts"]],
        "sent_count": outcome["sent_count"],
        "errors": outcome["errors"],
    }


# ═════════════════════════════════════════════════════════════════════════
# Part 2 — Unanswered reminders, follow-up suggestions, analytics,
# conversation history, attachment download, manual re-categorize (NEW)
# ═════════════════════════════════════════════════════════════════════════

@router.get("/accounts/{account_id}/messages/unanswered")
async def unanswered_messages(
    account_id: str, hours: Optional[int] = Query(None, ge=0, le=24 * 30),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """AI reminder for unanswered emails — action-required inbox messages
    with no reply yet, older than the configured threshold."""
    account = await _get_owned_account(account_id, db, current_user)
    messages = await automation.list_unanswered(db, account, hours=hours)
    return {"messages": [_serialize_message(m) for m in messages]}


@router.post("/messages/{message_id}/follow-up")
async def generate_follow_up(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """AI follow-up suggestion for a sent message that looks unanswered."""
    message = await _get_owned_message(message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    if message.folder != "sent":
        raise HTTPException(status_code=400, detail="Follow-up suggestions only apply to sent messages")
    try:
        followup = await automation.generate_follow_up_suggestion(db, account, message)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Follow-up generation failed: {e}") from e
    return _serialize_followup(followup)


@router.get("/accounts/{account_id}/analytics")
async def get_analytics(
    account_id: str, days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Email analytics — volume, response time, category/priority/
    sentiment breakdown, spam caught, AI replies sent."""
    account = await _get_owned_account(account_id, db, current_user)
    return await automation.compute_analytics(db, account, days=days)


@router.get("/messages/{message_id}/thread")
async def get_thread_history(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Conversation history — every locally-synced message on the same
    provider thread, oldest first."""
    message = await _get_owned_message(message_id, db, current_user)
    if not message.provider_thread_id:
        return {"thread": [_serialize_message(message)]}
    result = await db.execute(
        select(PersonalEmailMessage).where(
            PersonalEmailMessage.account_id == message.account_id,
            PersonalEmailMessage.provider_thread_id == message.provider_thread_id,
        ).order_by(PersonalEmailMessage.received_at.asc())
    )
    thread = result.scalars().all()
    return {"thread": [_serialize_message(m) for m in thread]}


@router.get("/messages/{message_id}/attachments/{attachment_id}/download")
async def download_attachment(
    message_id: str, attachment_id: str,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    message = await _get_owned_message(message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    meta = next((a for a in (message.attachments or []) if a.get("attachment_id") == attachment_id), None)
    if not meta:
        raise HTTPException(status_code=404, detail="Attachment not found on this message")
    try:
        access_token = await sync_service.ensure_valid_access_token(db, account)
        raw_bytes = await gmail.get_attachment(access_token, message.provider_message_id, attachment_id)
    except (gmail.GmailAPIError, sync_service.PersonalEmailSyncError) as e:
        raise HTTPException(status_code=502, detail=f"Could not download attachment: {e}") from e
    filename = meta.get("filename") or "attachment"
    return Response(
        content=raw_bytes,
        media_type=meta.get("mime_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/messages/{message_id}/categorize")
async def categorize_message(
    message_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Manually re-run auto-categorize / smart labels / spam screening for
    one message (e.g. after the user disagrees with the current label)."""
    message = await _get_owned_message(message_id, db, current_user)
    account = await _get_owned_account(message.account_id, db, current_user)
    try:
        classification = await ai.classify_email(
            account.user_id, subject=message.subject or "", sender=message.sender_email or "",
            body=message.body_text or message.snippet or "",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Categorization failed: {e}") from e
    message.category = classification["category"]
    message.labels = classification["labels"]
    message.is_spam = classification["is_spam"]
    message.spam_score = classification["spam_score"]
    message.spam_reason = classification["spam_reason"]
    await db.commit()
    return _serialize_message(message, include_body=True)


class EditLabelsRequest(BaseModel):
    labels: list[str]


@router.patch("/messages/{message_id}/labels")
async def edit_labels(
    message_id: str, payload: EditLabelsRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Smart labels are AI-suggested but always user-editable."""
    message = await _get_owned_message(message_id, db, current_user)
    message.labels = [str(l).strip().lower() for l in payload.labels if str(l).strip()][:10]
    await db.commit()
    return {"labels": message.labels}


# ═════════════════════════════════════════════════════════════════════════
# Part 2 — Optional auto-reply rules (NEW)
# ═════════════════════════════════════════════════════════════════════════

class AutoReplyRuleIn(BaseModel):
    name: str
    sender_contains: Optional[str] = None
    subject_contains: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    style: str = "professional"
    instructions: Optional[str] = None
    require_approval: bool = True


@router.get("/accounts/{account_id}/auto-reply-rules")
async def list_auto_reply_rules(
    account_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    result = await db.execute(
        select(PersonalEmailAutoReplyRule).where(PersonalEmailAutoReplyRule.account_id == account.id)
        .order_by(PersonalEmailAutoReplyRule.created_at)
    )
    rules = result.scalars().all()
    return {"rules": [_serialize_rule(r) for r in rules]}


@router.post("/accounts/{account_id}/auto-reply-rules")
async def create_auto_reply_rule(
    account_id: str, payload: AutoReplyRuleIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    account = await _get_owned_account(account_id, db, current_user)
    style = payload.style if payload.style in ai.VALID_STYLES else "professional"
    rule = PersonalEmailAutoReplyRule(
        account_id=account.id, name=payload.name, sender_contains=payload.sender_contains,
        subject_contains=payload.subject_contains, category=payload.category, priority=payload.priority,
        style=style, instructions=payload.instructions, require_approval=payload.require_approval,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _serialize_rule(rule)


async def _get_owned_rule(rule_id: str, db: AsyncSession, current_user: User) -> PersonalEmailAutoReplyRule:
    result = await db.execute(select(PersonalEmailAutoReplyRule).where(PersonalEmailAutoReplyRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Auto-reply rule not found")
    await _get_owned_account(rule.account_id, db, current_user)
    return rule


@router.patch("/auto-reply-rules/{rule_id}")
async def update_auto_reply_rule(
    rule_id: str, payload: AutoReplyRuleIn,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_rule(rule_id, db, current_user)
    rule.name = payload.name
    rule.sender_contains = payload.sender_contains
    rule.subject_contains = payload.subject_contains
    rule.category = payload.category
    rule.priority = payload.priority
    rule.style = payload.style if payload.style in ai.VALID_STYLES else "professional"
    rule.instructions = payload.instructions
    rule.require_approval = payload.require_approval
    await db.commit()
    return _serialize_rule(rule)


@router.post("/auto-reply-rules/{rule_id}/toggle")
async def toggle_auto_reply_rule(
    rule_id: str, payload: ToggleRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_rule(rule_id, db, current_user)
    rule.is_active = payload.enabled
    await db.commit()
    return {"is_active": rule.is_active}


@router.delete("/auto-reply-rules/{rule_id}")
async def delete_auto_reply_rule(
    rule_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_rule(rule_id, db, current_user)
    await db.delete(rule)
    await db.commit()
    return {"deleted": True}
