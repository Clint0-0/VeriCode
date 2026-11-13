import { useEffect, useState } from 'react'
import { Play } from 'lucide-react'
import { api } from '../api'
import { TaskReport } from '../components/TaskReport'
import { Badge, Button, Card, Checkbox, ErrorBox, Field, inputCls, Select, Spinner, useApi } from '../components/ui'

const MODES = [
  { value: 'vericode', label: 'VeriCode — adaptive', hint: 'Pre-flight only when the task shows API risk; generated code is always audited.' },
  { value: 'vericode_full', label: 'VeriCode — full pre-flight', hint: 'Planner + API verification before every task.' },
  { value: 'baseline', label: 'Baseline — whole repository', hint: 'Conventional agent: entire repo as context, no pre-flight.' },
]

function RepoPanel({ path }: { path: string }) {
  const [env, setEnv] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  useEffect(() => {
    let alive = true
    setEnv(null); setErr(null)
    if (!path) return
    api('/projects/inspect', { body: { path } }).then((d) => { if (alive) setEnv(d) }).catch((e) => { if (alive) setErr(e) })
    return () => { alive = false }
  }, [path])
  if (err) return <p className="text-xs text-fg-muted">Repository details unavailable: {(err as any)?.message ?? String(err)}</p>
  if (!env) return <Spinner label="Inspecting repository…" />
  const deps = env.dependencies ?? []
  return (
    <div className="space-y-3 text-[13px]">
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(env.languages ?? {}).map(([k, v]: any) => <Badge key={k} tone="blue">{k} · {v} files</Badge>)}
        {(env.frameworks ?? []).map((f: string) => <Badge key={f} tone="gray">{f}</Badge>)}
      </div>
      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">Validation</div>
        <div className="mt-0.5 font-mono text-xs text-fg">{(env.test_commands ?? []).map((c: string[]) => c.join(' ')).join(' · ') || 'no test command (changes would be unvalidated)'}</div>
      </div>
      <div>
        <div className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">Installed dependencies ({deps.length})</div>
        <ul className="mt-1 space-y-0.5">
          {deps.slice(0, 8).map((d: any) => (
            <li key={d.ecosystem + d.name} className="flex items-center justify-between gap-2 font-mono text-xs"><span className="truncate text-fg">{d.name}</span><span className={d.installed ? 'text-fg-muted' : 'text-err'}>{d.installed ?? 'not installed'}</span></li>
          ))}
          {deps.length > 8 && <li className="text-xs text-fg-subtle">+{deps.length - 8} more (Pre-Flight Inspector)</li>}
        </ul>
      </div>
      {(env.warnings ?? []).map((w: string) => <div key={w} className="text-xs text-warn">{w}</div>)}
    </div>
  )
}

export default function Workspace(_: { param?: string }) {
  const ws = useApi<any[]>('/workspaces')
  const cat = useApi<any[]>('/catalog')
  const [path, setPath] = useState('sample_project')
  const [prompt, setPrompt] = useState('')
  const [catalogId, setCatalogId] = useState<string>('')
  const [mode, setMode] = useState<string>('vericode')
  const [live, setLive] = useState(true)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const task = useApi<any>(taskId ? `/tasks/${taskId}` : null, 1500)
  const running = task.data && (String(task.data.status).startsWith('running') || task.data.status === 'queued')

  const pick = (id: string) => {
    setCatalogId(id)
    const t = cat.data?.find((x) => x.id === id)
    if (t) { setPrompt(t.prompt); setPath(t.project) }
  }
  const start = async () => {
    setErr(null); setBusy(true)
    try {
      const body: any = { path, prompt, mode, live }
      const t = cat.data?.find((x) => x.id === catalogId)
      if (t && t.prompt === prompt) body.catalog_id = catalogId // attaches the task's acceptance tests
      const r = await api<any>('/tasks', { body })
      setTaskId(r.task_id)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card title="New coding task" description="The change runs in an isolated copy of the workspace; nothing is written to your files until you apply it.">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Workspace">
              <Select aria-label="Workspace" className="w-full" value={path} onChange={(e) => setPath(e.target.value)}>
                {(ws.data ?? []).map((w) => <option key={w.name} value={w.name}>{w.name}</option>)}
              </Select>
            </Field>
            <Field label="Demo task (optional)" hint="Bundled tasks include acceptance tests">
              <Select aria-label="Demo task" className="w-full" value={catalogId} onChange={(e) => pick(e.target.value)}>
                <option value="">— custom —</option>
                {(cat.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
              </Select>
            </Field>
            <Field label="Mode" hint={MODES.find((m) => m.value === mode)?.hint}>
              <Select aria-label="Mode" className="w-full" value={mode} onChange={(e) => setMode(e.target.value)}>
                {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </Select>
            </Field>
          </div>
          <div className="mt-3">
            <Field label="Instruction">
              <textarea aria-label="Instruction" className={`${inputCls} h-32 resize-y font-mono leading-relaxed`} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the change…" />
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <Checkbox checked={live} onChange={setLive}>Live documentation verification (Tavily) for risky APIs</Checkbox>
            <Button onClick={start} disabled={busy || !!running || prompt.trim().length < 3} icon={<Play aria-hidden className="h-3.5 w-3.5" />}>{busy ? 'Starting…' : 'Run task'}</Button>
          </div>
          <div className="mt-3"><ErrorBox error={err} /></div>
        </Card>
        <Card title="Repository" description={<span className="font-mono">{path}</span>}><RepoPanel path={path} /></Card>
      </div>
      {taskId && (task.data ? <TaskReport task={task.data} onApplied={task.reload} /> : task.error ? <ErrorBox error={task.error} /> : <Spinner label="Starting task…" />)}
    </div>
  )
}
