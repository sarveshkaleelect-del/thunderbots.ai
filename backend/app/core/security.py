"""
ThunderBots password hashing — v6 authentication fix.

ROOT CAUSE: passlib==1.7.4 is incompatible with bcrypt>=4.0.0.
- bcrypt 4.x removed the private bcrypt.__about__ attribute passlib reads at
  import time, raising AttributeError and preventing the context from loading.
- bcrypt 4.x also added a hard 72-byte enforcement that fires on passlib's
  internal secret encoding, raising:
      ValueError: password cannot be longer than 72 bytes
      passlib.handlers.bcrypt._bcrypt.hashpw(secret, config)
  This made every login and registration fail with a 500 that surfaces as
  "Invalid email or password." to the user.

FIX: drop passlib entirely and call bcrypt directly. bcrypt's own API is
stable, requires no intermediary, and works correctly on Python 3.12.
All existing $2b$12$ hashes stored in the database remain fully verifiable —
bcrypt's hash format is self-contained and cross-version compatible, so no
database migration is needed.
"""
import logging
import bcrypt

logger = logging.getLogger(__name__)

# Work factor — 12 is the OWASP-recommended minimum for bcrypt (2024).
_BCRYPT_ROUNDS = 12


def hash_password(plaintext: str) -> str:
    """
    Hash a plaintext password with bcrypt. Returns a UTF-8 string suitable
    for storage. Raises ValueError on empty input.
    """
    if not plaintext:
        raise ValueError("Password must not be empty")
    # bcrypt.hashpw requires bytes; encode to UTF-8 first.
    # bcrypt has a hard 72-byte limit on input — enforce it explicitly here
    # so the error is clear rather than silently truncating.
    encoded = plaintext.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password must not exceed 72 bytes when encoded as UTF-8")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(encoded, salt).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.
    Returns False on any mismatch or error — never raises.
    Supports both $2b$ (current) and $2a$/$2y$ (legacy) hash prefixes.
    """
    if not plaintext or not hashed:
        return False
    try:
        return bcrypt.checkpw(
            plaintext.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except Exception as e:
        logger.warning(f"Password verification error: {type(e).__name__}: {e}")
        return False


# Constant-time dummy hash for timing-safe login (prevents user enumeration
# via response-time differences when the email doesn't exist in the database).
# Pre-computed so every failed login attempt takes approximately the same time
# as a real verification, regardless of whether the user exists.
_DUMMY_HASH = hash_password("thunderbots-dummy-password-for-timing-safety")
