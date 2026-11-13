import { useState } from 'react'
import { CheckCircle2, Circle, CircleAlert, CircleX, FileCode2, Loader2 } from 'lucide-react'
import { api, fmt } from '../api'
import { FindingsList, KV } from './Findings'
import { ConfidenceHeatmap, CorrectionsList } from './Heatmap'
import { Badge, Button, Card, Diff, Empty, ErrorBox, Mono, Notice } from './ui'

const ERROR_TITLE: Record<string, string> = {
  executable_not_found: 'Required program not found',
  dependencies_not_installed: 'Dependencies not installed',
  workspace_missing: 'Sandbox workspace missing',
  launch_failed: 'Command could not start',
}

/** Structured execution error from the backend: what failed, where, and how to fix it (no raw traceback). */
export function ExecutionError({ detail }: { detail: any }) {
  const details = Object.entries(detail.details ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
  return (
    <div role="alert" className="rounded-md border border-err/25 bg-err-soft px-3 py-2.5 text-[13px] text-err">
      <div className="flex items-start gap-2">
        <CircleAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 space-y-1 break-words">
          <div className="font-semibold">{ERROR_TITLE[detail.category] ?? 'Execution error'}{detail.stage && <span className="font-normal"> · stage {detail.stage}</span>}</div>
          <div>{detail.message}</div>
          {detail.action && <div className="text-fg"><b className="font-medium">Fix:</b> {detail.action}</div>}
          {details.length > 0 && (
            <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-0.5 pt-1 font-mono text-[11px] text-fg-muted">
              {details.map(([k, v]) => <div key={k} className="contents"><dt>{k}</dt><dd className="break-all">{Array.isArray(v) ? v.join(' ') : String(v)}</dd></div>)}
            </dl>
          )}
          <div className="font-mono text-[11px] text-fg-subtle">{detail.category}</div>
        </div>
      </div>
    </div>
  )
}

const VERDICT: Record<string, string> = { VERIFIED_LOCAL: 'verified', VERIFIED_LIVE: 'verified', STALE: 'verified', DEPRECATED: 'verified', INCOMPATIBLE: 'verified', NOT_FOUND: 'not_found', ERROR: 'error' }
/** Same counting as the backend summary (verify_api.summarize), for reports stored before it existed. */
export function summarizeFindings(findings: any[]) {
  const m: Record<string, number> = { planned: findings.length, verified: 0, not_found: 0, uncertain: 0, error: 0 }
  for (const f of findings) m[VERDICT[f.status] ?? 'uncertain'] += 1
  return m
}

export function TokenTable({ tokens }: { tokens: any }) {
  if (!tokens) return <Empty>No token usage recorded.</Empty>
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="text-left text-[11px] uppercase tracking-wide text-fg-subtle"><tr><th className="py-1.5 font-medium">Stage</th><th className="font-medium">Input</th><th className="font-medium">Output</th><th className="text-right font-medium">Calls</th></tr></thead>
          <tbody>
            {Object.entries(tokens.by_stage ?? {}).map(([k, v]: any) => (
              <tr key={k} className="border-t border-line"><td className="py-1.5 font-mono text-xs">{k}</td><td className="tabular-nums">{fmt.n(v.input)}</td><td className="tabular-nums">{fmt.n(v.output)}</td><td className="text-right tabular-nums">{v.calls}</td></tr>
            ))}
            <tr className="border-t border-line-strong font-semibold"><td className="py-1.5">Total</td><td className="tabular-nums">{fmt.n(tokens.input)}</td><td className="tabular-nums">{fmt.n(tokens.output)}</td><td className="text-right tabular-nums">{tokens.calls}</td></tr>
          </tbody>
        </table>
      </div>
      <div className="mt-2"><Badge tone={tokens.estimated ? 'amber' : 'green'}>{tokens.measurement}</Badge></div>
    </div>
  )
}

