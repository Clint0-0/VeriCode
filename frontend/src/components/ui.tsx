import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api'

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-ink-700 bg-ink-900 ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-700 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

const TONES: Record<string, string> = {
  green: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30',
  amber: 'bg-amber-500/10 text-amber-300 ring-amber-500/30',
  red: 'bg-rose-500/10 text-rose-300 ring-rose-500/30',
  blue: 'bg-sky-500/10 text-sky-300 ring-sky-500/30',
  gray: 'bg-slate-500/10 text-slate-300 ring-slate-500/30',
}
const STATUS_TONE: Record<string, string> = {
  VERIFIED_LOCAL: 'green', VERIFIED_LIVE: 'green', CURRENT_SUPPORTED: 'green', succeeded: 'green', ok: 'green',
  STALE: 'amber', DEPRECATED: 'amber', POTENTIALLY_STALE: 'amber', UNCERTAIN: 'amber', CONFLICTING_EVIDENCE: 'amber', UNVERIFIED: 'amber',
  INCOMPATIBLE: 'red', NOT_FOUND: 'red', CONTRADICTED: 'red', failed: 'red',
  NOT_CHECKED: 'gray', NOT_APPLICABLE: 'gray', queued: 'gray',
}

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const t = tone ?? STATUS_TONE[String(children)] ?? (String(children).startsWith('running') ? 'blue' : 'gray')
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px] font-medium ring-1 ring-inset ${TONES[t]}`}>{children}</span>
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'green' | 'amber' | 'red' }) {
  const color = tone === 'green' ? 'text-emerald-300' : tone === 'amber' ? 'text-amber-300' : tone === 'red' ? 'text-rose-300' : 'text-slate-100'
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 px-4 py-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  )
}

export function Button({ children, onClick, disabled, variant = 'primary', type = 'button', title }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; variant?: 'primary' | 'ghost' | 'danger'; type?: 'button' | 'submit'; title?: string
}) {
  const v = variant === 'primary' ? 'bg-sky-600 hover:bg-sky-500 text-white' : variant === 'danger' ? 'bg-rose-600/80 hover:bg-rose-500 text-white' : 'border border-ink-600 hover:bg-ink-800 text-slate-200'
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${v}`}>
      {children}
    </button>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-slate-400">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      {label}
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null
  const e = error as ApiError
  const hint = e.code === 'llm_unavailable' ? ' Configure an LLM provider in .env (see Settings).' : e.code === 'network' ? ' Is the backend running on :8000?' : ''
  return <div role="alert" className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{e.message ?? String(error)}{hint}</div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-ink-600 px-4 py-8 text-center text-sm text-slate-500">{children}</div>
}

export function Notice({ children, tone = 'amber' }: { children: ReactNode; tone?: 'amber' | 'blue' }) {
  const c = tone === 'amber' ? 'border-amber-500/30 bg-amber-500/5 text-amber-200' : 'border-sky-500/30 bg-sky-500/5 text-sky-200'
  return <div className={`rounded-md border px-3 py-2 text-xs ${c}`}>{children}</div>
}

export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <pre className={`overflow-auto whitespace-pre-wrap rounded-md border border-ink-700 bg-ink-950 p-3 font-mono text-xs leading-relaxed text-slate-300 ${className}`}>{children}</pre>
}

export function Diff({ text }: { text: string }) {
  if (!text) return <Empty>No changes.</Empty>
  return (
    <pre className="overflow-auto rounded-md border border-ink-700 bg-ink-950 p-3 font-mono text-xs leading-relaxed">
      {text.split('\n').map((l, i) => (
        <div key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'bg-emerald-500/10 text-emerald-300' : l.startsWith('-') && !l.startsWith('---') ? 'bg-rose-500/10 text-rose-300' : l.startsWith('@@') ? 'text-sky-400' : 'text-slate-400'}>{l || ' '}</div>
      ))}
    </pre>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-slate-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export const inputCls = 'w-full rounded-md border border-ink-600 bg-ink-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none'

/** Fetch helper with loading/error state and optional polling. */
export function useApi<T>(path: string | null, pollMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(!!path)
  const alive = useRef(true)
  const load = useCallback(async () => {
    if (!path) return
    try {
      const d = await api<T>(path)
      if (alive.current) { setData(d); setError(null) }
    } catch (e) {
      if (alive.current) setError(e)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [path])
  useEffect(() => {
    alive.current = true
    setLoading(!!path)
    load()
    if (!pollMs) return () => { alive.current = false }
    const id = setInterval(load, pollMs)
    return () => { alive.current = false; clearInterval(id) }
  }, [load, pollMs, path])
  return { data, error, loading, reload: load, setData }
}

export function Expand({ head, children, defaultOpen = false }: { head: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-md border border-ink-700 bg-ink-850">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-ink-800">
        <span className={`text-slate-500 transition-transform ${open ? 'rotate-90' : ''}`}>›</span>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{head}</div>
      </button>
      {open && <div className="border-t border-ink-700 px-3 py-3 text-sm">{children}</div>}
    </div>
  )
}
