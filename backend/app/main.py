"""
ThunderBots API v5 — Build. Train. Deploy. Scale.
"""
import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

import asyncio

from app.core.database import init_db
from app.core.redis import init_redis, close_redis
from app.services import live_agent_ws_manager, shop_assistant_ws_manager
from app.services.campaign_dispatch_service import run_scheduler_loop as run_campaign_scheduler_loop
from app.services.instagram_service import run_token_refresh_loop as run_instagram_token_refresh_loop
from app.api.v1 import auth, workflows, history, chat, knowledge
from app.api.v1 import settings as settings_api
from app.api.v1 import deploy
from app.api.v1 import analytics
from app.api.v1 import whatsapp
from app.api.v1 import instagram
from app.api.v1 import telegram
from app.api.v1 import voice
from app.api.v1 import marketplace
from app.api.v1 import admin
from app.api.v1 import audit
from app.api.v1 import teams
from app.api.v1 import campaigns
from app.api.v1 import live_agent
from app.api.v1 import ai_supervisor
from app.api.v1 import personal_email
from app.api.v1 import assistant
from app.api.v1 import call_agent
from app.api.v1 import call_agent_calls
from app.api.v1 import call_agent_agents
from app.api.v1 import shop_assistant
from app.api.v1 import shop_assistant_public
from app.api.v1 import business_advisor
from app.api.v1 import tutorial
from app.services.personal_email_sync_service import run_daily_digest_loop as run_personal_email_digest_loop
from app.services.personal_email_send_service import run_scheduled_send_loop as run_personal_email_scheduled_send_loop
from app.services.personal_email_automation_service import run_unanswered_reminder_loop as run_personal_email_reminder_loop
from app.services.shop_reservation_scheduler import run_scheduler_loop as run_shop_reservation_scheduler_loop
from app.api.ws import chat_ws
from app.api.ws import live_agent_ws
from app.api.ws import call_stream_ws
from app.api.ws import shop_assistant_ws
from app.config import settings
from app.services import email_service

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


