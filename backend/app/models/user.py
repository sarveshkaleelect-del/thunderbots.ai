"""
ThunderBots User Models
FIX v4: All ForeignKeys use ondelete="CASCADE", passive_deletes=True on relationships.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # NEW (Google SSO): nullable — an account created via "Sign in with
    # Google" has no local password at all until the user optionally sets
    # one. Every existing row keeps its bcrypt hash unchanged; login() still
    # requires a non-null password to succeed, so this is purely additive.
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    # NEW (Google SSO): set the first time a user signs in with Google,
    # either on a brand-new account or linked onto an existing
    # email/password account that matches the verified Google email.
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    # NEW (TOTP 2FA): Fernet-encrypted TOTP secret (same encrypt_key/
    # decrypt_key helper already used for provider API keys — see
    # services/totp_service.py). Present but totp_enabled=False while a
    # setup is in progress and not yet confirmed with a valid code.
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # NEW (TOTP 2FA): JSON array of SHA-256 hashes of one-time backup codes
    # (same hashing approach as PasswordResetToken.token_hash) — the raw
    # codes are shown to the user exactly once and never stored.
    totp_backup_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NEW (Admin Dashboard): platform-role + account-status flags.
    # is_admin gates every /api/v1/admin/* route (see core/auth.get_current_admin_user).
    # is_active=False is an admin-triggered "disable" — get_current_user rejects the
    # token for a disabled account, and /auth/login refuses to issue a new one.
    # Purely additive: both default True/False and never change behavior for an
    # existing account an admin hasn't touched.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # NEW (Email Verification): set True once the user completes the
    # verification-email link flow. Defaults False for every NEW account
    # (register/google) — the migration backfills every EXISTING row to
    # True via server_default, so no current user is retroactively locked
    # out of anything. Nothing today gates on this flag (login, /me, and
    # every other route behave identically regardless of its value) — it
    # is purely additive data, ready for a future phase to enforce.
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    workflows: Mapped[list] = relationship(
        "Workflow", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    knowledge_bases: Mapped[list] = relationship(
        "KnowledgeBase", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    api_keys: Mapped[list["UserAPIKey"]] = relationship(
        "UserAPIKey", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserAPIKey(Base):
    """Stores encrypted API keys per user per provider."""
    __tablename__ = "user_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(100), default="")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_tested: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship("User", back_populates="api_keys", passive_deletes=True)
