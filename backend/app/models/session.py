"""
ThunderBots Active Sessions & Device Management — models (NEW, Phase 2)

Purely additive module — no existing table, column, or relationship is
touched. Same conventions as models/notification.py: UUID string PKs,
ForeignKey(..., ondelete="CASCADE"), relationship(..., passive_deletes=True).

UserSession is what makes "remote logout" possible at all: ThunderBots
access tokens are stateless JWTs (see core/auth.py), so previously nothing
short of a token's own expiry could ever invalidate it. Every access token
now carries a "sid" claim equal to a UserSession.id — get_current_user
(core/auth.py) looks that row up on every request and rejects the token if
the session has been revoked or has expired, even though the JWT signature
itself is still valid. Tokens minted before this feature (no "sid" claim)
have nothing to look up and keep working unchanged until they naturally
expire — fully backward compatible.

- device_name/browser/os/device_type: parsed, best-effort, from the
  request's User-Agent header at login time (see services/session_service.py
  — parse_user_agent). Never blocks login if parsing fails; falls back to
  "Unknown".
- ip_address: the client IP observed at login (see
  services/session_service.get_client_ip), honoring X-Forwarded-For when
  present (reverse-proxy deployments) the same way rate_limit.py does.
- location: best-effort "City, Region, Country" string from IP geolocation.
  Off by default (settings.IP_GEOLOCATION_ENABLED) — never a required
  network call, and always None for private/loopback IPs regardless of the
  setting. See services/session_service.geolocate_ip.
- last_active_at: updated (throttled — see core/auth.get_current_user) as
  the session is used, so the sessions list can show "Active now" /
  "3 hours ago" style timestamps instead of only the original login time.
- expires_at: mirrors the access token's own expiry so a session row never
  outlives the token it backs.
- revoked_at/revoked_reason: set by POST /auth/logout (own device),
  DELETE /auth/sessions/{id} (remote logout of one device), POST
  /auth/sessions/revoke-all ("log out other devices"), or POST
  /auth/logout-all ("log out everywhere"). A revoked session is never
  deleted — it stays as an audit trail — it is simply excluded from the
  "active sessions" list and rejected by get_current_user.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Device / client info (best-effort, parsed at login) ──────────────
    device_name: Mapped[str] = mapped_column(String(150), default="Unknown device")
    browser: Mapped[str] = mapped_column(String(50), default="Unknown")
    os: Mapped[str] = mapped_column(String(50), default="Unknown")
    device_type: Mapped[str] = mapped_column(String(20), default="unknown")  # desktop | mobile | tablet | unknown
    user_agent: Mapped[str] = mapped_column(Text, default="")

    # ── Network info ──────────────────────────────────────────────────────
    ip_address: Mapped[str] = mapped_column(String(64), default="unknown")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    user: Mapped["User"] = relationship("User", passive_deletes=True)  # noqa: F821

    __table_args__ = (
        # Every session listing/revocation query filters by user_id and
        # active-ness — a composite index keeps GET /auth/sessions cheap
        # even for accounts with a long revoked-session history.
        Index("ix_user_sessions_user_active", "user_id", "revoked_at"),
    )
