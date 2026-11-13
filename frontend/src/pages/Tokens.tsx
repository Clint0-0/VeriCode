import { useState } from 'react'
import { api, fmt, MEASUREMENT_TONE } from '../api'
import { Badge, Button, Card, Empty, ErrorBox, Notice, Select, Spinner, Stat, useApi } from '../components/ui'

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
  const [kind, setKind] = useState<'ACTUAL_PROVIDER_USAGE' | 'MOCK_OR_ESTIMATED'>('ACTUAL_PROVIDER_USAGE')
  const start = async () => {
    setErr(null)
    try { await api('/benchmarks', { body: { runs } }); b.reload() } catch (e) { setErr(e) }
  }
  if (a.loading) return <Spinner />
  if (a.error) return <ErrorBox error={a.error} />
  const d = a.data
  const tot = (rows: any[]) => rows.reduce((s, r) => ({ input: s.input + (r.input ?? 0), output: s.output + (r.output ?? 0), calls: s.calls + r.calls, est: s.est + (r.estimated_calls ?? 0) }), { input: 0, output: 0, calls: 0, est: 0 })
  const t = tot(d.by_stage)
  const real = (d.by_measurement ?? []).filter((m: any) => m.measurement !== 'MOCK')
  const cost = real.reduce((c: number, m: any) => c + ((m.input ?? 0) * d.cost_per_mtok.input + (m.output ?? 0) * d.cost_per_mtok.output) / 1e6, 0)
  const stage = (n: string) => d.by_stage.find((s: any) => s.stage === n)
  const results = (b.data?.results ?? []).filter((r: any) => (kind === 'ACTUAL_PROVIDER_USAGE') === (r.measurement === 'ACTUAL_PROVIDER_USAGE'))
  const latest = results[0]
  return (
    <div className="space-y-5">
      {t.est > 0 && <Notice>{t.est} of {t.calls} recorded LLM calls used <b>estimated</b> token counts (mock provider or provider without usage data). Provider-reported counts are used whenever available.</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Input tokens" value={fmt.n(t.input)} />
        <Stat label="Output tokens" value={fmt.n(t.output)} />
        <Stat label="Model calls" value={fmt.n(t.calls)} sub={`${d.cache_entries} cache entries (env/search)`} />
        <Stat label="Est. cost" value={`$${cost.toFixed(4)}`} sub={`real-provider calls only, at $${d.cost_per_mtok.input}/$${d.cost_per_mtok.output} per Mtok`} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Card title="Tokens by measurement type">
          {!d.by_measurement?.length ? <Empty>No LLM calls recorded.</Empty> : d.by_measurement.map((m: any) => (
            <div key={m.measurement} className="flex items-center justify-between border-t border-ink-700 py-1.5 text-sm first:border-0">
              <Badge tone={MEASUREMENT_TONE[m.measurement] ?? 'gray'}>{m.measurement}</Badge>
              <span className="tabular-nums text-slate-300">{fmt.n(m.input)} in / {fmt.n(m.output)} out · {m.calls} calls</span>
            </div>
          ))}
          <p className="mt-2 text-xs text-slate-500">ACTUAL_PROVIDER_USAGE = usage reported by the provider API. ESTIMATED = real provider without usage data (chars/4). MOCK = scripted offline demo provider.</p>
        </Card>
        <Card title="Tavily search usage (tracked separately, no token cost invented)">
          <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            <div><div className="text-xs text-slate-500">Requests</div><div className="tabular-nums">{fmt.n(d.search?.requests)}</div></div>
            <div><div className="text-xs text-slate-500">Cache hits</div><div className="tabular-nums">{fmt.n(d.search?.cache_hits)}</div></div>
            <div><div className="text-xs text-slate-500">Credits</div><div className="tabular-nums">{d.search?.credits ?? 0}</div></div>
            <div><div className="text-xs text-slate-500">Failures</div><div className="tabular-nums">{fmt.n(d.search?.failures)}</div></div>
          </div>
        </Card>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {['planner', 'coder', 'repair'].map((s) => <Stat key={s} label={`${s} tokens`} value={fmt.n(stage(s) ? stage(s).input + stage(s).output : 0)} sub={`${stage(s)?.calls ?? 0} calls`} />)}
        <Stat label="Verification / documentation model tokens" value={fmt.n(['claim_extraction', 'claim_judge'].reduce((n, k) => n + (stage(k) ? stage(k).input + stage(k).output : 0), 0))} sub="API checks, claim extraction and evidence comparison are deterministic (no LLM)" />
      </div>

      {d.by_model?.length > 0 && (
        <Card title="Usage and cost by model">
          <table className="w-full text-xs">
            <thead className="text-left text-slate-500"><tr><th className="py-1">Provider / model</th><th>Measurement</th><th>Input</th><th>Output</th><th>Calls</th><th>Cost (USD)</th><th>Cost basis</th></tr></thead>
            <tbody>{d.by_model.map((m: any, i: number) => (
              <tr key={i} className="border-t border-ink-700"><td className="py-1 font-mono">{m.provider} / {m.model}</td><td><Badge tone={MEASUREMENT_TONE[m.measurement] ?? 'gray'}>{m.measurement || '—'}</Badge></td><td className="tabular-nums">{fmt.n(m.input)}</td><td className="tabular-nums">{fmt.n(m.output)}</td><td>{m.calls}</td><td className="tabular-nums">{m.cost_usd == null ? '—' : `$${m.cost_usd}`}</td><td className="text-slate-500">{m.cost_basis}</td></tr>
            ))}</tbody>
          </table>
        </Card>
      )}

      <Card title="Benchmark: baseline vs VeriCode (identical tasks, model, repo state, tests, repair budget)" actions={<>
        <Select size="sm" aria-label="Measurement" className="w-52" value={kind} onChange={(e) => setKind(e.target.value as any)}>
          <option value="ACTUAL_PROVIDER_USAGE">Real provider results</option>
          <option value="MOCK_OR_ESTIMATED">Mock / estimated results</option>
        </Select>
        <Select size="sm" aria-label="Runs" className="w-36" value={runs} onChange={(e) => setRuns(+e.target.value)}>
          {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n} run{n > 1 ? 's' : ''}/mode</option>)}
        </Select>
        <Button onClick={start} disabled={b.data?.running}>{b.data?.running ? 'Running…' : 'Run benchmark'}</Button>
      </>}>
        <ErrorBox error={err ?? (b.data?.error ? { message: b.data.error } : null)} />
        {b.data?.running && <Spinner label="Benchmark running…" />}
        {!latest ? <Empty>{kind === 'ACTUAL_PROVIDER_USAGE' ? 'No real-provider benchmark yet. Configure an LLM key and run one — mock results are kept separately.' : 'No mock/estimated benchmark results.'}</Empty> : (
          <div className="space-y-4">
            <div className="text-xs text-slate-500">{latest.id} · {fmt.time(latest.created_at)} · provider {latest.provider}{latest.coder_model ? ` (${latest.coder_model})` : ''} · <Badge tone={MEASUREMENT_TONE[latest.measurement] ?? 'gray'}>{latest.measurement}</Badge> · n={latest.runs_per_mode}/mode · repair budget {latest.repair_budget}</div>
            {latest.average_savings_pct != null && <div className="text-sm text-slate-300">Average savings across {latest.comparable_tasks}/{latest.total_tasks} comparable tasks: <b className={latest.average_savings_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}>{latest.average_savings_pct}%</b>{latest.savings_stdev_across_tasks != null ? ` (sd ${latest.savings_stdev_across_tasks} pts)` : ''}</div>}
            {latest.tasks.map((tk: any) => {
              const B = tk.summary.baseline, V = tk.summary.vericode
              return (
                <div key={tk.task} className="rounded-md border border-ink-700 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="text-sm font-medium text-slate-200">{tk.title}</div>
                    {tk.token_savings_pct != null ? <span className={`text-lg font-semibold ${tk.token_savings_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{tk.token_savings_pct >= 0 ? `${tk.token_savings_pct}% fewer tokens` : `${-tk.token_savings_pct}% more tokens`}</span> : <span className="text-xs text-amber-300">{tk.savings_note}</span>}
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
                        ['Verification overhead tokens (planner/judge)', fmt.n(B.verification_overhead_tokens?.mean ?? 0), fmt.n(V.verification_overhead_tokens?.mean ?? 0)],
                        ['Paired-run savings', '', (tk.paired_run_savings_pct ?? []).map((x: number) => `${x}%`).join(', ') || '—'],
                        ['Flagged (deprecated/incompatible) APIs shipped in final code', (tk.flagged_api_usage ?? []).map((x: any) => x.baseline_flagged_apis_used).join(', ') || '—', (tk.flagged_api_usage ?? []).map((x: any) => x.vericode_flagged_apis_used).join(', ') || '—'],
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
              <tr key={r.id} className="border-t border-ink-700"><td className="py-1"><a className="font-mono text-sky-300 hover:underline" href={`#history/${r.id}`}>{r.id}</a></td><td>{r.mode}</td><td className="tabular-nums">{fmt.n(r.input)}</td><td className="tabular-nums">{fmt.n(r.output)}</td><td>{r.calls}</td><td>{r.repair_attempts ?? '—'}</td><td>{r.search_calls ?? '—'}</td><td>{r.success ? '✓' : '✗'}</td><td>{r.measurement ? <Badge tone={MEASUREMENT_TONE[r.measurement] ?? 'gray'}>{r.measurement}</Badge> : '—'}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
