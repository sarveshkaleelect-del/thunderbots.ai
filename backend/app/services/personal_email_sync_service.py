"""
ThunderBots Personal Email AI Assistant — Sync Orchestration (NEW — Part 1)

Provider-agnostic orchestration layer sitting between api/v1/personal_email.py
and the provider-specific client (services/gmail_service.py today; a future
services/outlook_service.py would plug in here via `_client_for(account)`
without changing any function below). Handles: valid-access-token
resolution (refreshing via the provider when expired), syncing a folder's
messages into PersonalEmailMessage rows, running AI analysis on newly
synced/unanalyzed messages, and generating the Daily AI Email Digest.

Also exposes `run_daily_digest_loop()`, a background task with the exact
shape of services/campaign_dispatch_service.run_scheduler_loop and
services/instagram_service.run_token_refresh_loop (polls periodically,
never raises out of its own loop) — wired into app/main.py's lifespan the
same additive way those two already are.

Part 2 additions (NEW — additive only): `_upsert_message` now also
persists attachment metadata and runs `ai.classify_email` (category/smart
labels/spam) alongside the existing `ai.analyze_email` call inside
`analyze_message`; `sync_account` now also marks the original inbox
message "answered" once a matching `sent` message on the same thread is
seen (drives the unanswered-email AI reminder in
services/personal_email_automation_service.py). Sending, scheduling, bulk
reply, auto-reply rules, follow-ups, and analytics all live in the new
services/personal_email_send_service.py and
services/personal_email_automation_service.py so this file's Part 1
responsibilities (token refresh, sync, digest) stay unchanged in shape.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.personal_email import (
    PersonalEmailAccount, PersonalEmailMessage, PersonalEmailDigest,
)
from app.services import gmail_service as gmail
from app.services import personal_email_ai_service as ai

logger = logging.getLogger(__name__)

SYNC_FOLDERS = ("inbox", "sent", "drafts")


class PersonalEmailSyncError(RuntimeError):
    pass


async def ensure_valid_access_token(db: AsyncSession, account: PersonalEmailAccount) -> str:
    """Returns a usable access token for `account`, refreshing it first if
    it's expired (or about to be) and a refresh token is on file. Persists
    the refreshed token. Raises PersonalEmailSyncError if the account needs
    to be reconnected (no refresh token, or refresh itself fails)."""
    now = datetime.now(timezone.utc)
    needs_refresh = account.token_expires_at is not None and account.token_expires_at <= now

    if not needs_refresh:
        return gmail.decrypt_credential(account.encrypted_access_token)

    if not account.encrypted_refresh_token:
        account.status = "expired"
        account.last_error = "Access token expired and no refresh token is on file — please reconnect."
        await db.commit()
        raise PersonalEmailSyncError(account.last_error)

    try:
        refresh_token = gmail.decrypt_credential(account.encrypted_refresh_token)
        token_data = await gmail.refresh_access_token(refresh_token)
        account.encrypted_access_token = gmail.encrypt_credential(token_data["access_token"])
        account.token_expires_at = gmail.token_expiry_from_expires_in(token_data.get("expires_in"))
        account.status = "connected"
        account.last_error = None
        await db.commit()
        return token_data["access_token"]
    except gmail.GmailAPIError as e:
        account.status = "expired" if e.error_type == "expired_token" else "error"
        account.last_error = str(e)
        await db.commit()
        raise PersonalEmailSyncError(f"Failed to refresh Gmail access token: {e}") from e


async def _upsert_message(
    db: AsyncSession, account: PersonalEmailAccount, folder: str, parsed: "gmail.EmailMessage",
) -> tuple[PersonalEmailMessage, bool]:
    result = await db.execute(
        select(PersonalEmailMessage).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.provider_message_id == parsed.provider_message_id,
        )
    )
    row = result.scalar_one_or_none()
    is_new = row is None
    if row is None:
        row = PersonalEmailMessage(account_id=account.id, provider_message_id=parsed.provider_message_id, folder=folder)
        db.add(row)

    row.provider_thread_id = parsed.provider_thread_id
    row.sender_name = parsed.sender_name
    row.sender_email = parsed.sender_email
    row.to_addresses = parsed.to_addresses
    row.subject = parsed.subject
    row.snippet = parsed.snippet
    row.body_text = parsed.body_text
    row.body_html = parsed.body_html
    row.received_at = parsed.received_at
    row.is_starred = parsed.is_starred
    row.is_read = parsed.is_read
    # folder is the folder we actually synced it under (inbox/sent/drafts);
    # starred is layered on top via is_starred and never overwrites folder.
    row.folder = folder
    # ── Part 2: attachment metadata ────────────────────────────────────────
    attachments = getattr(parsed, "attachments", None) or []
    row.attachments = attachments
    row.has_attachments = bool(attachments)
    return row, is_new


async def sync_account(
    db: AsyncSession, account: PersonalEmailAccount, *, folders: Optional[list] = None,
    max_per_folder: int = 25, analyze_new: bool = True,
) -> dict:
    """Fetches recent messages for each requested folder, upserts them, and
    (by default) runs AI analysis on newly-synced messages that don't have
    one yet. Returns a small summary dict for the API response."""
    folders = folders or list(SYNC_FOLDERS)
    access_token = await ensure_valid_access_token(db, account)

    synced = 0
    new_messages: list[PersonalEmailMessage] = []
    errors: list[str] = []

    for folder in folders:
        try:
            listing = await gmail.list_message_ids(access_token, folder=folder, max_results=max_per_folder)
            for message_id in listing["ids"]:
                try:
                    parsed = await gmail.get_message(access_token, message_id)
                except gmail.GmailAPIError as e:
                    errors.append(f"{folder}/{message_id}: {e}")
                    continue
                row, is_new = await _upsert_message(db, account, folder, parsed)
                synced += 1
                if is_new:
                    new_messages.append(row)
        except gmail.GmailAPIError as e:
            errors.append(f"{folder}: {e}")

    # ── Part 2: mark answered (both directions) ────────────────────────────
    # A new `sent` message answers any inbox message on the same thread
    # ("unanswered" reminder clears); a new `inbox` message answers any
    # `sent` message on the same thread (AI follow-up suggestions stop).
    now = datetime.now(timezone.utc)
    sent_thread_ids = {r.provider_thread_id for r in new_messages if r.folder == "sent" and r.provider_thread_id}
    inbox_thread_ids = {r.provider_thread_id for r in new_messages if r.folder == "inbox" and r.provider_thread_id}
    if sent_thread_ids:
        result = await db.execute(
            select(PersonalEmailMessage).where(
                PersonalEmailMessage.account_id == account.id,
                PersonalEmailMessage.folder == "inbox",
                PersonalEmailMessage.provider_thread_id.in_(sent_thread_ids),
                PersonalEmailMessage.is_answered == False,  # noqa: E712
            )
        )
        for row in result.scalars().all():
            row.is_answered, row.answered_at = True, now
    if inbox_thread_ids:
        result = await db.execute(
            select(PersonalEmailMessage).where(
                PersonalEmailMessage.account_id == account.id,
                PersonalEmailMessage.folder == "sent",
                PersonalEmailMessage.provider_thread_id.in_(inbox_thread_ids),
                PersonalEmailMessage.is_answered == False,  # noqa: E712
            )
        )
        for row in result.scalars().all():
            row.is_answered, row.answered_at = True, now

    account.last_sync_at = datetime.now(timezone.utc)
    account.last_sync_status = "ok" if not errors else "error"
    if errors:
        account.last_error = "; ".join(errors[:5])
    await db.flush()

    analyzed = 0
    if analyze_new and new_messages:
        for row in new_messages:
            try:
                await analyze_message(db, account, row, commit=False)
                analyzed += 1
            except Exception as e:  # noqa: BLE001 — one bad analysis must not abort the sync
                row.ai_analysis_error = str(e)[:500]

    await db.commit()

    # ── Part 2: evaluate opt-in auto-reply rules for new inbox mail ───────
    # Deliberately after commit/analysis so rules can match on category/
    # priority/spam that analyze_message just populated. Import here (not
    # at module top) to avoid a circular import, since the automation
    # service itself calls back into this module's ensure_valid_access_token.
    if analyze_new and new_messages:
        from app.services import personal_email_automation_service as automation
        for row in new_messages:
            if row.folder == "inbox" and not row.is_spam:
                try:
                    await automation.evaluate_auto_reply_rules(db, account, row)
                except Exception as e:  # noqa: BLE001 — one rule failure must not abort the sync
                    logger.warning(f"[personal-email] auto-reply rule evaluation failed for message={row.id}: {e}")

    return {
        "synced": synced,
        "new_messages": len(new_messages),
        "analyzed": analyzed,
        "errors": errors,
    }


async def analyze_message(
    db: AsyncSession, account: PersonalEmailAccount, message: PersonalEmailMessage, *, commit: bool = True,
) -> PersonalEmailMessage:
    result = await ai.analyze_email(
        account.user_id,
        subject=message.subject or "(no subject)",
        sender=message.sender_email or message.sender_name or "unknown",
        body=message.body_text or message.snippet or "",
    )
    message.ai_summary = result["ai_summary"]
    message.ai_priority = result["ai_priority"]
    message.ai_sentiment = result["ai_sentiment"]
    message.ai_deadline = result["ai_deadline"]
    message.ai_tasks = result["ai_tasks"]
    message.ai_action_required = result["ai_action_required"]
    message.ai_analyzed_at = datetime.now(timezone.utc)
    message.ai_analysis_error = None

    # ── Part 2: auto-categorize / smart labels / spam & phishing screen ───
    try:
        classification = await ai.classify_email(
            account.user_id,
            subject=message.subject or "(no subject)",
            sender=message.sender_email or message.sender_name or "unknown",
            body=message.body_text or message.snippet or "",
        )
        message.category = classification["category"]
        message.labels = classification["labels"]
        message.is_spam = classification["is_spam"]
        message.spam_score = classification["spam_score"]
        message.spam_reason = classification["spam_reason"]
    except Exception as e:  # noqa: BLE001 — classification failure must not block core analysis
        logger.warning(f"[personal-email] classification failed for message={message.id}: {e}")

    if commit:
        await db.commit()
    return message


async def set_starred(db: AsyncSession, account: PersonalEmailAccount, message: PersonalEmailMessage, starred: bool) -> None:
    access_token = await ensure_valid_access_token(db, account)
    await gmail.modify_message_labels(
        access_token, message.provider_message_id,
        add=["STARRED"] if starred else [], remove=[] if starred else ["STARRED"],
    )
    message.is_starred = starred
    await db.commit()


async def generate_digest(db: AsyncSession, account: PersonalEmailAccount, *, for_date: Optional[str] = None) -> PersonalEmailDigest:
    digest_date = for_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    existing = await db.execute(
        select(PersonalEmailDigest).where(
            PersonalEmailDigest.account_id == account.id, PersonalEmailDigest.digest_date == digest_date,
        )
    )
    existing_row = existing.scalar_one_or_none()

    result = await db.execute(
        select(PersonalEmailMessage).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
        ).order_by(PersonalEmailMessage.received_at.desc()).limit(50)
    )
    messages = result.scalars().all()

    email_payload = [
        {
            "subject": m.subject, "sender": m.sender_email, "summary": m.ai_summary,
            "priority": m.ai_priority, "action_required": m.ai_action_required, "deadline": m.ai_deadline,
        }
        for m in messages
    ]
    summary_text = await ai.generate_digest_summary(account.user_id, emails=email_payload)

    highlights = [
        {"message_id": m.id, "subject": m.subject, "reason": m.ai_deadline or "High priority"}
        for m in messages if m.ai_priority in ("high", "urgent")
    ][:10]

    if existing_row:
        row = existing_row
    else:
        row = PersonalEmailDigest(account_id=account.id, digest_date=digest_date, summary="")
        db.add(row)

    row.summary = summary_text
    row.total_emails = len(messages)
    row.action_required_count = sum(1 for m in messages if m.ai_action_required)
    row.high_priority_count = sum(1 for m in messages if m.ai_priority in ("high", "urgent"))
    row.highlights = highlights

    account.last_digest_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Background loop — daily digest for every digest_enabled account, at most
# once per UTC calendar day. Mirrors campaign_dispatch_service's scheduler
# shape exactly; never raises out of the loop.
# ─────────────────────────────────────────────────────────────────────────────

async def run_daily_digest_loop() -> None:
    from app.core.database import AsyncSessionLocal

    interval = max(60, settings.PERSONAL_EMAIL_DIGEST_CHECK_INTERVAL_MINUTES * 60)
    while True:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PersonalEmailAccount).where(
                        PersonalEmailAccount.digest_enabled == True,  # noqa: E712
                        PersonalEmailAccount.status == "connected",
                        PersonalEmailAccount.sync_enabled == True,  # noqa: E712
                    )
                )
                accounts = result.scalars().all()
                for account in accounts:
                    already_today = account.last_digest_at and account.last_digest_at.strftime("%Y-%m-%d") == today
                    if already_today:
                        continue
                    try:
                        await sync_account(db, account, analyze_new=True)
                        await generate_digest(db, account, for_date=today)
                    except Exception as e:  # noqa: BLE001 — one account's failure must not stop the loop
                        logger.warning(f"[personal-email-digest] account={account.id} failed: {e}")
        except Exception as e:  # noqa: BLE001 — the loop itself must never die
            logger.error(f"[personal-email-digest] loop iteration failed: {e}", exc_info=True)
        await asyncio.sleep(interval)
