import { useEffect, useRef, useState, type ComponentType } from 'react'
import {
  BarChart3, ClipboardCheck, FileSearch, History as HistoryIcon, LayoutDashboard, Library, LogOut, Menu, Settings as SettingsIcon,
  SquareTerminal, X,
} from 'lucide-react'
import { api, AUTH_EVENT, login, setCsrf } from './api'
import { Button, ErrorBox, inputCls, Spinner, StatusDot, useApi } from './components/ui'
import Dashboard from './pages/Dashboard'
import Workspace from './pages/Workspace'
import Preflight from './pages/Preflight'
import Stale from './pages/Stale'
import Evidence from './pages/Evidence'
import Tokens from './pages/Tokens'
import History from './pages/History'
import Settings from './pages/Settings'

type Page = { id: string; label: string; el: ComponentType<{ param?: string }>; icon: ComponentType<{ className?: string }>; group: string; description: string }

export const PAGES: Page[] = [
  { id: 'dashboard', label: 'Dashboard', el: Dashboard, icon: LayoutDashboard, group: 'Overview', description: 'Tasks, verification activity and provider status at a glance.' },
  { id: 'workspace', label: 'Coding Workspace', el: Workspace, icon: SquareTerminal, group: 'Build', description: 'Run a coding task in an isolated copy, review the diff and test results, then apply.' },
  { id: 'preflight', label: 'Pre-Flight Inspector', el: Preflight, icon: ClipboardCheck, group: 'Build', description: 'Verify planned third-party APIs against the packages installed in a workspace.' },
  { id: 'stale', label: 'Stale-Answer Detector', el: Stale, icon: FileSearch, group: 'Verify', description: 'Split an AI answer into claims and check each one against current evidence.' },
  { id: 'evidence', label: 'Evidence Explorer', el: Evidence, icon: Library, group: 'Verify', description: 'Every source retrieved for claim verification, with authority and dates.' },
  { id: 'tokens', label: 'Token Analytics', el: Tokens, icon: BarChart3, group: 'Measure', description: 'Provider-reported token usage and paired baseline vs VeriCode benchmarks.' },
  { id: 'history', label: 'Task History', el: History, icon: HistoryIcon, group: 'Measure', description: 'All coding and pre-flight runs with their results.' },
  { id: 'settings', label: 'Settings', el: Settings, icon: SettingsIcon, group: 'System', description: 'Provider, models, integrations, sandbox and verification rules.' },
]
const GROUPS = ['Overview', 'Build', 'Verify', 'Measure', 'System']

export function navigate(page: string, param?: string) {
  window.location.hash = param ? `${page}/${param}` : page
}

function useHash() {
  const [h, setH] = useState(() => window.location.hash.slice(1))
  useEffect(() => {
    const f = () => setH(window.location.hash.slice(1))
    window.addEventListener('hashchange', f)
    return () => window.removeEventListener('hashchange', f)
  }, [])
  return h
}

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg aria-hidden viewBox="0 0 24 24" className="h-7 w-7 shrink-0">
        <rect x="1" y="1" width="22" height="22" rx="5" fill="#0f6f68" />
        <path d="M7 12.5l3.2 3.2L17 8.8" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {!compact && (
        <div className="min-w-0 leading-tight">
          <div className="text-[15px] font-semibold tracking-tight text-side-fg">VeriCode</div>
          <div className="text-[11px] text-side-muted">Verification Workspace</div>
        </div>
      )}
    </div>
  )
}

