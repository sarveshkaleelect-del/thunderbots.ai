/**
 * ThunderBots v5 — Error message extraction
 *
 * FIX: Previously, axios network/timeout errors surfaced as the raw
 * "Network Error" or "Connection Error" string with no actionable detail.
 * This utility always extracts the most specific, actionable message
 * available: backend `detail` field first, then HTTP status context,
 * then a clear network-level explanation — never a bare generic string.
 */
import { AxiosError } from 'axios'

export function getErrorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (!err) return fallback

  if (err instanceof AxiosError) {
    // Backend returned a structured error body
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation error array
      const first = detail[0]
      if (first?.msg) return `${first.loc?.join('.') || 'field'}: ${first.msg}`
    }

    if (err.code === 'ECONNABORTED') {
      return 'The request timed out. The server may be under heavy load — please try again.'
    }

    if (err.response) {
      const status = err.response.status
      if (status === 401) return 'Your session has expired. Please log in again.'
      if (status === 403) return "You don't have permission to do that."
      if (status === 404) return 'The requested resource was not found.'
      if (status === 413) return 'The file is too large to upload.'
      if (status === 422) return 'The data submitted was invalid.'
      if (status >= 500) return `Server error (${status}). Please try again in a moment.`
      return `Request failed with status ${status}.`
    }

    if (err.request) {
      // Request was made, no response received — actual connectivity issue
      return 'Could not reach the server. Check that the backend is running and reachable at the configured API URL.'
    }

    return err.message || fallback
  }

  if (err instanceof Error) {
    return err.message || fallback
  }

  if (typeof err === 'string') return err

  return fallback
}
