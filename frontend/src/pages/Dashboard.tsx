import { ArrowRight, BarChart3, ClipboardCheck, FileSearch, SquareTerminal } from 'lucide-react'
import { fmt, MEASUREMENT_TONE } from '../api'
import { IntegrationStatus } from '../components/Integrations'
import { Badge, Card, DataTable, Empty, ErrorBox, Notice, Spinner, Stat, useApi } from '../components/ui'

const QUICK = [
  { href: '#workspace', label: 'Run a coding task', sub: 'Isolated copy, tests, diff', icon: SquareTerminal },
  { href: '#preflight', label: 'Verify planned APIs', sub: 'Against installed packages', icon: ClipboardCheck },
  { href: '#stale', label: 'Check an AI answer', sub: 'Claim-by-claim evidence', icon: FileSearch },
  { href: '#tokens', label: 'Benchmark tokens', sub: 'Baseline vs VeriCode', icon: BarChart3 },
]

export default function Dashboard(_: { param?: string }) {
  const { data, error, loading } = useApi<any>('/dashboard', 10000)
  const stale = useApi<any[]>('/stale', 30000)
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  if (!data) return null
  const lb = data.latest_real_benchmark ?? data.latest_benchmark
  const est = data.estimated_calls > 0
  const byM: any[] = data.tokens_by_measurement ?? []
  const actual = byM.find((m) => m.measurement === 'ACTUAL_PROVIDER_USAGE')
  const mixTotal = byM.reduce((s, m) => s + (m.tokens ?? 0), 0)
  const MIX: Record<string, string> = { ACTUAL_PROVIDER_USAGE: 'bg-ok', ESTIMATED: 'bg-warn', MOCK: 'bg-fg-subtle' }
  return (
    <div className="space-y-5">
      {data.provider === 'mock' && <Notice>LLM provider is the <b>scripted mock</b> (no API key configured). Coding runs use canned responses for the bundled demo tasks only, and token counts are <b>estimates</b> (chars/4). Configure ANTHROPIC_API_KEY or OPENAI_API_KEY for real measurements.</Notice>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Coding tasks" value={fmt.n(data.coding_tasks)} sub={data.partial_tasks ? `${fmt.n(data.partial_tasks)} partial (unvalidated)` : 'all configurations'} />
        <Stat label="Succeeded" value={fmt.n(data.successful_tasks)} sub={data.coding_tasks ? `${Math.round((data.successful_tasks / data.coding_tasks) * 100)}% of tasks` : '—'} tone={data.successful_tasks ? 'green' : undefined} />
        <Stat label="Failed" value={fmt.n(data.failed_tasks ?? 0)} sub="checks still failing after repairs" tone={data.failed_tasks ? 'red' : undefined} />
        <Stat label="Provider-reported tokens" value={fmt.n(actual?.tokens ?? 0)} sub={actual ? `${fmt.n(actual.calls)} calls (actual usage)` : 'no real-provider calls yet'} />
        <Stat label="Pre-flight verifications" value={fmt.n(data.preflight_runs)} sub={`${data.rules} verified rules in memory`} />
        <Stat label="Stale / contradicted claims" value={fmt.n(data.stale_claims)} sub={`of ${fmt.n(data.claims_checked)} claims checked`} tone={data.stale_claims ? 'amber' : undefined} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          <Card title="Recent coding tasks" actions={<a href="#history" className="text-xs font-medium no-underline">View all</a>} flush>
            {!data.recent_tasks.length ? <div className="p-4"><Empty>No tasks yet — start one in the Coding Workspace.</Empty></div> : (
              <DataTable label="Recent coding tasks">
                <thead><tr><th>Task</th><th>Prompt</th><th>Mode</th><th>Status</th><th className="text-right">Tokens</th><th>Created</th></tr></thead>
                <tbody>{data.recent_tasks.map((t: any) => (
                  <tr key={t.id}>
                    <td><a className="font-mono text-xs no-underline" href={`#history/${t.id}`}>{t.id}</a></td>
                    <td className="min-w-[14rem] max-w-[28rem]"><span className="line-clamp-2 text-fg">{t.prompt}</span></td>
                    <td><span className="font-mono text-xs text-fg-muted">{t.mode}</span></td>
                    <td><Badge>{t.outcome ?? t.status}</Badge></td>
                    <td className="text-right tabular-nums text-fg-muted">{t.tokens ? fmt.n(t.tokens.total) : '—'}</td>
                    <td className="whitespace-nowrap text-xs text-fg-subtle">{fmt.time(t.created_at)}</td>
                  </tr>
                ))}</tbody>
              </DataTable>
            )}
          </Card>

          <Card title="Recent stale-answer analyses" actions={<a href="#stale" className="text-xs font-medium no-underline">Open detector</a>} flush>
            {stale.error ? <div className="p-4"><ErrorBox error={stale.error} /></div> : !stale.data ? <div className="p-4"><Spinner /></div> : !stale.data.length ? <div className="p-4"><Empty>No analyses yet.</Empty></div> : (
              <DataTable label="Recent stale-answer analyses">
                <thead><tr><th>Analysis</th><th>Answer</th><th>Evidence</th><th>Created</th></tr></thead>
                <tbody>{stale.data.slice(0, 6).map((a: any) => (
                  <tr key={a.id}>
                    <td><a className="font-mono text-xs no-underline" href={`#stale/${a.id}`}>{a.id}</a></td>
                    <td className="min-w-[14rem] max-w-[30rem]"><span className="line-clamp-2 text-fg">{a.answer}</span></td>
                    <td><Badge tone={a.evidence_mode?.startsWith('fixture') ? 'amber' : 'blue'}>{a.evidence_mode}</Badge></td>
                    <td className="whitespace-nowrap text-xs text-fg-subtle">{fmt.time(a.created_at)}</td>
                  </tr>
                ))}</tbody>
              </DataTable>
            )}
          </Card>

          <Card title={<>Latest benchmark {lb && <Badge tone={MEASUREMENT_TONE[lb.measurement] ?? 'gray'}>{lb.measurement}</Badge>}</>} actions={<a href="#tokens" className="text-xs font-medium no-underline">Token Analytics</a>} flush>
            {!lb ? <div className="p-4"><Empty>No benchmark yet. Run one from Token Analytics.</Empty></div> : (
              <DataTable label="Latest benchmark" caption={<>Measurement: {lb.measurement}{lb.measurement !== 'ACTUAL_PROVIDER_USAGE' ? ' — not real model usage' : ''} · provider {lb.provider} · n={lb.runs_per_mode} per configuration · repair budget {lb.repair_budget}{lb.average_savings_pct != null ? ` · average savings ${lb.average_savings_pct}% over ${lb.comparable_tasks}/${lb.total_tasks} comparable tasks` : ''}</>}>
                <thead><tr><th>Task</th><th className="text-right">Baseline tokens</th><th className="text-right">VeriCode tokens</th><th className="text-right">Savings</th><th>Success (B / V)</th></tr></thead>
                <tbody>{lb.tasks.map((t: any) => (
                  <tr key={t.task}>
                    <td className="font-mono text-xs">{t.task}</td>
                    <td className="text-right tabular-nums">{fmt.n(t.summary.baseline.total_tokens.mean)}</td>
                    <td className="text-right tabular-nums">{fmt.n(t.summary.vericode.total_tokens.mean)}</td>
                    <td className="text-right tabular-nums">{t.token_savings_pct == null ? <span className="text-fg-subtle" title={t.savings_note}>n/a</span> : <span className={t.token_savings_pct >= 0 ? 'text-ok' : 'text-err'}>{t.token_savings_pct}%</span>}</td>
                    <td className="tabular-nums">{fmt.pct(t.summary.baseline.success_rate)} / {fmt.pct(t.summary.vericode.success_rate)}</td>
                  </tr>
                ))}</tbody>
              </DataTable>
            )}
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          <Card title="Quick actions" flush>
            <ul className="divide-y divide-line">
              {QUICK.map((q) => (
                <li key={q.href}>
                  <a href={q.href} className="group flex items-center gap-3 px-4 py-2.5 text-fg no-underline hover:bg-subtle/60">
                    <q.icon aria-hidden className="h-4 w-4 shrink-0 text-fg-subtle group-hover:text-accent" />
                    <span className="min-w-0 flex-1"><span className="block text-[13px] font-medium">{q.label}</span><span className="block text-xs text-fg-subtle">{q.sub}</span></span>
                    <ArrowRight aria-hidden className="h-3.5 w-3.5 text-fg-subtle group-hover:text-accent" />
                  </a>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Integrations"><IntegrationStatus i={data.integrations} /></Card>
          {byM.length > 0 && (
            <Card title="Recorded tokens by measurement">
              <div className="flex h-2 overflow-hidden rounded-full bg-subtle" aria-hidden>
                {byM.map((m) => <div key={m.measurement} className={`${MIX[m.measurement] ?? 'bg-info'} border-r-2 border-surface last:border-r-0`} style={{ width: `${mixTotal ? (m.tokens / mixTotal) * 100 : 0}%` }} />)}
              </div>
              <div className="mt-3 space-y-1.5">
                {byM.map((m) => <div key={m.measurement} className="flex items-center justify-between gap-2 text-xs"><Badge tone={MEASUREMENT_TONE[m.measurement] ?? 'gray'}>{m.measurement}</Badge><span className="tabular-nums text-fg-muted">{fmt.n(m.tokens)} · {m.calls} calls</span></div>)}
              </div>
              {est && <p className="mt-2 text-xs text-fg-subtle">{data.estimated_calls} of {fmt.n(data.llm_calls)} calls used estimated counts.</p>}
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
