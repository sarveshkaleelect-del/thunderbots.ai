"""
ThunderBots TOTP Two-Factor Authentication Service (NEW)

Purely additive module — does not import from or modify app/engine/*
(Workflow Runtime), app/knowledge/* (Knowledge Base), or the AI Engine
beyond reusing its already-existing, already-shared encrypt_key/decrypt_key
Fernet helpers (same pattern services/whatsapp_service.py already
established for provider credentials).

Everything needed to add optional RFC 6238 TOTP 2FA to an account:
  - generate_secret / get_provisioning_uri / generate_qr_svg — setup screen
  - verify_totp_code                                          — 6-digit code
  - generate_backup_codes / hash_backup_codes / consume_backup_code — the
    one-time recovery codes shown once when 2FA is first enabled

Secrets at rest: the raw base32 TOTP secret is Fernet-encrypted before being
stored on User.totp_secret (identical cipher/key-derivation to provider API
keys — see services/ai_engine.py). Backup codes are never stored raw; only
a SHA-256 hash of each is kept, matching the PasswordResetToken.token_hash
convention already used in api/v1/auth.py.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import secrets
from typing import Optional

import pyotp
import qrcode
import qrcode.image.svg

from app.config import settings
from app.services.ai_engine import encrypt_key, decrypt_key  # reused as-is, not modified

logger = logging.getLogger(__name__)

# 32 base32 characters == 160 bits of entropy for the shared secret, well
# above the RFC 4226 §4 recommendation of 128 bits minimum.
_SECRET_LENGTH = 32
_BACKUP_CODE_COUNT = 10
# One clock step (30s) of tolerance on either side of "now" — absorbs
# minor clock drift between the server and the user's device without
# meaningfully widening the guessing window.
_VALID_WINDOW = 1


# ─────────────────────────────────────────────────────────────────────────────
# Secret encryption — thin, purpose-named wrappers over the shared Fernet
# helpers, same convention as services/whatsapp_service.py.
# ─────────────────────────────────────────────────────────────────────────────

def encrypt_totp_secret(plaintext: str) -> str:
    return encrypt_key(plaintext)


def decrypt_totp_secret(ciphertext: str) -> str:
    return decrypt_key(ciphertext)


# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

def generate_secret() -> str:
    """A fresh random base32 TOTP secret. Never persisted in the clear —
    callers must run it through encrypt_totp_secret before saving."""
    return pyotp.random_base32(length=_SECRET_LENGTH)


def get_provisioning_uri(secret: str, account_email: str) -> str:
    """otpauth://totp/... URI encoding the secret, account label, and
    issuer — what authenticator apps actually scan/import."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_email,
        issuer_name=settings.TOTP_ISSUER_NAME,
    )


def generate_qr_svg(otpauth_uri: str) -> str:
    """Renders the provisioning URI as an inline SVG string for the setup
    screen. Uses qrcode's SVG path image factory, which does NOT require
    Pillow — no new image/binary dependency for the backend."""
    img = qrcode.make(otpauth_uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────

def verify_totp_code(secret: str, code: str) -> bool:
    """Checks a 6-digit code against the current time step (±1 step for
    clock drift). Never raises — malformed input just fails to verify."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=_VALID_WINDOW)
    except Exception as e:
        logger.warning(f"TOTP verification error: {type(e).__name__}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Backup codes
# ─────────────────────────────────────────────────────────────────────────────

def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().replace("-", "").upper().encode("utf-8")).hexdigest()


def generate_backup_codes(count: int = _BACKUP_CODE_COUNT) -> list[str]:
    """Returns `count` fresh, human-typeable one-time codes, e.g.
    'A1B2C-D3E4F'. Callers must hash these with hash_backup_codes before
    persisting — the values returned here are shown to the user exactly
    once and never stored."""
    codes = []
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_backup_codes(codes: list[str]) -> str:
    """Serializes a list of hashed backup codes for storage in
    User.totp_backup_codes."""
    return json.dumps([_hash_code(c) for c in codes])


def consume_backup_code(stored_hashes_json: Optional[str], code: str) -> Optional[str]:
    """Checks `code` against the stored backup-code hashes. If it matches,
    returns the *updated* JSON string with that code removed (single-use)
    so the caller can persist it; returns None if there's no match (leaving
    the caller's existing value untouched) — callers must not overwrite
    totp_backup_codes unless this returns non-None."""
    if not stored_hashes_json or not code:
        return None
    try:
        hashes: list[str] = json.loads(stored_hashes_json)
    except (ValueError, TypeError):
        return None

    target = _hash_code(code)
    for h in hashes:
        if secrets.compare_digest(h, target):
            remaining = [x for x in hashes if x != h]
            return json.dumps(remaining)
    return None


def count_remaining_backup_codes(stored_hashes_json: Optional[str]) -> int:
    if not stored_hashes_json:
        return 0
    try:
        return len(json.loads(stored_hashes_json))
    except (ValueError, TypeError):
        return 0
