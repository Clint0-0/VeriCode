import React, { useCallback, useEffect, useRef, useState, type ReactNode, type ChangeEvent, type KeyboardEvent } from 'react'
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
        options.push({
          value: val,
          label: p.children ?? val,
          disabled: !!p.disabled,
        })
      } else if (node.props && (node.props as any).children) {
        visit((node.props as any).children)
      }
    }
  }
  visit(children)
  return options
}

export function Select({
  value,
  onChange,
  children,
  className = '',
  size = 'md',
  disabled = false,
  'aria-label': ariaLabel,
  id,
  name,
  title,
  placeholder = 'Select…',
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
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('pointerdown', handleClickOutside)
    return () => document.removeEventListener('pointerdown', handleClickOutside)
  }, [isOpen])

  useEffect(() => {
    if (isOpen && highlightIndex >= 0 && listRef.current) {
      const item = listRef.current.children[highlightIndex] as HTMLElement
      if (item?.scrollIntoView) {
        item.scrollIntoView({ block: 'nearest' })
      }
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
    <div
      ref={containerRef}
      className={`relative ${className.includes('w-') ? '' : 'inline-block'} ${className}`}
    >
      <button
        type="button"
        id={id}
        aria-label={ariaLabel}
        title={title}
        disabled={disabled}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`group flex w-full items-center justify-between gap-2 rounded-md border bg-ink-950 font-normal text-slate-200 shadow-sm transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${
          isSm ? 'px-2.5 py-1 text-xs' : 'px-3 py-2 text-sm'
        } ${
          isOpen
            ? 'border-sky-500/80 ring-1 ring-sky-500/30 bg-ink-900/90'
            : 'border-ink-600/80 hover:border-ink-500 hover:bg-ink-900/60 focus-visible:border-sky-500 focus-visible:ring-1 focus-visible:ring-sky-500/40 focus-visible:outline-none'
        }`}
      >
        <span className="truncate text-left flex-1">{displayLabel}</span>
        <svg
          className={`shrink-0 transition-transform duration-200 text-slate-400 group-hover:text-slate-300 ${
            isSm ? 'h-3.5 w-3.5' : 'h-4 w-4'
          } ${isOpen ? 'rotate-180 text-sky-400' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth="2"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {isOpen && (
        <div
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          className={`absolute top-full z-50 mt-1 max-h-60 min-w-full w-max max-w-xs sm:max-w-md overflow-y-auto rounded-lg border border-ink-700 bg-ink-900/98 p-1 shadow-xl shadow-black/60 backdrop-blur-md ring-1 ring-white/5 focus:outline-none ${
            alignRight ? 'right-0' : 'left-0'
          }`}
        >
          {options.map((opt, i) => {
            const isSelected = opt.value === strVal
            const isHighlighted = i === highlightIndex
            return (
              <button
                key={`${opt.value}-${i}`}
                type="button"
                role="option"
                data-value={opt.value}
                aria-selected={isSelected}
                disabled={opt.disabled}
                onClick={() => handleSelect(opt.value)}
                onMouseEnter={() => setHighlightIndex(i)}
                className={`group flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors duration-100 ${
                  opt.disabled
                    ? 'cursor-not-allowed opacity-40'
                    : isSelected
                    ? 'bg-ink-800 text-sky-300 font-medium'
                    : isHighlighted
                    ? 'bg-ink-800/70 text-slate-100'
                    : 'text-slate-300 hover:bg-ink-800/60 hover:text-white'
                }`}
              >
                <span className="truncate flex-1">{opt.label}</span>
                {isSelected && (
                  <svg
                    className="h-3.5 w-3.5 shrink-0 text-sky-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth="2.5"
                    stroke="currentColor"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                  </svg>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* keeps `name` for form submission only; hidden from assistive tech so each dropdown is one control */}
      <select
        ref={selectRef}
        aria-hidden="true"
        name={name}
        value={value}
        onChange={onChange}
        disabled={disabled}
        tabIndex={-1}
        className="sr-only absolute inset-0 -z-10 h-full w-full opacity-0 pointer-events-none"
      >
        {children}
      </select>
    </div>
  )
}
