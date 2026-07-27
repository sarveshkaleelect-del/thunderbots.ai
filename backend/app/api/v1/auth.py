"""
ThunderBots Auth API — v6 authentication fix.
Replaces passlib.CryptContext with direct bcrypt via app.core.security,
fixing the passlib==1.7.4 / bcrypt>=4.0.0 incompatibility that caused
every login and registration to fail with a 500 on Python 3.12.

NEW (Email & Notification Service): registration now fires a welcome email
and this module gains /forgot-password + /reset-password. Both send/verify
paths run through app.services.email_service and are purely additive — no
change to the existing register/login/me behavior or response shapes.

NEW (Google SSO & 2FA): adds POST /google (Sign in with Google) and the
/2fa/* family (setup, enable, disable, status, verify, backup-codes). Both
features are strictly additive and off by default:
  - Google Sign-In only activates once GOOGLE_CLIENT_ID is configured.
  - TOTP 2FA is opt-in per user (User.totp_enabled defaults False) — an
    account that never visits Settings -> Security sees zero behavior
    change from /login, /register, or /me.
When 2FA *is* enabled, /login and /google no longer return an access token
directly; they return {"mfa_required": true, "mfa_token": "..."} and the
client must complete POST /2fa/verify with a TOTP or backup code to receive
the actual access token. This is the only behavior change visible to an
existing integration, and only for accounts that explicitly opted in.

NEW (Email Verification — Phase 1): registration now also issues a signup
verification email and this module gains /verify-email + /resend-verification.
Both are purely additive: nothing currently requires is_email_verified to be
true for login, /me, or any other route, so no existing or new caller is
blocked by this. Google Sign-In accounts are marked verified automatically
since Google has already asserted the email.

NEW (Active Sessions & Device Management — Phase 2): every route that issues
a real access token (register, login, google, 2fa/verify) now also creates a
UserSession row (app/models/session.py) capturing device/browser/OS, IP, and
best-effort location, and embeds its id as the token's "sid" claim (see
core/auth.create_access_token / get_current_user). This module also gains:
  - GET    /sessions              list this account's active sessions
  - DELETE /sessions/{session_id} remote logout of one specific session
  - POST   /sessions/revoke-all   log out every OTHER session (keeps this one)
  - POST   /logout                log out the current session
  - POST   /logout-all            log out every session, including this one
None of this changes the shape or behavior of the existing auth responses —
a session is just quietly created alongside the access token that was
already being returned.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.core.database import get_db
from app.core.auth import create_access_token, create_mfa_token, verify_mfa_token, get_current_user
from app.core.security import hash_password, verify_password, _DUMMY_HASH
from app.core.rate_limit import rate_limiter
from app.models.user import User
from app.models.notification import PasswordResetToken, EmailVerificationToken
from app.models.session import UserSession
from app.services import email_service, totp_service, google_oauth, session_service, audit_service
from app.services.audit_service import Action

router = APIRouter()
logger = logging.getLogger(__name__)

# SECURITY FIX: brute-force / credential-stuffing protection. 10 attempts per
# 5 minutes per IP is generous for a real user (typos) while making automated
# password-guessing impractical. See app/core/rate_limit.py for details.
_login_rate_limit = Depends(rate_limiter("login", limit=10, window_seconds=300))
_register_rate_limit = Depends(rate_limiter("register", limit=10, window_seconds=300))
# NEW: forgot-password is unauthenticated and email-enumerable by design (it
# always returns the same generic response), but still rate-limited per IP
# so it can't be used to mass-spam arbitrary inboxes with reset emails.
_forgot_password_rate_limit = Depends(rate_limiter("forgot_password", limit=5, window_seconds=300))
_reset_password_rate_limit = Depends(rate_limiter("reset_password", limit=10, window_seconds=300))
# NEW (Google SSO & 2FA): google auth is unauthenticated like /login, so it
# gets the same class of per-IP protection. The 2FA code-verification
# endpoints guard a 6-digit (1-in-a-million) or backup-code secret, so they
# are rate-limited tightly regardless of whether the caller is
# authenticated (2fa/enable, /disable, /backup-codes/regenerate) or not
# (2fa/verify) — a stolen access token or mfa_token alone must not be
# enough to brute-force past 2FA.
_google_rate_limit = Depends(rate_limiter("google_auth", limit=20, window_seconds=300))
_mfa_verify_rate_limit = Depends(rate_limiter("mfa_verify", limit=10, window_seconds=300))
_totp_code_rate_limit = Depends(rate_limiter("totp_code", limit=10, window_seconds=300))
# NEW (Email Verification): resend is unauthenticated and email-enumerable
# by design (always returns the same generic response), rate-limited per IP
# like forgot-password. verify-email just consumes a token, but is still
# rate-limited so a token can't be brute-forced.
_resend_verification_rate_limit = Depends(rate_limiter("resend_verification", limit=5, window_seconds=300))
_verify_email_rate_limit = Depends(rate_limiter("verify_email", limit=20, window_seconds=300))


class RegisterRequest(BaseModel):
    name:     str
    email:    EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token:        str
    new_password: str


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


# ── Google SSO & 2FA request models (NEW) ────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    credential: str  # Google Identity Services ID token (JWT)


class TOTPCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=11)  # "123456" or "ABCDE-FGHJK" backup code


class TOTPDisableRequest(BaseModel):
    password: str | None = None
    code:     str | None = None


class MFAVerifyRequest(BaseModel):
    mfa_token: str
    code:      str = Field(..., min_length=6, max_length=11)


def _user_payload(user: User) -> dict:
    """Shared response shape for register/login/me/google/2fa-verify.
    NEW (Google SSO & 2FA): totp_enabled/google_linked/has_password are
    additive fields — existing clients that only read the fields they
    already know about are unaffected."""
    return {
        "id":            user.id,
        "name":          user.name,
        "email":         user.email,
        "preferences":   user.preferences or {},
        "is_admin":      user.is_admin,
        "is_active":     user.is_active,
        "totp_enabled":  user.totp_enabled,
        "google_linked": bool(user.google_id),
        "has_password":  user.password is not None,
        "is_email_verified": user.is_email_verified,
    }


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl=_register_rate_limit,
):
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )
    # Enforce the 72-byte bcrypt limit up-front with a clear message
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must not exceed 72 characters",
        )

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    # NEW (Admin Dashboard): the very first account ever created on a fresh
    # platform install becomes an admin automatically — otherwise there would
    # be no way to reach /admin at all on a brand-new deployment. Every
    # subsequent registration is a regular (is_admin=False) user; admin status
    # after that point is only ever granted by an existing admin.
    user_count = await db.execute(select(func.count()).select_from(User))
    is_first_user = (user_count.scalar_one() or 0) == 0

    try:
        hashed = hash_password(payload.password)
    except Exception as e:
        logger.error(f"Password hashing failed during registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed — could not process password",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        password=hashed,
        preferences={},
        is_admin=is_first_user,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # NEW (Active Sessions & Device Management): one UserSession row per
    # issued access token — see module docstring.
    session = await session_service.create_session(db, request, user.id)
    token = create_access_token(user.id, session_id=session.id)
    logger.info(f"New user registered: {user.email}" + (" (admin)" if user.is_admin else ""))
    # NEW (Audit Log — v58): additive, best-effort — never blocks registration.
    await audit_service.record(
        db, Action.REGISTER, actor=user, target_type="user", target_id=user.id,
        target_label=user.email, request=request,
        metadata={"is_admin": user.is_admin},
    )
    # NEW (Email & Notification Service): fire-and-forget welcome email —
    # runs after the response is sent and never blocks/fails registration.
    background_tasks.add_task(email_service.send_welcome_email, user.email, user.name)
    # NEW (Email Verification): issue a verification token and email it.
    # Purely additive — registration still succeeds and returns an access
    # token even if this fails, exactly as it did before this feature.
    await _issue_and_send_verification_email(db, background_tasks, user)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": _user_payload(user),
    }


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl=_login_rate_limit,
):
    result = await db.execute(select(User).where(User.email == payload.email))
    user   = result.scalar_one_or_none()

    # Timing-safe: always run a bcrypt verify regardless of whether the user
    # exists, to prevent user-enumeration via response-time differences.
    # NEW (Google SSO): a Google-only account has password=None — routed to
    # the same dummy-hash path (rather than short-circuiting) so a
    # Google-only account can't be distinguished from a nonexistent one by
    # response timing either.
    stored = user.password if (user and user.password) else _DUMMY_HASH
    valid  = verify_password(payload.password, stored)

    if not user or not valid:
        # NEW (Audit Log — v58): failed logins are recorded without an
        # actor_id (nothing to link to if the email doesn't match a real
        # account) but with the attempted email for investigation.
        await audit_service.record(
            db, Action.LOGIN_FAILED, actor_type="user",
            actor_email=payload.email, status="failure",
            status_detail="Invalid email or password", request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # NEW (Admin Dashboard): a disabled account can't obtain a new token either.
    if not user.is_active:
        await audit_service.record(
            db, Action.LOGIN_FAILED, actor=user, status="failure",
            status_detail="Account disabled", request=request,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled. Contact an administrator.",
        )

    # NEW (2FA): password checked out, but the account requires a TOTP/backup
    # code before an access token is issued. Response shape intentionally
    # differs from the block below — see module docstring.
    if user.totp_enabled:
        logger.info(f"Password verified for {user.email}, awaiting 2FA code")
        return {"mfa_required": True, "mfa_token": create_mfa_token(user.id)}

    session = await session_service.create_session(db, request, user.id)
    token = create_access_token(user.id, session_id=session.id)
    logger.info(f"User logged in: {user.email}")
    await audit_service.record(db, Action.LOGIN, actor=user, request=request)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": _user_payload(user),
    }


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return _user_payload(current_user)


# ── Deployment diagnostics (NEW) ─────────────────────────────────────────────
# Unauthenticated, read-only, and exposes no secrets — only whether each
# piece of auth-related config is *present*, never its value. Added because
# the most common real-world cause of "login/registration doesn't work" on a
# freshly deployed environment (Vercel, Railway, Render, etc.) is a missing
# or mismatched environment variable, not a code defect — and that class of
# problem is invisible from the browser (it just looks like "Google button
# missing" or "network error") and easy to mix up with an actual bug. Hitting
# GET /api/v1/auth/config-status against the deployed backend immediately
# tells you which side (frontend env, backend env, or CORS allow-list) is
# misconfigured without reading logs or guessing.
@router.get("/config-status")
async def auth_config_status(request: Request):
    origin = request.headers.get("origin")
    return {
        "environment": "production" if not settings.DEBUG else "development",
        "google_sso": {
            "backend_client_id_configured": bool(settings.GOOGLE_CLIENT_ID),
            "note": (
                "backend_client_id_configured must be true AND the frontend's "
                "NEXT_PUBLIC_GOOGLE_CLIENT_ID must be set to the SAME client ID "
                "for the Google button to appear and for /auth/google to succeed. "
                "The frontend value can't be checked from here — it's baked into "
                "the browser bundle at build time, not sent to this API."
            ),
        },
        "cors": {
            "configured_origins": settings.CORS_ORIGINS,
            "request_origin": origin,
            "request_origin_allowed": (origin in settings.CORS_ORIGINS) if origin else None,
            "note": (
                "If request_origin_allowed is false, add your deployed frontend's "
                "exact origin (e.g. https://your-app.vercel.app, no trailing "
                "slash) to CORS_ORIGINS on the backend."
            ),
        },
        "secret_key_is_placeholder": settings.SECRET_KEY == "change-me-in-production-min-32-chars!!",
    }


# ── Password reset (NEW — Email & Notification Service) ─────────────────────
# Token model: PasswordResetToken (app/models/notification.py). Only a
# SHA-256 hash of the raw token is ever persisted — the raw token exists
# only in the outbound email link, same principle as never storing a
# plaintext password. Single-use (used_at) and time-boxed (expires_at).

_GENERIC_FORGOT_RESPONSE = {
    "message": "If an account with that email exists, a password reset link has been sent."
}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _rl=_forgot_password_rate_limit,
):
    """Always returns the same generic response regardless of whether the
    email matches an account or is currently active — this prevents using
    the endpoint to enumerate registered email addresses."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return _GENERIC_FORGOT_RESPONSE

    # Invalidate any previous unused tokens for this user so only the most
    # recently requested link is valid.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
    )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()

    background_tasks.add_task(email_service.send_password_reset_email, user.email, user.name, raw_token)
    logger.info(f"Password reset requested for {user.email}")
    audit_service.record_bg(background_tasks, Action.PASSWORD_RESET_REQUESTED, actor=user)
    return _GENERIC_FORGOT_RESPONSE


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    _rl=_reset_password_rate_limit,
):
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )
    if len(payload.new_password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must not exceed 72 characters",
        )

    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    reset_token = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not reset_token or reset_token.used_at is not None or reset_token.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired",
        )

    user = await db.get(User, reset_token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired",
        )

    try:
        user.password = hash_password(payload.new_password)
    except Exception as e:
        logger.error(f"Password hashing failed during reset: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed — could not process password",
        )

    reset_token.used_at = now
    await db.commit()
    logger.info(f"Password reset completed for {user.email}")
    await audit_service.record(db, Action.PASSWORD_RESET_COMPLETED, actor=user)
    return {"message": "Your password has been reset. You can now log in with your new password."}


