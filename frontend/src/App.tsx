import { useEffect, useState } from 'react'
import { useApi } from './components/ui'
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

export default function App() {
  const hash = useHash()
  const [page, param] = hash.split('/')
  const current = PAGES.find((p) => p.id === page) ?? PAGES[0]
  const health = useApi<any>('/health', 15000)
  const Page = current.el
  return (
    <div className="flex h-full">
      <nav className="flex w-60 shrink-0 flex-col border-r border-ink-700 bg-ink-900">
        <div className="border-b border-ink-700 px-4 py-4">
          <div className="text-base font-semibold tracking-tight text-slate-100">Veri<span className="text-sky-400">Code</span></div>
          <div className="text-[11px] text-slate-500">Verify before you generate</div>
        </div>
        <ul className="flex-1 space-y-0.5 p-2">
          {PAGES.map((p) => (
            <li key={p.id}>
              <a href={`#${p.id}`} aria-current={p.id === current.id ? 'page' : undefined}
                className={`block rounded-md px-3 py-1.5 text-sm ${p.id === current.id ? 'bg-ink-800 text-slate-100' : 'text-slate-400 hover:bg-ink-850 hover:text-slate-200'}`}>
                {p.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="space-y-1 border-t border-ink-700 p-3 text-[11px] text-slate-500">
          {health.error ? <div className="text-rose-300">Backend offline</div> : health.data ? (
            <>
              <div>LLM: <span className={health.data.provider === 'mock' ? 'text-amber-300' : 'text-slate-300'}>{health.data.provider}{health.data.provider === 'mock' ? ' (scripted demo)' : ''}</span></div>
              <div>Tavily: <span className={health.data.tavily_configured ? 'text-emerald-300' : 'text-amber-300'}>{health.data.tavily_configured ? 'configured' : 'no key'}</span></div>
              <div>Sandbox net: {health.data.network_isolation ? 'isolated' : 'not isolated'}</div>
            </>
          ) : '…'}
        </div>
      </nav>
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <h1 className="mb-5 text-lg font-semibold text-slate-100">{current.label}</h1>
          <Page param={param} />
        </div>
      </main>
    </div>
  )
}