_DEFAULT_SECRET_KEY = "change-me-in-production-min-32-chars!!"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ThunderBots API v5 starting up…")
    # SECURITY FIX: previously silent — running with the shipped default
    # SECRET_KEY in a non-DEBUG (production) deployment means JWTs can be
    # forged and stored API keys (encrypted with a key derived from
    # SECRET_KEY) can be decrypted by anyone who reads the source. This does
    # not block startup (to avoid breaking existing deployments), it just
    # makes the misconfiguration loud instead of silent.
    if not settings.DEBUG and settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
        logger.warning(
            "SECURITY WARNING: SECRET_KEY is still the default placeholder value. "
            "Set a unique, random SECRET_KEY (32+ chars) in your environment before "
            "exposing this deployment publicly — it is used to sign JWTs and to "
            "encrypt stored API keys."
        )
    await init_db()
    await init_redis()

    # HORIZONTAL-SCALING FIX (v107): subscribes this worker to the Redis
    # pub/sub channels used by the Live Agent and Shop Assistant WebSocket
    # registries, so real-time pushes reach the right socket even when it's
    # held by a *different* worker process/replica behind a load balancer.
    # No-ops safely if Redis is unavailable — see each manager's docstring.
    live_agent_bridge_task = await live_agent_ws_manager.start_cross_worker_bridge()  # noqa: F841 — task tracked internally by the manager module
    shop_assistant_bridge_task = await shop_assistant_ws_manager.start_cross_worker_bridge()  # noqa: F841

    # NEW (AI Broadcast & Auto-Reply Engine): polls every 60s for "scheduled"
    # campaigns whose scheduled_at has arrived and dispatches them. Additive
    # background task — does not touch any existing startup behavior, and
    # its own internal loop never raises (see run_scheduler_loop).
    campaign_scheduler_task = asyncio.create_task(run_campaign_scheduler_loop())

    # NEW (Instagram DM Channel): periodically refreshes Page Access Tokens
    # nearing expiry so a connected bot doesn't silently stop answering DMs.
    # Purely additive background task, mirrors the campaign scheduler above;
    # its own internal loop never raises.
    instagram_token_refresh_task = asyncio.create_task(run_instagram_token_refresh_loop())

    # NEW (Personal Email AI Assistant): periodically generates the Daily
    # AI Email Digest for connected, digest-enabled accounts (at most once
    # per UTC calendar day per account). Purely additive background task,
    # mirrors the two above; its own internal loop never raises.
    personal_email_digest_task = asyncio.create_task(run_personal_email_digest_loop())

    # NEW (Personal Email AI Assistant — Part 2): dispatches Schedule Send
    # drafts once due, and periodically timestamps the unanswered-email AI
    # reminder. Both purely additive background tasks, same never-raises
    # shape as every loop above.
    personal_email_scheduled_send_task = asyncio.create_task(run_personal_email_scheduled_send_loop())
    personal_email_reminder_task = asyncio.create_task(run_personal_email_reminder_loop())

    # NEW (Smart Shop Assistant — Reservation System): polls every 30s for
    # 'pending' reservations whose hold has expired, restores their stock,
    # and auto-fulfils the waiting list for any product that just freed up.
    # Purely additive background task, same never-raises shape as every loop
    # above.
    shop_reservation_scheduler_task = asyncio.create_task(run_shop_reservation_scheduler_loop())

    logger.info("ThunderBots API v5 ready")
    yield
    logger.info("ThunderBots API v5 shutting down…")
    campaign_scheduler_task.cancel()
    try:
        await campaign_scheduler_task
    except asyncio.CancelledError:
        pass
    instagram_token_refresh_task.cancel()
    try:
        await instagram_token_refresh_task
    except asyncio.CancelledError:
        pass
    personal_email_digest_task.cancel()
    try:
        await personal_email_digest_task
    except asyncio.CancelledError:
        pass
    personal_email_scheduled_send_task.cancel()
    try:
        await personal_email_scheduled_send_task
    except asyncio.CancelledError:
        pass
    personal_email_reminder_task.cancel()
    try:
        await personal_email_reminder_task
    except asyncio.CancelledError:
        pass
    shop_reservation_scheduler_task.cancel()
    try:
        await shop_reservation_scheduler_task
    except asyncio.CancelledError:
        pass
    await live_agent_ws_manager.stop_cross_worker_bridge()
    await shop_assistant_ws_manager.stop_cross_worker_bridge()
    await close_redis()


