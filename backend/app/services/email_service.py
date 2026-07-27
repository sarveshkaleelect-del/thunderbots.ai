"""
ThunderBots Email & Notification Service (NEW)

Purely additive module — does not import from or modify app/engine/*
(Workflow Runtime), app/services/ai_engine.py (AI Engine), app/knowledge/*
(Knowledge Base pipeline), or any Builder/Nodes business logic. Follows the
same conventions already established by app/services/whatsapp_service.py:
a provider abstraction with retry/backoff, structured logging, and no hard
dependency on any single third party.

── Providers ──────────────────────────────────────────────────────────────
EMAIL_PROVIDER (see app/config.py) selects the transport at runtime:
  - "console"  (default) logs the rendered email instead of sending it.
               Zero configuration required — nothing breaks in local dev or
               on a fresh deploy that hasn't set up email yet.
  - "smtp"     sends via any standard SMTP relay (Amazon SES, Postmark,
               Mailgun, Gmail relay, etc.) using only the Python standard
               library (smtplib), run off the event loop via
               asyncio.to_thread — no new dependency required.
  - "sendgrid" sends via SendGrid's HTTP API using httpx, which is already
               a dependency of this project (used for Ollama) — no SendGrid
               SDK required.
If the selected provider is missing required credentials, this module logs
a warning and safely falls back to "console" rather than raising on import
or at startup, so a misconfiguration here can never take down the API.

── Reliability ─────────────────────────────────────────────────────────────
Every send goes through `send_email`, which retries transient failures up
to 3 times with exponential backoff (0.5s, 1.5s, 3s) and records the
outcome (sent/failed) to the email_logs table for observability — logging
failures never raise or block the send path itself.

── Usage ────────────────────────────────────────────────────────────────
Callers in the API layer (auth.py, teams.py, admin.py, main.py) should
always invoke these functions via FastAPI's BackgroundTasks (already the
established pattern in workflows.py / knowledge.py) so email delivery never
adds latency to — or can fail — the triggering request.
"""
from __future__ import annotations

import asyncio
import html as _html_module
import logging
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Optional

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.5, 3.0)


class EmailSendError(RuntimeError):
    """Raised by a provider when a send attempt fails."""

    def __init__(self, message: str, provider: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


# ─────────────────────────────────────────────────────────────────────────────
# Template rendering
# ─────────────────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"</(p|div|tr|h1|h2|h3|li)\s*>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def _html_to_text(html_body: str) -> str:
    """Best-effort plain-text fallback derived from the rendered HTML, for
    mail clients / spam filters that prefer (or require) a text/plain part."""
    text = _SCRIPT_STYLE_RE.sub("", html_body)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _html_module.unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    out, blank_run = [], 0
    for ln in lines:
        if ln:
            out.append(ln)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run <= 1:
                out.append("")
    return "\n".join(out).strip()


def render_template(template_name: str, context: dict) -> tuple[str, str]:
    template = _jinja_env.get_template(f"{template_name}.html")
    full_context = {
        "app_name": settings.APP_NAME,
        "app_base_url": settings.APP_BASE_URL,
        **context,
    }
    html_body = template.render(**full_context)
    text_body = _html_to_text(html_body)
    return html_body, text_body


# ─────────────────────────────────────────────────────────────────────────────
# Providers
# ─────────────────────────────────────────────────────────────────────────────

class EmailProvider:
    async def send(self, to_email: str, to_name: Optional[str], subject: str, html_body: str, text_body: str) -> None:
        raise NotImplementedError


class ConsoleEmailProvider(EmailProvider):
    """Dev-safe fallback — logs instead of sending. Never raises."""

    async def send(self, to_email: str, to_name: Optional[str], subject: str, html_body: str, text_body: str) -> None:
        logger.info(
            f"[EmailService:console] EMAIL_PROVIDER not configured for real delivery — "
            f"would send to={to_email!r} subject={subject!r}"
        )


class SMTPEmailProvider(EmailProvider):
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.use_ssl = settings.SMTP_USE_SSL
        self.use_tls = settings.SMTP_USE_TLS

    def _send_sync(self, msg: MIMEMultipart, to_email: str) -> None:
        if self.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=15) as server:
                if self.username:
                    server.login(self.username, self.password or "")
                server.sendmail(settings.EMAIL_FROM_ADDRESS, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                if self.use_tls:
                    server.starttls(context=ssl.create_default_context())
                if self.username:
                    server.login(self.username, self.password or "")
                server.sendmail(settings.EMAIL_FROM_ADDRESS, [to_email], msg.as_string())

    async def send(self, to_email: str, to_name: Optional[str], subject: str, html_body: str, text_body: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM_ADDRESS))
        msg["To"] = formataddr((to_name or "", to_email))
        if settings.EMAIL_REPLY_TO:
            msg["Reply-To"] = settings.EMAIL_REPLY_TO
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        try:
            await asyncio.to_thread(self._send_sync, msg, to_email)
        except Exception as e:
            raise EmailSendError(str(e), provider="smtp") from e