# ── Email Verification (NEW) ─────────────────────────────────────────────
# Token model: EmailVerificationToken (app/models/notification.py). Same
# hash-only-storage / single-use / time-boxed pattern as password reset.
# Verifying is purely additive right now — no route currently checks
# is_email_verified, so an unverified account can still log in and use the
# product exactly as before this feature. That leaves room for a later
# phase to add enforcement without another migration.

_GENERIC_RESEND_RESPONSE = {
    "message": "If an account with that email exists and isn't already verified, a verification link has been sent."
}


async def _issue_and_send_verification_email(
    db: AsyncSession, background_tasks: BackgroundTasks, user: User
) -> None:
    """Shared by /register and /resend-verification. Invalidates any
    previous unused token for this user, issues a new one, and schedules
    the send as a background task."""
    await db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=datetime.now(timezone.utc))
    )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)

    db.add(EmailVerificationToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()

    background_tasks.add_task(email_service.send_verification_email, user.email, user.name, raw_token)


@router.post("/verify-email")
async def verify_email(
    payload: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    _rl=_verify_email_rate_limit,
):
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    result = await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash))
    verification_token = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not verification_token or verification_token.used_at is not None or verification_token.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired",
        )

    user = await db.get(User, verification_token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired",
        )

    verification_token.used_at = now
    if not user.is_email_verified:
        user.is_email_verified = True
    await db.commit()

    logger.info(f"Email verified for {user.email}")
    await audit_service.record(db, Action.EMAIL_VERIFIED, actor=user)
    return {"message": "Your email address has been verified.", "is_email_verified": True}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    payload: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _rl=_resend_verification_rate_limit,
):
    """Always returns the same generic response regardless of whether the
    email matches an account, is already verified, or is inactive — same
    anti-enumeration reasoning as /forgot-password."""
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not user.is_active or user.is_email_verified:
        return _GENERIC_RESEND_RESPONSE

    await _issue_and_send_verification_email(db, background_tasks, user)
    logger.info(f"Verification email resent for {user.email}")
    audit_service.record_bg(background_tasks, Action.EMAIL_VERIFICATION_SENT, actor=user)
    return _GENERIC_RESEND_RESPONSE


