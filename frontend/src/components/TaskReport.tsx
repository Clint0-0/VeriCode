import { useState } from 'react'
import { api, fmt } from '../api'
import { FindingsList, KV } from './Findings'
import { Badge, Button, Card, Diff, Empty, ErrorBox, Mono, Notice } from './ui'

export function TokenTable({ tokens }: { tokens: any }) {
  if (!tokens) return <Empty>No token usage recorded.</Empty>
  return (
    <div>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Stage</th><th>Input</th><th>Output</th><th>Calls</th></tr></thead>
        <tbody>
          {Object.entries(tokens.by_stage ?? {}).map(([k, v]: any) => (
            <tr key={k} className="border-t border-ink-700"><td className="py-1 font-mono text-xs">{k}</td><td className="tabular-nums">{fmt.n(v.input)}</td><td className="tabular-nums">{fmt.n(v.output)}</td><td>{v.calls}</td></tr>
          ))}
          <tr className="border-t border-ink-600 font-semibold"><td className="py-1">Total</td><td className="tabular-nums">{fmt.n(tokens.input)}</td><td className="tabular-nums">{fmt.n(tokens.output)}</td><td>{tokens.calls}</td></tr>
        </tbody>
      </table>
      <div className="mt-2 text-xs"><Badge tone={tokens.estimated ? 'amber' : 'green'}>{tokens.measurement}</Badge></div>
    </div>
  )
}

export function TaskReport({ task, onApplied }: { task: any; onApplied?: () => void }) {
  const [applyErr, setApplyErr] = useState<unknown>(null)
  const [applied, setApplied] = useState<string[] | null>(null)
  const res = task.result ?? {}
  const pf = task.preflight ?? {}
  const running = String(task.status).startsWith('running') || task.status === 'queued'
  const apply = async () => {
    setApplyErr(null)
    try {
      const r = await api<any>(`/tasks/${task.id}/apply`, { method: 'POST' })
      setApplied(r.applied)
      onApplied?.()
    } catch (e) { setApplyErr(e) }
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge>{task.status}</Badge><Badge tone="blue">{task.mode}</Badge>
        <span className="font-mono text-xs text-slate-500">{task.id}</span>
        <span className="text-xs text-slate-500">provider: {task.provider}</span>
        {res.duration_s != null && <span className="text-xs text-slate-500">{res.duration_s}s</span>}
      </div>
      {task.provider === 'mock' && <Notice>Scripted mock provider: responses are canned for demo tasks and token counts are estimated.</Notice>}
      {res.error && <ErrorBox error={{ message: res.error }} />}
      <Card title="Progress">
        <ol className="space-y-1 text-sm">
          {(task.events ?? []).map((e: any, i: number) => (
            <li key={i} className="flex gap-3"><span className="w-20 shrink-0 font-mono text-xs text-slate-500">{e.stage}</span><span className="text-slate-300">{e.message}</span></li>
          ))}
          {running && <li className="text-xs text-sky-300">running…</li>}
        </ol>
      </Card>
      {pf.selected_files && (
        <Card title={`Context files (${pf.selected_files.length})`}>
          <ul className="space-y-1 text-xs">{pf.selected_files.map((f: any) => <li key={f.path}><span className="font-mono text-slate-200">{f.path}</span> <span className="text-slate-500">— {f.reasons?.join('; ')}</span></li>)}</ul>
        </Card>
      )}
      {pf.findings && (
        <Card title="Pre-flight report">
          <div className="mb-3 grid gap-3 md:grid-cols-3">
            <KV k="Planned APIs" v={pf.findings.length} />
            <KV k="Tavily calls" v={`${pf.tavily_calls ?? 0}${pf.tavily_configured ? '' : ' (no key: live verification not performed)'}`} />
            <KV k="Rules saved to memory" v={pf.rules_saved?.length ?? 0} />
          </div>
          <FindingsList findings={pf.findings} />
          <div className="mt-3 text-xs font-medium text-slate-400">Briefing injected into the coder prompt</div>
          <Mono className="mt-1">{pf.briefing}</Mono>
        </Card>
      )}
      {res.attempts && (
        <Card title="Attempts & validation">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">#</th><th>Stage</th><th>Edits</th><th>Edit errors</th><th>Checks</th><th>Tokens (in/out)</th></tr></thead>
            <tbody>{res.attempts.map((a: any) => (
              <tr key={a.attempt} className="border-t border-ink-700"><td className="py-1">{a.attempt}</td><td className="font-mono text-xs">{a.stage}</td><td>{a.edits}</td><td className="text-xs text-rose-300">{a.edit_errors.join('; ')}</td><td><Badge tone={a.passed ? 'green' : 'red'}>{a.passed ? 'passed' : 'failed'}</Badge></td><td className="tabular-nums">{fmt.n(a.input_tokens)} / {fmt.n(a.output_tokens)}</td></tr>
            ))}</tbody>
          </table>
          {res.checks?.results?.map((r: any, i: number) => (
            <div key={i} className="mt-3">
              <div className="text-xs text-slate-400"><span className="font-mono">{r.command}</span> → exit {r.returncode} · isolation: {r.isolation}</div>
              <Mono className="mt-1 max-h-64">{(r.stdout || '') + (r.stderr ? `\n${r.stderr}` : '')}</Mono>
            </div>
          ))}
        </Card>
      )}
      {res.diff !== undefined && (
        <Card title={`Changes (${res.changed_files?.length ?? 0} files)`} actions={
          res.success && !res.applied_at && !applied ? <Button onClick={apply}>Apply to workspace</Button> : (res.applied_at || applied) ? <Badge tone="green">applied</Badge> : null
        }>
          <p className="mb-2 text-xs text-slate-500">Changes were made and validated in an isolated copy ({res.sandbox}). Applying copies them into the real workspace; it is refused if those files changed since the run.</p>
          <ErrorBox error={applyErr} />
          <Diff text={res.diff} />
        </Card>
      )}
      <Card title="Token usage"><TokenTable tokens={res.tokens} /></Card>
    </div>
  )
}
