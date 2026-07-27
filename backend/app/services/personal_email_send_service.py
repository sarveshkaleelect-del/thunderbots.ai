"""
ThunderBots Personal Email AI Assistant — Send Orchestration (NEW — Part 2)

Everything that actually sends mail on behalf of the user funnels through
this module: one-click Send, Schedule Send, and Bulk Reply. All three
build on the SAME `_send_draft_now` primitive so there is exactly one
send code path to reason about. Nothing here modifies Part 1's read-only
sync (services/personal_email_sync_service.py) or the AI Engine — it
reuses `sync_service.ensure_valid_access_token` for token handling and
`personal_email_ai_service.generate_reply_draft` for draft generation,
same provider-agnostic pattern as the rest of this module.

Send requires the `gmail.send` OAuth scope, added in Part 2
(services/gmail_service.OAUTH_SCOPES). Accounts connected before Part 2
shipped won't have it until they reconnect — every send path below checks
`gmail.has_send_scope(account.scopes)` first and raises
PersonalEmailSendError (mapped to HTTP 409 "please reconnect") rather than
attempting a call that Google would reject anyway.

Also exposes `run_scheduled_send_loop()`, a background task with the same
never-raises polling shape as
services/personal_email_sync_service.run_daily_digest_loop and
services/campaign_dispatch_service.run_scheduler_loop.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.personal_email import PersonalEmailAccount, PersonalEmailMessage, PersonalEmailDraft
from app.services import gmail_service as gmail
from app.services import personal_email_sync_service as sync_service
from app.services import personal_email_ai_service as ai

logger = logging.getLogger(__name__)


class PersonalEmailSendError(RuntimeError):
    pass


def _validate_attachments(attachments: list) -> None:
    if not attachments:
        return
    max_bytes = settings.PERSONAL_EMAIL_MAX_ATTACHMENT_MB * 1024 * 1024
    total = 0
    for att in attachments:
        content = att.get("content_base64", "")
        total += len(content) * 3 // 4  # rough base64 -> bytes size
    if total > max_bytes:
        raise PersonalEmailSendError(
            f"Attachments exceed the {settings.PERSONAL_EMAIL_MAX_ATTACHMENT_MB}MB limit for this account."
        )


async def _send_draft_now(
    db: AsyncSession, account: PersonalEmailAccount, message: PersonalEmailMessage, draft: PersonalEmailDraft,
) -> PersonalEmailDraft:
    """The single primitive every send path (one-click, scheduled, bulk,
    auto-reply) goes through. Raises PersonalEmailSendError on any
    pre-flight failure (missing scope, missing recipient); on-the-wire
    Gmail failures are captured onto draft.send_error and re-raised as
    PersonalEmailSendError so callers can surface a 502."""
    if not gmail.has_send_scope(account.scopes):
        raise PersonalEmailSendError(
            "This account was connected before Send was available and needs to be reconnected "
            "to grant permission to send email on your behalf."
        )

    to_address = draft.to_addresses or message.sender_email
    if not to_address:
        raise PersonalEmailSendError("No recipient address could be determined for this reply.")

    _validate_attachments(draft.attachments or [])

    access_token = await sync_service.ensure_valid_access_token(db, account)
    subject = draft.subject_override or (f"Re: {message.subject}" if message.subject else "Re:")

    try:
        raw = gmail.build_mime_message(
            to=to_address, subject=subject, body_text=draft.content,
            from_name=account.display_name, cc=draft.cc, bcc=draft.bcc,
            in_reply_to=message.provider_message_id, thread_references=message.provider_message_id,
            attachments=draft.attachments or [],
        )
        result = await gmail.send_message(access_token, raw_message=raw, thread_id=message.provider_thread_id)
    except gmail.GmailAPIError as e:
        draft.send_status = "failed"
        draft.send_error = str(e)
        await db.commit()
        raise PersonalEmailSendError(f"Failed to send via Gmail: {e}") from e

    draft.send_status = "sent"
    draft.send_error = None
    draft.sent_at = datetime.now(timezone.utc)
    draft.sent_provider_message_id = result.get("id")
    message.is_answered = True
    message.answered_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(draft)
    return draft


async def send_draft(
    db: AsyncSession, account: PersonalEmailAccount, message: PersonalEmailMessage, draft: PersonalEmailDraft,
) -> PersonalEmailDraft:
    """One-click Send. Refuses if the draft is still awaiting approval."""
    if draft.approval_status == "pending":
        raise PersonalEmailSendError("This draft is awaiting approval and cannot be sent yet.")
    return await _send_draft_now(db, account, message, draft)


async def schedule_draft(
    db: AsyncSession, account: PersonalEmailAccount, draft: PersonalEmailDraft, scheduled_at: datetime,
) -> PersonalEmailDraft:
    """Schedule Send — validated but not sent now; the background loop
    (`run_scheduled_send_loop`) picks it up once `scheduled_at` arrives."""
    if draft.approval_status == "pending":
        raise PersonalEmailSendError("This draft is awaiting approval and cannot be scheduled yet.")
    if not gmail.has_send_scope(account.scopes):
        raise PersonalEmailSendError(
            "This account needs to be reconnected to grant permission to send email before scheduling."
        )
    if scheduled_at <= datetime.now(timezone.utc):
        raise PersonalEmailSendError("Scheduled time must be in the future.")
    draft.send_status = "scheduled"
    draft.scheduled_at = scheduled_at
    draft.send_error = None
    await db.commit()
    await db.refresh(draft)
    return draft


async def cancel_scheduled_send(db: AsyncSession, draft: PersonalEmailDraft) -> PersonalEmailDraft:
    if draft.send_status != "scheduled":
        raise PersonalEmailSendError("This draft is not currently scheduled.")
    draft.send_status = "draft"
    draft.scheduled_at = None
    await db.commit()
    await db.refresh(draft)
    return draft


async def approve_draft(db: AsyncSession, draft: PersonalEmailDraft) -> PersonalEmailDraft:
    draft.approval_status = "approved"
    await db.commit()
    await db.refresh(draft)
    return draft


async def reject_draft(db: AsyncSession, draft: PersonalEmailDraft) -> PersonalEmailDraft:
    draft.approval_status = "rejected"
    draft.send_status = "draft"
    await db.commit()
    await db.refresh(draft)
    return draft


async def bulk_reply(
    db: AsyncSession, account: PersonalEmailAccount, messages: list[PersonalEmailMessage],
    *, style: str, instructions: Optional[str], auto_send: bool,
) -> dict:
    """Generates (and optionally immediately sends) one reply draft per
    message in `messages`. Returns a summary; per-message failures are
    collected rather than aborting the whole batch."""
    created: list[PersonalEmailDraft] = []
    sent_count = 0
    errors: list[str] = []

    for message in messages:
        try:
            content = await ai.generate_reply_draft(
                account.user_id, subject=message.subject or "", sender=message.sender_email or "",
                body=message.body_text or message.snippet or "", style=style, instructions=instructions,
            )
        except Exception as e:  # noqa: BLE001 — one bad generation must not abort the batch
            errors.append(f"{message.id}: draft generation failed — {e}")
            continue

        draft = PersonalEmailDraft(message_id=message.id, style=style, content=content)
        db.add(draft)
        await db.flush()
        created.append(draft)

        if auto_send:
            try:
                await _send_draft_now(db, account, message, draft)
                sent_count += 1
            except PersonalEmailSendError as e:
                errors.append(f"{message.id}: {e}")

    await db.commit()
    for d in created:
        await db.refresh(d)
    return {"drafts": created, "sent_count": sent_count, "errors": errors}


# ─────────────────────────────────────────────────────────────────────────────
# Background loop — dispatches drafts whose scheduled_at has arrived.
# Mirrors campaign_dispatch_service / personal_email_sync_service's
# scheduler shape exactly; never raises out of the loop.
# ─────────────────────────────────────────────────────────────────────────────

async def run_scheduled_send_loop() -> None:
    import asyncio
    from app.core.database import AsyncSessionLocal

    interval = max(10, settings.PERSONAL_EMAIL_SCHEDULED_SEND_POLL_SECONDS)
    while True:
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PersonalEmailDraft).where(
                        PersonalEmailDraft.send_status == "scheduled",
                        PersonalEmailDraft.scheduled_at <= now,
                    )
                )
                due_drafts = result.scalars().all()
                for draft in due_drafts:
                    try:
                        msg_result = await db.execute(
                            select(PersonalEmailMessage).where(PersonalEmailMessage.id == draft.message_id)
                        )
                        message = msg_result.scalar_one_or_none()
                        if not message:
                            draft.send_status = "failed"
                            draft.send_error = "Original message no longer exists."
                            await db.commit()
                            continue
                        acct_result = await db.execute(
                            select(PersonalEmailAccount).where(PersonalEmailAccount.id == message.account_id)
                        )
                        account = acct_result.scalar_one_or_none()
                        if not account:
                            draft.send_status = "failed"
                            draft.send_error = "Email account no longer exists."
                            await db.commit()
                            continue
                        await _send_draft_now(db, account, message, draft)
                    except Exception as e:  # noqa: BLE001 — one draft's failure must not stop the loop
                        logger.warning(f"[personal-email-scheduled-send] draft={draft.id} failed: {e}")
        except Exception as e:  # noqa: BLE001 — the loop itself must never die
            logger.error(f"[personal-email-scheduled-send] loop iteration failed: {e}", exc_info=True)
        await asyncio.sleep(interval)