# ── Google SSO (NEW) ──────────────────────────────────────────────────────
# Verifies a Google Identity Services ID token entirely server-side (no
# OAuth client secret or extra redirect flow — see services/google_oauth.py)
# and either logs in a linked account, links Google onto a matching
# email/password account, or creates a brand-new account. Honors 2FA the
# same way /login does: if the resolved account has totp_enabled, this
# returns {"mfa_required": true, ...} instead of an access token.

@router.post("/google")
async def google_login(
    payload: GoogleAuthRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl=_google_rate_limit,
):
    try:
        identity = google_oauth.verify_google_id_token(payload.credential)
    except google_oauth.GoogleTokenError as e:
        detail = str(e)
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if "not configured" in detail
            else status.HTTP_401_UNAUTHORIZED
        )
        raise HTTPException(status_code=code, detail=detail)

    if not identity["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your Google account's email address is not verified",
        )

    result = await db.execute(
        select(User).where(
            (User.google_id == identity["google_id"]) | (User.email == identity["email"])
        )
    )
    user = result.scalar_one_or_none()
    is_new_user = False

    if user is None:
        # NEW (Admin Dashboard rule, reused): first account on a fresh
        # install becomes an admin, same as /register.
        user_count = await db.execute(select(func.count()).select_from(User))
        is_first_user = (user_count.scalar_one() or 0) == 0
        user = User(
            name=identity["name"],
            email=identity["email"],
            password=None,
            google_id=identity["google_id"],
            preferences={},
            is_admin=is_first_user,
            # NEW (Email Verification): Google has already asserted this
            # exact email is verified (checked above), so a Google-created
            # account skips the email-link step entirely.
            is_email_verified=True,
        )
        db.add(user)
        is_new_user = True
    else:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account has been disabled. Contact an administrator.",
            )
        if not user.google_id:
            # Linking: an existing email/password account signing in with
            # Google for the first time. Safe to link automatically because
            # Google has already asserted this exact email is verified.
            user.google_id = identity["google_id"]
        # NEW (Email Verification): Google re-asserts this email is
        # verified on every sign-in, so linking/using Google also verifies
        # an account that hadn't clicked its original signup link yet.
        if not user.is_email_verified:
            user.is_email_verified = True

    await db.commit()
    await db.refresh(user)

    if is_new_user:
        logger.info(f"New user registered via Google: {user.email}" + (" (admin)" if user.is_admin else ""))
        background_tasks.add_task(email_service.send_welcome_email, user.email, user.name)
        audit_service.record_bg(
            background_tasks, Action.GOOGLE_SSO_LOGIN, actor=user, request=request,
            metadata={"is_new_user": True, "is_admin": user.is_admin},
        )
    else:
        logger.info(f"User signed in via Google: {user.email}")
        audit_service.record_bg(
            background_tasks, Action.GOOGLE_SSO_LOGIN, actor=user, request=request,
            metadata={"is_new_user": False},
        )

    if user.totp_enabled:
        return {"mfa_required": True, "mfa_token": create_mfa_token(user.id)}

    session = await session_service.create_session(db, request, user.id)
    token = create_access_token(user.id, session_id=session.id)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": _user_payload(user),
    }