class SendGridEmailProvider(EmailProvider):
    _ENDPOINT = "https://api.sendgrid.com/v3/mail/send"

    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY

    async def send(self, to_email: str, to_name: Optional[str], subject: str, html_body: str, text_body: str) -> None:
        payload = {
            "personalizations": [{"to": [{"email": to_email, "name": to_name or ""}]}],
            "from": {"email": settings.EMAIL_FROM_ADDRESS, "name": settings.EMAIL_FROM_NAME},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        }
        if settings.EMAIL_REPLY_TO:
            payload["reply_to"] = {"email": settings.EMAIL_REPLY_TO}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(self._ENDPOINT, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise EmailSendError(
                    f"SendGrid error {resp.status_code}: {resp.text[:300]}",
                    provider="sendgrid",
                    status_code=resp.status_code,
                )
        except EmailSendError:
            raise
        except Exception as e:
            raise EmailSendError(str(e), provider="sendgrid") from e


def _get_provider() -> EmailProvider:
    provider = (settings.EMAIL_PROVIDER or "console").lower().strip()
    if provider == "sendgrid":
        if settings.SENDGRID_API_KEY:
            return SendGridEmailProvider()
        logger.warning("EMAIL_PROVIDER=sendgrid but SENDGRID_API_KEY is not set — falling back to console logging")
    elif provider == "smtp":
        if settings.SMTP_HOST:
            return SMTPEmailProvider()
        logger.warning("EMAIL_PROVIDER=smtp but SMTP_HOST is not set — falling back to console logging")
    elif provider != "console":
        logger.warning(f"Unknown EMAIL_PROVIDER={provider!r} — falling back to console logging")
    return ConsoleEmailProvider()


# ─────────────────────────────────────────────────────────────────────────────
# Delivery logging (best-effort — never blocks or fails a send)
# ─────────────────────────────────────────────────────────────────────────────

async def _log_email(email_type: str, to_email: str, status_: str, provider: str = "", error: str = "") -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.notification import EmailLog

        async with AsyncSessionLocal() as db:
            db.add(EmailLog(
                email_type=email_type,
                to_email=to_email,
                status=status_,
                provider=provider,
                error=(error or "")[:2000],
            ))
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist email_logs row (non-fatal): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Core send path
# ─────────────────────────────────────────────────────────────────────────────

async def send_email(
    *,
    to_email: str,
    subject: str,
    template_name: str,
    context: dict,
    to_name: Optional[str] = None,
    email_type: str = "generic",
) -> bool:
    """Render `template_name` with `context` and send it, retrying transient
    failures. Returns True on success, False otherwise. Never raises —
    email delivery problems must never break the calling request/task."""
    if not to_email:
        logger.warning(f"send_email called with no recipient (type={email_type}) — skipped")
        return False

    try:
        html_body, text_body = render_template(template_name, context)
    except Exception as e:
        logger.error(f"Email template render failed (type={email_type}, template={template_name}): {e}", exc_info=True)
        await _log_email(email_type, to_email, "failed", error=f"template render error: {e}")
        return False

    provider = _get_provider()
    provider_name = provider.__class__.__name__
    last_error = ""

    for attempt in range(_MAX_ATTEMPTS):
        try:
            await provider.send(to_email, to_name, subject, html_body, text_body)
            await _log_email(email_type, to_email, "sent", provider=provider_name)
            logger.info(f"Email sent: type={email_type} to={to_email} provider={provider_name}")
            return True
        except EmailSendError as e:
            last_error = str(e)
            logger.warning(
                f"Email send attempt {attempt + 1}/{_MAX_ATTEMPTS} failed "
                f"(type={email_type}, to={to_email}, provider={provider_name}): {e}"
            )
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
        except Exception as e:
            last_error = str(e)
            logger.error(f"Unexpected email send error (type={email_type}, to={to_email}): {e}", exc_info=True)
            break

    await _log_email(email_type, to_email, "failed", provider=provider_name, error=last_error)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# High-level, purpose-built senders — the API layer only ever calls these
# ─────────────────────────────────────────────────────────────────────────────

async def send_welcome_email(to_email: str, to_name: str) -> bool:
    return await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"Welcome to {settings.APP_NAME} 🎉",
        template_name="welcome",
        context={"user_name": to_name},
        email_type="welcome",
    )


