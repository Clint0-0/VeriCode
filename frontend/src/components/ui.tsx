import React, { useCallback, useEffect, useId, useRef, useState, type ReactNode, type ChangeEvent, type KeyboardEvent } from 'react'
import { AlertTriangle, Check, ChevronDown, ChevronRight, CircleAlert, Info, Loader2 } from 'lucide-react'
import { api, ApiError } from '../api'

/* ------------------------------------------------------------------ layout */

/** Bordered panel. Use for distinct objects (a table, a form); plain sections use <Section>. */
export function Card({ title, actions, children, className = '', flush = false, description }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; flush?: boolean; description?: ReactNode
}) {
  return (
    <section className={`min-w-0 rounded-lg border border-line bg-surface shadow-raised ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            <h2 className="flex flex-wrap items-center gap-2 text-[13px] font-semibold text-fg">{title}</h2>
            {description && <p className="mt-0.5 text-xs text-fg-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={flush ? '' : 'p-4'}>{children}</div>
    </section>
  )
}

/** Unboxed section with a small heading: keeps pages from becoming a stack of cards. */
export function Section({ title, actions, children, className = '', description }: { title: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; description?: ReactNode }) {
  return (
    <section className={`min-w-0 ${className}`}>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold text-fg">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-fg-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

export function Toolbar({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`flex flex-wrap items-center gap-2 ${className}`}>{children}</div>
}

/** Table wrapper: horizontal scroll inside the panel (never the page), consistent header styling. */
export function DataTable({ children, caption, className = '', dense = false, label }: { children: ReactNode; caption?: ReactNode; className?: string; dense?: boolean; label?: string }) {
  return (
    <div className={`min-w-0 overflow-x-auto ${className}`}>
      <table aria-label={label} className={`w-full border-collapse text-left ${dense ? 'text-xs' : 'text-[13px]'} [&_th]:whitespace-nowrap [&_th]:border-b [&_th]:border-line [&_th]:bg-subtle/60 [&_th]:px-3 [&_th]:py-2 [&_th]:text-[11px] [&_th]:font-medium [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-fg-subtle [&_td]:border-b [&_td]:border-line [&_td]:px-3 [&_td]:py-2 [&_td]:align-top [&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr:hover]:bg-subtle/50`}>
        {children}
        {caption && <caption className="caption-bottom px-3 pt-2 pb-1 text-left text-xs text-fg-subtle">{caption}</caption>}
      </table>
    </div>
  )
}

/* ------------------------------------------------------------------ status */

const TONES: Record<string, string> = {
  green: 'border-ok/25 bg-ok-soft text-ok',
  amber: 'border-warn/25 bg-warn-soft text-warn',
  red: 'border-err/25 bg-err-soft text-err',
  blue: 'border-info/20 bg-info-soft text-info',
  gray: 'border-line bg-subtle text-fg-muted',
}
const DOT: Record<string, string> = { green: 'bg-ok', amber: 'bg-warn', red: 'bg-err', blue: 'bg-info', gray: 'bg-fg-subtle' }
export const STATUS_TONE: Record<string, string> = {
  VERIFIED_LOCAL: 'green', VERIFIED_LIVE: 'green', CURRENT_SUPPORTED: 'green', succeeded: 'green', ok: 'green', SUCCESS: 'green',
  STALE: 'amber', DEPRECATED: 'amber', POTENTIALLY_STALE: 'amber', UNCERTAIN: 'amber', CONFLICTING_EVIDENCE: 'amber', UNVERIFIED: 'amber', partial: 'amber', BLOCKED: 'amber',
  INCOMPATIBLE: 'red', NOT_FOUND: 'red', CONTRADICTED: 'red', failed: 'red', FAILED: 'red',
  NOT_CHECKED: 'gray', NOT_APPLICABLE: 'gray', queued: 'gray', ERROR: 'gray',  // ERROR = verification tool failed: not checked, not missing
}
export function toneOf(status: unknown): string {
  const s = String(status)
  return STATUS_TONE[s] ?? (s.startsWith('running') ? 'blue' : 'gray')
}

/** Status badge. Status codes (UPPER_CASE) render in monospace; a dot keeps identity off colour alone. */
export function Badge({ children, tone, title }: { children: ReactNode; tone?: string; title?: string }) {
  const t = tone ?? toneOf(children)
  const code = typeof children === 'string' && /^[A-Z0-9_]+$/.test(children)
  return (
    <span title={title} className={`inline-flex max-w-full items-center gap-1.5 whitespace-nowrap rounded border px-1.5 py-px text-[11px] font-medium leading-5 ${code ? 'font-mono tracking-tight' : ''} ${TONES[t] ?? TONES.gray}`}>
      <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT[t] ?? DOT.gray}`} />
      <span className="truncate">{children}</span>
    </span>
  )
}

export function StatusDot({ tone = 'gray', label }: { tone?: string; label: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted">
      <span aria-hidden className={`h-2 w-2 rounded-full ${DOT[tone] ?? DOT.gray}`} />
      {label}
    </span>
  )
}

/** Compact metric. */
export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'green' | 'amber' | 'red' }) {
  const color = tone === 'green' ? 'text-ok' : tone === 'red' ? 'text-err' : tone === 'amber' ? 'text-warn' : 'text-fg'
  return (
    <div className="min-w-0 rounded-lg border border-line bg-surface px-3.5 py-3 shadow-raised">
      <div className="text-xs font-medium leading-snug text-fg-muted">{label}</div>
      <div className={`mt-1 text-[22px] font-semibold leading-tight tabular-nums ${color}`}>{value}</div>
      {sub && <div className="mt-1 text-xs leading-snug text-fg-subtle">{sub}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ controls */

export function Button({ children, onClick, disabled, variant = 'primary', type = 'button', title, size = 'md', icon }: {
  children?: ReactNode; onClick?: () => void; disabled?: boolean; variant?: 'primary' | 'ghost' | 'danger' | 'quiet'; type?: 'button' | 'submit'; title?: string; size?: 'sm' | 'md'; icon?: ReactNode
}) {
  const v = {
    primary: 'border-accent bg-accent text-white hover:bg-accent-strong hover:border-accent-strong',
    ghost: 'border-line-strong bg-surface text-fg hover:bg-subtle',
    quiet: 'border-transparent bg-transparent text-fg-muted hover:bg-hover hover:text-fg',
    danger: 'border-err/30 bg-surface text-err hover:bg-err-soft',
  }[variant]
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={`inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-[13px]'} ${v}`}>
      {icon}{children}
    </button>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-2 text-[13px] text-fg-muted">
      <Loader2 aria-hidden className="h-4 w-4 animate-spin text-accent" />
      {label}
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null
  const e = error as ApiError
  const hint = e.code === 'llm_unavailable' ? ' Configure an LLM provider in .env (see Settings).' : e.code === 'network' ? ' Is the backend running on :8000?' : ''
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-err/25 bg-err-soft px-3 py-2 text-[13px] text-err">
      <CircleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="min-w-0 break-words">{e.message ?? String(error)}{hint}</span>
    </div>
  )
}

export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-line-strong px-4 py-8 text-center text-[13px] text-fg-muted">
      <div>{children}</div>
      {action}
    </div>
  )
}

