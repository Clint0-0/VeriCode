import { useEffect, useState } from 'react'
import { api, AUTH_EVENT, login, setCsrf } from './api'
import { Button, ErrorBox, inputCls, Spinner, useApi } from './components/ui'
import Dashboard from './pages/Dashboard'
import Workspace from './pages/Workspace'
import Preflight from './pages/Preflight'
import Stale from './pages/Stale'
import Evidence from './pages/Evidence'
import Tokens from './pages/Tokens'
import History from './pages/History'
import Settings from './pages/Settings'

export const PAGES = [
  { id: 'dashboard', label: 'Dashboard', el: Dashboard },
  { id: 'workspace', label: 'Coding Workspace', el: Workspace },
  { id: 'preflight', label: 'Pre-Flight Inspector', el: Preflight },
  { id: 'stale', label: 'Stale-Answer Detector', el: Stale },
  { id: 'evidence', label: 'Evidence Explorer', el: Evidence },
  { id: 'tokens', label: 'Token Analytics', el: Tokens },
  { id: 'history', label: 'Task History', el: History },
  { id: 'settings', label: 'Settings & Rules', el: Settings },
] as const

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

function Login({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const submit = async () => {
    setErr(null)
    try { await login(token.trim()); onDone() } catch (e) { setErr(e) }
  }
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-md rounded-lg border border-ink-700 bg-ink-900 p-6">
        <div className="text-lg font-semibold text-slate-100">Veri<span className="text-sky-400">Code</span> — sign in</div>
        <p className="mt-2 text-sm text-slate-400">Open the login URL printed by the server, or paste the access token from <span className="font-mono">.vericode_token</span>.</p>
        <input aria-label="Access token" type="password" className={`${inputCls} mt-4 font-mono`} value={token} onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }} placeholder="access token" />
        <div className="mt-3 flex justify-end"><Button onClick={submit} disabled={!token.trim()}>Sign in</Button></div>
        <div className="mt-3"><ErrorBox error={err} /></div>
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
  return <Shell />
}

function Shell() {
  const hash = useHash()
  const [page, param] = hash.split('/')
  const current = PAGES.find((p) => p.id === page) ?? PAGES[0]
  const health = useApi<any>('/health', 15000)
  const Page = current.el
  return (
    <div className="flex h-full">
      <nav className="flex w-14 shrink-0 flex-col border-r border-ink-700 bg-ink-900 md:w-60">
        <div className="border-b border-ink-700 px-4 py-4">
          <div className="text-base font-semibold tracking-tight text-slate-100"><span className="md:hidden">V<span className="text-sky-400">C</span></span><span className="hidden md:inline">Veri<span className="text-sky-400">Code</span></span></div>
          <div className="hidden text-[11px] text-slate-500 md:block">Verify before you generate</div>
        </div>
        <ul className="flex-1 space-y-0.5 p-2">
          {PAGES.map((p) => (
            <li key={p.id}>
              <a href={`#${p.id}`} aria-label={p.label} aria-current={p.id === current.id ? 'page' : undefined}
                className={`block rounded-md px-3 py-1.5 text-sm ${p.id === current.id ? 'bg-ink-800 text-slate-100' : 'text-slate-400 hover:bg-ink-850 hover:text-slate-200'}`}>
                <span className="md:hidden" title={p.label}>{p.label.split(' ').map((w) => w[0]).join('').slice(0, 2)}</span>
                <span className="hidden md:inline">{p.label}</span>
              </a>
            </li>
          ))}
        </ul>
        <div className="hidden space-y-1 border-t border-ink-700 p-3 text-[11px] text-slate-500 md:block">
          {health.error ? <div className="text-rose-300">Backend offline</div> : health.data ? (
            <>
              <div>LLM: <span className={health.data.provider === 'mock' || !health.data.provider_ready ? 'text-amber-300' : 'text-emerald-300'}>{health.data.provider}{health.data.provider === 'mock' ? ' (scripted demo)' : health.data.provider_ready ? '' : ' (not ready)'}</span></div>
              <div>Tavily: <span className={health.data.tavily_configured ? 'text-emerald-300' : 'text-amber-300'}>{health.data.tavily_configured ? 'configured' : 'no key'}</span></div>
              <div>Process sandbox net: {health.data.network_isolation ? 'unshare' : 'not isolated'}</div>
            </>
          ) : '…'}
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl px-3 py-6 md:px-6">
          <h1 className="mb-5 text-lg font-semibold text-slate-100">{current.label}</h1>
          <Page param={param} />
        </div>
      </main>
    </div>
  )
}
