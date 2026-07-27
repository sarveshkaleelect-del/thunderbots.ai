"""
ThunderBots Active Sessions & Device Management — service (NEW, Phase 2)

Everything needed to turn a login request into a UserSession row, plus the
small helpers the /auth/sessions endpoints use to render and revoke them.

Design notes:
- Device/browser/OS parsing is a lightweight, dependency-free regex parser
  over the User-Agent header — good enough to produce a friendly label like
  "Chrome on macOS" for the sessions list. It is intentionally not a full
  UA-database parser (no new dependency, mirrors the project's existing
  "no new binary/heavy dependency" preference — see qrcode's SVG-only
  usage in totp_service.py). Anything unrecognized degrades to "Unknown"
  rather than raising.
- IP geolocation is opt-in (settings.IP_GEOLOCATION_ENABLED, default False)
  and uses the already-present `httpx` dependency — no new package. It is
  wrapped in try/except with a short timeout and NEVER raises: a failed or
  disabled lookup just means session.location stays None, exactly as if
  this feature were never added.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.session import UserSession

logger = logging.getLogger(__name__)


# ── User-Agent parsing ───────────────────────────────────────────────────

_BROWSER_PATTERNS = [
    ("Edge",             re.compile(r"Edg(?:A|iOS)?/")),
    ("Opera",            re.compile(r"OPR/|Opera/")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/")),
    ("Firefox",          re.compile(r"Firefox/")),
    ("Chrome",           re.compile(r"Chrome/|CriOS/")),
    ("Safari",           re.compile(r"Safari/")),  # checked after Chrome/Edge/Opera, which also include "Safari/"
]

_OS_PATTERNS = [
    ("Windows", re.compile(r"Windows NT")),
    ("iOS",     re.compile(r"iPhone|iPad|iPod")),
    ("macOS",   re.compile(r"Mac OS X")),
    ("Android", re.compile(r"Android")),
    ("Chrome OS", re.compile(r"CrOS")),
    ("Linux",   re.compile(r"Linux")),
]


def parse_user_agent(user_agent: str) -> dict:
    """Returns {browser, os, device_type, device_name}. Never raises —
    falls back to "Unknown" for anything it doesn't recognize."""
    ua = user_agent or ""

    browser = "Unknown"
    for name, pattern in _BROWSER_PATTERNS:
        if pattern.search(ua):
            browser = name
            break

    os_name = "Unknown"
    for name, pattern in _OS_PATTERNS:
        if pattern.search(ua):
            os_name = name
            break

    if re.search(r"iPad|Tablet", ua):
        device_type = "tablet"
    elif re.search(r"Mobi|iPhone|Android.*Mobile", ua):
        device_type = "mobile"
    elif ua:
        device_type = "desktop"
    else:
        device_type = "unknown"

    if browser == "Unknown" and os_name == "Unknown":
        device_name = "Unknown device"
    else:
        device_name = f"{browser} on {os_name}" if browser != "Unknown" else os_name

    return {
        "browser": browser,
        "os": os_name,
        "device_type": device_type,
        "device_name": device_name,
    }


# ── Client IP ─────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Same X-Forwarded-For-aware precedence a reverse-proxy deployment
    needs; falls back to the direct socket peer, matching the approach
    already used ad-hoc in core/rate_limit.py."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry is the original client per the standard de-facto format.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast)


# ── Best-effort IP geolocation (opt-in, off by default) ─────────────────

async def geolocate_ip(ip: str) -> Optional[str]:
    """Returns a "City, Region, Country" string, or None. Never raises —
    any failure (disabled, timeout, bad response, private IP) just means
    no location is shown."""
    if not settings.IP_GEOLOCATION_ENABLED or not _is_public_ip(ip):
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.IP_GEOLOCATION_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,city,regionName,country"},
            )
            data = resp.json()
        if data.get("status") != "success":
            return None
        parts = [p for p in (data.get("city"), data.get("regionName"), data.get("country")) if p]
        return ", ".join(parts) if parts else None
    except Exception as e:
        logger.debug(f"IP geolocation lookup failed for {ip} (non-fatal): {e}")
        return None


# ── Session lifecycle ─────────────────────────────────────────────────────

async def create_session(db: AsyncSession, request: Request, user_id: str) -> UserSession:
    """Creates and persists a new UserSession for a successful login/
    register/2fa-verify. The returned session's `id` is embedded as the
    "sid" claim in the access token (see core/auth.create_access_token) —
    that row is what get_current_user checks on every subsequent request
    to make remote logout actually take effect."""
    user_agent = request.headers.get("user-agent", "")
    device_info = parse_user_agent(user_agent)
    ip_address = get_client_ip(request)
    location = await geolocate_ip(ip_address)

    now = datetime.now(timezone.utc)
    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        device_name=device_info["device_name"],
        browser=device_info["browser"],
        os=device_info["os"],
        device_type=device_info["device_type"],
        user_agent=user_agent[:2000],
        ip_address=ip_address,
        location=location,
        created_at=now,
        last_active_at=now,
        expires_at=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def session_payload(session: UserSession, current_session_id: Optional[str]) -> dict:
    """Shared response shape for GET /auth/sessions."""
    return {
        "id":             session.id,
        "device_name":    session.device_name,
        "browser":        session.browser,
        "os":             session.os,
        "device_type":    session.device_type,
        "ip_address":     session.ip_address,
        "location":       session.location,
        "created_at":     session.created_at,
        "last_active_at": session.last_active_at,
        "is_current":     session.id == current_session_id,
    }
