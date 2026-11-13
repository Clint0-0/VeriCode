import { useMemo, useState } from 'react'
import { ArrowLeft, Search } from 'lucide-react'
import { fmt } from '../api'
import { TaskReport } from '../components/TaskReport'
import { Badge, Card, DataTable, Empty, ErrorBox, inputCls, Select, Spinner, useApi } from '../components/ui'

const repoOf = (p?: string) => (p ? p.split(/[\\/]/).filter(Boolean).pop() : '—')

export default function History({ param }: { param?: string }) {
  const list = useApi<any[]>('/tasks', 5000)
  const one = useApi<any>(param ? `/tasks/${param}` : null, param ? 3000 : undefined)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [mode, setMode] = useState('')
  const modes = useMemo(() => [...new Set((list.data ?? []).map((t) => t.mode))].sort(), [list.data])
  const statuses = useMemo(() => [...new Set((list.data ?? []).map((t) => t.status))].sort(), [list.data])

  if (param) {
    return (
      <div className="space-y-4">
        <a href="#history" className="inline-flex items-center gap-1 text-xs font-medium no-underline"><ArrowLeft aria-hidden className="h-3.5 w-3.5" />All tasks</a>
        {one.error ? <ErrorBox error={one.error} /> : one.data ? (
          <>
            <Card title="Task">
              <p className="text-[13px] leading-relaxed text-fg">{one.data.prompt}</p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted"><span>repository <b className="font-mono font-medium text-fg">{repoOf(one.data.project_path)}</b></span><span>created <b className="font-medium text-fg">{fmt.time(one.data.created_at)}</b></span>{one.data.finished_at && <span>finished <b className="font-medium text-fg">{fmt.time(one.data.finished_at)}</b></span>}</div>
            </Card>
            <TaskReport task={one.data} onApplied={one.reload} />
          </>
        ) : <Spinner />}
      </div>
    )
  }
  if (list.loading) return <Spinner />
  if (list.error) return <ErrorBox error={list.error} />
  const all = list.data ?? []
  const rows = all.filter((t) => (!status || t.status === status) && (!mode || t.mode === mode) && (!q || `${t.id} ${t.prompt} ${t.project_path}`.toLowerCase().includes(q.toLowerCase())))
  return (
    <Card title="All tasks" description={all.length ? `${rows.length} of ${all.length} shown` : undefined} flush
      actions={all.length > 0 && <>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 text-fg-subtle" />
          <input aria-label="Search tasks" className={`${inputCls} h-7 w-56 py-0 pl-7 text-xs`} placeholder="Search id, prompt, repository…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select size="sm" aria-label="Filter by mode" className="w-40" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="">all modes</option>{modes.map((m) => <option key={m} value={m}>{m}</option>)}
        </Select>
        <Select size="sm" aria-label="Filter by status" className="w-36" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">all statuses</option>{statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
      </>}>
      {!all.length ? <div className="p-4"><Empty>No tasks yet.</Empty></div> : !rows.length ? <div className="p-4"><Empty>No tasks match the filters.</Empty></div> : (
        <DataTable label="Tasks" caption="* estimated token counts">
          <thead><tr><th>Task</th><th>Prompt</th><th>Repository</th><th>Mode</th><th>Status</th><th className="text-right">Tokens</th><th className="text-right">Duration</th><th>Created</th></tr></thead>
          <tbody>{rows.map((t) => (
            <tr key={t.id}>
              <td><a className="font-mono text-xs no-underline" href={`#history/${t.id}`}>{t.id}</a></td>
              <td className="min-w-[14rem] max-w-[28rem]"><span className="line-clamp-2 text-fg">{t.prompt}</span>{t.changed_files?.length > 0 && <div className="mt-0.5 truncate font-mono text-[11px] text-fg-subtle">{t.changed_files.join(', ')}</div>}</td>
              <td className="font-mono text-xs text-fg-muted">{repoOf(t.project_path)}</td>
              <td><span className="font-mono text-xs text-fg-muted">{t.mode}</span>{t.benchmark_id && <span className="ml-1 rounded bg-subtle px-1 text-[10px] text-fg-subtle">bench</span>}</td>
              <td><Badge>{t.status}</Badge></td>
              <td className="text-right tabular-nums text-fg-muted">{t.tokens ? fmt.n(t.tokens.total) : '—'}{t.tokens?.estimated ? <span className="text-warn">*</span> : ''}</td>
              <td className="text-right tabular-nums text-fg-muted">{t.created_at && t.finished_at ? `${(t.finished_at - t.created_at).toFixed(1)}s` : '—'}</td>
              <td className="whitespace-nowrap text-xs text-fg-subtle">{fmt.time(t.created_at)}</td>
            </tr>
          ))}</tbody>
        </DataTable>
      )}
    </Card>
  )
}