app = FastAPI(
    title="ThunderBots API",
    description="AI Agent Builder & Chatbot Workflow Platform",
    version="5.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# MONITORING FIX (v107): no request-timing/slow-operation visibility existed
# anywhere in the app — under load, the first sign of a problem would be
# user complaints, not logs. This adds a per-request wall-clock timer, an
# `X-Process-Time` response header (cheap to inspect from the client/curl
# during incident response), and a WARNING log line for any request over
# 1s so slow endpoints/queries surface on their own instead of needing to
# be discovered by hand. Pure observability — never alters the response
# body or status code.
_SLOW_REQUEST_THRESHOLD_SECONDS = 1.0


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    if elapsed > _SLOW_REQUEST_THRESHOLD_SECONDS:
        logger.warning(
            f"SLOW REQUEST: {request.method} {request.url.path} took {elapsed:.3f}s "
            f"(status={response.status_code})"
        )
    return response


# SECURITY FIX: no security headers were being set anywhere in the app.
# Adds the standard, low-risk, zero-behavior-change set: prevents MIME
# sniffing, blocks the API from being framed (clickjacking), disables the
# legacy XSS auditor quirk mode, and trims referrer leakage. Deliberately
# does NOT add a Content-Security-Policy here — the server-rendered embed
# widget (/api/v1/deploy/embed/{slug}) relies on inline <style>/<script>,
# and shipping a CSP without auditing every inline usage risks breaking it;
# that inline-script surface is separately hardened at the source (see
# api/v1/deploy.py escaping fixes) rather than blocked wholesale here.
_FRAMEABLE_PREFIXES = ("/api/v1/deploy/embed/", "/api/v1/deploy/live/")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # The embed widget is *meant* to be framed on third-party sites — every
    # other route gets the standard clickjacking protection.
    if not request.url.path.startswith(_FRAMEABLE_PREFIXES):
        response.headers["X-Frame-Options"] = "DENY"
    return response

# ROOT CAUSE FIX: allow_origins=["*"] combined with allow_credentials=True is
# an invalid CORS configuration. Per the Fetch/CORS spec, a browser refuses to
# expose the response to any request made with credentials (cookies, or an
# Authorization header sent by a client with withCredentials/credentials
# enabled) unless Access-Control-Allow-Origin echoes back the exact request
# origin — "*" is explicitly disallowed in that case. Depending on the
# deployed origin and browser, this can silently turn every API call from the
# frontend into a network-level failure with no response body at all — surfaced
# to the user as "Could not reach the server." settings.CORS_ORIGINS already
# existed for exactly this purpose but was never wired in; it is used here so
# the actual configured frontend origin(s) are always explicitly allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ──────────────────────────────────────────────────
async def _notify_admins_of_error(exc: Exception, request: Request) -> None:
    """NEW (Email & Notification Service): best-effort admin alert on any
    unhandled server error. No-ops if ADMIN_NOTIFICATION_EMAILS is unset and
    is throttled to one alert per 5 minutes — see
    email_service.send_error_notification_email. Runs as a Starlette
    BackgroundTask *after* the response is sent, so it can never add latency
    to, or itself cause, an error response."""
    try:
        await email_service.send_error_notification_email(
            error_summary=f"{type(exc).__name__}: {str(exc)[:300]}",
            request_path=str(request.url.path),
            request_method=request.method,
        )
    except Exception as notify_err:
        logger.warning(f"Error-notification email failed (non-fatal): {notify_err}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception {request.method} {request.url}: {exc}", exc_info=True)
    # SECURITY FIX: raw exception text (which can include internals such as
    # DB connection details, file paths, or provider error bodies) was always
    # returned to the client, even in production. It's still logged in full
    # server-side; only the response body is now generic unless DEBUG=True.
    detail = f"Internal server error: {str(exc)[:200]}" if settings.DEBUG else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
        background=BackgroundTask(_notify_admins_of_error, exc, request),
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api/v1/auth",      tags=["Auth"])
app.include_router(workflows.router,     prefix="/api/v1/workflows",  tags=["Workflows"])
app.include_router(history.router,       prefix="/api/v1/history",    tags=["History"])
app.include_router(chat.router,          prefix="/api/v1/chat",       tags=["Chat"])
app.include_router(knowledge.router,     prefix="/api/v1/knowledge",  tags=["Knowledge Base"])
app.include_router(settings_api.router,  prefix="/api/v1/settings",   tags=["Settings"])
app.include_router(deploy.router,        prefix="/api/v1/deploy",     tags=["Deploy"])
app.include_router(analytics.router,     prefix="/api/v1/analytics",  tags=["Analytics"])
app.include_router(whatsapp.router,      prefix="/api/v1/whatsapp",   tags=["WhatsApp"])
app.include_router(instagram.router,     prefix="/api/v1/instagram",  tags=["Instagram"])
app.include_router(telegram.router,      prefix="/api/v1/telegram",   tags=["Telegram"])
app.include_router(voice.router,         prefix="/api/v1/voice",      tags=["Voice"])
app.include_router(marketplace.router,   prefix="/api/v1/marketplace", tags=["Marketplace"])
app.include_router(admin.router,         prefix="/api/v1/admin",      tags=["Admin"])
app.include_router(audit.router,         prefix="/api/v1/admin/audit-logs", tags=["Audit Log"])
app.include_router(teams.router,         prefix="/api/v1/teams",      tags=["Teams"])
app.include_router(campaigns.router,     prefix="/api/v1/campaigns",  tags=["Campaigns"])
app.include_router(live_agent.router,    prefix="/api/v1/live-agent", tags=["Live Agent"])
app.include_router(ai_supervisor.router, prefix="/api/v1/ai-supervisor", tags=["AI Supervisor"])
app.include_router(personal_email.router, prefix="/api/v1/personal-email", tags=["Personal Email AI Assistant"])
app.include_router(assistant.router,     prefix="/api/v1/assistant",  tags=["Owner Assistant"])
app.include_router(call_agent.router,    prefix="/api/v1/call-agent", tags=["AI Call Agent"])
app.include_router(call_agent_calls.router, prefix="/api/v1/call-agent", tags=["AI Call Agent"])
app.include_router(call_agent_agents.router, prefix="/api/v1/call-agent", tags=["AI Call Agent — Voice Agents"])
app.include_router(shop_assistant.router,  prefix="/api/v1/shop-assistant", tags=["Smart Shop Assistant"])
app.include_router(shop_assistant_public.router, prefix="/api/v1/shop-assistant/public", tags=["Smart Shop Assistant — Public"])
app.include_router(business_advisor.router, prefix="/api/v1/business-advisor", tags=["AI Business Advisor"])
app.include_router(tutorial.router,      prefix="/api/v1/tutorial",   tags=["Interactive Tutorials"])
app.include_router(chat_ws.router,       prefix="/ws",                tags=["WebSocket"])
app.include_router(live_agent_ws.router, prefix="/ws",                tags=["WebSocket"])
app.include_router(call_stream_ws.router, prefix="/ws",                tags=["WebSocket"])
app.include_router(shop_assistant_ws.router, prefix="/ws",             tags=["WebSocket"])

# ── Static assets (branding: logos/avatars/favicons/backgrounds; NEW: Smart
# Shop Assistant product images) ───────────────────────────────────────────
import mimetypes
mimetypes.add_type("image/webp", ".webp")  # defensive — some minimal base images ship without this registered
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# ── Clean deploy URL alias: https://domain.ai/b/{slug} -> /chat/{slug} ────────
# The frontend owns /chat/[slug] as the canonical public chat route; /b/{slug}
# is offered as the short-form URL per the Deploy URL spec and simply
# redirects at the API edge so both link styles work even if the frontend
# origin differs from the API origin.
@app.get("/b/{slug}", tags=["Deploy"])
async def short_deploy_link(slug: str):
    return RedirectResponse(url=f"{settings.APP_BASE_URL}/chat/{slug}")


@app.get("/health", tags=["System"])
async def health():
    """
    MONITORING/SCALABILITY FIX (v107): previously a static {"status": "ok"}
    with no actual backend checks — a load balancer or orchestrator (k8s,
    ECS, etc.) using this for readiness probes would keep routing traffic to
    a replica whose database or Redis connection was down, since the
    endpoint always returned 200 regardless. Now performs a fast, bounded
    (2s timeout each) check of both dependencies and reports per-component
    status. Redis is best-effort/degraded-not-fatal (the app already runs
    without it — see CacheService), but Postgres is required, so a DB
    failure returns 503 so the orchestrator can route around this replica.
    """
    from app.core.database import engine as _engine
    from sqlalchemy import text as _sql_text

    db_ok = True
    try:
        async with asyncio.timeout(2):
            async with _engine.connect() as conn:
                await conn.execute(_sql_text("SELECT 1"))
    except Exception as e:
        db_ok = False
        logger.warning(f"Health check: database unreachable: {e}")

    redis_ok = True
    from app.core.redis import get_redis
    redis_client = get_redis()
    if redis_client is None:
        redis_ok = False
    else:
        try:
            async with asyncio.timeout(2):
                await redis_client.ping()
        except Exception as e:
            redis_ok = False
            logger.warning(f"Health check: redis unreachable: {e}")

    body = {
        "status": "ok" if db_ok else "degraded",
        "service": "thunderbots-api",
        "version": "6.6.0",
        "checks": {"database": "ok" if db_ok else "unreachable", "redis": "ok" if redis_ok else "unavailable"},
    }
    return JSONResponse(status_code=200 if db_ok else 503, content=body)


@app.get("/widget.js", tags=["Deploy"])
async def widget_loader():
    """Embeddable launcher script — feature 8 (Embed Widget).
    Reads data-slug / data-position / data-color / data-size / data-radius /
    data-animation / data-greeting off its own <script> tag, injects a
    floating launcher button, and lazily mounts the branded chat iframe
    (served by GET /api/v1/deploy/embed/{slug}) on click."""
    from fastapi.responses import Response

    js = """(function(){
  var s = document.currentScript;
  var slug = s.getAttribute('data-slug');
  if (!slug) { console.warn('[ThunderBots] widget.js: missing data-slug'); return; }
  var api = s.src.replace(/\\/widget\\.js.*/, '');
  var position = s.getAttribute('data-position') || 'bottom-right';
  var color = s.getAttribute('data-color') || '#6366f1';
  var size = s.getAttribute('data-size') || 'medium';
  var radius = parseInt(s.getAttribute('data-radius') || '16', 10);
  var animation = s.getAttribute('data-animation') || 'pop';
  var greeting = s.getAttribute('data-greeting') || '';
  var dims = { small: [340, 480], medium: [380, 580], large: [420, 680] }[size] || [380, 580];
  var corner = position.indexOf('left') > -1 ? 'left' : 'right';
  var vcorner = position.indexOf('top') > -1 ? 'top' : 'bottom';

  var style = document.createElement('style');
  style.textContent =
    '@keyframes tbPop{0%{transform:scale(.85);opacity:0}100%{transform:scale(1);opacity:1}}' +
    '@keyframes tbSlide{0%{transform:translateY(16px);opacity:0}100%{transform:translateY(0);opacity:1}}' +
    '@keyframes tbFade{0%{opacity:0}100%{opacity:1}}' +
    '#tb-launcher{position:fixed;' + vcorner + ':20px;' + corner + ':20px;width:58px;height:58px;' +
      'border-radius:50%;background:' + color + ';box-shadow:0 6px 20px rgba(0,0,0,.25);' +
      'display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:999999;' +
      'transition:transform .18s ease;border:none}' +
    '#tb-launcher:hover{transform:scale(1.06)}' +
    '#tb-launcher svg{width:26px;height:26px}' +
    '#tb-frame-wrap{position:fixed;' + vcorner + ':90px;' + corner + ':20px;width:' + dims[0] + 'px;' +
      'height:' + dims[1] + 'px;max-width:calc(100vw - 24px);max-height:calc(100vh - 110px);' +
      'border-radius:' + radius + 'px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.3);' +
      'display:none;z-index:999998;background:#070708}' +
    '#tb-frame-wrap.tb-open{display:block;animation:' +
      (animation === 'slide' ? 'tbSlide' : animation === 'fade' ? 'tbFade' : animation === 'none' ? 'none' : 'tbPop') +
      ' .22s ease both}' +
    '#tb-frame-wrap iframe{width:100%;height:100%;border:0}' +
    '#tb-greeting{position:fixed;' + vcorner + ':20px;' + corner + ':92px;max-width:220px;' +
      'background:#fff;color:#111;padding:10px 14px;border-radius:14px;font:13px/1.4 -apple-system,sans-serif;' +
      'box-shadow:0 6px 20px rgba(0,0,0,.18);z-index:999999;animation:tbSlide .25s ease both;cursor:pointer}' +
    '@media(max-width:480px){#tb-frame-wrap{width:calc(100vw - 24px)!important;height:calc(100vh - 110px)!important}}';
  document.head.appendChild(style);

  var launcher = document.createElement('button');
  launcher.id = 'tb-launcher';
  launcher.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';
  document.body.appendChild(launcher);

  var wrap = document.createElement('div');
  wrap.id = 'tb-frame-wrap';
  document.body.appendChild(wrap);

  var greetEl = null;
  if (greeting) {
    greetEl = document.createElement('div');
    greetEl.id = 'tb-greeting';
    greetEl.textContent = greeting;
    greetEl.onclick = open;
    document.body.appendChild(greetEl);
    setTimeout(function(){ if (greetEl && greetEl.parentNode) greetEl.remove(); }, 10000);
  }

  var mounted = false, open_ = false;
  function open() {
    if (greetEl && greetEl.parentNode) greetEl.remove();
    if (!mounted) {
      var iframe = document.createElement('iframe');
      iframe.src = api + '/api/v1/deploy/embed/' + slug;
      wrap.appendChild(iframe);
      mounted = true;
    }
    wrap.classList.add('tb-open');
    open_ = true;
  }
  function close() {
    wrap.classList.remove('tb-open');
    open_ = false;
  }
  launcher.onclick = function(){ open_ ? close() : open(); };
})();"""
    return Response(content=js, media_type="application/javascript")