function Login({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const submit = async () => {
    setErr(null)
    try { await login(token.trim()); onDone() } catch (e) { setErr(e) }
  }
  return (
    <div className="flex min-h-full items-center justify-center bg-canvas p-6">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <svg aria-hidden viewBox="0 0 24 24" className="h-8 w-8"><rect x="1" y="1" width="22" height="22" rx="5" fill="#0f6f68" /><path d="M7 12.5l3.2 3.2L17 8.8" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <div><div className="text-base font-semibold text-fg">VeriCode</div><div className="text-xs text-fg-muted">Verify before you generate</div></div>
        </div>
        <div className="rounded-lg border border-line bg-surface p-5 shadow-raised">
          <h1 className="text-[15px] font-semibold text-fg">Sign in</h1>
          <p className="mt-1 text-[13px] text-fg-muted">Open the login URL printed by the server, or paste the access token from <span className="font-mono text-fg">.vericode_token</span>.</p>
          <label className="mt-4 block">
            <span className="mb-1 block text-xs font-medium text-fg-muted">Access token</span>
            <input aria-label="Access token" type="password" className={`${inputCls} font-mono`} value={token} onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }} placeholder="access token" autoFocus />
          </label>
          <div className="mt-4 flex justify-end"><Button onClick={submit} disabled={!token.trim()}>Sign in</Button></div>
          <div className="mt-3"><ErrorBox error={err} /></div>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  useEffect(() => {
    const url = new URL(window.location.href)
    const t = url.searchParams.get('token')
    const check = async () => {
      if (t) {
        url.searchParams.delete('token')
        window.history.replaceState(null, '', url.pathname + url.search + url.hash)
        try { await login(t); setAuthed(true); return } catch { /* fall through */ }
      }
      try { const s = await api<any>('/auth/status'); setCsrf(s.csrf); setAuthed(!!s.authenticated) } catch { setAuthed(false) }
    }
    check()
    const onAuth = () => setAuthed(false)
    window.addEventListener(AUTH_EVENT, onAuth)
    return () => window.removeEventListener(AUTH_EVENT, onAuth)
  }, [])
  if (authed === null) return <div className="p-6"><Spinner label="Connecting…" /></div>
  if (!authed) return <Login onDone={() => setAuthed(true)} />
  return <Shell onSignOut={() => setAuthed(false)} />
}

