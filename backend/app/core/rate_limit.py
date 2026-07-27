"""
Lightweight rate limiting for sensitive, unauthenticated endpoints
(login, register) — SECURITY FIX.

ROOT CAUSE: no rate limiting existed anywhere in the API, so /api/v1/auth/login
and /api/v1/auth/register could be hit an unlimited number of times per
second, enabling credential-stuffing / brute-force attacks against user
passwords and unbounded account-creation abuse.

Design: a simple fixed-window counter in Redis (already a required
dependency — no new package added). Keyed by client IP + route, so it adds
no per-request overhead beyond one INCR/EXPIRE round trip. Fails OPEN if
Redis is unavailable, consistent with how CacheService already degrades
elsewhere in this codebase — an outage of the cache layer must never be able
to lock every user out of login.
"""
import logging
from fastapi import HTTPException, Request, status

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def rate_limiter(key_prefix: str, limit: int, window_seconds: int):
    """Returns a FastAPI dependency enforcing `limit` requests per
    `window_seconds` per client IP for the given key_prefix."""

    async def _dependency(request: Request):
        redis = get_redis()
        if not redis:
            return  # fail open — no Redis means no rate limiting, not a 500
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{key_prefix}:{client_ip}"
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait a moment and try again.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Rate limiter check failed for {key}: {e}")
            return  # fail open on any Redis error

    return _dependency
