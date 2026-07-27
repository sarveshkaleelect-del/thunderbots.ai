# ThunderBots — Production Deployment Guide

Verified against this release: frontend build/typecheck/start all pass; backend
migrations 001→036 apply cleanly on a fresh Postgres DB; full auth flow
(register, login, Google SSO + linking, 2FA, password reset, sessions/logout)
tested end-to-end against a live backend + real Postgres + Redis.

---

## 1. GitHub push steps

```bash
cd ThunderBots
git init
git add .
git commit -m "Production-ready release"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

`.gitignore` (root) already excludes `node_modules`, `.next`, `.env`,
`__pycache__`, and upload directories — confirm before your first push:

```bash
git status   # should NOT list node_modules, .next, .env, or __pycache__
```

---

## 2. Backend deployment steps

Vercel cannot run this backend — it's a long-running FastAPI service using
WebSockets, PostgreSQL, Redis, and ChromaDB. Deploy it to **Railway, Render,
Fly.io, or a VM/EC2 instance** instead. The included `backend/Dockerfile`
works as-is on any of these.

1. Provision managed **PostgreSQL** and **Redis** instances (Railway/Render
   both offer these as one-click add-ons).
2. Provision **ChromaDB** — either the managed ChromaDB Cloud, or run the
   `chromadb/chroma` image alongside your backend (same platform).
3. Set the environment variables from Section 4 below.
4. Deploy the `backend/` directory using its `Dockerfile`:
   ```bash
   docker build -t thunderbots-backend ./backend
   docker run -p 8000:8000 --env-file backend/.env thunderbots-backend
   ```
   or point your platform's "Dockerfile" build setting at `backend/Dockerfile`.
5. Run migrations once, against the production `DATABASE_URL` (Section 6).
6. Confirm health: `curl https://your-backend.example.com/health` should
   return `{"status":"ok", "checks": {"database":"ok","redis":"ok"}}`.

---

## 3. Frontend Vercel deployment steps

1. Push the repo to GitHub (Section 1).
2. In Vercel: **New Project → Import** your GitHub repo.
3. **Root Directory:** set to `frontend` (Project Settings → General → Root
   Directory). This is the one setting Vercel can't infer on its own in this
   monorepo layout — do this even though `vercel.json` also declares the
   build commands, so Vercel's file-system detection (Next.js version, etc.)
   works correctly.
4. Framework Preset: Next.js (auto-detected once Root Directory is set).
5. Add the environment variables from Section 4 (Frontend) in Project
   Settings → Environment Variables, for both **Production** and **Preview**.
6. Deploy. Vercel runs `npm ci && npm run build` automatically.
7. Once deployed, copy the Vercel URL (or your custom domain) and:
   - Add it to the backend's `CORS_ORIGINS`.
   - Add it as an authorized JavaScript origin in Google Cloud Console
     (Section 5) if using Google Sign-In.

### Local verification already performed on this release
```
npm ci            ✅ 573 packages, clean
npm run build     ✅ 52 routes compiled, 0 errors
npx tsc --noEmit  ✅ 0 type errors
npm start         ✅ /login → 200, / → 307 (redirect to /dashboard, expected)
```

---

## 4. Environment variables

### Frontend (Vercel Project Settings → Environment Variables)

| Variable | Required | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | `https://your-backend.example.com` (no trailing slash) |
| `NEXT_PUBLIC_WS_URL` | Yes | `wss://your-backend.example.com` |
| `NEXT_PUBLIC_SITE_URL` | Yes | `https://your-app.vercel.app` or custom domain |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | No | Only if enabling "Sign in with Google" — must exactly match backend's `GOOGLE_CLIENT_ID` |

These are baked into the JS bundle at **build time** — changing them in
Vercel requires a redeploy, not just a restart.

