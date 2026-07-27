"""
ThunderBots AI Broadcast Campaign — Audience Resolution Service
Purely additive. Resolves a campaign's `audience_type` + `audience_config`
(see app/models/campaign.py) into a de-duplicated, validated list of send
targets, shared by:
- app/api/v1/campaigns.py's `/audience/resolve` preview endpoint (Step 2 of
  the Campaign Flow: total/valid/invalid/duplicate counts + a message
  preview sample), and
- app/services/campaign_dispatch_service.py's `_sync_whatsapp_recipients` /
  `_sync_telegram_recipients`, which upsert the resolved list into the real
  `campaign_recipients` ledger at send time.

NEW (Telegram Integration — Part 2): audience resolution is now channel-
aware (`channel` param, default "whatsapp" so every existing caller that
never passed it keeps behaving exactly as before). For channel="telegram",
resolution reads app.models.telegram.TelegramSubscriber instead of
WhatsAppContact/ContactGroup — and, regardless of which audience_type was
requested, every resolved identifier is cross-checked against the real
TelegramSubscriber table for that bot before being treated as valid. That
cross-check is what guarantees a Telegram campaign can never reach anyone
who hasn't themselves started the bot conversation, even if a caller (e.g.
a manual/CSV entry) supplies a chat_id ThunderBots has never seen — it is
simply resolved as invalid, exactly like an unreachable WhatsApp number is
today.

Does not touch WhatsAppContact/TelegramSubscriber writes, the Workflow
Runtime, or either channel's webhook — this module only *reads* rows and
normalizes/validates identifiers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsapp import WhatsAppContact
from app.models.contact_group import ContactGroup, ContactGroupMember
from app.models.telegram import TelegramSubscriber

# Loose E.164-ish validator: optional leading +, 8-15 digits overall. This is
# intentionally permissive (WhatsApp wa_ids arrive without '+') — it exists
# to catch obviously-broken CSV/manual rows (letters, too short/long),
# not to be a strict phone-format authority.
PHONE_RE = re.compile(r"^\+?\d{8,15}$")

# Telegram chat ids are signed integers (negative for group/channel chats,
# though Part 1/2 only ever target private bot-DM chats, which are
# positive). Loose on purpose for the same reason as PHONE_RE above — the
# real authority on whether an id is reachable is the subscriber
# cross-check in _resolve_telegram_audience, not this shape check.
CHAT_ID_RE = re.compile(r"^-?\d{1,20}$")

AUDIENCE_TYPES = {"contacts", "tags", "groups", "manual"}


@dataclass
class AudienceEntry:
    identifier: str                 # normalized, '+' and non-digits stripped
    name: Optional[str] = None
    city: Optional[str] = None
    company: Optional[str] = None
    valid: bool = True
    reason: Optional[str] = None    # set when valid=False


@dataclass
class AudienceResult:
    entries: list[AudienceEntry] = field(default_factory=list)   # valid, de-duplicated
    invalid: list[AudienceEntry] = field(default_factory=list)   # failed phone validation
    duplicate_count: int = 0

    @property
    def total(self) -> int:
        return len(self.entries) + len(self.invalid) + self.duplicate_count

    @property
    def valid_count(self) -> int:
        return len(self.entries)


def normalize_phone(raw: str) -> str:
    return re.sub(r"[^\d]", "", (raw or "").strip())


def _is_valid_phone(raw: str) -> bool:
    return bool(PHONE_RE.match((raw or "").strip()))


def _is_valid_chat_id(raw: str) -> bool:
    return bool(CHAT_ID_RE.match((raw or "").strip()))


def _dedupe(raw_entries: list[AudienceEntry]) -> AudienceResult:
    """Validates + de-dupes a raw (unvalidated) WhatsApp entry list, keeping
    the first occurrence of each normalized number and the input order."""
    result = AudienceResult()
    seen: set[str] = set()
    for entry in raw_entries:
        if not entry.identifier or not _is_valid_phone(entry.identifier):
            entry.valid = False
            entry.reason = entry.reason or "Invalid phone number"
            result.invalid.append(entry)
            continue
        normalized = normalize_phone(entry.identifier)
        if normalized in seen:
            result.duplicate_count += 1
            continue
        seen.add(normalized)
        entry.identifier = normalized
        result.entries.append(entry)
    return result


async def _contacts_for_workflow(db: AsyncSession, workflow_id: str) -> list[WhatsAppContact]:
    result = await db.execute(
        select(WhatsAppContact).where(WhatsAppContact.workflow_id == workflow_id)
    )
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────────────────────
# Telegram (NEW — Part 2)
# ─────────────────────────────────────────────────────────────────────────────

async def _telegram_subscribers_for_workflow(db: AsyncSession, workflow_id: str) -> list[TelegramSubscriber]:
    """ALL subscriber rows (subscribed and unsubscribed/blocked) for this
    bot — unsubscribed rows are deliberately included so the audience
    preview can surface them as 'Invalid / unreachable' (bot blocked)
    rather than silently dropping them."""
    result = await db.execute(
        select(TelegramSubscriber).where(TelegramSubscriber.workflow_id == workflow_id)
    )
    return list(result.scalars().all())


def _telegram_display_name(s: TelegramSubscriber) -> Optional[str]:
    if s.first_name and s.last_name:
        return f"{s.first_name} {s.last_name}"
    return s.first_name or (f"@{s.username}" if s.username else None)


async def _resolve_telegram_audience(
    db: AsyncSession, workflow_id: Optional[str], audience_type: str, config: dict,
) -> AudienceResult:
    """Telegram campaigns may ONLY ever reach chat_ids that are on file as
    TelegramSubscriber rows for this bot — i.e. people who have themselves
    started the bot conversation (models/telegram.py's opt-in guarantee).
    This is enforced here regardless of audience_type: every candidate
    identifier, however it was sourced, is cross-checked against the real
    subscriber table before being treated as valid. There is no code path
    in this function that can mark an identifier valid without it being a
    real, current TelegramSubscriber row."""
    subscribers = await _telegram_subscribers_for_workflow(db, workflow_id) if workflow_id else []
    by_chat_id = {s.chat_id: s for s in subscribers}

    raw: list[AudienceEntry] = []

    if audience_type == "manual":
        # CSV/manual chat ids — still cross-checked below like every other
        # source. A chat_id typed in here that never messaged the bot is
        # resolved as invalid, never sent to.
        for row in (config.get("manual_entries") or []):
            identifier = str(row.get("identifier") or row.get("chat_id") or row.get("phone") or "").strip()
            raw.append(AudienceEntry(identifier=identifier, name=row.get("name") or None))

    elif audience_type in ("tags", "groups"):
        # Tags/Contact Groups are a WhatsApp-contact concept (see
        # models/contact_group.py) with no Telegram equivalent today — the
        # Campaign UI doesn't offer these sources for a Telegram campaign,
        # so there is nothing to resolve. Fails safe (empty), not with an error.
        raw = []

    else:  # "contacts" (default) — every opted-in Telegram subscriber, or an explicit subset
        contact_ids = config.get("contact_ids") or None
        candidates = subscribers
        if contact_ids:
            wanted = set(contact_ids)
            candidates = [s for s in candidates if s.id in wanted]
        for s in candidates:
            raw.append(AudienceEntry(identifier=s.chat_id, name=_telegram_display_name(s)))

    result = AudienceResult()
    seen: set[str] = set()
    for entry in raw:
        chat_id = (entry.identifier or "").strip()
        if not chat_id or not _is_valid_chat_id(chat_id):
            entry.valid = False
            entry.reason = entry.reason or "Not a valid Telegram chat id"
            result.invalid.append(entry)
            continue

        subscriber = by_chat_id.get(chat_id)
        if not subscriber:
            entry.valid = False
            entry.reason = "This person has never started a conversation with your Telegram bot"
            result.invalid.append(entry)
            continue
        if not subscriber.is_subscribed:
            entry.valid = False
            entry.reason = "Telegram bot was blocked by this user"
            result.invalid.append(entry)
            continue

        if chat_id in seen:
            result.duplicate_count += 1
            continue
        seen.add(chat_id)
        entry.identifier = chat_id
        entry.name = entry.name or _telegram_display_name(subscriber)
        result.entries.append(entry)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_audience(
    db: AsyncSession, user_id: str, workflow_id: Optional[str],
    audience_type: str, audience_config: Optional[dict],
    channel: str = "whatsapp",
) -> AudienceResult:
    """Resolves an audience_type + audience_config into validated,
    de-duplicated send targets. `workflow_id` is required for
    contacts/tags/groups sources against opted-in WhatsApp contacts
    (groups can also carry never-messaged numbers directly).

    `channel` (NEW — Part 2) selects which opt-in source of truth is used:
    "whatsapp" (default, unchanged behavior) reads WhatsAppContact/
    ContactGroup; "telegram" reads TelegramSubscriber and enforces that
    every recipient has actually started the bot conversation."""
    config = audience_config or {}
    audience_type = audience_type if audience_type in AUDIENCE_TYPES else "contacts"

    if channel == "telegram":
        return await _resolve_telegram_audience(db, workflow_id, audience_type, config)

    raw: list[AudienceEntry] = []

    if audience_type == "manual":
        for row in (config.get("manual_entries") or []):
            raw.append(AudienceEntry(
                identifier=str(row.get("identifier") or row.get("phone") or ""),
                name=row.get("name") or None,
                city=row.get("city") or None,
                company=row.get("company") or None,
            ))

    elif audience_type == "tags":
        wanted_tags = {t.strip().lower() for t in (config.get("tags") or []) if t.strip()}
        contacts = await _contacts_for_workflow(db, workflow_id) if workflow_id else []
        for c in contacts:
            contact_tags = {str(t).strip().lower() for t in (c.tags or [])}
            if wanted_tags and not (wanted_tags & contact_tags):
                continue
            raw.append(AudienceEntry(
                identifier=c.wa_id, name=c.profile_name, city=c.city, company=c.company,
            ))

    elif audience_type == "groups":
        group_ids = config.get("group_ids") or []
        if group_ids:
            result = await db.execute(
                select(ContactGroupMember)
                .join(ContactGroup, ContactGroup.id == ContactGroupMember.group_id)
                .where(ContactGroupMember.group_id.in_(group_ids), ContactGroup.user_id == user_id)
            )
            members = result.scalars().all()
            # Enrich with live WhatsAppContact data (name/city/company) when
            # the group member has since messaged the bot, without a
            # required join — group membership works standalone.
            contact_by_wa = {}
            if workflow_id:
                contact_by_wa = {c.wa_id: c for c in await _contacts_for_workflow(db, workflow_id)}
            for m in members:
                live = contact_by_wa.get(normalize_phone(m.wa_id))
                raw.append(AudienceEntry(
                    identifier=m.wa_id,
                    name=(live.profile_name if live else None) or m.contact_name,
                    city=(live.city if live else None) or m.city,
                    company=(live.company if live else None) or m.company,
                ))

    else:  # "contacts" — every (optionally explicitly-selected) opted-in contact
        contact_ids = config.get("contact_ids") or None
        contacts = await _contacts_for_workflow(db, workflow_id) if workflow_id else []
        if contact_ids:
            wanted = set(contact_ids)
            contacts = [c for c in contacts if c.id in wanted]
        for c in contacts:
            raw.append(AudienceEntry(
                identifier=c.wa_id, name=c.profile_name, city=c.city, company=c.company,
            ))

    return _dedupe(raw)
