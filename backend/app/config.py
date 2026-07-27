from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ThunderBots"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-min-32-chars!!"

    # Database
    DATABASE_URL: str = "postgresql://thunderbots:password@localhost:5432/thunderbots"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ALGORITHM: str = "HS256"
    # NEW (Google SSO & 2FA): short-lived token issued after a *password or
    # Google credential* checks out but the account still has TOTP 2FA
    # enabled. It carries type="mfa" (never "access" — see
    # core/auth.verify_token) so it cannot be replayed as a bearer token
    # against any authenticated route; it is only ever accepted by
    # POST /api/v1/auth/2fa/verify, and only within this window.
    MFA_TOKEN_EXPIRE_MINUTES: int = 5

    # ── GOOGLE SSO (NEW) ──────────────────────────────────────────────────
    # OAuth 2.0 Client ID from Google Cloud Console (Web application type).
    # Unset by default: POST /api/v1/auth/google returns 503 until this is
    # configured, and the frontend only renders the "Sign in with Google"
    # button when NEXT_PUBLIC_GOOGLE_CLIENT_ID is also set — so an
    # unconfigured deployment behaves exactly as it did before this feature.
    GOOGLE_CLIENT_ID: Optional[str] = None

    # ── TOTP TWO-FACTOR AUTHENTICATION (NEW) ─────────────────────────────
    # Issuer label shown in the user's authenticator app (Google
    # Authenticator, Authy, 1Password, etc) next to the account name.
    TOTP_ISSUER_NAME: str = "ThunderBots"

    # ── ACTIVE SESSIONS & DEVICE MANAGEMENT (NEW — Phase 2) ───────────────
    # How stale session.last_active_at must be before get_current_user
    # bothers writing a fresh timestamp. Keeps the "Active now" / "5 minutes
    # ago" display reasonably accurate on the sessions list without turning
    # every single authenticated request into an extra DB write.
    SESSION_ACTIVITY_UPDATE_INTERVAL_MINUTES: int = 5
    # IP geolocation for the sessions list ("Location: San Francisco, CA,
    # US") is a best-effort *external* HTTP lookup and is OFF by default —
    # an unconfigured deployment makes zero extra network calls and every
    # session simply shows no location, exactly as if this feature didn't
    # exist. Private/loopback IPs (localhost, LAN dev) are never looked up
    # regardless of this setting.
    IP_GEOLOCATION_ENABLED: bool = False
    IP_GEOLOCATION_TIMEOUT_SECONDS: float = 2.0

    # ── AUDIT LOG (NEW — v58) ───────────────────────────────────────────────
    # How many days an AuditLog row is kept before it becomes eligible for
    # deletion by services.audit_service.purge_expired(). Nothing calls that
    # function automatically — wire it into a scheduled job to actually
    # enforce this. 0 (or any non-positive value) disables pruning: logs are
    # then kept indefinitely, which is also the default (no data loss for an
    # unconfigured deployment).
    AUDIT_LOG_RETENTION_DAYS: int = 365

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # ── SMART SHOP ASSISTANT (NEW) ─────────────────────────────────────────
    # Base URL of the deployed frontend, used to build the public customer
    # link (`{FRONTEND_BASE_URL}/shop/<public_slug>`) that gets encoded into
    # each shop's QR code. Defaults to local dev; set this to the real
    # deployed domain in production or every printed QR code will point at
    # localhost.
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # ── AI PROVIDER (env-level fallback; users override per-key in DB) ──
    # Google Gemini is the only supported AI provider.
    #
    # FIX v6.3: gemini-1.5-flash / gemini-1.5-pro / gemini-1.0-pro are fully
    # retired (all Gemini 1.0 and 1.5 models return a hard 404 "model not
    # found" on every request as of their provider-side shutdown). Point the
    # default at the current stable production model instead.
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash"

    # ── KNOWLEDGE BASE ─────────────────────────────────────────────────
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION: str = "thunderbots_kb"

    # Google Gemini is the only embedding provider — Gemini's embedding
    # endpoint is used for all Knowledge Base document embeddings.
    EMBEDDING_PROVIDER: Optional[str] = "gemini"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-001"  # Gemini embedding model
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    MAX_RETRIEVAL_RESULTS: int = 5
    RETRIEVAL_SCORE_THRESHOLD: float = 0.3

    # ── UPLOAD ─────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "/tmp/thunderbots_uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_BRANDING_ASSET_SIZE_MB: int = 5
    MAX_PRODUCT_IMAGE_SIZE_MB: int = 8

    # ── HISTORY ────────────────────────────────────────────────────────
    MAX_HISTORY_VERSIONS: int = 50

    # ── CACHE ──────────────────────────────────────────────────────────
    WORKFLOW_CACHE_TTL: int = 300
    KB_CACHE_TTL: int = 600
    SESSION_CACHE_TTL: int = 3600

    # ── DEPLOY ─────────────────────────────────────────────────────────
    APP_BASE_URL: str = "http://localhost:3000"
    # FIX v5: explicit API URL setting (was inferred via fragile ":3000"->":8000"
    # string replace, which broke on any custom domain or port in production).
    APP_API_URL: str = "http://localhost:8000"

    # ── EMAIL / NOTIFICATIONS (NEW) ──────────────────────────────────────
    # EMAIL_PROVIDER selects the transport: "console" (default — logs the
    # rendered email instead of sending; safe zero-config default for local
    # dev so nothing breaks if this is left unset), "smtp", or "sendgrid".
    # Falls back to "console" automatically if the selected provider is
    # missing its required credentials (see services/email_service.py).
    EMAIL_PROVIDER: str = "console"
    EMAIL_FROM_ADDRESS: str = "thunderbots.ai@gmail.com"
    EMAIL_FROM_NAME: str = "ThunderBots"
    EMAIL_REPLY_TO: Optional[str] = None

    # SMTP transport (e.g. Postmark, Amazon SES, Mailgun, Gmail SMTP relay)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True   # STARTTLS on SMTP_PORT (587 typical)
    SMTP_USE_SSL: bool = False  # implicit TLS on connect (465 typical) — overrides SMTP_USE_TLS when true

    # SendGrid transport (HTTP API — no extra SDK dependency, sent via httpx)
    SENDGRID_API_KEY: Optional[str] = None

    # Password reset tokens expire after this many minutes.
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # NEW (Email Verification): signup verification links expire after this
    # many minutes. Default 24h — long enough that a user checking email a
    # bit later the same day isn't locked out, short enough to bound how
    # long a stale link stays valid.
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES: int = 1440

    # ── AI CALL AGENT — PHONE VERIFICATION (NEW, Voice AI Part 2) ─────────
    # Phone number setup/verification only — no call automation. Mirrors
    # EMAIL_PROVIDER exactly: PHONE_VERIFICATION_PROVIDER selects the
    # transport ("console" default — logs the code instead of sending it,
    # zero configuration required; or "twilio" — sends OTP/SMS codes via
    # Twilio's HTTP API). Falls back to "console" automatically if the
    # selected provider is missing credentials (see
    # services/phone_verification_service.py). "Call" verification always
    # degrades to console in this part — placing a real outbound call is
    # left for a future phase.
    PHONE_VERIFICATION_PROVIDER: str = "console"
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None

    # How long a sent verification code stays valid.
    PHONE_VERIFICATION_CODE_EXPIRE_MINUTES: int = 10
    # Wrong-code attempts allowed against a single sent code before the
    # phone number's status flips to "failed" and a fresh code is required.
    PHONE_VERIFICATION_MAX_ATTEMPTS: int = 5

    # ── AI CALL AGENT — REALTIME CALLS (NEW, Voice AI Part 3) ─────────────
    # Reuses TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER above
    # (same Twilio project already used for verification SMS) for placing
    # and receiving real calls via Twilio Voice + Media Streams. Nothing
    # here is loaded/executed unless a phone number is actually enabled
    # for AI Call Agent — an unconfigured deployment behaves exactly as if
    # this feature didn't exist (503s from call_agent_calls.py).
    #
    # Publicly-reachable base URL of THIS backend, used to build the
    # TwiML webhook / Media Stream WebSocket URLs handed to Twilio (Twilio
    # must be able to reach these over the public internet — use an ngrok/
    # cloud URL in local dev). Falls back to APP_BASE_URL only as a last
    # resort; almost always needs to be set explicitly and separately from
    # the frontend's APP_BASE_URL.
    BACKEND_PUBLIC_URL: Optional[str] = None

    # Realtime speech-to-text provider for inbound call audio. "deepgram"
    # is the only real streaming provider implemented (accepts Twilio's
    # native mulaw/8000 audio directly, no transcoding needed on the way
    # in). If DEEPGRAM_API_KEY is unset, calls still connect but no STT
    # happens — the AI Call Agent plays a "speech recognition is not
    # configured" message and the call is marked failed, rather than
    # hanging silently (see services/call_stt_service.py).
    VOICE_CALL_STT_PROVIDER: str = "deepgram"
    DEEPGRAM_API_KEY: Optional[str] = None

    # Default TTS provider/voice/speed/language for calls when a phone
    # number hasn't set its own call_settings yet. Reuses the EXACT SAME
    # tts_engine.py provider catalog and UserAPIKey credentials as Voice
    # Responses (Part 1) — no second voice engine.
    VOICE_CALL_DEFAULT_VOICE_PROVIDER: str = "gemini"
    VOICE_CALL_DEFAULT_VOICE_ID: str = "Kore"
    VOICE_CALL_DEFAULT_SPEED: float = 1.0
    VOICE_CALL_DEFAULT_LANGUAGE: str = "en-US"

    # Barge-in: stop AI speech instantly once the caller starts talking.
    # A kill switch only — this should stay true in every real deployment.
    VOICE_CALL_BARGE_IN_ENABLED: bool = True
    # Recording is OFF by default — enabling it has call-recording consent/
    # legal notice implications the account owner must opt into explicitly
    # per phone number (call_settings.recording_enabled), not globally.
    VOICE_CALL_RECORDING_ENABLED_DEFAULT: bool = False

    # Played (via TTS) and the call is handed off / ended gracefully
    # whenever the AI Engine errors out or the Knowledge Base/AI Agent
    # explicitly can't answer — this is the "fast fallback" requirement.
    VOICE_CALL_FALLBACK_MESSAGE: str = (
        "I'm sorry, I'm having trouble answering that right now. "
        "Let me get you connected with someone who can help."
    )
    # Maximum seconds the AI is allowed to think before the fallback
    # message plays instead, so a caller is never left in silence.
    VOICE_CALL_MAX_THINKING_SECONDS: float = 8.0

    # ── Voice AI Part 4 (NEW) — admin control defaults ─────────────────────
    # Per-number overrides live in PhoneNumber.call_settings (JSONB, no
    # migration needed); these are only the defaults used when a number
    # hasn't set its own value yet.
    # interrupt: barge-in cuts the AI off immediately (existing Part 3
    #   behavior). queue: caller speech is transcribed but the AI finishes
    #   its current sentence before responding (barge-in disabled for that
    #   call). ignore: barge-in fully disabled, matches VOICE_CALL_BARGE_IN_ENABLED=False.
    VOICE_CALL_DEFAULT_INTERRUPT_BEHAVIOR: str = "interrupt"
    # strict: only answer from the bound Knowledge Base(s); if nothing
    #   relevant is retrieved, speak the fallback prompt instead of calling
    #   the LLM at all. open: retrieved KB context is given to the model as
    #   supporting material but it may still answer from general/workflow
    #   knowledge when the KB has nothing relevant.
    VOICE_CALL_DEFAULT_PROMPT_SCOPE: str = "open"
    # Spoken when business_hours is enabled on a number and an inbound call
    # arrives outside the configured window, before the call is ever
    # connected to the AI/Media Stream at all.
    VOICE_CALL_CLOSED_MESSAGE: str = (
        "Thanks for calling. We're currently closed. Please call back during "
        "our business hours, or leave a message after the tone."
    )

    # Recipients for system error-notification emails (comma-separated in
    # .env, parsed into a list). Empty by default — no emails are sent until
    # this is configured.
    ADMIN_NOTIFICATION_EMAILS: List[str] = []

    # ── INSTAGRAM DM CHANNEL (NEW) ────────────────────────────────────────
    # Meta App credentials for the Facebook Login OAuth flow used to connect
    # an Instagram Business account (via its linked Facebook Page). Unset by
    # default: the "Connect Instagram" / OAuth-authorize endpoint returns
    # 503 until these are configured, so an unconfigured deployment behaves
    # exactly as if this feature didn't exist — same pattern as
    # GOOGLE_CLIENT_ID above.
    INSTAGRAM_APP_ID: Optional[str] = None
    INSTAGRAM_APP_SECRET: Optional[str] = None
    # Must exactly match a "Valid OAuth Redirect URI" configured in the Meta
    # App dashboard. Defaults to this API's own OAuth callback route.
    INSTAGRAM_REDIRECT_URI: Optional[str] = None
    # Single app-wide shared secret Meta echoes back on the GET webhook
    # verification handshake. Instagram/Messenger webhooks are registered
    # once per Meta App (not per connected account), unlike the
    # per-connection WhatsApp verify token above.
    INSTAGRAM_WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    INSTAGRAM_GRAPH_API_VERSION: str = "v21.0"
    # How often the background token-refresh loop checks for Page Access
    # Tokens nearing expiry (see services/instagram_service.py /
    # run_token_refresh_loop, wired into main.py's lifespan).
    INSTAGRAM_TOKEN_REFRESH_INTERVAL_MINUTES: int = 60
    # Refresh a token once it has fewer than this many days left.
    INSTAGRAM_TOKEN_REFRESH_THRESHOLD_DAYS: int = 7

    # ── PERSONAL EMAIL AI ASSISTANT (NEW — Part 1) ────────────────────────
    # Google OAuth 2.0 Client (Web application type) with the Gmail API
    # enabled. Distinct from GOOGLE_CLIENT_ID above, which is only used for
    # the client-side "Sign in with Google" ID-token flow and never
    # requests Gmail scope or a refresh token. Unset by default: the
    # oauth/authorize endpoint returns 503 until these are configured, so
    # an unconfigured deployment behaves exactly as if this module didn't
    # exist — same pattern as INSTAGRAM_APP_ID above.
    GMAIL_CLIENT_ID: Optional[str] = None
    GMAIL_CLIENT_SECRET: Optional[str] = None
    # Must exactly match an "Authorized redirect URI" configured for the
    # OAuth Client in Google Cloud Console. Defaults to this API's own
    # OAuth callback route.
    GMAIL_REDIRECT_URI: Optional[str] = None
    # How often the background daily-digest loop checks whether any
    # digest-enabled account is due for its Daily AI Email Digest (each
    # account is still only digested once per UTC calendar day, regardless
    # of this interval — see services/personal_email_sync_service.py).
    PERSONAL_EMAIL_DIGEST_CHECK_INTERVAL_MINUTES: int = 60
    PERSONAL_EMAIL_SYNC_MAX_MESSAGES_PER_FOLDER: int = 25

    # ── PERSONAL EMAIL AI ASSISTANT — Part 2 (Send / Schedule / Automation) ──
    # How often the background scheduler checks for drafts whose
    # scheduled_at has arrived (Schedule Send). Kept short since a sent
    # time is a user-facing promise.
    PERSONAL_EMAIL_SCHEDULED_SEND_POLL_SECONDS: int = 30
    # How often the background loop checks inbox messages for the
    # "unanswered email" AI reminder.
    PERSONAL_EMAIL_REMINDER_CHECK_INTERVAL_MINUTES: int = 60
    # An action-required inbox message with no reply after this many hours
    # is surfaced as an "unanswered" AI reminder (see
    # services/personal_email_automation_service.py).
    PERSONAL_EMAIL_UNANSWERED_REMINDER_HOURS: int = 24
    # A reminder is re-surfaced at most once per this many hours, so the
    # same unanswered email doesn't re-notify constantly.
    PERSONAL_EMAIL_REMINDER_COOLDOWN_HOURS: int = 24
    # Inline (base64) attachment size cap for outgoing drafts, in MB.
    PERSONAL_EMAIL_MAX_ATTACHMENT_MB: int = 10

    class Config:
        env_file = ".env"



settings = Settings()
