import { useState } from 'react'
import { Play } from 'lucide-react'
import { api, fmt, MEASUREMENT_TONE } from '../api'
import BenchmarkAnalytics from '../components/BenchmarkAnalytics'
import { Badge, Button, Card, DataTable, Empty, ErrorBox, Expand, Notice, Select, Spinner, Stat, useApi } from '../components/ui'

function Bars({ base, veri }: { base: number; veri: number }) {
  const max = Math.max(base, veri, 1)
  return (
    <div className="space-y-1.5">
      {[['Baseline', base, '#2a78d6'], ['VeriCode', veri, '#1baf7a']].map(([l, v, c]: any) => (
        <div key={l} className="flex items-center gap-2 text-xs">
          <span className="w-16 text-fg-muted">{l}</span>
          <div className="h-2.5 flex-1 rounded-sm bg-subtle"><div className="h-2.5 rounded-r" style={{ width: `${(v / max) * 100}%`, background: c, minWidth: v ? 2 : 0 }} /></div>
          <span className="w-16 text-right tabular-nums text-fg">{fmt.n(v)}</span>
        </div>
      ))}
    </div>
  )
}

export default function Tokens(_: { param?: string }) {
  const a = useApi<any>('/analytics/tokens', 10000)
  const b = useApi<any>('/benchmarks', 3000)
  const pub = useApi<any>('/benchmarks/published')
  const [source, setSource] = useState('')
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
  const sources = [
    ...(pub.data?.results ?? []).map((r: any) => ({ key: `pub:${r.name}`, label: `Published: ${r.name}`, summary: r.summary, labels: r.measurement_labels ?? [], meta: r })),
    ...(b.data?.results ?? []).filter((r: any) => r.summary?.tasks).map((r: any) => ({ key: `local:${r.id}`, label: `Local run ${r.id} (${fmt.time(r.created_at)})`, summary: r.summary, labels: r.measurement_labels ?? [r.measurement], meta: r })),
  ]
  const cur = sources.find((x) => x.key === source) ?? sources[0]
  return (
    <div className="space-y-5">
      {t.est > 0 && <Notice>{t.est} of {t.calls} recorded LLM calls used <b>estimated</b> token counts (mock provider or provider without usage data). Provider-reported counts are used whenever available.</Notice>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Input tokens" value={fmt.n(t.input)} />
        <Stat label="Output tokens" value={fmt.n(t.output)} />
        <Stat label="Model calls" value={fmt.n(t.calls)} sub={`${d.cache_entries} cache entries (env/search)`} />
        <Stat label="Est. cost" value={`$${cost.toFixed(4)}`} sub={`real-provider calls only, at $${d.cost_per_mtok.input}/$${d.cost_per_mtok.output} per Mtok`} />
      </div>

      <Card title="Benchmark analytics" description="Paired runs on identical tasks, model, repository snapshot, tests and repair budget. Savings use only repetitions where both runs succeeded."
        actions={sources.length > 1 ? (
          <Select size="sm" aria-label="Benchmark source" className="w-72" value={cur?.key ?? ''} onChange={(e) => setSource(e.target.value)}>
            {sources.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
          </Select>) : undefined}>
        {!cur ? <Empty>No benchmark with configuration results yet. Published results live in docs/submission/benchmark-results/.</Empty> : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted">
              <span>provider <b className="font-medium text-fg">{cur.meta.provider ?? '—'}</b></span>
              {cur.meta.coder_model && <span>model <b className="font-mono font-medium text-fg">{cur.meta.coder_model}</b></span>}
              <span>repetitions <b className="font-medium text-fg">{cur.meta.runs_per_mode}</b> per configuration</span>
              {cur.meta.source_runs?.length > 0 && <span>CI runs <span className="font-mono text-fg">{cur.meta.source_runs.join(', ')}</span></span>}
              {cur.meta.stopped && <span className="text-warn">stopped early: {cur.meta.stopped}</span>}
            </div>
            <BenchmarkAnalytics summary={cur.summary} labels={cur.labels} />
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Tokens by measurement type" flush>
          {!d.by_measurement?.length ? <div className="p-4"><Empty>No LLM calls recorded.</Empty></div> : (
            <DataTable label="Tokens by measurement type" caption="ACTUAL_PROVIDER_USAGE = usage reported by the provider API · ESTIMATED = real provider without usage data (chars/4) · MOCK = scripted offline demo provider.">
              <thead><tr><th>Measurement</th><th className="text-right">Input</th><th className="text-right">Output</th><th className="text-right">Calls</th></tr></thead>
              <tbody>{d.by_measurement.map((m: any) => (
                <tr key={m.measurement}><td><Badge tone={MEASUREMENT_TONE[m.measurement] ?? 'gray'}>{m.measurement}</Badge></td><td className="text-right tabular-nums">{fmt.n(m.input)}</td><td className="text-right tabular-nums">{fmt.n(m.output)}</td><td className="text-right tabular-nums">{m.calls}</td></tr>
              ))}</tbody>
            </DataTable>
          )}
        </Card>
        <Card title="Pipeline stages and search" description="Tavily searches are tracked separately; no token cost is invented for them.">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-3">
            {['planner', 'coder', 'repair'].map((s) => (
              <div key={s}><div className="text-xs text-fg-muted">{s} tokens</div><div className="text-base font-semibold tabular-nums text-fg">{fmt.n(stage(s) ? stage(s).input + stage(s).output : 0)}</div><div className="text-xs text-fg-subtle">{stage(s)?.calls ?? 0} calls</div></div>
            ))}
            <div><div className="text-xs text-fg-muted">Verification model tokens</div><div className="text-base font-semibold tabular-nums text-fg">{fmt.n(['claim_extraction', 'claim_judge'].reduce((n, k) => n + (stage(k) ? stage(k).input + stage(k).output : 0), 0))}</div><div className="text-xs text-fg-subtle">API checks are deterministic</div></div>
            <div><div className="text-xs text-fg-muted">Tavily requests</div><div className="text-base font-semibold tabular-nums text-fg">{fmt.n(d.search?.requests)}</div><div className="text-xs text-fg-subtle">{fmt.n(d.search?.cache_hits)} cache hits · {d.search?.credits ?? 0} credits</div></div>
            <div><div className="text-xs text-fg-muted">Search failures</div><div className="text-base font-semibold tabular-nums text-fg">{fmt.n(d.search?.failures)}</div></div>
          </div>
        </Card>
      </div>

      {d.by_model?.length > 0 && (
        <Card title="Usage and cost by model" flush>
          <DataTable label="Usage and cost by model" dense>
            <thead><tr><th>Provider / model</th><th>Measurement</th><th className="text-right">Input</th><th className="text-right">Output</th><th className="text-right">Calls</th><th className="text-right">Cost (USD)</th><th>Cost basis</th></tr></thead>
            <tbody>{d.by_model.map((m: any, i: number) => (
              <tr key={i}><td className="font-mono">{m.provider} / {m.model}</td><td><Badge tone={MEASUREMENT_TONE[m.measurement] ?? 'gray'}>{m.measurement || '—'}</Badge></td><td className="text-right tabular-nums">{fmt.n(m.input)}</td><td className="text-right tabular-nums">{fmt.n(m.output)}</td><td className="text-right">{m.calls}</td><td className="text-right tabular-nums">{m.cost_usd == null ? '—' : `$${m.cost_usd}`}</td><td className="text-fg-muted">{m.cost_basis}</td></tr>
            ))}</tbody>
          </DataTable>
        </Card>
      )}

      <Card title="Benchmark runs: baseline vs VeriCode" description="Identical tasks, model, repository state, tests and repair budget. Mock and estimated results are kept separate from real-provider results."
        actions={<>
          <Select size="sm" aria-label="Measurement" className="w-52" value={kind} onChange={(e) => setKind(e.target.value as any)}>
            <option value="ACTUAL_PROVIDER_USAGE">Real provider results</option>
            <option value="MOCK_OR_ESTIMATED">Mock / estimated results</option>
          </Select>
          <Select size="sm" aria-label="Runs" className="w-36" value={runs} onChange={(e) => setRuns(+e.target.value)}>
            {[1, 2, 3, 5].map((n) => <option key={n} value={n}>{n} run{n > 1 ? 's' : ''}/mode</option>)}
          </Select>
          <Button size="sm" onClick={start} disabled={b.data?.running} icon={<Play aria-hidden className="h-3.5 w-3.5" />}>{b.data?.running ? 'Running…' : 'Run benchmark'}</Button>
        </>}>
        <ErrorBox error={err ?? (b.data?.error ? { message: b.data.error } : null)} />
        {b.data?.running && <Spinner label="Benchmark running…" />}
        {!latest ? <Empty>{kind === 'ACTUAL_PROVIDER_USAGE' ? 'No real-provider benchmark yet. Configure an LLM key and run one — mock results are kept separately.' : 'No mock/estimated benchmark results.'}</Empty> : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted"><span className="font-mono">{latest.id}</span><span>{fmt.time(latest.created_at)}</span><span>provider {latest.provider}{latest.coder_model ? ` (${latest.coder_model})` : ''}</span><Badge tone={MEASUREMENT_TONE[latest.measurement] ?? 'gray'}>{latest.measurement}</Badge><span>n={latest.runs_per_mode} per configuration</span><span>repair budget {latest.repair_budget}</span></div>
            {latest.average_savings_pct != null && <div className="text-[13px] text-fg">Average savings across {latest.comparable_tasks}/{latest.total_tasks} comparable tasks: <b className={latest.average_savings_pct >= 0 ? 'text-ok' : 'text-err'}>{latest.average_savings_pct}%</b>{latest.savings_stdev_across_tasks != null ? ` (sd ${latest.savings_stdev_across_tasks} pts)` : ''}</div>}
            {latest.tasks.map((tk: any) => {
              const B = tk.summary.baseline, V = tk.summary.vericode
              return (
                <Expand key={tk.task} head={<>
                  <span className="font-medium text-fg">{tk.title}</span>
                  <span className="ml-auto text-xs">{tk.token_savings_pct != null
                    ? <b className={tk.token_savings_pct >= 0 ? 'text-ok' : 'text-err'}>{tk.token_savings_pct >= 0 ? `${tk.token_savings_pct}% fewer tokens` : `${-tk.token_savings_pct}% more tokens`}</b>
                    : <span className="text-warn">savings not computed</span>}</span>
                </>}>
                  {tk.token_savings_pct == null && <p className="mb-2 text-xs text-warn">{tk.savings_note}</p>}
                  <Bars base={B.total_tokens.mean ?? 0} veri={V.total_tokens.mean ?? 0} />
                  <DataTable className="mt-3" dense label={`${tk.task} details`}>
                    <thead><tr><th>Metric</th><th>Baseline</th><th>VeriCode</th></tr></thead>
                    <tbody>
                      {[
                        ['Final success', fmt.pct(B.success_rate), fmt.pct(V.success_rate)],
                        ['First-pass test success', fmt.pct(B.first_pass_rate), fmt.pct(V.first_pass_rate)],
                        ['Total tokens (mean ± sd)', `${fmt.n(B.total_tokens.mean)} ± ${B.total_tokens.stdev}`, `${fmt.n(V.total_tokens.mean)} ± ${V.total_tokens.stdev}`],
                        ['Input / output tokens', `${fmt.n(B.input_tokens.mean)} / ${fmt.n(B.output_tokens.mean)}`, `${fmt.n(V.input_tokens.mean)} / ${fmt.n(V.output_tokens.mean)}`],
                        ['Planner overhead tokens', fmt.n(B.verification_overhead_tokens?.mean ?? 0), fmt.n(V.verification_overhead_tokens?.mean ?? 0)],
                        ['Paired-run savings', '', (tk.paired_run_savings_pct ?? []).map((x: number) => `${x}%`).join(', ') || '—'],
                        ['Flagged APIs shipped in final code', (tk.flagged_api_usage ?? []).map((x: any) => x.baseline_flagged_apis_used ?? '—').join(', ') || '—', (tk.flagged_api_usage ?? []).map((x: any) => x.vericode_flagged_apis_used ?? '—').join(', ') || '—'],
                        ['LLM calls', B.llm_calls.mean, V.llm_calls.mean],
                        ['Repair attempts', B.repair_attempts.mean, V.repair_attempts.mean],
                        ['Duration (s)', B.duration_s.mean, V.duration_s.mean],
                      ].map(([k, x, y]: any) => <tr key={k}><td className="text-fg-muted">{k}</td><td className="tabular-nums">{x}</td><td className="tabular-nums">{y}</td></tr>)}
                    </tbody>
                  </DataTable>
                  {tk.detection?.detection_rate != null && (
                    <div className="mt-2 text-xs text-fg-muted">Incompatibility detection rate {fmt.pct(tk.detection.detection_rate)} · false-positive rate {fmt.pct(tk.detection.false_positive_rate)} (TP {tk.detection.tp}, FP {tk.detection.fp}, FN {tk.detection.fn}, TN {tk.detection.tn})</div>
                  )}
                </Expand>
              )
            })}
          </div>
        )}
      </Card>

      <Card title="Per-task usage" flush>
        {!d.per_task.length ? <div className="p-4"><Empty>No tasks recorded.</Empty></div> : (
          <DataTable label="Per-task usage" dense>
            <thead><tr><th>Task</th><th>Mode</th><th className="text-right">Input</th><th className="text-right">Output</th><th className="text-right">Calls</th><th className="text-right">Repairs</th><th className="text-right">Searches</th><th>Success</th><th>Measured</th></tr></thead>
            <tbody>{d.per_task.map((r: any) => (
              <tr key={r.id}><td><a className="font-mono no-underline" href={`#history/${r.id}`}>{r.id}</a></td><td className="font-mono text-fg-muted">{r.mode}</td><td className="text-right tabular-nums">{fmt.n(r.input)}</td><td className="text-right tabular-nums">{fmt.n(r.output)}</td><td className="text-right">{r.calls}</td><td className="text-right">{r.repair_attempts ?? '—'}</td><td className="text-right">{r.search_calls ?? '—'}</td><td>{r.success ? <span className="text-ok">✓</span> : <span className="text-err">✗</span>}</td><td>{r.measurement ? <Badge tone={MEASUREMENT_TONE[r.measurement] ?? 'gray'}>{r.measurement}</Badge> : '—'}</td></tr>
            ))}</tbody>
          </DataTable>
        )}
      </Card>
    </div>
  )
}
