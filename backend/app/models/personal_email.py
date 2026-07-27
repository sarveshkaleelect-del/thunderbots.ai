"""
ThunderBots Personal Email AI Assistant — Models (NEW — Part 1)

Purely additive module. Does not import from or modify app/engine/*
(Workflow Runtime), app/core/auth.py (Authentication), app/knowledge/*
(Knowledge Base), the AI Engine's provider classes (only the already-shared
encrypt_key/decrypt_key Fernet helpers are reused, same pattern as
services/whatsapp_service.py and services/instagram_service.py), or the
existing Email Channel (services/email_service.py, models/notification.py)
— this is a completely separate feature: an AI assistant over a user's own
*personal* inbox, not the customer-support Email Channel.

Four tables:

- PersonalEmailAccount: one row per connected personal mailbox. `provider`
  ("gmail" today) plus a provider-agnostic token/credential shape (encrypted
  access + refresh token, expiry, scopes) is deliberately generic so a
  future "outlook" row can reuse every column and every service/API route
  unchanged — only a new provider-specific OAuth client module would be
  added (see services/gmail_service.py docstring). A user may connect
  several mailboxes (multiple Gmail accounts, and later Outlook too).

- PersonalEmailMessage: a locally-synced copy of a message from the
  provider mailbox, tagged with which local `folder` it belongs to
  (inbox/sent/drafts/starred — starred is a boolean flag layered on top of
  inbox/sent rather than a mutually exclusive folder, mirroring how Gmail
  itself treats "starred" as a label, not a folder) plus the AI-derived
  fields (summary, priority, sentiment, deadline, tasks, action_required)
  populated by services/personal_email_ai_service.py. Unique on
  (account_id, provider_message_id) so re-sync is idempotent.

- PersonalEmailDraft: AI-generated reply drafts for a given message. A
  message can have several drafts (one per style: professional/friendly/
  short), each independently editable/regeneratable/translatable. Nothing
  in this table is ever sent — there is no send path in Part 1.

- PersonalEmailDigest: one row per generated Daily AI Email Digest for an
  account, so the digest has history instead of being recomputed and
  thrown away every time.

Part 2 (NEW — additive only, no Part 1 column removed/renamed):

- PersonalEmailMessage gains categorization/spam/attachment/reply-tracking
  columns (category, labels, is_spam, spam_score, spam_reason,
  is_answered, answered_at, has_attachments, attachments) populated by
  services/personal_email_ai_service.py's new `classify_email()` and by
  services/gmail_service.py's attachment-metadata parsing.

- PersonalEmailDraft gains a send lifecycle (send_status, scheduled_at,
  sent_at, sent_provider_message_id, approval_status, to_addresses, cc,
  bcc, attachments) so a draft can move professional/friendly/short ->
  pending_approval/approved -> scheduled -> sent, all still driven by
  services/personal_email_send_service.py. Nothing here changes how
  Part 1 drafts are generated/edited/regenerated/translated.

- PersonalEmailAutoReplyRule (NEW table): optional, per-account,
  opt-in-only rules ("Optional auto-reply rules") matching on
  sender/subject/category/priority, each producing either an
  auto-generated draft awaiting approval or (only if the user explicitly
  sets require_approval=False on the rule) an automatically sent reply.

- PersonalEmailAiFollowUp (NEW table): AI-suggested follow-up drafts for
  a *sent* message that appears to have gone unanswered, so a suggestion
  persists instead of being recomputed/discarded every page load.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PersonalEmailAccount(Base):
    """One connected personal mailbox. `provider` is "gmail" today;
    "outlook" is designed for but not implemented in Part 1 — see
    services/gmail_service.py and api/v1/personal_email.py module docs."""
    __tablename__ = "personal_email_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="gmail", index=True)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))

    # ── OAuth credential (encrypted with the shared Fernet helper) ────────
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)  # space-separated, as granted

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connected")
    # connected | expired | error | disconnected
    last_error: Mapped[str | None] = mapped_column(Text)

    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(20))  # ok | error
    last_history_id: Mapped[str | None] = mapped_column(String(64))  # gmail incremental-sync cursor

    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_digest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages: Mapped[list["PersonalEmailMessage"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    digests: Mapped[list["PersonalEmailDigest"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "provider", "email_address", name="uq_personal_email_account_identity"),
    )


class PersonalEmailMessage(Base):
    """A locally-synced copy of one provider message, plus AI analysis."""
    __tablename__ = "personal_email_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_email_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    provider_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_thread_id: Mapped[str | None] = mapped_column(String(128), index=True)

    # inbox | sent | drafts — starred is `is_starred`, layered on top, not a
    # separate folder value, matching Gmail's own label semantics.
    folder: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sender_name: Mapped[str | None] = mapped_column(String(255))
    sender_email: Mapped[str | None] = mapped_column(String(255), index=True)
    to_addresses: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # ── AI analysis (populated by personal_email_ai_service) ──────────────
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_priority: Mapped[str | None] = mapped_column(String(10))  # low | medium | high | urgent
    ai_sentiment: Mapped[str | None] = mapped_column(String(10))  # positive | neutral | negative
    ai_deadline: Mapped[str | None] = mapped_column(String(64))   # free-form/ISO date text, if detected
    ai_tasks: Mapped[list] = mapped_column(JSONB, default=list)   # list[str]
    ai_action_required: Mapped[bool | None] = mapped_column(Boolean)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_analysis_error: Mapped[str | None] = mapped_column(Text)

    # ── Part 2: auto-categorize / smart labels / spam-phishing detection ──
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    # work | personal | finance | promotions | social | updates | spam | other
    labels: Mapped[list] = mapped_column(JSONB, default=list)  # list[str], free-form AI "smart labels"
    is_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    spam_score: Mapped[int | None] = mapped_column(Integer)  # 0-100, higher = more likely spam/phishing
    spam_reason: Mapped[str | None] = mapped_column(Text)

    # ── Part 2: unanswered-email tracking (drives the AI reminder) ────────
    is_answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Part 2: attachments (metadata only; bytes fetched on demand) ──────
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attachments: Mapped[list] = mapped_column(JSONB, default=list)
    # list[{"attachment_id": provider part id, "filename": str, "mime_type": str, "size": int}]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    account: Mapped["PersonalEmailAccount"] = relationship(back_populates="messages")
    drafts: Mapped[list["PersonalEmailDraft"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("account_id", "provider_message_id", name="uq_personal_email_message_identity"),
        Index("ix_personal_email_messages_account_folder", "account_id", "folder"),
    )


class PersonalEmailDraft(Base):
    """An AI-generated reply draft for a message. Never sent — Part 1 has
    no send path. `style` is professional | friendly | short."""
    __tablename__ = "personal_email_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_email_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )

    style: Mapped[str] = mapped_column(String(20), nullable=False)  # professional | friendly | short
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # ── Part 2: send lifecycle ─────────────────────────────────────────────
    # draft -> pending_approval -> (approved) -> scheduled -> sending -> sent
    # any state can move to "failed" (see send_error) or back to draft on reject.
    send_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_required")
    # not_required | pending | approved | rejected — only meaningful for
    # drafts created by an auto-reply rule with require_approval=True.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_provider_message_id: Mapped[str | None] = mapped_column(String(128))
    send_error: Mapped[str | None] = mapped_column(Text)
    to_addresses: Mapped[str | None] = mapped_column(Text)  # override; defaults to original sender on send
    cc: Mapped[str | None] = mapped_column(Text)
    bcc: Mapped[str | None] = mapped_column(Text)
    subject_override: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JSONB, default=list)
    # list[{"filename": str, "mime_type": str, "content_base64": str, "size": int}]
    created_by_rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("personal_email_auto_reply_rules.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    message: Mapped["PersonalEmailMessage"] = relationship(back_populates="drafts")


class PersonalEmailDigest(Base):
    """One generated Daily AI Email Digest for an account."""
    __tablename__ = "personal_email_digests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_email_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    digest_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD (account owner's UTC day)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    total_emails: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_priority_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    highlights: Mapped[list] = mapped_column(JSONB, default=list)  # list[{message_id, subject, reason}]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    account: Mapped["PersonalEmailAccount"] = relationship(back_populates="digests")

    __table_args__ = (
        UniqueConstraint("account_id", "digest_date", name="uq_personal_email_digest_day"),
    )


class PersonalEmailAutoReplyRule(Base):
    """An OPT-IN, per-account auto-reply rule (Part 2). Disabled by
    default on creation (`is_active` defaults True but the feature itself
    only ever runs for accounts that have at least one rule — nothing is
    auto-created). Every rule match always creates a PersonalEmailDraft;
    only when `require_approval` is explicitly False does the sync loop
    send it immediately, otherwise it sits as `approval_status="pending"`
    for the user to approve/reject (see api/v1/personal_email.py's
    /drafts/{id}/approve and /reject routes)."""
    __tablename__ = "personal_email_auto_reply_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_email_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Matching conditions — all provided keys must match (AND). Any of
    # these may be omitted/null to mean "don't filter on this".
    sender_contains: Mapped[str | None] = mapped_column(String(255))
    subject_contains: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[str | None] = mapped_column(String(10))

    # Action
    style: Mapped[str] = mapped_column(String(20), nullable=False, default="professional")
    instructions: Mapped[str | None] = mapped_column(Text)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    account: Mapped["PersonalEmailAccount"] = relationship()


class PersonalEmailAiFollowUp(Base):
    """An AI-suggested follow-up draft for a SENT message that appears to
    have gone unanswered (Part 2). Distinct from PersonalEmailDraft, which
    is a reply *to an inbox message*; a follow-up is a new nudge message
    on a thread the user already sent and is still waiting on."""
    __tablename__ = "personal_email_ai_followups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("personal_email_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suggested_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="suggested")
    # suggested | dismissed | used
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    message: Mapped["PersonalEmailMessage"] = relationship()