export function Notice({ children, tone = 'amber' }: { children: ReactNode; tone?: 'amber' | 'blue' }) {
  const amber = tone === 'amber'
  const Icon = amber ? AlertTriangle : Info
  return (
    <div className={`flex items-start gap-2.5 rounded-md border px-3 py-2 text-[13px] leading-relaxed ${amber ? 'border-warn/25 bg-warn-soft text-fg' : 'border-info/20 bg-info-soft text-fg'}`}>
      <Icon aria-hidden className={`mt-0.5 h-4 w-4 shrink-0 ${amber ? 'text-warn' : 'text-info'}`} />
      <div className="min-w-0 flex-1 [&>b]:font-semibold">{children}</div>
    </div>
  )
}

/** Monospace block for logs, briefings and JSON. */
export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <pre className={`overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-subtle/70 p-3 font-mono text-xs leading-relaxed text-fg ${className}`}>{children}</pre>
}
export const CodeBlock = Mono

/** Unified diff with a +/- gutter and per-file headers. */
export function Diff({ text }: { text: string }) {
  if (!text) return <Empty>No changes.</Empty>
  let oldNo = 0, newNo = 0
  const rows = text.split('\n').map((l, i) => {
    if (l.startsWith('+++') || l.startsWith('---')) {
      return l.startsWith('+++') ? <div key={i} className="sticky left-0 border-y border-line bg-subtle px-3 py-1.5 font-sans text-xs font-medium text-fg">{l.replace(/^\+\+\+ (b\/)?/, '')}</div> : null
    }
    if (l.startsWith('@@')) {
      const m = /@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(l)
      if (m) { oldNo = +m[1]; newNo = +m[2] }
      return <div key={i} className="bg-info-soft/60 px-3 py-0.5 text-info">{l}</div>
    }
    const add = l.startsWith('+'), del = l.startsWith('-')
    const o = add ? '' : String(oldNo++), n = del ? '' : String(newNo++)
    return (
      <div key={i} className={`grid grid-cols-[3rem_3rem_1.25rem_1fr] ${add ? 'bg-diff-add text-diff-add-fg' : del ? 'bg-diff-del text-diff-del-fg' : 'text-fg'}`}>
        <span className="select-none pr-2 text-right text-fg-subtle">{o}</span>
        <span className="select-none pr-2 text-right text-fg-subtle">{n}</span>
        <span aria-hidden className="select-none text-center">{add ? '+' : del ? '−' : ' '}</span>
        <span className="whitespace-pre pr-3">{add || del ? l.slice(1) : l.slice(1) || ' '}</span>
      </div>
    )
  })
  return (
    <div className="overflow-auto rounded-md border border-line bg-surface font-mono text-xs leading-relaxed" role="region" aria-label="Unified diff">
      <div className="min-w-max">{rows}</div>
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-xs font-medium text-fg-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-fg-subtle">{hint}</span>}
    </label>
  )
}

