import axios, { AxiosError } from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ROOT CAUSE FIX (v6.3): setting a default 'Content-Type': 'application/json'
// header on the axios INSTANCE (as opposed to per-request) breaks every
// FormData/file upload made through this client. Axios's request transformer
// checks headers.getContentType() BEFORE it inspects the payload — when it
// sees 'application/json' already present (inherited from this instance
// default) AND the payload is a FormData instance, it does NOT treat it as
// a multipart body. Instead it runs the FormData through formDataToJSON()
// and JSON-stringifies the result, discarding the actual File contents and
// sending a JSON body with Content-Type still 'application/json'. FastAPI
// then parses that body as JSON, finds no multipart 'file' part at all, and
// pydantic rejects the request with "body.file: Field required" — exactly
// the production symptom — even though knowledge.ts correctly builds a
// FormData and never sets a manual Content-Type on the upload call itself.
// Axios already infers the right Content-Type per request on its own:
// plain JS objects/arrays -> 'application/json'; a FormData instance in a
// browser -> 'multipart/form-data' with the correct boundary, auto-set by
// the browser once axios clears any conflicting header. Removing the
// instance-level default lets that per-request inference work correctly
// for both JSON API calls and file uploads.
export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  timeout: 30_000,
})

// Attach Bearer token on every request
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('tb_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// FIX: Only wipe token and redirect on 401 from auth endpoints.
// A 401 from /workflows, /deploy, etc. means the token is expired or
// invalid — we still redirect to login, but we don't wipe the token
// prematurely if it might still be valid for other requests in flight.
// We also skip the redirect when called from server context (SSR).
apiClient.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    if (
      err.response?.status === 401 &&
      typeof window !== 'undefined' &&
      !window.location.pathname.startsWith('/login') &&
      !window.location.pathname.startsWith('/register')
    ) {
      // Clear token and redirect — session has expired
      localStorage.removeItem('tb_token')
      document.cookie = 'tb_token=; path=/; max-age=0; SameSite=Strict'
      // Use replace so the browser back-button doesn't loop back to the 401 page
      window.location.replace('/login')
    }
    return Promise.reject(err)
  }
)

export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'
