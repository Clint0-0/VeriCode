// Thin typed client for the VeriCode REST API. No mock data: every call hits the backend.
// Auth: HttpOnly session cookie (set by /api/auth/login) + CSRF token echoed in X-CSRF-Token on writes.
export class ApiError extends Error {
  status: number
  code?: string
  data?: any
  constructor(message: string, status: number, code?: string, data?: any) {
    super(message)
    this.status = status
    this.code = code
    this.data = data
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''
let csrfToken: string | null = null

export function setCsrf(t: string | null) { csrfToken = t }

function csrfFromCookie(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)vc_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : null
}

export const AUTH_EVENT = 'vericode:auth-required'

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 120_000)
  const method = opts.method ?? (opts.body !== undefined ? 'POST' : 'GET')
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') {
    const t = csrfToken ?? csrfFromCookie()
    if (t) headers['X-CSRF-Token'] = t
  }
  try {
    const res = await fetch(`${BASE}/api${path}`, {
      method, headers, credentials: 'same-origin',
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    })
    const text = await res.text()
    const data = text ? JSON.parse(text) : null
    if (!res.ok) {
      const detail = data?.detail
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join('; ') : `HTTP ${res.status}`
      if (res.status === 401 && data?.code === 'auth') window.dispatchEvent(new Event(AUTH_EVENT))
      throw new ApiError(msg, res.status, data?.code, data)
    }
    return data as T
  } catch (e: any) {
    if (e?.name === 'AbortError') throw new ApiError('Request timed out', 0, 'timeout')
    if (e instanceof ApiError) throw e
    throw new ApiError(`Backend unreachable: ${e?.message ?? e}`, 0, 'network')
  } finally {
    clearTimeout(timer)
  }
}

export async function login(token: string): Promise<boolean> {
  const r = await api<{ csrf: string }>('/auth/login', { body: { token } })
  setCsrf(r.csrf)
  return true
}

export const fmt = {
  n: (x: number | null | undefined) => (x == null ? '—' : Number(x).toLocaleString()),
  time: (t: number | null | undefined) => (t ? new Date(t * 1000).toLocaleString() : '—'),
  pct: (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`),
}

export const MEASUREMENT_TONE: Record<string, string> = { ACTUAL_PROVIDER_USAGE: 'green', ESTIMATED: 'amber', MOCK: 'amber' }