# ── Two-Factor Authentication (NEW — Google SSO & 2FA) ───────────────────────
# Setup is a two-step confirm flow: /2fa/setup generates and stores an
# encrypted secret but leaves totp_enabled=False; /2fa/enable requires one
# valid code against that secret before flipping totp_enabled=True. This
# means a user can never lock themselves out by saving a secret their
# authenticator app didn't actually end up scanning correctly.

@router.post("/2fa/setup")
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled",
        )

    secret = totp_service.generate_secret()
    current_user.totp_secret = totp_service.encrypt_totp_secret(secret)
    await db.commit()

    uri = totp_service.get_provisioning_uri(secret, current_user.email)
    logger.info(f"2FA setup started for {current_user.email}")
    return {
        "secret":       secret,
        "otpauth_url":  uri,
        "qr_code_svg":  totp_service.generate_qr_svg(uri),
    }


@router.post("/2fa/enable")
async def enable_2fa(
    payload: TOTPCodeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl=_totp_code_rate_limit,
):
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled",
        )
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start setup with POST /auth/2fa/setup first",
        )

    secret = totp_service.decrypt_totp_secret(current_user.totp_secret)
    if not totp_service.verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    backup_codes = totp_service.generate_backup_codes()
    current_user.totp_backup_codes = totp_service.hash_backup_codes(backup_codes)
    current_user.totp_enabled = True
    await db.commit()

    logger.info(f"2FA enabled for {current_user.email}")
    background_tasks.add_task(
        email_service.send_usage_alert_email,
        current_user.email,
        current_user.name,
        "Two-factor authentication was enabled",
        "Two-factor authentication was just turned on for your account. "
        "If you didn't do this, reset your password immediately and contact support.",
    )
    audit_service.record_bg(background_tasks, Action.TWO_FA_ENABLED, actor=current_user)
    return {
        "message":      "Two-factor authentication is now enabled.",
        "backup_codes": backup_codes,
    }


