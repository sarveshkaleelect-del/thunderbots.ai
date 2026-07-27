import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.core.database import get_db

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)   # FIX: auto_error=False lets us return 401 cleanly


def create_access_token(user_id: str, session_id: Optional[str] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    # NEW (Active Sessions & Device Management): "sid" ties this token to a
    # UserSession row (app/models/session.py) so it can be individually
    # revoked (remote logout / logout-all) before it would otherwise expire
    # — see get_current_user below. Optional and backward compatible: any
    # caller that doesn't pass session_id gets a token identical to before
    # this feature existed, and it is simply never checked against a
    # session (see get_current_user's `if session_id:` branch).
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


# NEW (Google SSO & 2FA): issued by /auth/login and /auth/google when the
# account has TOTP enabled — proves the password/Google credential checked
# out, without yet granting API access. type="mfa" is the load-bearing part:
# verify_token() below rejects it everywhere an "access" token is expected,
# so this token is only ever useful against POST /auth/2fa/verify.
def create_mfa_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.MFA_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "mfa"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_token_payload(token: str, expected_type: str = "access") -> Optional[dict]:
    """NEW (Active Sessions & Device Management): like verify_token, but
    returns the full JWT payload (so callers can read "sid" in addition to
    "sub") instead of just the user id. Never raises.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError as e:
        logger.debug(f"Token verification failed: {e}")
        return None


def verify_token(token: str, expected_type: str = "access") -> Optional[str]:
    """Returns user_id string or None. Never raises.

    NEW (Google SSO & 2FA): validates the "type" claim against
    `expected_type`. Existing tokens minted by create_access_token already
    carried type="access", so this is fully backward compatible for every
    current caller (get_current_user, the WebSocket auth in chat_ws.py) —
    it only starts *rejecting* the new type="mfa" tokens from being usable
    as if they were full access tokens.
    """
    payload = decode_token_payload(token, expected_type)
    return payload.get("sub") if payload else None


def verify_mfa_token(token: str) -> Optional[str]:
    """NEW (Google SSO & 2FA): returns user_id if `token` is a valid,
    unexpired type="mfa" token, else None."""
    return verify_token(token, expected_type="mfa")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    FIX: HTTPBearer with auto_error=False means missing header returns
    credentials=None instead of raising 403. We convert that to a clean 401.
    """
    from app.models.user import User
    from app.models.session import UserSession

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token_payload(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    session_id = payload.get("sid")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # NEW (Admin Dashboard): a disabled account's existing token is rejected on
    # its very next request — an admin "Disable" action takes effect immediately
    # instead of waiting for the token to expire.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been disabled. Contact an administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # NEW (Active Sessions & Device Management): if the token carries a
    # session id, that UserSession row must still exist, be unrevoked, and
    # be unexpired — this is what makes remote logout / "log out other
    # devices" / "log out everywhere" take effect immediately instead of
    # waiting up to ACCESS_TOKEN_EXPIRE_MINUTES for the JWT to expire on
    # its own. Tokens minted before this feature shipped carry no "sid" at
    # all and skip this block entirely — zero behavior change for them.
    if session_id:
        sess_result = await db.execute(select(UserSession).where(UserSession.id == session_id))
        session = sess_result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not session or session.revoked_at is not None or session.expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This session has been signed out. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Best-effort, throttled activity heartbeat so the sessions list can
        # show a reasonably fresh "last active" time without turning every
        # authenticated request into an extra write. Never blocks or fails
        # the request if it errors.
        if (now - session.last_active_at) > timedelta(minutes=settings.SESSION_ACTIVITY_UPDATE_INTERVAL_MINUTES):
            try:
                session.last_active_at = now
                await db.commit()
            except Exception as e:
                logger.debug(f"Session activity heartbeat failed (non-fatal): {e}")
                await db.rollback()
        # Transient, non-persisted attribute — lets /auth/sessions and
        # /auth/logout know which session backs *this* request without
        # changing get_current_user's return type (it's depended on by
        # every authenticated route in the app as `User`).
        user.current_session_id = session_id
    else:
        user.current_session_id = None

    return user


async def get_current_admin_user(
    user=Depends(get_current_user),
):
    """NEW (Admin Dashboard): gates every /api/v1/admin/* route. Requires a
    valid, active session (via get_current_user) AND is_admin=True."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
