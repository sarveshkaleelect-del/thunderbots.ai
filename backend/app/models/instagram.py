"""
ThunderBots Instagram DM Integration Models
NEW (Instagram Channel).

Mirrors the exact conventions already established by models/whatsapp.py
(itself following models/user.py, models/workflow.py, models/analytics.py):
ondelete="CASCADE" on every FK, passive_deletes=True on every relationship,
JSONB default=dict handled Python-side, String(36) UUID primary keys.
Purely additive — no existing table, model, or relationship is touched.

Four tables:

- InstagramAccount: one row per connected Instagram Business account, tied
  to a single workflow (one IG account per chatbot, same shape as
  WhatsAppChannel), but a user/workspace may have many InstagramAccount
  rows — i.e. multiple Instagram accounts per workspace, each driving a
  different bot. Holds the Meta Graph API connection obtained via Facebook
  Login OAuth: the connected Facebook Page id, the Instagram-scoped user id
  (ig_user_id), encrypted long-lived Page Access Token (used both to send
  messages and to validate/refresh), and token expiry so "Expired" can be
  detected proactively instead of only on next failed send.

  `platform` is carried on this table (always "instagram" today) so the
  same schema/service/webhook-routing code can grow a "messenger" row for
  Facebook Messenger later without a new table or a single line of the
  existing Instagram code path changing.

- InstagramContact: maps an Instagram-scoped sender id (IGSID) to the
  stable `session_id` used by the existing Workflow Runtime's
  ExecutionContext — identical role to WhatsAppContact.

- InstagramMessageLog: records the Meta message id (mid) of every inbound
  webhook message actually processed, with a unique constraint on
  (account_id, mid). This is the sole duplicate-webhook-processing guard:
  Meta may redeliver the same webhook event on timeout/retry, and this
  table lets the webhook handler detect "already handled" before it ever
  touches the Workflow Runtime a second time. Also carries optional
  attachment fields (attachment_type/url) — populated today for visibility
  even though only text is executed through the AI Agent, and reserved for
  the future image/video/attachment download pipeline (see
  services/instagram_service.py module docstring).

- InstagramWebhookLog: append-only connection + webhook delivery log
  (verification handshakes, inbound deliveries, send failures, token
  refreshes) surfaced in the Settings UI "Logs" panel, independent of the
  message-level dedup table above.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class InstagramAccount(Base):
    """One Instagram Business connection per chatbot (workflow). A user may
    own several of these — one per bot — which is what makes "multiple
    Instagram accounts per workspace" true without any additional table."""
    __tablename__ = "instagram_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Future-ready for Facebook Messenger on the same architecture — always
    # "instagram" today; a "messenger" row would reuse every column below.
    platform: Mapped[str] = mapped_column(String(20), default="instagram", index=True)

    # ── Meta Graph API connection (obtained via Facebook Login OAuth) ─────────
    ig_user_id: Mapped[str] = mapped_column(String(64), nullable=False)  # Instagram-scoped account id
    ig_username: Mapped[str | None] = mapped_column(String(255))
    facebook_page_id: Mapped[str] = mapped_column(String(64), nullable=False)
    facebook_page_name: Mapped[str | None] = mapped_column(String(255))
    encrypted_page_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    # Long-lived user token — kept (encrypted) solely so the Page Access
    # Token can be silently re-derived/refreshed without forcing the owner
    # back through the OAuth consent screen; never used to call the API
    # directly on the user's behalf.
    encrypted_user_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # connecting | connected | expired | disconnected | error
    status: Mapped[str] = mapped_column(String(20), default="disconnected", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # healthy | degraded | error | unknown
    health_status: Mapped[str] = mapped_column(String(20), default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text)

    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_token_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages_received_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_failed_count: Mapped[int] = mapped_column(Integer, default=0)

    # Free-form bag for forward-compatible settings without another migration.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contacts: Mapped[list["InstagramContact"]] = relationship(
        "InstagramContact", back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    message_logs: Mapped[list["InstagramMessageLog"]] = relationship(
        "InstagramMessageLog", back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    webhook_logs: Mapped[list["InstagramWebhookLog"]] = relationship(
        "InstagramWebhookLog", back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )


class InstagramContact(Base):
    """Maps an Instagram-scoped sender id (IGSID) to the Workflow Runtime
    session that carries their ExecutionContext."""
    __tablename__ = "instagram_contacts"

    __table_args__ = (
        UniqueConstraint("account_id", "igsid", name="uq_instagram_contact_account_igsid"),
        Index("idx_ig_contact_account_igsid", "account_id", "igsid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    igsid: Mapped[str] = mapped_column(String(64), nullable=False)  # Instagram-scoped sender id
    username: Mapped[str | None] = mapped_column(String(255))
    profile_pic_url: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    account: Mapped["InstagramAccount"] = relationship(
        "InstagramAccount", back_populates="contacts", passive_deletes=True
    )


class InstagramMessageLog(Base):
    """Dedup + audit trail for every inbound webhook message actually
    processed. The unique constraint on (account_id, mid) is what prevents
    duplicate webhook processing when Meta redelivers an event."""
    __tablename__ = "instagram_message_logs"

    __table_args__ = (
        UniqueConstraint("account_id", "mid", name="uq_instagram_message_account_mid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    mid: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # Meta message id
    igsid: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), default="inbound")  # inbound | outbound

    message_type: Mapped[str] = mapped_column(String(20), default="text")  # text|image|video|audio|file|unsupported
    # Reserved for the future media pipeline — populated when Meta includes
    # an attachment payload, not yet downloaded/re-hosted.
    attachment_type: Mapped[str | None] = mapped_column(String(20))
    attachment_url: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="processed")  # processed|failed|duplicate|skipped
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    account: Mapped["InstagramAccount"] = relationship(
        "InstagramAccount", back_populates="message_logs", passive_deletes=True
    )


class InstagramWebhookLog(Base):
    """Append-only connection & webhook delivery log surfaced in the
    Settings UI. Independent of InstagramMessageLog (which is specifically
    the dedup ledger) — this is the human-readable operational trail:
    verification handshakes, OAuth connects, token refreshes, rate-limit
    backoffs, and delivery failures."""
    __tablename__ = "instagram_webhook_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # oauth_connect|oauth_error|webhook_verify|webhook_receive|token_refresh|
    # send_success|send_failed|rate_limited|signature_invalid
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    account: Mapped["InstagramAccount"] = relationship(
        "InstagramAccount", back_populates="webhook_logs", passive_deletes=True
    )