export const inputCls = 'w-full rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-[13px] text-fg placeholder:text-fg-subtle shadow-raised focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:bg-subtle disabled:text-fg-muted'

export function Checkbox({ checked, onChange, children, title }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; title?: string }) {
  return (
    <label className="inline-flex items-center gap-2 text-[13px] text-fg" title={title}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  )
}

/** Segmented control (radio group) for small, mutually exclusive choices. */
export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string }) {
  const name = useId()
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded-md border border-line-strong bg-subtle p-0.5">
      {options.map((o) => (
        <label key={o.value} className={`flex cursor-pointer items-center gap-1.5 rounded px-2.5 py-1 text-[13px] ${value === o.value ? 'bg-surface font-medium text-fg shadow-raised' : 'text-fg-muted hover:text-fg'}`}>
          <input type="radio" name={name} className="sr-only" checked={value === o.value} onChange={() => onChange(o.value)} />
          {o.label}
        </label>
      ))}
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, tabs, label }: { value: T; onChange: (v: T) => void; tabs: { id: T; label: ReactNode; count?: number }[]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-[13px] ${value === t.id ? 'border-accent font-medium text-fg' : 'border-transparent text-fg-muted hover:text-fg'}`}>
          {t.label}{t.count != null && <span className="ml-1.5 rounded bg-subtle px-1.5 text-[11px] text-fg-muted">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

/** Fetch helper with loading/error state and optional polling. */
export function useApi<T>(path: string | null, pollMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(!!path)
  const alive = useRef(true)
  const current = useRef(path)  // a response is applied only if it belongs to the path still being shown
  const load = useCallback(async () => {
    if (!path) return
    try {
      const d = await api<T>(path)
      if (alive.current && current.current === path) { setData(d); setError(null) }
    } catch (e) {
      if (alive.current && current.current === path) setError(e)
    } finally {
      if (alive.current && current.current === path) setLoading(false)
    }
  }, [path])
  useEffect(() => {
    alive.current = true
    if (current.current !== path) { current.current = path; setData(null); setError(null) }  // never show another run's data
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
    <div className={`rounded-md border bg-surface ${open ? 'border-line-strong' : 'border-line'}`}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-subtle/60">
        <ChevronRight aria-hidden className={`h-3.5 w-3.5 shrink-0 text-fg-subtle transition-transform ${open ? 'rotate-90' : ''}`} />
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{head}</div>
      </button>
      {open && <div className="border-t border-line px-3 py-3 text-[13px]">{children}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ select (listbox) */

export interface SelectOption {
  value: string
  label: ReactNode
  disabled?: boolean
}

export interface SelectProps {
  value?: string | number
  onChange?: (e: { target: { value: string } } | ChangeEvent<HTMLSelectElement>) => void
  children?: ReactNode
  className?: string
  size?: 'sm' | 'md'
  disabled?: boolean
  'aria-label'?: string
  id?: string
  name?: string
  title?: string
  placeholder?: string
}

function parseOptions(children: ReactNode): SelectOption[] {
  const options: SelectOption[] = []
  const visit = (node: ReactNode) => {
    if (!node) return
    if (Array.isArray(node)) {
      node.forEach(visit)
      return
    }
    if (React.isValidElement(node)) {
      if (node.type === 'option') {
        const p = node.props as any
        const val = p.value !== undefined ? String(p.value) : (typeof p.children === 'string' || typeof p.children === 'number' ? String(p.children) : '')
        options.push({ value: val, label: p.children ?? val, disabled: !!p.disabled })
      } else if (node.props && (node.props as any).children) {
        visit((node.props as any).children)
      }
    }
  }
  visit(children)
  return options
}

export function Select({
  value, onChange, children, className = '', size = 'md', disabled = false, 'aria-label': ariaLabel, id, name, title, placeholder = 'Select…',
}: SelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState(-1)
  const [alignRight, setAlignRight] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const selectRef = useRef<HTMLSelectElement>(null)

  const options = parseOptions(children)
  const strVal = value !== undefined ? String(value) : ''
  const selectedOption = options.find((o) => o.value === strVal)
  const displayLabel = selectedOption ? selectedOption.label : (strVal || placeholder)

  useEffect(() => {
    if (isOpen && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      setAlignRight(rect.right + 140 > window.innerWidth)
      const idx = options.findIndex((o) => o.value === strVal)
      setHighlightIndex(idx >= 0 ? idx : 0)
    }
  }, [isOpen, strVal, options.length])

  useEffect(() => {
    if (!isOpen) return
    const handleClickOutside = (e: MouseEvent | PointerEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setIsOpen(false)
    }
    document.addEventListener('pointerdown', handleClickOutside)
    return () => document.removeEventListener('pointerdown', handleClickOutside)
  }, [isOpen])

  useEffect(() => {
    if (isOpen && highlightIndex >= 0 && listRef.current) {
      const item = listRef.current.children[highlightIndex] as HTMLElement
      if (item?.scrollIntoView) item.scrollIntoView({ block: 'nearest' })
    }
  }, [isOpen, highlightIndex])

  const handleSelect = (val: string) => {
    // call onChange exactly once; the hidden native select follows `value` on the next render
    if (val !== strVal) onChange?.({ target: { value: val } } as any)
    setIsOpen(false)
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (disabled) return
    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        setIsOpen(true)
      }
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      setIsOpen(false)
    } else if (e.key === 'Tab') {
      setIsOpen(false)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIndex((prev) => {
        let next = prev + 1
        while (next < options.length && options[next].disabled) next++
        return next < options.length ? next : prev
      })
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIndex((prev) => {
        let next = prev - 1
        while (next >= 0 && options[next].disabled) next--
        return next >= 0 ? next : prev
      })
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (highlightIndex >= 0 && highlightIndex < options.length) {
        const opt = options[highlightIndex]
        if (!opt.disabled) handleSelect(opt.value)
      }
    }
  }

  const isSm = size === 'sm'
  return (
    <div ref={containerRef} className={`relative ${className.includes('w-') ? '' : 'inline-block'} ${className}`}>
      <button
        type="button" id={id} aria-label={ariaLabel} title={title} disabled={disabled}
        onClick={() => !disabled && setIsOpen(!isOpen)} onKeyDown={handleKeyDown}
        aria-haspopup="listbox" aria-expanded={isOpen}
        className={`flex w-full items-center justify-between gap-2 rounded-md border bg-surface text-left text-fg shadow-raised transition-colors disabled:cursor-not-allowed disabled:bg-subtle disabled:opacity-60 ${
          isSm ? 'h-7 px-2 text-xs' : 'h-8 px-2.5 text-[13px]'
        } ${isOpen ? 'border-accent ring-2 ring-accent/15' : 'border-line-strong hover:border-fg-subtle'}`}
      >
        <span className="min-w-0 flex-1 truncate">{displayLabel}</span>
        <ChevronDown aria-hidden className={`h-3.5 w-3.5 shrink-0 text-fg-subtle transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div ref={listRef} role="listbox" tabIndex={-1}
          className={`absolute top-full z-50 mt-1 max-h-64 w-max min-w-full max-w-[min(28rem,calc(100vw-2rem))] overflow-y-auto rounded-md border border-line bg-surface p-1 shadow-overlay focus:outline-none ${alignRight ? 'right-0' : 'left-0'}`}>
          {options.map((opt, i) => {
            const isSelected = opt.value === strVal
            const isHighlighted = i === highlightIndex
            return (
              <button key={`${opt.value}-${i}`} type="button" role="option" data-value={opt.value} aria-selected={isSelected}
                disabled={opt.disabled} onClick={() => handleSelect(opt.value)} onMouseEnter={() => setHighlightIndex(i)}
                className={`flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left text-[13px] ${
                  opt.disabled ? 'cursor-not-allowed opacity-40' : isHighlighted ? 'bg-subtle text-fg' : 'text-fg'
                } ${isSelected ? 'font-medium' : ''}`}>
                <span className="min-w-0 flex-1 truncate">{opt.label}</span>
                {isSelected && <Check aria-hidden className="h-3.5 w-3.5 shrink-0 text-accent" />}
              </button>
            )
          })}
        </div>
      )}

      {/* keeps `name` for form submission only; hidden from assistive tech so each dropdown is one control */}
      <select ref={selectRef} aria-hidden="true" name={name} value={value} onChange={onChange} disabled={disabled} tabIndex={-1}
        className="pointer-events-none absolute inset-0 -z-10 h-full w-full opacity-0 sr-only">
        {children}
      </select>
    </div>
  )
}