@router.post("/2fa/disable")
async def disable_2fa(
    payload: TOTPDisableRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl=_totp_code_rate_limit,
):
    if not current_user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is not enabled")

    # Re-authentication required to disable: either the account password, or
    # a currently valid TOTP/backup code. Prevents a briefly-stolen access
    # token from silently turning off 2FA.
    verified = False
    if payload.password and current_user.password:
        verified = verify_password(payload.password, current_user.password)
    if not verified and payload.code and current_user.totp_secret:
        secret = totp_service.decrypt_totp_secret(current_user.totp_secret)
        verified = totp_service.verify_totp_code(secret, payload.code)
        if not verified:
            remaining = totp_service.consume_backup_code(current_user.totp_backup_codes, payload.code)
            if remaining is not None:
                verified = True
                current_user.totp_backup_codes = remaining

    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password or verification code")

    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_backup_codes = None
    await db.commit()

    logger.info(f"2FA disabled for {current_user.email}")
    background_tasks.add_task(
        email_service.send_usage_alert_email,
        current_user.email,
        current_user.name,
        "Two-factor authentication was disabled",
        "Two-factor authentication was just turned off for your account. "
        "If you didn't do this, secure your account immediately.",
    )
    audit_service.record_bg(background_tasks, Action.TWO_FA_DISABLED, actor=current_user)
    return {"message": "Two-factor authentication has been disabled."}


