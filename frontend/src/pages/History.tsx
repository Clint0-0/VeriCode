import { fmt } from '../api'
import { TaskReport } from '../components/TaskReport'
import { Badge, Card, Empty, ErrorBox, Spinner, useApi } from '../components/ui'

export default function History({ param }: { param?: string }) {
  const list = useApi<any[]>('/tasks', 5000)
  const one = useApi<any>(param ? `/tasks/${param}` : null, param ? 3000 : undefined)
  if (param) {
    return (
      <div className="space-y-3">
        <a href="#history" className="text-xs text-sky-300 hover:underline">← all tasks</a>
        {one.error ? <ErrorBox error={one.error} /> : one.data ? <><p className="text-sm text-slate-300">{one.data.prompt}</p><TaskReport task={one.data} onApplied={one.reload} /></> : <Spinner />}
      </div>
    )
  }
  if (list.loading) return <Spinner />
  if (list.error) return <ErrorBox error={list.error} />
  return (
    <Card title="All tasks">
      {!list.data?.length ? <Empty>No tasks yet.</Empty> : (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Task</th><th>Date</th><th>Mode</th><th>Prompt</th><th>Files</th><th>Tokens</th><th>Status</th></tr></thead>
          <tbody>{list.data.map((t) => (
            <tr key={t.id} className="border-t border-ink-700">
              <td className="py-2"><a className="font-mono text-xs text-sky-300 hover:underline" href={`#history/${t.id}`}>{t.id}</a></td>
              <td className="whitespace-nowrap text-xs text-slate-400">{fmt.time(t.created_at)}</td>
              <td><Badge tone="blue">{t.mode}</Badge>{t.benchmark_id && <span className="ml-1 text-[10px] text-slate-500">bench</span>}</td>
              <td className="max-w-md truncate text-slate-300">{t.prompt}</td>
              <td className="font-mono text-xs text-slate-400">{t.changed_files?.join(', ') || '—'}</td>
              <td className="tabular-nums text-slate-400">{t.tokens ? fmt.n(t.tokens.total) : '—'}{t.tokens?.estimated ? <span className="text-amber-300">*</span> : ''}</td>
              <td><Badge>{t.status}</Badge></td>
            </tr>
          ))}</tbody>
          <caption className="caption-bottom pt-2 text-left text-xs text-slate-500">* estimated token counts</caption>
        </table>
      )}
    </Card>
  )
}