### Backend

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql://user:pass@host:5432/dbname` |
| `REDIS_URL` | Yes | `redis://host:6379` |
| `SECRET_KEY` | Yes | Random 32+ char string — generate with `openssl rand -hex 32`. **Never use the placeholder default.** |
| `CORS_ORIGINS` | Yes | JSON array, e.g. `["https://your-app.vercel.app"]` — must exactly match the frontend origin, no trailing slash |
| `APP_BASE_URL` | Yes | Your deployed frontend URL |
| `APP_API_URL` | Yes | Your deployed backend's own public URL |
| `FRONTEND_BASE_URL` | Yes | Same as `APP_BASE_URL` (used for QR codes etc.) |
| `DEBUG` | Yes | Set to `false` in production |
| `GEMINI_API_KEY` | Recommended | Env-level fallback; users can also set their own in-app |
| `GOOGLE_CLIENT_ID` | No | Only if enabling Google Sign-In |
| `CHROMA_HOST` / `CHROMA_PORT` | Yes (if using Knowledge Base) | Point at your ChromaDB instance |
| `EMAIL_PROVIDER` | No | `console` (default, logs only) / `smtp` / `sendgrid` |
| `SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD` | Conditional | Required if `EMAIL_PROVIDER=smtp` |
| `SENDGRID_API_KEY` | Conditional | Required if `EMAIL_PROVIDER=sendgrid` |

Full list with defaults: `backend/.env.example`.

---

## 5. Google Cloud OAuth setup (for "Sign in with Google")

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials).
2. Create a new project (or select an existing one).
3. **Create Credentials → OAuth client ID → Application type: Web application.**
4. Under **Authorized JavaScript origins**, add:
   - `https://your-app.vercel.app` (production)
   - `http://localhost:3000` (local dev, optional)
5. No redirect URI or client secret is needed — this app uses Google
   Identity Services' ID-token flow, verified server-side.
6. Copy the generated **Client ID** and set it as:
   - `GOOGLE_CLIENT_ID` on the backend
   - `NEXT_PUBLIC_GOOGLE_CLIENT_ID` on the frontend (same exact value)
7. Redeploy both. Confirm via `GET /api/v1/auth/config-status` on the
   backend — `google_sso.backend_client_id_configured` should be `true`.

---

## 6. Database migration commands

Run once against production, from the `backend/` directory, with
`DATABASE_URL` set to the production database:

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
python -m alembic upgrade head
```

This applies all 36 migrations (verified linear, single-head chain, no
branches). To check current state without applying anything:

```bash
python -m alembic current
python -m alembic history
```

Alembic's `env.py` in this project already auto-converts a plain
`postgresql://` URL to the async-driver form — no manual edits needed.

---

## 7. Final testing checklist

**Backend**
- [ ] `GET /health` → `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`
- [ ] `GET /api/v1/auth/config-status` → confirms CORS + Google SSO config
- [ ] `POST /api/v1/auth/register` → 201 with access token
- [ ] `POST /api/v1/auth/login` (correct password) → access token
- [ ] `POST /api/v1/auth/login` (wrong password) → 401
- [ ] Forgot/reset password round-trip → new password logs in, old one doesn't
- [ ] Enable 2FA → login now returns `mfa_required` → verify with TOTP app → access token
- [ ] `POST /api/v1/auth/logout` → subsequent request with same token → 401

**Frontend (on the deployed Vercel URL)**
- [ ] `/register` creates an account and lands on `/dashboard`
- [ ] `/login` with correct/incorrect credentials behaves as expected
- [ ] "Continue with Google" button appears only if `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is set, and completes a real Google sign-in
- [ ] Visiting `/dashboard` while logged out redirects to `/login`
- [ ] Visiting `/login` while logged in redirects to `/dashboard`
- [ ] Refreshing the page after login keeps the session (no unexpected logout)
- [ ] Logout clears the session and redirects appropriately
- [ ] Mobile viewport (phone-width) renders correctly (already fixed in v114)

**Cross-cutting**
- [ ] Browser network tab shows requests going to the correct production `NEXT_PUBLIC_API_URL`, not localhost
- [ ] No CORS errors in the browser console
- [ ] `SECRET_KEY` on the backend is not the placeholder default (`config-status` confirms this)
