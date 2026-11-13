import { useState } from 'react'
import { Play, ScanSearch } from 'lucide-react'
import { api } from '../api'
import { FindingsList } from '../components/Findings'
import { ConfidenceHeatmap } from '../components/Heatmap'
import { TokenTable } from '../components/TaskReport'
import { Badge, Button, Card, DataTable, Empty, ErrorBox, Expand, Field, inputCls, Mono, Select, Spinner, Stat, useApi } from '../components/ui'

const DEP_TONE: Record<string, string> = { INSTALLED: 'green', VERSION_MISMATCH: 'amber', NOT_INSTALLED: 'red', UNKNOWN: 'gray', UNRESOLVED: 'gray' }
const DEP_HELP: Record<string, string> = {
  INSTALLED: 'installed in the project environment',
  VERSION_MISMATCH: 'installed version differs from the lockfile or the declared range',
  NOT_INSTALLED: 'environment available, package absent',
  UNKNOWN: 'no usable environment: installed version unknown (not proof it is missing)',
  UNRESOLVED: 'installed version unknown and not in the lockfile',
}
const ENV_TONE: Record<string, 'green' | 'amber' | 'red' | 'gray'> = { AVAILABLE: 'green', AMBIGUOUS: 'amber', UNAVAILABLE: 'gray', CONFIGURATION_ERROR: 'red' }
const LOCKFILES = ['poetry.lock', 'uv.lock', 'Pipfile.lock', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock']

function EnvironmentPanel({ envData, path, onChanged }: { envData: any; path: string; onChanged: () => void }) {
  const manifests: string[] = envData.manifests ?? []
  const locks = manifests.filter((m) => LOCKFILES.includes(m.split('/').pop() ?? ''))
  const envs: Record<string, any> = envData.environments ?? {}
  const py = envs.python
  const [interp, setInterp] = useState(py?.source === 'configured' ? py.interpreter ?? '' : '')
  const [msg, setMsg] = useState<unknown>(null)
  const save = async (value: string) => {
    setMsg(null)
    try { await api('/projects/python-interpreter', { body: { path, interpreter: value } }); onChanged() } catch (e) { setMsg(e) }
  }
  const inspected = envData.dependencies.filter((d: any) => d.installed).length
  return (
    <div className="space-y-2 border-b border-line px-4 py-3 text-xs">
      <div className="flex flex-wrap gap-x-5 gap-y-1.5">
        <span>Manifest <Badge tone={manifests.length ? 'green' : 'gray'}>{manifests.filter((m) => !LOCKFILES.includes(m.split('/').pop() ?? '')).join(', ') || 'none'}</Badge></span>
        <span>Lockfile <Badge tone={locks.length ? 'green' : 'gray'}>{locks.join(', ') || 'none (no resolved versions)'}</Badge></span>
        {Object.entries(envs).map(([eco, e]: any) => (
          <span key={eco}>{eco === 'python' ? 'Python' : 'Node'} environment <Badge tone={ENV_TONE[e.status] ?? 'gray'}>{e.status}</Badge>
            {e.source && <span className="ml-1 text-fg-muted">{e.source}{e.version ? ` · ${e.version}` : ''}</span>}</span>
        ))}
        <span>Installed inspection <Badge tone={inspected ? 'green' : 'gray'}>{inspected}/{envData.dependencies.length} versions read</Badge></span>
      </div>
      {py && py.interpreter && <div className="font-mono text-[11px] text-fg-muted">interpreter: {py.interpreter}</div>}
      {py && (py.status === 'UNAVAILABLE' || py.status === 'CONFIGURATION_ERROR') && (
        <div className="rounded-md border border-line bg-subtle/60 p-2.5 text-fg">
          <b className="font-medium">{py.status === 'UNAVAILABLE' ? 'Python environment unavailable.' : 'Python environment misconfigured.'}</b> Declared dependencies were detected, but installed versions could not be verified, so their APIs are reported as uncertain, not missing.
          <div className="mt-1 text-fg-muted">{py.detail} Create one with <span className="font-mono">python -m venv .venv</span> and install the requirements, or choose the project's interpreter below. VeriCode never installs packages itself.</div>
        </div>
      )}
      {py && py.status === 'AMBIGUOUS' && <div className="text-warn">{py.detail}</div>}
      {py && (
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label="Python interpreter" className={`${inputCls} max-w-md font-mono text-xs`} value={interp} onChange={(e) => setInterp(e.target.value)} placeholder="Absolute path to the project's python / python.exe (optional)" />
          <Button size="sm" variant="ghost" onClick={() => save(interp)} disabled={!interp.trim()}>Use interpreter</Button>
          {py.source === 'configured' && <Button size="sm" variant="quiet" onClick={() => { setInterp(''); save('') }}>Clear</Button>}
        </div>
      )}
      <ErrorBox error={msg} />
    </div>
  )
}

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
  const switchWorkspace = (p: string) => {  // results always belong to the selected workspace: never show another one's
    setPath(p); setEnvData(null); setRes(null); setManualRes(null); setErr(null)
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
  const sum = res?.summary ?? { planned: findings.length, analyzed: 0, verified: 0, not_found: 0, uncertain: 0, error: 0, problems: 0 }

  return (
    <div className="space-y-5">
      <Card title="Project environment" description="Declared, resolved and installed versions — the ground truth every check uses."
        actions={<>
          <Select aria-label="Workspace" size="sm" className="w-48" value={path} onChange={(e) => switchWorkspace(e.target.value)}>
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
            <EnvironmentPanel key={envData.root} envData={envData} path={path} onChanged={() => { setRes(null); setManualRes(null); inspect() }} />
            {envData.warnings.filter((w: string) => !w.startsWith('Python environment')).map((w: string) => <div key={w} className="border-b border-line px-4 py-2 text-xs text-warn">{w}</div>)}
            <DataTable label="Dependencies">
              <thead><tr><th>Package</th><th>Declared</th><th>Resolved (lockfile)</th><th>Installed</th><th>Status</th></tr></thead>
              <tbody>{envData.dependencies.map((d: any) => (
                <tr key={d.ecosystem + d.name}>
                  <td className="font-mono text-xs text-fg">{d.name} <span className="text-fg-subtle">({d.ecosystem})</span></td>
                  <td className="font-mono text-xs text-fg-muted">{d.declared ?? '—'} <span className="text-fg-subtle">{d.declared_in}</span></td>
                  <td className="font-mono text-xs text-fg-muted">{d.resolved ?? '—'}</td>
                  <td className="font-mono text-xs font-medium text-fg">{d.installed ?? '—'}</td>
                  <td><Badge tone={DEP_TONE[d.status] ?? 'gray'} title={DEP_HELP[d.status]}>{d.status}</Badge></td>
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
            <div className="text-xs text-fg-muted">Report for <b className="font-medium text-fg">{res.workspace ?? path}</b> · run <span className="font-mono">{res.task_id}</span></div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <Stat label="Planned APIs" value={sum.planned} sub={`${sum.analyzed} analyzed`} />
              <Stat label="Verified" value={sum.verified} sub="exist in installed package" tone={sum.verified ? 'green' : undefined} />
              <Stat label="Not found" value={sum.not_found} tone={sum.not_found ? 'red' : undefined} />
              <Stat label="Uncertain" value={sum.uncertain} sub="not enough evidence" tone={sum.uncertain ? 'amber' : undefined} />
              <Stat label="Verification errors" value={sum.error} sub="tool failed: not checked" tone={sum.error ? 'amber' : undefined} />
              <Stat label="Planner tokens" value={res.tokens?.total ?? '—'} sub={res.tokens?.measurement} />
            </div>
            {sum.problems > 0 && <div className="text-xs text-fg-muted">{sum.problems} with problems (not found · incompatible · deprecated) — see findings.</div>}
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