@router.get("/2fa/status")
async def get_2fa_status(current_user: User = Depends(get_current_user)):
    return {
        "enabled": current_user.totp_enabled,
        "backup_codes_remaining": (
            totp_service.count_remaining_backup_codes(current_user.totp_backup_codes)
            if current_user.totp_enabled else 0
        ),
    }


@router.post("/2fa/backup-codes/regenerate")
async def regenerate_backup_codes(
    payload: TOTPCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl=_totp_code_rate_limit,
):
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is not enabled")

    secret = totp_service.decrypt_totp_secret(current_user.totp_secret)
    if not totp_service.verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    backup_codes = totp_service.generate_backup_codes()
    current_user.totp_backup_codes = totp_service.hash_backup_codes(backup_codes)
    await db.commit()
    logger.info(f"2FA backup codes regenerated for {current_user.email}")
    await audit_service.record(db, Action.TWO_FA_BACKUP_CODES_REGENERATED, actor=current_user)
    return {"backup_codes": backup_codes}


@router.post("/2fa/verify")
async def verify_2fa(
    payload: MFAVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl=_mfa_verify_rate_limit,
):
    """Completes a login for an account with 2FA enabled. `mfa_token` is
    the short-lived token returned by /login or /google when the resolved
    account has totp_enabled=True (see core/auth.create_mfa_token /
    verify_mfa_token) — it cannot be used as a regular access token."""
    user_id = verify_mfa_token(payload.mfa_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This verification session has expired. Please log in again.",
        )

    user = await db.get(User, user_id)
    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This verification session has expired. Please log in again.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled. Contact an administrator.",
        )

    secret = totp_service.decrypt_totp_secret(user.totp_secret)
    valid = totp_service.verify_totp_code(secret, payload.code)

    if not valid:
        remaining = totp_service.consume_backup_code(user.totp_backup_codes, payload.code)
        if remaining is not None:
            valid = True
            user.totp_backup_codes = remaining
            await db.commit()

    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code")

    session = await session_service.create_session(db, request, user.id)
    token = create_access_token(user.id, session_id=session.id)
    logger.info(f"2FA verified, user logged in: {user.email}")
    await audit_service.record(db, Action.LOGIN, actor=user, request=request, metadata={"via": "2fa"})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": _user_payload(user),
    }


