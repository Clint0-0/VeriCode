import { useState } from 'react'
import { Play, ScanSearch } from 'lucide-react'
import { api } from '../api'
import { FindingsList } from '../components/Findings'
import { ConfidenceHeatmap } from '../components/Heatmap'
import { TokenTable } from '../components/TaskReport'
import { Badge, Button, Card, DataTable, Empty, ErrorBox, Expand, Field, inputCls, Mono, Select, Spinner, Stat, useApi } from '../components/ui'

const PROBLEMS = ['NOT_FOUND', 'INCOMPATIBLE', 'DEPRECATED']

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
  const findings: any[] = res?.findings ?? []
  const verified = findings.filter((f) => String(f.status).startsWith('VERIFIED')).length
  const problems = findings.filter((f) => PROBLEMS.includes(f.status)).length
  const toolErrors = findings.filter((f) => f.status === 'ERROR').length

  return (
    <div className="space-y-5">
      <Card title="Project environment" description="Declared, resolved and installed versions — the ground truth every check uses."
        actions={<>
          <Select aria-label="Workspace" size="sm" className="w-48" value={path} onChange={(e) => setPath(e.target.value)}>
            {(ws.data ?? []).map((w) => <option key={w.name} value={w.name}>{w.name}</option>)}
          </Select>
          <Button variant="ghost" size="sm" onClick={inspect} disabled={!!busy} icon={<ScanSearch aria-hidden className="h-3.5 w-3.5" />}>{busy === 'inspect' ? 'Inspecting…' : 'Inspect'}</Button>
        </>} flush>
        {!envData ? <div className="p-4"><Empty>Inspect a workspace to see declared, resolved and installed dependency versions.</Empty></div> : (
          <>
            <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 text-xs">
              {Object.entries(envData.languages).map(([k, v]: any) => <Badge key={k} tone="blue">{k}: {v} files</Badge>)}
              {envData.frameworks.map((f: string) => <Badge key={f} tone="gray">{f}</Badge>)}
              <span className="text-fg-muted">checks: <span className="font-mono text-fg">{envData.test_commands.map((c: string[]) => c.join(' ')).join(', ') || 'none'}</span></span>
            </div>
            {envData.warnings.map((w: string) => <div key={w} className="border-b border-line px-4 py-2 text-xs text-warn">{w}</div>)}
            <DataTable label="Dependencies">
              <thead><tr><th>Package</th><th>Declared</th><th>Resolved (lockfile)</th><th>Installed</th><th>Status</th></tr></thead>
              <tbody>{envData.dependencies.map((d: any) => (
                <tr key={d.ecosystem + d.name}>
                  <td className="font-mono text-xs text-fg">{d.name} <span className="text-fg-subtle">({d.ecosystem})</span></td>
                  <td className="font-mono text-xs text-fg-muted">{d.declared ?? '—'} <span className="text-fg-subtle">{d.declared_in}</span></td>
                  <td className="font-mono text-xs text-fg-muted">{d.resolved ?? '—'}</td>
                  <td className="font-mono text-xs font-medium text-fg">{d.installed ?? '—'}</td>
                  <td><Badge tone={d.status === 'ok' ? 'green' : d.status === 'mismatch' ? 'amber' : 'red'}>{d.status}</Badge></td>
                </tr>
              ))}</tbody>
            </DataTable>
          </>
        )}
      </Card>

      <Card title="Run pre-flight for a task" description="Planner + local + live verification. No code is generated.">
        <div className="flex flex-col gap-2 md:flex-row">
          <Select aria-label="Demo task" className="w-full md:w-60 md:shrink-0" value="" onChange={(e) => { const t = cat.data?.find((x) => x.id === e.target.value); if (t) setTask(t.prompt) }}>
            <option value="">— load demo task —</option>
            {(cat.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}
          </Select>
          <input aria-label="Task" className={inputCls} value={task} onChange={(e) => setTask(e.target.value)} placeholder="Task description" />
          <Button onClick={run} disabled={!!busy || task.length < 3} icon={<Play aria-hidden className="h-3.5 w-3.5" />}>{busy === 'preflight' ? 'Running…' : 'Run pre-flight'}</Button>
        </div>
        <div className="mt-3"><ErrorBox error={err} /></div>
        {busy === 'preflight' && <div className="mt-3"><Spinner label="Planning and verifying…" /></div>}
        {res && (
          <div className="mt-4 space-y-5">
            <div className={`grid grid-cols-2 gap-3 ${toolErrors ? 'md:grid-cols-5' : 'md:grid-cols-4'}`}>
              <Stat label="Planned APIs" value={findings.length} />
              <Stat label="Verified" value={verified} tone={verified ? 'green' : undefined} />
              <Stat label="Problems" value={problems} sub="not found · incompatible · deprecated" tone={problems ? 'red' : undefined} />
              {toolErrors > 0 && <Stat label="Not checked" value={toolErrors} sub="verification tool error" tone="amber" />}
              <Stat label="Planner tokens" value={res.tokens?.total ?? '—'} sub={res.tokens?.measurement} />
            </div>
            <div>
              <div className="mb-2 text-xs font-medium text-fg-muted">API confidence overview</div>
              {findings.length ? <ConfidenceHeatmap findings={findings} /> : <Empty>No third-party APIs planned.</Empty>}
            </div>
            <div>
              <div className="mb-2 text-xs font-medium text-fg-muted">Findings</div>
              <FindingsList findings={findings} />
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <Expand head={<span className="text-[13px] font-medium">Planned API skeleton (validated JSON)</span>}>
                <Mono className="max-h-72">{JSON.stringify(res.skeleton, null, 2)}</Mono>
                {res.skeleton_errors?.length > 0 && <div className="mt-2 text-xs text-warn">Schema corrections: {res.skeleton_errors.join(' | ')}</div>}
              </Expand>
              <Expand head={<span className="text-[13px] font-medium">Surgical briefing (coder prompt)</span>} defaultOpen>
                <Mono>{res.briefing}</Mono>
              </Expand>
            </div>
            <div className="max-w-xl"><div className="mb-2 text-xs font-medium text-fg-muted">Token usage</div><TokenTable tokens={res.tokens} /></div>
          </div>
        )}
      </Card>

      <Card title="Check a single API" description="Deterministic: resolved against installed source or the TypeScript compiler. No LLM.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {(['package', 'import_path', 'name', 'arguments'] as const).map((k) => (
            <Field key={k} label={k.replace('_', ' ')}><input aria-label={k} className={`${inputCls} font-mono`} value={(manual as any)[k]} onChange={(e) => setManual({ ...manual, [k]: e.target.value })} /></Field>
          ))}
          <Field label="type">
            <Select aria-label="type" className="w-full" value={manual.type} onChange={(e) => setManual({ ...manual, type: e.target.value })}>
              {['function', 'class', 'method', 'decorator', 'attribute', 'module'].map((t) => <option key={t}>{t}</option>)}
            </Select>
          </Field>
          <div className="flex items-end"><Button variant="ghost" onClick={check} disabled={!!busy}>{busy === 'manual' ? 'Verifying…' : 'Verify'}</Button></div>
        </div>
        {manualRes && <div className="mt-4"><FindingsList findings={[manualRes]} /></div>}
      </Card>
    </div>
  )
}
