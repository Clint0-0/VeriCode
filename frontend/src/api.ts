// Thin typed client for the VeriCode REST API. No mock data: every call hits the backend.
export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 120_000)
  try {
    const res = await fetch(`${BASE}/api${path}`, {
      method: opts.method ?? (opts.body !== undefined ? 'POST' : 'GET'),
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: ctrl.signal,
    })
    const text = await res.text()
    const data = text ? JSON.parse(text) : null
    if (!res.ok) {
      const detail = data?.detail
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join('; ') : `HTTP ${res.status}`
      throw new ApiError(msg, res.status, data?.code)
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

export const fmt = {
  n: (x: number | null | undefined) => (x == null ? '—' : x.toLocaleString()),
  time: (t: number | null | undefined) => (t ? new Date(t * 1000).toLocaleString() : '—'),
  pct: (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`),
}
