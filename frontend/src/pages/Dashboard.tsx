import { fmt, MEASUREMENT_TONE } from '../api'
import { IntegrationStatus } from '../components/Integrations'
import { Badge, Card, Empty, ErrorBox, Notice, Spinner, Stat, useApi } from '../components/ui'

export default function Dashboard(_: { param?: string }) {
  const { data, error, loading } = useApi<any>('/dashboard', 10000)
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  if (!data) return null
  const lb = data.latest_real_benchmark ?? data.latest_benchmark
  const est = data.estimated_calls > 0
  return (
    <div className="space-y-5">
      {data.provider === 'mock' && <Notice>LLM provider is the <b>scripted mock</b> (no API key configured). Coding runs use canned responses for the bundled demo tasks only, and token counts are <b>estimates</b> (chars/4). Configure ANTHROPIC_API_KEY or OPENAI_API_KEY for real measurements.</Notice>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Coding tasks" value={fmt.n(data.coding_tasks)} sub={`${fmt.n(data.successful_tasks)} succeeded · ${fmt.n(data.partial_tasks)} partial`} />
        <Stat label="Pre-flight verifications" value={fmt.n(data.preflight_runs)} sub={`${data.rules} verified rules in memory`} />
        <Stat label="Stale / contradicted claims" value={fmt.n(data.stale_claims)} sub={`of ${fmt.n(data.claims_checked)} claims checked`} tone={data.stale_claims ? 'amber' : undefined} />
        <Stat label="Total tokens" value={fmt.n(data.total_tokens)} sub={`${fmt.n(data.llm_calls)} LLM calls${est ? ` · ${data.estimated_calls} estimated` : ''}`} />
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title={<>Latest benchmark (baseline vs VeriCode) {lb && <Badge tone={MEASUREMENT_TONE[lb.measurement] ?? 'gray'}>{lb.measurement}</Badge>}</>} className="lg:col-span-2">
          {!lb ? <Empty>No benchmark yet. Run one from Token Analytics.</Empty> : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1">Task</th><th>Baseline tokens</th><th>VeriCode tokens</th><th>Savings</th><th>Success (B / V)</th></tr></thead>
              <tbody>{lb.tasks.map((t: any) => (
                <tr key={t.task} className="border-t border-ink-700">
                  <td className="py-2">{t.task}</td>
                  <td className="tabular-nums">{fmt.n(t.summary.baseline.total_tokens.mean)}</td>
                  <td className="tabular-nums">{fmt.n(t.summary.vericode.total_tokens.mean)}</td>
                  <td className="tabular-nums">{t.token_savings_pct == null ? <span className="text-slate-500" title={t.savings_note}>n/a</span> : <span className="text-emerald-300">{t.token_savings_pct}%</span>}</td>
                  <td>{fmt.pct(t.summary.baseline.success_rate)} / {fmt.pct(t.summary.vericode.success_rate)}</td>
                </tr>
              ))}</tbody>
              <caption className="caption-bottom pt-2 text-left text-xs text-slate-500">Measurement: {lb.measurement}{lb.measurement !== 'ACTUAL_PROVIDER_USAGE' ? ' — not real model usage' : ''} · provider {lb.provider} · n={lb.runs_per_mode} per mode · repair budget {lb.repair_budget}{lb.average_savings_pct != null ? ` · average savings ${lb.average_savings_pct}% over ${lb.comparable_tasks}/${lb.total_tasks} comparable tasks` : ''}</caption>
            </table>
          )}
        </Card>
        <Card title="Integrations">
          <IntegrationStatus i={data.integrations} />
          {data.tokens_by_measurement?.length > 0 && (
            <div className="mt-3 border-t border-ink-700 pt-2 text-xs text-slate-400">
              <div className="mb-1 font-medium">Recorded tokens by measurement</div>
              {data.tokens_by_measurement.map((m: any) => <div key={m.measurement} className="flex justify-between"><Badge tone={MEASUREMENT_TONE[m.measurement] ?? 'gray'}>{m.measurement}</Badge><span className="tabular-nums">{fmt.n(m.tokens)} ({m.calls} calls)</span></div>)}
            </div>
          )}
        </Card>
      </div>
      <Card title="Recent tasks">
        {!data.recent_tasks.length ? <Empty>No tasks yet — start one in the Coding Workspace.</Empty> : (
          <table className="w-full text-sm">
            <tbody>{data.recent_tasks.map((t: any) => (
              <tr key={t.id} className="border-t border-ink-700 first:border-0">
                <td className="py-2"><a className="font-mono text-xs text-sky-300 hover:underline" href={`#history/${t.id}`}>{t.id}</a></td>
                <td><Badge tone="blue">{t.mode}</Badge></td>
                <td className="max-w-md truncate text-slate-300">{t.prompt}</td>
                <td><Badge>{t.outcome ?? t.status}</Badge></td>
                <td className="text-right tabular-nums text-slate-400">{t.tokens ? `${fmt.n(t.tokens.total)} tok` : ''}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
