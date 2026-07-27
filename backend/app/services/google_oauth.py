"""
ThunderBots Google SSO Service (NEW)

Purely additive module — does not import from or modify app/engine/*
(Workflow Runtime), app/core/auth.py (Authentication), app/knowledge/*
(Knowledge Base), or the AI Engine.

Verifies the ID token ("credential") produced client-side by Google
Identity Services (https://accounts.google.com/gsi/client) against
Google's published signing keys — no OAuth client *secret*, redirect flow,
or extra round trip to Google is needed server-side. This is Google's
recommended flow for "Sign in with Google" on a single-page app.

Verification is delegated entirely to the `google-auth` library
(google.oauth2.id_token.verify_oauth2_token), which:
  - fetches and caches Google's current JWKS,
  - checks the token signature, expiry, and issuer,
  - and — because we pass `audience=` — checks the token was actually
    issued for *this* app's OAuth client ID, not some other Google-integrated
    app that happens to accept the same user's sign-in.
"""
from __future__ import annotations

import logging
from typing import TypedDict

from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings

logger = logging.getLogger(__name__)

_VALID_ISSUERS = ("accounts.google.com", "https://accounts.google.com")

# A single shared transport/cert-cache instance — google-auth caches
# Google's JWKS response in-memory according to its Cache-Control headers,
# so reusing this across requests avoids refetching certs on every login.
_google_request = google_requests.Request()


class GoogleTokenError(Exception):
    """Raised when a Google credential fails verification for any reason
    (bad signature, expired, wrong audience/issuer, or Google SSO isn't
    configured on this server)."""


class GoogleIdentity(TypedDict):
    google_id: str
    email: str
    email_verified: bool
    name: str


def verify_google_id_token(credential: str) -> GoogleIdentity:
    """Verifies `credential` (the JWT ID token from Google Identity
    Services) and returns the identity it asserts. Raises GoogleTokenError
    on any failure — callers should surface that as 401/503, never fall
    back to trusting an unverified token."""
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleTokenError("Google Sign-In is not configured on this server")
    if not credential:
        raise GoogleTokenError("Missing Google credential")

    try:
        idinfo = google_id_token.verify_oauth2_token(
            credential,
            _google_request,
            audience=settings.GOOGLE_CLIENT_ID,
        )
    except (GoogleAuthError, ValueError) as e:
        logger.info(f"Google ID token verification failed: {type(e).__name__}: {e}")
        raise GoogleTokenError("Invalid or expired Google credential") from e

    # verify_oauth2_token already enforces this, but checking explicitly
    # here keeps the guarantee legible and independent of library internals.
    if idinfo.get("iss") not in _VALID_ISSUERS:
        raise GoogleTokenError("Invalid Google credential issuer")

    email = idinfo.get("email")
    sub = idinfo.get("sub")
    if not email or not sub:
        raise GoogleTokenError("Google credential is missing required claims")

    return GoogleIdentity(
        google_id=sub,
        email=email,
        email_verified=bool(idinfo.get("email_verified", False)),
        name=idinfo.get("name") or email.split("@")[0],
    )