async def send_verification_email(to_email: str, to_name: str, verification_token: str) -> bool:
    """NEW (Email Verification): fired on register/google-signup and on
    /auth/resend-verification. Never blocks/fails the calling request —
    call via BackgroundTasks like every other sender in this module."""
    verify_url = f"{settings.APP_BASE_URL}/verify-email?token={verification_token}"
    return await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"Verify your {settings.APP_NAME} email address",
        template_name="verify_email",
        context={
            "user_name": to_name,
            "verify_url": verify_url,
            "expires_hours": max(1, settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES // 60),
        },
        email_type="email_verification",
    )


async def send_password_reset_email(to_email: str, to_name: str, reset_token: str) -> bool:
    reset_url = f"{settings.APP_BASE_URL}/reset-password?token={reset_token}"
    return await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"Reset your {settings.APP_NAME} password",
        template_name="password_reset",
        context={
            "user_name": to_name,
            "reset_url": reset_url,
            "expires_minutes": settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
        },
        email_type="password_reset",
    )


async def send_team_invite_email(to_email: str, team_name: str, inviter_name: str, role: str, invite_token: str) -> bool:
    accept_url = f"{settings.APP_BASE_URL}/teams/invites/{invite_token}"
    return await send_email(
        to_email=to_email,
        to_name=None,
        subject=f"{inviter_name} invited you to join {team_name} on {settings.APP_NAME}",
        template_name="team_invite",
        context={
            "team_name": team_name,
            "inviter_name": inviter_name,
            "role": role,
            "accept_url": accept_url,
        },
        email_type="team_invite",
    )


async def send_account_status_email(to_email: str, to_name: str, is_active: bool) -> bool:
    if is_active:
        headline = "Your account has been re-enabled"
        message = "an administrator has re-enabled your account. You can log in again right away."
    else:
        headline = "Your account has been disabled"
        message = "an administrator has disabled your account. Contact your workspace admin if you believe this is a mistake."
    return await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"{settings.APP_NAME}: {headline}",
        template_name="usage_alert",
        context={
            "user_name": to_name,
            "headline": headline,
            "message": message,
            "cta_label": "Go to login" if is_active else None,
            "cta_url": f"{settings.APP_BASE_URL}/login" if is_active else None,
        },
        email_type="account_status",
    )


async def send_usage_alert_email(
    to_email: str,
    to_name: str,
    headline: str,
    message: str,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
) -> bool:
    """Generic reusable hook for product-usage notifications (approaching a
    limit, a deploy going live, a KB re-index finishing, etc). Callers
    elsewhere in the codebase can invoke this directly with their own
    copy — no changes to this module are required to add a new usage
    notification."""
    return await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=f"{settings.APP_NAME}: {headline}",
        template_name="usage_alert",
        context={
            "user_name": to_name,
            "headline": headline,
            "message": message,
            "cta_label": cta_label,
            "cta_url": cta_url,
        },
        email_type="usage_alert",
    )


async def _error_notify_allowed() -> bool:
    """Global throttle so a burst of identical errors sends at most one
    admin notification every 5 minutes. Fails open (allows the send) if
    Redis is unavailable — an email-service outage must never suppress
    error visibility during a real incident."""
    try:
        from app.core.redis import get_redis
        redis = get_redis()
        if not redis:
            return True
        was_set = await redis.set("email:error_notify:throttle", "1", nx=True, ex=300)
        return bool(was_set)
    except Exception:
        return True


async def send_error_notification_email(
    error_summary: str,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
) -> bool:
    """Best-effort alert to ADMIN_NOTIFICATION_EMAILS (see config.py) about
    an unhandled server error. No-ops (returns False) if no admin
    recipients are configured, or if the 5-minute global throttle is
    active. Intended to be called from main.py's global exception handler
    via a Starlette BackgroundTask so it never delays the error response."""
    recipients = [e.strip() for e in (settings.ADMIN_NOTIFICATION_EMAILS or []) if e.strip()]
    if not recipients:
        return False
    if not await _error_notify_allowed():
        logger.info("Error notification throttled (another alert was sent within the last 5 minutes)")
        return False

    context = {
        "error_summary": error_summary,
        "request_path": request_path or "",
        "request_method": request_method or "",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
    ok = True
    for addr in recipients:
        sent = await send_email(
            to_email=addr,
            to_name=None,
            subject=f"⚠️ {settings.APP_NAME} server error",
            template_name="error_notification",
            context=context,
            email_type="error_notification",
        )
        ok = ok and sent
    return ok