function Timeline({ events, running }: { events: any[]; running: boolean }) {
  if (!events.length && !running) return <Empty>No events yet.</Empty>
  return (
    <ol className="space-y-2">
      {events.map((e: any, i: number) => {
        const failed = e.stage === 'error' || /failed/i.test(e.message)
        const Icon = failed ? CircleX : e.stage === 'test' && /passed/i.test(e.message) ? CheckCircle2 : Circle
        return (
          <li key={i} className="flex gap-2.5 text-[13px]">
            <Icon aria-hidden className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${failed ? 'text-err' : Icon === CheckCircle2 ? 'text-ok' : 'text-fg-subtle'}`} />
            <div className="min-w-0">
              <span className="mr-2 font-mono text-[11px] uppercase text-fg-subtle">{e.stage}</span>
              <span className="text-fg">{e.message}</span>
            </div>
          </li>
        )
      })}
      {running && <li className="flex items-center gap-2.5 text-[13px] text-accent"><Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />running…</li>}
    </ol>
  )
}

export function TaskReport({ task, onApplied }: { task: any; onApplied?: () => void }) {
  const [applyErr, setApplyErr] = useState<unknown>(null)
  const [conflicts, setConflicts] = useState<any[] | null>(null)
  const [applied, setApplied] = useState<string[] | null>(null)
  const res = task.result ?? {}
  const pf = task.preflight ?? {}
  const running = String(task.status).startsWith('running') || task.status === 'queued'
  const apply = async () => {
    setApplyErr(null); setConflicts(null)
    try {
      const r = await api<any>(`/tasks/${task.id}/apply`, { method: 'POST' })
      setApplied(r.applied)
      onApplied?.()
    } catch (e: any) {
      setApplyErr(e)
      if (e?.data?.conflicts) setConflicts(e.data.conflicts)
    }
  }
  const path = res.execution_path ?? pf.execution_path
  const audit = res.api_audit
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-line bg-surface px-4 py-2.5 shadow-raised">
        <Badge>{task.outcome ?? res.outcome ?? task.status}</Badge>
        <Badge tone="blue">{task.mode}</Badge>
        {path && <span className="text-xs text-fg-muted">path <b className="font-medium text-fg">{path}</b></span>}
        {res.backend && <span className="text-xs text-fg-muted">sandbox <b className="font-medium text-fg">{res.backend}</b></span>}
        {res.duration_s != null && <span className="text-xs text-fg-muted">duration <b className="font-medium tabular-nums text-fg">{res.duration_s}s</b></span>}
        {res.tokens && <span className="text-xs text-fg-muted">tokens <b className="font-medium tabular-nums text-fg">{fmt.n(res.tokens.total)}</b></span>}
        <span className="text-xs text-fg-muted">provider <b className="font-medium text-fg">{task.provider}</b></span>
        <span className="ml-auto font-mono text-[11px] text-fg-subtle">{task.id}</span>
      </div>
      {task.provider === 'mock' && <Notice>Scripted mock provider: responses are canned for demo tasks and token counts are estimated (MOCK).</Notice>}
      {res.outcome === 'partial' && <Notice>Partial: code was changed but the project has no tests, so the change is unvalidated. It is not counted as a success.</Notice>}
      {res.error_detail ? <ExecutionError detail={res.error_detail} /> : res.error && <ErrorBox error={{ message: res.error }} />}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          {res.diff !== undefined && (
            <Card title={<><FileCode2 aria-hidden className="h-4 w-4 text-fg-subtle" />Changes ({res.changed_files?.length ?? 0} file{res.changed_files?.length === 1 ? '' : 's'})</>}
              description={<>Made and validated in an isolated copy (<span className="font-mono">{res.sandbox}</span>). Applying copies the files into the real workspace and is refused if they changed since the run.</>}
              actions={res.success && !res.applied_at && !applied ? <Button onClick={apply}>Apply to workspace</Button> : (res.applied_at || applied) ? <Badge tone="green">applied</Badge> : null}>
              <ErrorBox error={applyErr} />
              {conflicts && conflicts.map((c) => (
                <div key={c.path} className="mb-3">
                  <Notice>Conflict: <span className="font-mono">{c.path}</span> was {c.state} in your workspace after the run started. Nothing was overwritten — re-run the task or merge manually. Your change:</Notice>
                  <div className="mt-2"><Diff text={c.user_diff} /></div>
                </div>
              ))}
              {res.changed_files?.length > 1 && (
                <div className="mb-2 flex flex-wrap gap-1.5">{res.changed_files.map((f: string) => <span key={f} className="rounded border border-line bg-subtle px-1.5 py-px font-mono text-[11px] text-fg">{f}</span>)}</div>
              )}
              <Diff text={res.diff} />
            </Card>
          )}

          {res.attempts && (
            <Card title="Validation" description="Each attempt's edits and the project checks run in the sandbox." flush>
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead className="border-b border-line bg-subtle/60 text-left text-[11px] uppercase tracking-wide text-fg-subtle"><tr><th className="px-4 py-2 font-medium">#</th><th className="font-medium">Stage</th><th className="font-medium">Edits</th><th className="font-medium">Edit errors</th><th className="font-medium">Checks</th><th className="font-medium">API audit</th><th className="px-4 text-right font-medium">Tokens in / out</th></tr></thead>
                  <tbody>{res.attempts.map((a: any) => (
                    <tr key={a.attempt} className="border-b border-line last:border-b-0"><td className="px-4 py-2">{a.attempt}</td><td className="font-mono text-xs">{a.stage}</td><td>{a.edits}</td><td className="max-w-xs text-xs text-err">{a.edit_errors.join('; ')}</td><td><Badge tone={a.passed ? 'green' : 'red'}>{a.passed ? 'passed' : 'failed'}</Badge></td><td className="text-xs text-fg-muted">{a.audit_problems == null ? '—' : a.audit_problems === 0 ? 'clean' : `${a.audit_problems} problem(s)`}</td><td className="px-4 text-right tabular-nums">{fmt.n(a.input_tokens)} / {fmt.n(a.output_tokens)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              {res.checks?.results?.length > 0 && (
                <div className="space-y-3 border-t border-line p-4">
                  {res.checks.results.map((r: any, i: number) => (
                    <div key={i}>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted"><Badge tone={r.passed ? 'green' : r.required === false ? 'amber' : 'red'}>{r.kind ?? 'test'}{r.required === false && !r.passed ? ' (pre-existing, advisory)' : ''}</Badge> <span className="font-mono text-fg">{r.command}</span> exit {r.returncode} · isolation: {r.isolation}</div>
                      <Mono className="mt-1.5 max-h-64">{(r.stdout || '') + (r.stderr ? `\n${r.stderr}` : '')}</Mono>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          {pf.findings && (
            <Card title="Pre-flight report" description="Planned third-party APIs verified against the installed packages before code generation.">
              <div className="mb-4 grid gap-4 sm:grid-cols-3">
                <KV k="APIs" v={(() => { const m = pf.summary ?? summarizeFindings(pf.findings); return `${m.planned} planned · ${m.verified} verified · ${m.not_found} not found · ${m.uncertain} uncertain · ${m.error} errors` })()} />
                <KV k="Tavily calls" v={`${pf.tavily_calls ?? 0}${pf.tavily_configured ? '' : ' (no key: live verification not performed)'}`} />
                <KV k="Rules saved to memory" v={pf.rules_saved?.length ?? 0} />
              </div>
              {pf.findings.length > 0 && <div className="mb-4"><ConfidenceHeatmap findings={pf.findings} corrections={res.api_corrections} /></div>}
              <FindingsList findings={pf.findings} />
              {res.api_corrections?.length > 0 && <><div className="mt-4 text-xs font-medium text-fg-muted">Flagged APIs in the generated code</div><CorrectionsList corrections={res.api_corrections} /></>}
              <div className="mt-4 text-xs font-medium text-fg-muted">Briefing injected into the coder prompt</div>
              <Mono className="mt-1.5">{pf.briefing}</Mono>
            </Card>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          <Card title="Run"><Timeline events={task.events ?? []} running={running} /></Card>
          {(audit || pf.risk) && (
            <Card title="API audit">
              {pf.risk && <div className="mb-2 text-xs text-fg-muted">Risk gate: <b className="font-medium text-fg">{pf.risk.risk}</b> → {pf.risk.fast_path ? 'planner skipped' : 'full verification'}<div className="mt-1 text-fg-subtle">{pf.risk.reasons?.[0]}</div></div>}
              {audit && <div className="text-xs text-fg-muted">Final code: {audit.checked} third-party API use(s) audited, <b className={audit.problem_count ? 'text-err' : 'text-ok'}>{audit.problem_count} problem(s)</b></div>}
              {audit?.problems?.length > 0 && <ul className="mt-2 space-y-1">{audit.problems.map((p: any, i: number) => <li key={i} className="flex flex-wrap items-center gap-1.5 text-xs"><Badge>{p.status}</Badge><span className="font-mono">{p.planned_api}</span></li>)}</ul>}
            </Card>
          )}
          {pf.selected_files && (
            <Card title={`Context files (${pf.selected_files.length})`}>
              <ul className="space-y-1.5 text-xs">{pf.selected_files.map((f: any) => <li key={f.path}><div className="font-mono text-fg">{f.path}</div><div className="text-fg-subtle">{f.reasons?.join('; ')}</div></li>)}</ul>
            </Card>
          )}
          <Card title="Token usage"><TokenTable tokens={res.tokens} /></Card>
        </div>
      </div>
    </div>
  )
}
