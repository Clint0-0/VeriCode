import { useState } from 'react'
import { api, fmt } from '../api'
import { Badge, Button, Card, Empty, ErrorBox, Notice, Spinner, Stat, useApi } from '../components/ui'

function Bars({ base, veri }: { base: number; veri: number }) {
  const max = Math.max(base, veri, 1)
  return (
    <div className="space-y-1.5">
      {[['Baseline', base, 'bg-slate-500'], ['VeriCode', veri, 'bg-sky-500']].map(([l, v, c]: any) => (
        <div key={l} className="flex items-center gap-2 text-xs">
          <span className="w-16 text-slate-400">{l}</span>
          <div className="h-3 flex-1 rounded bg-ink-800"><div className={`h-3 rounded ${c}`} style={{ width: `${(v / max) * 100}%` }} /></div>
          <span className="w-16 text-right tabular-nums text-slate-300">{fmt.n(v)}</span>
        </div>
      ))}
    </div>
  )
}

export default function Tokens(_: { param?: string }) {
  const a = useApi<any>('/analytics/tokens', 10000)
  const b = useApi<any>('/benchmarks', 3000)
  const [err, setErr] = useState<unknown>(null)
  const [runs, setRuns] = useState(1)
  const start = async () => {
    setErr(null)
    try { await api('/benchmarks', { body: { runs } }); b.reload() } catch (e) { setErr(e) }
  }
  if (a.loading) return <Spinner />
  if (a.error) return <ErrorBox error={a.error} />
  const d = a.data
  const tot = (rows: any[]) => rows.reduce((s, r) => ({ input: s.input + (r.input ?? 0), output: s.output + (r.output ?? 0), calls: s.calls + r.calls, est: s.est + (r.estimated_calls ?? 0) }), { input: 0, output: 0, calls: 0, est: 0 })
  const t = tot(d.by_stage)
  const cost = (t.input * d.cost_per_mtok.input + t.output * d.cost_per_mtok.output) / 1e6
  const stage = (n: string) => d.by_stage.find((s: any) => s.stage === n)
  const latest = b.data?.results?.[0]
  return (
    <div className="space-y-5">
      {t.est > 0 && <Notice>{t.est} of {t.calls} recorded LLM calls used <b>estimated</b> token counts (mock provider or provider without usage data). Provider-reported counts are used whenever available.</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Input tokens" value={fmt.n(t.input)} />
        <Stat label="Output tokens" value={fmt.n(t.output)} />
        <Stat label="Model calls" value={fmt.n(t.calls)} sub={`${d.cache_entries} cache entries (env/search)`} />
        <Stat label="Est. cost" value={`$${cost.toFixed(4)}`} sub={`at $${d.cost_per_mtok.input}/$${d.cost_per_mtok.output} per Mtok`} />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {['planner', 'coder', 'repair'].map((s) => <Stat key={s} label={`${s} tokens`} value={fmt.n(stage(s) ? stage(s).input + stage(s).output : 0)} sub={`${stage(s)?.calls ?? 0} calls`} />)}
        <Stat label="Verification / documentation model tokens" value={fmt.n(['claim_extraction', 'claim_judge'].reduce((n, k) => n + (stage(k) ? stage(k).input + stage(k).output : 0), 0))} sub="API checks, claim extraction and evidence comparison are deterministic (no LLM)" />
      </div>

      <Card title="Benchmark: baseline vs VeriCode (identical tasks, model, repo state, tests, repair budget)" actions={<>
        <select aria-label="Runs" className="rounded border border-ink-600 bg-ink-950 px-2 py-1 text-sm" value={runs} onChange={(e) => setRuns(+e.target.value)}>
          {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n} run{n > 1 ? 's' : ''}/mode</option>)}
        </select>
        <Button onClick={start} disabled={b.data?.running}>{b.data?.running ? 'Running…' : 'Run benchmark'}</Button>
      </>}>
        <ErrorBox error={err ?? (b.data?.error ? { message: b.data.error } : null)} />
        {b.data?.running && <Spinner label="Benchmark running…" />}
        {!latest ? <Empty>No benchmark results yet.</Empty> : (
          <div className="space-y-4">
            <div className="text-xs text-slate-500">{latest.id} · {fmt.time(latest.created_at)} · provider {latest.provider} · <Badge tone={latest.measurement.startsWith('estimated') ? 'amber' : 'green'}>{latest.measurement}</Badge> · n={latest.runs_per_mode}/mode · repair budget {latest.repair_budget}</div>
            {latest.tasks.map((tk: any) => {
              const B = tk.summary.baseline, V = tk.summary.vericode
              return (
                <div key={tk.task} className="rounded-md border border-ink-700 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-sm font-medium text-slate-200">{tk.title}</div>
                    {tk.token_savings_pct != null ? <span className="text-lg font-semibold text-emerald-300">{tk.token_savings_pct}% fewer tokens</span> : <span className="text-xs text-amber-300">{tk.savings_note}</span>}
                  </div>
                  <Bars base={B.total_tokens.mean ?? 0} veri={V.total_tokens.mean ?? 0} />
                  <table className="mt-3 w-full text-xs">
                    <thead className="text-left text-slate-500"><tr><th className="py-1">Metric</th><th>Baseline</th><th>VeriCode</th></tr></thead>
                    <tbody>
                      {[
                        ['Final success', fmt.pct(B.success_rate), fmt.pct(V.success_rate)],
                        ['First-pass test success', fmt.pct(B.first_pass_rate), fmt.pct(V.first_pass_rate)],
                        ['Total tokens (mean ± sd)', `${fmt.n(B.total_tokens.mean)} ± ${B.total_tokens.stdev}`, `${fmt.n(V.total_tokens.mean)} ± ${V.total_tokens.stdev}`],
                        ['Input / output tokens', `${fmt.n(B.input_tokens.mean)} / ${fmt.n(B.output_tokens.mean)}`, `${fmt.n(V.input_tokens.mean)} / ${fmt.n(V.output_tokens.mean)}`],
                        ['LLM calls', B.llm_calls.mean, V.llm_calls.mean],
                        ['Repair attempts', B.repair_attempts.mean, V.repair_attempts.mean],
                        ['Search calls (Tavily)', B.search_calls.mean, V.search_calls.mean],
                        ['Duration (s)', B.duration_s.mean, V.duration_s.mean],
                        ['Tokens by stage', Object.entries(B.by_stage).map(([k, v]: any) => `${k}:${v.input + v.output}`).join(' '), Object.entries(V.by_stage).map(([k, v]: any) => `${k}:${v.input + v.output}`).join(' ')],
                      ].map(([k, x, y]: any) => <tr key={k} className="border-t border-ink-700"><td className="py-1 text-slate-400">{k}</td><td className="tabular-nums">{x}</td><td className="tabular-nums">{y}</td></tr>)}
                    </tbody>
                  </table>
                  {tk.detection.flagged !== undefined && tk.detection.detection_rate != null && (
                    <div className="mt-2 text-xs text-slate-400">Incompatibility detection rate {fmt.pct(tk.detection.detection_rate)} · false-positive rate {fmt.pct(tk.detection.false_positive_rate)} (TP {tk.detection.tp}, FP {tk.detection.fp}, FN {tk.detection.fn}, TN {tk.detection.tn})</div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>

      <Card title="Per-task usage">
        {!d.per_task.length ? <Empty>No tasks recorded.</Empty> : (
          <table className="w-full text-xs">
            <thead className="text-left text-slate-500"><tr><th className="py-1">Task</th><th>Mode</th><th>Input</th><th>Output</th><th>Calls</th><th>Repairs</th><th>Searches</th><th>Success</th><th>Measured</th></tr></thead>
            <tbody>{d.per_task.map((r: any) => (
              <tr key={r.id} className="border-t border-ink-700"><td className="py-1"><a className="font-mono text-sky-300 hover:underline" href={`#history/${r.id}`}>{r.id}</a></td><td>{r.mode}</td><td className="tabular-nums">{fmt.n(r.input)}</td><td className="tabular-nums">{fmt.n(r.output)}</td><td>{r.calls}</td><td>{r.repair_attempts ?? '—'}</td><td>{r.search_calls ?? '—'}</td><td>{r.success ? '✓' : '✗'}</td><td>{r.calls ? <Badge tone={r.estimated ? 'amber' : 'green'}>{r.estimated ? 'estimated' : 'actual'}</Badge> : '—'}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