# ── Active Sessions & Device Management (NEW — Phase 2) ─────────────────────
# GET /sessions lists this account's currently-active (unrevoked, unexpired)
# sessions, each annotated with is_current so the frontend can label "This
# device" and disable its own revoke button. The remaining endpoints all
# revoke by setting revoked_at/revoked_reason — rows are never deleted, so
# they double as an audit trail — and take effect immediately on the next
# request through get_current_user (core/auth.py), not just when the JWT
# would otherwise have expired.

@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_active_at.desc())
    )
    sessions = result.scalars().all()
    current_session_id = getattr(current_user, "current_session_id", None)
    return [session_service.session_payload(s, current_session_id) for s in sessions]


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remote logout of one specific device/session. Revoking the session
    backing the *current* request is allowed (it simply logs this device
    out too, same as /logout) — there is no reason to special-case it."""
    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        session.revoked_reason = "remote_revoke"
        await db.commit()
        logger.info(f"Session {session_id} revoked for {current_user.email}")
        await audit_service.record(
            db, Action.SESSION_REVOKED, actor=current_user,
            target_type="user_session", target_id=session_id,
            metadata={"reason": "remote_revoke"},
        )

    return {"message": "Session signed out."}


@router.post("/sessions/revoke-all")
async def revoke_other_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """"Log out other devices" — revokes every active session for this
    account EXCEPT the one backing the current request."""
    current_session_id = getattr(current_user, "current_session_id", None)
    now = datetime.now(timezone.utc)

    stmt = update(UserSession).where(
        UserSession.user_id == current_user.id,
        UserSession.revoked_at.is_(None),
    )
    if current_session_id:
        stmt = stmt.where(UserSession.id != current_session_id)
    await db.execute(stmt.values(revoked_at=now, revoked_reason="logout_other_devices"))
    await db.commit()

    logger.info(f"All other sessions revoked for {current_user.email}")
    await audit_service.record(db, Action.SESSION_REVOKED, actor=current_user, metadata={"reason": "logout_other_devices"})
    return {"message": "You've been signed out of all other devices."}


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logs out the current device/session only. A token with no "sid"
    claim (minted before this feature shipped) has no session row to
    revoke — the client-side token deletion the frontend already performs
    on logout is what ends that session, exactly as before this feature."""
    current_session_id = getattr(current_user, "current_session_id", None)
    if current_session_id:
        await db.execute(
            update(UserSession)
            .where(UserSession.id == current_session_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc), revoked_reason="user_logout")
        )
        await db.commit()
    await audit_service.record(db, Action.LOGOUT, actor=current_user)
    return {"message": "Logged out."}


@router.post("/logout-all")
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """"Log out of all devices" — revokes every active session for this
    account, including the one making this request. The caller's own token
    stops working immediately afterward, same as everyone else's."""
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == current_user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc), revoked_reason="logout_all_devices")
    )
    await db.commit()
    logger.info(f"All sessions revoked (logout-all) for {current_user.email}")
    await audit_service.record(db, Action.LOGOUT_ALL, actor=current_user)
    return {"message": "You've been logged out of all devices."}

