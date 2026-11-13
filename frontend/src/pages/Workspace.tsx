import { useState } from 'react'
import { api } from '../api'
import { TaskReport } from '../components/TaskReport'
import { Button, Card, ErrorBox, Field, inputCls, Select, Spinner, useApi } from '../components/ui'

export default function Workspace(_: { param?: string }) {
  const ws = useApi<any[]>('/workspaces')
  const cat = useApi<any[]>('/catalog')
  const [path, setPath] = useState('sample_project')
  const [prompt, setPrompt] = useState('')
  const [catalogId, setCatalogId] = useState<string>('')
  const [mode, setMode] = useState<'vericode' | 'baseline'>('vericode')
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
      <Card title="New coding task">
        <div className="grid gap-4 md:grid-cols-3">
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
          <Field label="Mode">
            <Select aria-label="Mode" className="w-full" value={mode} onChange={(e) => setMode(e.target.value as any)}>
              <option value="vericode">VeriCode (pre-flight + surgical context)</option>
              <option value="baseline">Baseline (whole repo, no pre-flight)</option>
            </Select>
          </Field>
        </div>
        <div className="mt-4">
          <Field label="Instruction">
            <textarea aria-label="Instruction" className={`${inputCls} h-28 font-mono`} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the change…" />
          </Field>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-slate-400"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> Live documentation verification (Tavily) for risky APIs</label>
          <Button onClick={start} disabled={busy || !!running || prompt.trim().length < 3}>{busy ? 'Starting…' : 'Run task'}</Button>
        </div>
        <div className="mt-3"><ErrorBox error={err} /></div>
      </Card>
      {taskId && (task.data ? <TaskReport task={task.data} onApplied={task.reload} /> : task.error ? <ErrorBox error={task.error} /> : <Spinner label="Starting task…" />)}
    </div>
  )
}
