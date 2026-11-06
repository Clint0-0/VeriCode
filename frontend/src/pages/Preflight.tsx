import { useState } from 'react'
import { api } from '../api'
import { FindingsList } from '../components/Findings'
import { TokenTable } from '../components/TaskReport'
import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Mono, Spinner, useApi } from '../components/ui'

export default function Preflight(_: { param?: string }) {
  const ws = useApi<any[]>('/workspaces')
  const cat = useApi<any[]>('/catalog')
  const [path, setPath] = useState('sample_project')
  const [envData, setEnvData] = useState<any>(null)
  const [task, setTask] = useState('')
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [manual, setManual] = useState({ package: 'pydantic', import_path: 'pydantic', name: 'BaseSettings', type: 'class', arguments: '' })
  const [manualRes, setManualRes] = useState<any>(null)

  const inspect = async () => {
    setBusy('inspect'); setErr(null)
    try { setEnvData(await api('/projects/inspect', { body: { path } })) } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const run = async () => {
    setBusy('preflight'); setErr(null); setRes(null)
    try { setRes(await api('/preflight', { body: { path, task, live: true } })) } catch (e) { setErr(e) } finally { setBusy(null) }
  }
  const check = async () => {
    setBusy('manual'); setErr(null)
    try {
      setManualRes(await api('/verify-api', { body: { path, ...manual, arguments: manual.arguments.split(',').map((s) => s.trim()).filter(Boolean), live: true } }))
    } catch (e) { setErr(e) } finally { setBusy(null) }
  }

  return (
    <div className="space-y-5">
      <Card title="Project environment" actions={<Button variant="ghost" onClick={inspect} disabled={!!busy}>{busy === 'inspect' ? 'Inspecting…' : 'Inspect'}</Button>}>
        <div className="mb-3 max-w-xs">
          <select aria-label="Workspace" className={inputCls} value={path} onChange={(e) => setPath(e.target.value)}>
            {(ws.data ?? []).map((w) => <option key={w.name} value={w.name}>{w.name}</option>)}
          </select>
        </div>
        {!envData ? <Empty>Inspect a workspace to see declared, resolved and installed dependency versions.</Empty> : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(envData.languages).map(([k, v]: any) => <Badge key={k} tone="blue">{k}: {v} files</Badge>)}
              {envData.frameworks.map((f: string) => <Badge key={f} tone="gray">{f}</Badge>)}
              <span className="text-slate-500">checks: {envData.test_commands.map((c: string[]) => c.join(' ')).join(', ') || 'none'}</span>
            </div>
            {envData.warnings.map((w: string) => <div key={w} className="text-xs text-amber-300">{w}</div>)}
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Package</th><th>Declared</th><th>Resolved (lockfile)</th><th>Installed</th><th>Status</th></tr></thead>
              <tbody>{envData.dependencies.map((d: any) => (
                <tr key={d.ecosystem + d.name} className="border-t border-ink-700">
                  <td className="py-1 font-mono text-xs">{d.name} <span className="text-slate-500">({d.ecosystem})</span></td>
                  <td className="font-mono text-xs text-slate-400">{d.declared ?? '—'} <span className="text-slate-600">{d.declared_in}</span></td>
                  <td className="font-mono text-xs text-slate-400">{d.resolved ?? '—'}</td>
                  <td className="font-mono text-xs text-slate-100">{d.installed ?? '—'}</td>
                  <td><Badge tone={d.status === 'ok' ? 'green' : d.status === 'mismatch' ? 'amber' : 'red'}>{d.status}</Badge></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Run pre-flight for a task (planner + local + live verification, no code generation)">
        <div className="flex gap-2">
          <select aria-label="Demo task" className={`${inputCls} max-w-xs`} onChange={(e) => { const t = cat.data?.find((x) => x.id === e.target.value); if (t) setTask(t.prompt) }}>
            <option value="">— load demo task —</option>
            {(cat.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}
          </select>
          <input aria-label="Task" className={inputCls} value={task} onChange={(e) => setTask(e.target.value)} placeholder="Task description" />
          <Button onClick={run} disabled={!!busy || task.length < 3}>{busy === 'preflight' ? 'Running…' : 'Run pre-flight'}</Button>
        </div>
        <div className="mt-3"><ErrorBox error={err} /></div>
        {busy === 'preflight' && <div className="mt-3"><Spinner label="Planning and verifying…" /></div>}
        {res && (
          <div className="mt-4 space-y-4">
            <div>
              <div className="mb-1 text-xs font-medium text-slate-400">Planned API skeleton (validated JSON)</div>
              <Mono className="max-h-64">{JSON.stringify(res.skeleton, null, 2)}</Mono>
              {res.skeleton_errors?.length > 0 && <div className="mt-1 text-xs text-amber-300">Schema corrections: {res.skeleton_errors.join(' | ')}</div>}
            </div>
            <FindingsList findings={res.findings} />
            <div>
              <div className="mb-1 text-xs font-medium text-slate-400">Surgical briefing</div>
              <Mono>{res.briefing}</Mono>
            </div>
            <TokenTable tokens={res.tokens} />
          </div>
        )}
      </Card>

      <Card title="Check a single API (deterministic, no LLM)">
        <div className="grid gap-3 md:grid-cols-6">
          {(['package', 'import_path', 'name', 'arguments'] as const).map((k) => (
            <Field key={k} label={k}><input aria-label={k} className={inputCls} value={(manual as any)[k]} onChange={(e) => setManual({ ...manual, [k]: e.target.value })} /></Field>
          ))}
          <Field label="type">
            <select aria-label="type" className={inputCls} value={manual.type} onChange={(e) => setManual({ ...manual, type: e.target.value })}>
              {['function', 'class', 'method', 'decorator', 'attribute', 'module'].map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <div className="flex items-end"><Button onClick={check} disabled={!!busy}>Verify</Button></div>
        </div>
        {manualRes && <div className="mt-4"><FindingsList findings={[manualRes]} /></div>}
      </Card>
    </div>
  )
}