/** One list for every breakpoint: `rail` collapses it to icons below lg (tablet); the drawer passes rail=false. */
function NavList({ current, rail, onNavigate }: { current: string; rail: boolean; onNavigate?: () => void }) {
  const full = rail ? 'hidden lg:block' : 'block'
  return (
    <div className="flex-1 overflow-y-auto px-2 py-3">
      {GROUPS.map((g, gi) => (
        <div key={g} className={gi ? 'mt-4' : ''}>
          <div className={`px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-side-muted/80 ${full}`}>{g}</div>
          {rail && gi > 0 && <div className="mx-2 mb-3 border-t border-side-line lg:hidden" />}
          <ul className="space-y-0.5">
            {PAGES.filter((p) => p.group === g).map((p) => {
              const active = p.id === current
              const Icon = p.icon
              return (
                <li key={p.id}>
                  <a href={`#${p.id}`} aria-label={p.label} aria-current={active ? 'page' : undefined} title={p.label} onClick={onNavigate}
                    className={`group relative flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] no-underline ${rail ? 'justify-center lg:justify-start' : ''} ${
                      active ? 'bg-side-raised font-medium text-side-fg' : 'text-side-muted hover:bg-side-raised/60 hover:text-side-fg'}`}>
                    {active && <span aria-hidden className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-[#4fb3a9]" />}
                    <Icon className={`h-4 w-4 shrink-0 ${active ? 'text-[#7fcbc2]' : ''}`} />
                    <span className={`truncate ${rail ? 'hidden lg:inline' : ''}`}>{p.label}</span>
                  </a>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}

function SideStatus({ health }: { health: any }) {
  if (health.error) return <div className="text-[11px] text-[#f0a49e]">Backend offline</div>
  const h = health.data
  if (!h) return <div className="text-[11px] text-side-muted">…</div>
  return (
    <div className="space-y-1 text-[11px] text-side-muted">
      <div>Process sandbox network: <span className="text-side-fg">{h.network_isolation ? 'isolated (unshare)' : 'not isolated'}</span></div>
    </div>
  )
}

function Shell({ onSignOut }: { onSignOut: () => void }) {
  const hash = useHash()
  const [page, param] = hash.split('/')
  const current = PAGES.find((p) => p.id === page) ?? PAGES[0]
  const health = useApi<any>('/health', 15000)
  const integ = useApi<any>('/integrations', 60000)
  const [drawer, setDrawer] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const Page = current.el

  useEffect(() => { setDrawer(false) }, [hash])
  useEffect(() => {
    if (!drawer) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawer(false) }
    document.addEventListener('keydown', onKey)
    drawerRef.current?.querySelector<HTMLElement>('a[aria-current="page"], a')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [drawer])

  const signOut = async () => {
    try { await api('/auth/logout', { method: 'POST' }) } catch { /* session may already be gone */ }
    onSignOut()
  }
  const h = health.data
  const llm = integ.data?.llm
  const providerTone = health.error ? 'red' : !h ? 'gray' : h.provider === 'mock' || !h.provider_ready ? 'amber' : 'green'
  const providerLabel = health.error ? 'Backend offline' : !h ? '…' : h.provider === 'mock' ? 'LLM: mock (scripted demo)' : `LLM: ${h.provider}${h.provider_ready ? '' : ' (not ready)'}`

  return (
    <div className="flex h-full">
      {/* sidebar: icon rail on tablets, full on desktop, drawer on phones */}
      <nav aria-label="Main" className="hidden w-14 shrink-0 flex-col border-r border-side-line bg-side md:flex lg:w-60">
        <div className="flex h-14 items-center border-b border-side-line px-3 lg:px-4">
          <span className="lg:hidden"><Logo compact /></span><span className="hidden lg:block"><Logo /></span>
        </div>
        <div className="flex min-h-0 flex-1 flex-col"><NavList current={current.id} rail /></div>
        <div className="hidden border-t border-side-line px-4 py-3 lg:block"><SideStatus health={health} /></div>
      </nav>

      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-[#0b0f17]/50" onClick={() => setDrawer(false)} />
          <div ref={drawerRef} className="absolute inset-y-0 left-0 flex w-64 max-w-[85vw] flex-col bg-side shadow-overlay">
            <div className="flex h-14 items-center justify-between border-b border-side-line px-4">
              <Logo />
              <button type="button" aria-label="Close navigation" onClick={() => setDrawer(false)} className="rounded p-1 text-side-muted hover:bg-side-raised hover:text-side-fg"><X className="h-4 w-4" /></button>
            </div>
            <NavList current={current.id} rail={false} onNavigate={() => setDrawer(false)} />
            <div className="border-t border-side-line px-4 py-3"><SideStatus health={health} /></div>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-3 md:px-5">
          <button type="button" aria-label="Open navigation" onClick={() => setDrawer(true)} className="rounded-md p-1.5 text-fg-muted hover:bg-subtle md:hidden"><Menu className="h-5 w-5" /></button>
          <div className="min-w-0 flex-1 truncate text-[13px] text-fg-muted">
            <span className="hidden sm:inline">VeriCode</span><span className="mx-1.5 hidden text-fg-subtle sm:inline">/</span>
            <span className="font-medium text-fg">{current.label}</span>
            {param && <><span className="mx-1.5 text-fg-subtle">/</span><span className="font-mono text-xs">{param}</span></>}
          </div>
          <div className="hidden items-center gap-4 sm:flex">
            <span title={llm?.real ? `planner ${llm.planner_model || '—'} · coder ${llm.coder_model || '—'}` : undefined}>
              <StatusDot tone={providerTone} label={<>{providerLabel}{llm?.real && llm.coder_model ? <span className="ml-1 hidden font-mono text-[11px] text-fg-subtle xl:inline">{llm.coder_model}</span> : null}</>} />
            </span>
            {h && <span className="hidden md:inline"><StatusDot tone={h.tavily_configured ? 'green' : 'gray'} label={`Tavily: ${h.tavily_configured ? 'configured' : 'no key'}`} /></span>}
          </div>
          <Button variant="quiet" size="sm" onClick={signOut} title="Sign out" icon={<LogOut aria-hidden className="h-3.5 w-3.5" />}><span className="hidden sm:inline">Sign out</span></Button>
        </header>
        <main className="min-w-0 flex-1 overflow-auto">
          <div className="mx-auto max-w-[1400px] px-3 py-5 md:px-6 md:py-6">
            <div className="mb-5">
              <h1 className="text-lg font-semibold tracking-tight text-fg">{current.label}</h1>
              <p className="mt-0.5 text-[13px] text-fg-muted">{current.description}</p>
            </div>
            <Page param={param} />
          </div>
        </main>
      </div>
    </div>
  )
}
