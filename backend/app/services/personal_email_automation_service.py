"""
ThunderBots Personal Email AI Assistant — Automation & Analytics (NEW — Part 2)

Three independent features that all sit on top of Part 1's synced data
and Part 2's send primitives, kept in one module because they share the
same "read already-analyzed PersonalEmailMessage rows for an account"
shape:

1. Auto-reply rules — `evaluate_auto_reply_rules()` is called by
   services/personal_email_sync_service.sync_account() right after a new
   inbox message is analyzed. Purely opt-in: an account with zero
   PersonalEmailAutoReplyRule rows behaves exactly like Part 1. A match
   always creates a PersonalEmailDraft; it is only ever auto-sent when the
   rule itself has `require_approval=False` (the user's own explicit
   choice when creating the rule) — otherwise it sits as
   `approval_status="pending"` for the user to review.

2. Unanswered-email AI reminders — `list_unanswered()` (used by the
   accounts/{id}/messages/unanswered API route) and the background
   `run_unanswered_reminder_loop()`, which mirrors
   personal_email_sync_service.run_daily_digest_loop's polling shape and
   simply timestamps `last_reminder_at` (respecting a cooldown) so a
   future notification channel has a place to hook in without another
   migration.

3. Email analytics — `compute_analytics()` aggregates already-stored
   PersonalEmailMessage/PersonalEmailDraft rows (volume, response time,
   category/priority/sentiment breakdown, spam caught) with plain SQL
   aggregates. No new table: everything here is derived, never stored,
   so there is nothing to keep in sync.

Also: `generate_follow_up_suggestion()` for AI follow-up suggestions on a
sent-but-unanswered message, persisted to PersonalEmailAiFollowUp so a
suggestion isn't silently recomputed (and isn't lost) on every page load.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.personal_email import (
    PersonalEmailAccount, PersonalEmailMessage, PersonalEmailDraft,
    PersonalEmailAutoReplyRule, PersonalEmailAiFollowUp,
)
from app.services import personal_email_ai_service as ai

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auto-reply rules (optional, opt-in)
# ─────────────────────────────────────────────────────────────────────────────

def _rule_matches(rule: PersonalEmailAutoReplyRule, message: PersonalEmailMessage) -> bool:
    if rule.sender_contains:
        sender = (message.sender_email or "") + " " + (message.sender_name or "")
        if rule.sender_contains.lower() not in sender.lower():
            return False
    if rule.subject_contains:
        if rule.subject_contains.lower() not in (message.subject or "").lower():
            return False
    if rule.category and rule.category != message.category:
        return False
    if rule.priority and rule.priority != message.ai_priority:
        return False
    return True


async def evaluate_auto_reply_rules(
    db: AsyncSession, account: PersonalEmailAccount, message: PersonalEmailMessage,
) -> Optional[PersonalEmailDraft]:
    """Checks `message` against every active rule for `account` in
    creation order and acts on the FIRST match only (rules are meant to be
    ordered by the user from most to least specific). Returns the created
    draft, or None if no rule matched."""
    result = await db.execute(
        select(PersonalEmailAutoReplyRule).where(
            PersonalEmailAutoReplyRule.account_id == account.id,
            PersonalEmailAutoReplyRule.is_active == True,  # noqa: E712
        ).order_by(PersonalEmailAutoReplyRule.created_at)
    )
    rules = result.scalars().all()
    if not rules:
        return None

    for rule in rules:
        if not _rule_matches(rule, message):
            continue

        content = await ai.generate_reply_draft(
            account.user_id, subject=message.subject or "", sender=message.sender_email or "",
            body=message.body_text or message.snippet or "", style=rule.style, instructions=rule.instructions,
        )
        draft = PersonalEmailDraft(
            message_id=message.id, style=rule.style, content=content, created_by_rule_id=rule.id,
            approval_status="not_required" if not rule.require_approval else "pending",
        )
        db.add(draft)
        rule.last_triggered_at = datetime.now(timezone.utc)
        rule.trigger_count += 1
        await db.flush()

        if not rule.require_approval:
            # Local import avoids a circular import at module load time
            # (send_service imports sync_service, which would otherwise
            # import this module, which would import send_service).
            from app.services import personal_email_send_service as send_service
            try:
                await send_service._send_draft_now(db, account, message, draft)
            except send_service.PersonalEmailSendError as e:
                logger.warning(f"[personal-email] auto-reply rule '{rule.name}' failed to send: {e}")

        await db.commit()
        await db.refresh(draft)
        return draft

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Unanswered-email AI reminders
# ─────────────────────────────────────────────────────────────────────────────

async def list_unanswered(db: AsyncSession, account: PersonalEmailAccount, *, hours: Optional[int] = None) -> list:
    threshold_hours = hours if hours is not None else settings.PERSONAL_EMAIL_UNANSWERED_REMINDER_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    result = await db.execute(
        select(PersonalEmailMessage).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.ai_action_required == True,  # noqa: E712
            PersonalEmailMessage.is_answered == False,  # noqa: E712
            PersonalEmailMessage.is_spam == False,  # noqa: E712
            PersonalEmailMessage.received_at.isnot(None),
            PersonalEmailMessage.received_at <= cutoff,
        ).order_by(PersonalEmailMessage.received_at.asc())
    )
    return result.scalars().all()


async def run_unanswered_reminder_loop() -> None:
    """Timestamps `last_reminder_at` (respecting
    PERSONAL_EMAIL_REMINDER_COOLDOWN_HOURS) for every unanswered message
    across every account, so a future notification channel has a
    ready-made "reminder due" signal without another migration. Never
    raises out of its own loop, matching every other background loop in
    this module."""
    from app.core.database import AsyncSessionLocal

    interval = max(60, settings.PERSONAL_EMAIL_REMINDER_CHECK_INTERVAL_MINUTES * 60)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PersonalEmailAccount).where(
                        PersonalEmailAccount.status == "connected",
                        PersonalEmailAccount.sync_enabled == True,  # noqa: E712
                    )
                )
                accounts = result.scalars().all()
                cooldown = timedelta(hours=settings.PERSONAL_EMAIL_REMINDER_COOLDOWN_HOURS)
                now = datetime.now(timezone.utc)
                for account in accounts:
                    try:
                        unanswered = await list_unanswered(db, account)
                        for message in unanswered:
                            if message.last_reminder_at and (now - message.last_reminder_at) < cooldown:
                                continue
                            message.last_reminder_at = now
                        await db.commit()
                    except Exception as e:  # noqa: BLE001 — one account's failure must not stop the loop
                        logger.warning(f"[personal-email-reminders] account={account.id} failed: {e}")
        except Exception as e:  # noqa: BLE001 — the loop itself must never die
            logger.error(f"[personal-email-reminders] loop iteration failed: {e}", exc_info=True)
        await asyncio.sleep(interval)


# ─────────────────────────────────────────────────────────────────────────────
# AI follow-up suggestions (sent messages that appear unanswered)
# ─────────────────────────────────────────────────────────────────────────────

async def generate_follow_up_suggestion(db: AsyncSession, account: PersonalEmailAccount, message: PersonalEmailMessage) -> PersonalEmailAiFollowUp:
    if message.folder != "sent":
        raise ValueError("Follow-up suggestions are only generated for sent messages.")

    days_since_sent = 0
    if message.received_at:
        days_since_sent = max(0, (datetime.now(timezone.utc) - message.received_at).days)

    content = await ai.suggest_follow_up(
        account.user_id, subject=message.subject or "", recipient=message.to_addresses or "",
        original_body=message.body_text or message.snippet or "", days_since_sent=days_since_sent,
    )
    row = PersonalEmailAiFollowUp(message_id=message.id, suggested_content=content)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# 3. Email analytics
# ─────────────────────────────────────────────────────────────────────────────

async def compute_analytics(db: AsyncSession, account: PersonalEmailAccount, *, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_result = await db.execute(
        select(func.count(PersonalEmailMessage.id)).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.received_at >= since,
        )
    )
    total_received = total_result.scalar() or 0

    sent_result = await db.execute(
        select(func.count(PersonalEmailMessage.id)).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "sent",
            PersonalEmailMessage.received_at >= since,
        )
    )
    total_sent = sent_result.scalar() or 0

    spam_result = await db.execute(
        select(func.count(PersonalEmailMessage.id)).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.is_spam == True,  # noqa: E712
            PersonalEmailMessage.received_at >= since,
        )
    )
    spam_caught = spam_result.scalar() or 0

    unanswered = await list_unanswered(db, account, hours=0)

    category_result = await db.execute(
        select(PersonalEmailMessage.category, func.count(PersonalEmailMessage.id)).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.received_at >= since,
        ).group_by(PersonalEmailMessage.category)
    )
    by_category = {(cat or "uncategorized"): count for cat, count in category_result.all()}

    priority_result = await db.execute(
        select(PersonalEmailMessage.ai_priority, func.count(PersonalEmailMessage.id)).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.received_at >= since,
        ).group_by(PersonalEmailMessage.ai_priority)
    )
    by_priority = {(p or "unanalyzed"): count for p, count in priority_result.all()}

    sentiment_result = await db.execute(
        select(PersonalEmailMessage.ai_sentiment, func.count(PersonalEmailMessage.id)).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.received_at >= since,
        ).group_by(PersonalEmailMessage.ai_sentiment)
    )
    by_sentiment = {(s or "unanalyzed"): count for s, count in sentiment_result.all()}

    # Average response time: for each answered inbox message, time to the
    # earliest `sent` message on the same thread received after it.
    answered_result = await db.execute(
        select(PersonalEmailMessage).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailMessage.folder == "inbox",
            PersonalEmailMessage.is_answered == True,  # noqa: E712
            PersonalEmailMessage.answered_at.isnot(None),
            PersonalEmailMessage.received_at >= since,
        )
    )
    answered_messages = answered_result.scalars().all()
    response_seconds = [
        (m.answered_at - m.received_at).total_seconds()
        for m in answered_messages if m.answered_at and m.received_at and m.answered_at > m.received_at
    ]
    avg_response_hours = round((sum(response_seconds) / len(response_seconds)) / 3600, 1) if response_seconds else None

    drafts_sent_result = await db.execute(
        select(func.count(PersonalEmailDraft.id)).join(
            PersonalEmailMessage, PersonalEmailDraft.message_id == PersonalEmailMessage.id
        ).where(
            PersonalEmailMessage.account_id == account.id,
            PersonalEmailDraft.send_status == "sent",
            PersonalEmailDraft.sent_at >= since,
        )
    )
    ai_replies_sent = drafts_sent_result.scalar() or 0

    return {
        "period_days": days,
        "total_received": total_received,
        "total_sent": total_sent,
        "spam_caught": spam_caught,
        "unanswered_count": len(unanswered),
        "ai_replies_sent": ai_replies_sent,
        "avg_response_time_hours": avg_response_hours,
        "by_category": by_category,
        "by_priority": by_priority,
        "by_sentiment": by_sentiment,
    }
