import { apiClient } from './client'
import type { User, LoginResult, UserSession } from '@/types'

export interface AuthResponse {
  access_token: string
  token_type:   string
  user:         User
}

// NEW (Google SSO & 2FA) — mirrors types/index.ts MfaRequiredResponse so
// this file's local response shapes stay consistent with the rest of the app.
export interface MfaRequiredResponse {
  mfa_required: true
  mfa_token:    string
}

export interface TOTPSetupResponse {
  secret:      string
  otpauth_url: string
  qr_code_svg: string
}

export interface TOTPEnableResponse {
  message:      string
  backup_codes: string[]
}

export interface TOTPStatusResponse {
  enabled: boolean
  backup_codes_remaining: number
}

export const authApi = {
  register: (name: string, email: string, password: string) =>
    apiClient.post<AuthResponse>('/auth/register', { name, email, password }).then(r => r.data),

  // NEW (2FA): login can now return either a full AuthResponse or a
  // MfaRequiredResponse — callers must narrow with isMfaRequired() from
  // '@/types' before reading access_token. Existing accounts (2FA never
  // enabled) always get the old AuthResponse shape, unchanged.
  login: (email: string, password: string) =>
    apiClient.post<LoginResult>('/auth/login', { email, password }).then(r => r.data),

  me: () =>
    apiClient.get<User>('/auth/me').then(r => r.data),

  forgotPassword: (email: string) =>
    apiClient.post<{ message: string }>('/auth/forgot-password', { email }).then(r => r.data),

  resetPassword: (token: string, new_password: string) =>
    apiClient.post<{ message: string }>('/auth/reset-password', { token, new_password }).then(r => r.data),

  // ── Google SSO (NEW) ────────────────────────────────────────────────────
  // `credential` is the ID token handed back by Google Identity Services'
  // button/One Tap callback — see components/auth/GoogleSignInButton.tsx.
  googleLogin: (credential: string) =>
    apiClient.post<LoginResult>('/auth/google', { credential }).then(r => r.data),

  // ── TOTP 2FA (NEW) ──────────────────────────────────────────────────────
  verify2FA: (mfa_token: string, code: string) =>
    apiClient.post<AuthResponse>('/auth/2fa/verify', { mfa_token, code }).then(r => r.data),

  get2FAStatus: () =>
    apiClient.get<TOTPStatusResponse>('/auth/2fa/status').then(r => r.data),

  setup2FA: () =>
    apiClient.post<TOTPSetupResponse>('/auth/2fa/setup').then(r => r.data),

  enable2FA: (code: string) =>
    apiClient.post<TOTPEnableResponse>('/auth/2fa/enable', { code }).then(r => r.data),

  disable2FA: (params: { password?: string; code?: string }) =>
    apiClient.post<{ message: string }>('/auth/2fa/disable', params).then(r => r.data),

  regenerateBackupCodes: (code: string) =>
    apiClient.post<{ backup_codes: string[] }>('/auth/2fa/backup-codes/regenerate', { code }).then(r => r.data),

  // ── Active Sessions & Device Management (NEW — Phase 2) ─────────────────
  listSessions: () =>
    apiClient.get<UserSession[]>('/auth/sessions').then(r => r.data),

  revokeSession: (sessionId: string) =>
    apiClient.delete<{ message: string }>(`/auth/sessions/${sessionId}`).then(r => r.data),

  revokeOtherSessions: () =>
    apiClient.post<{ message: string }>('/auth/sessions/revoke-all').then(r => r.data),

  // Logs out the current session server-side. Best-effort — the frontend
  // already clears its own token locally regardless of whether this call
  // succeeds (see clearToken() below / TopBarMenus.handleLogout).
  logout: () =>
    apiClient.post<{ message: string }>('/auth/logout').then(r => r.data),

  logoutAllDevices: () =>
    apiClient.post<{ message: string }>('/auth/logout-all').then(r => r.data),
}

/** Save token to both localStorage (API calls) and cookie (middleware route protection). */
export function saveToken(token: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem('tb_token', token)
  const maxAge = 60 * 60 * 24 * 7   // 7 days — matches backend JWT expiry
  document.cookie = `tb_token=${token}; path=/; max-age=${maxAge}; SameSite=Strict`
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('tb_token')
}

/** Clear token from both localStorage and cookie on logout. */
export function clearToken(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem('tb_token')
  document.cookie = 'tb_token=; path=/; max-age=0; SameSite=Strict'
}
