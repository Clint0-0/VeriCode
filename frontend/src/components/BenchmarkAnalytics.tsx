import { fmt, MEASUREMENT_TONE } from '../api'
import { Badge, Empty } from './ui'

// Categorical order is fixed by configuration identity (validated: dark surface #10172a, CVD ΔE >= 8.4).
export const CONFIG_COLOR: Record<string, string> = {
  baseline: '#3987e5',
  vericode_full: '#d95926',
  vericode_adaptive: '#199e70',
  context_only: '#c98500',
}
export const CONFIG_LABEL: Record<string, string> = {
  baseline: 'Baseline',
  vericode_full: 'VeriCode (full pre-flight)',
  vericode_adaptive: 'VeriCode (adaptive)',
  context_only: 'Targeted context only (ablation)',
}
const ORDER = ['baseline', 'vericode_full', 'vericode_adaptive', 'context_only']
const STAGES: [string, string][] = [['planner_tokens', 'Planner'], ['coder_tokens', 'Coder'], ['repair_tokens', 'Repair']]

type Cfg = any
type Task = { task: string; title: string; language?: string; repo_size?: string; category?: string; configurations: Record<string, Cfg>; comparisons: Record<string, any> }

const sign = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '−' : v < 0 ? '+' : ''}${Math.abs(v)}% tokens`)

function Legend({ cfgs }: { cfgs: string[] }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-300" role="list" aria-label="Configurations">
      {cfgs.map((c) => (
        <span key={c} role="listitem" className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: CONFIG_COLOR[c] }} />
          {CONFIG_LABEL[c] ?? c}
        </span>
      ))}
    </div>
  )
}

export function MeasurementBanner({ labels }: { labels: string[] }) {
  const actual = labels.length === 1 && labels[0] === 'ACTUAL_PROVIDER_USAGE'
  if (actual) return <div className="text-xs text-slate-400">Measurement: <Badge tone="green">ACTUAL_PROVIDER_USAGE</Badge> provider-reported token counts only.</div>
  return (
    <div role="alert" className="rounded-md border border-amber-500/50 bg-amber-500/10 p-2 text-sm text-amber-200">
      <b>Not provider-measured:</b> {labels.length ? labels.map((l) => <Badge key={l} tone={MEASUREMENT_TONE[l] ?? 'gray'}>{l}</Badge>) : 'no measurement label'} — these figures are{' '}
      {labels.includes('MOCK') ? 'from the scripted offline mock provider' : 'estimated (chars/4)'} and must not be read as real token usage.
    </div>
  )
}

/** Mean tokens per configuration for every task, with the paired saving vs baseline next to each bar. */
function TaskBars({ tasks, cfgs }: { tasks: Task[]; cfgs: string[] }) {
  const max = Math.max(1, ...tasks.flatMap((t) => cfgs.map((c) => t.configurations[c]?.total_tokens?.mean ?? 0)))
  return (
    <div className="space-y-3">
      {tasks.map((t) => (
        <div key={t.task}>
          <div className="mb-1 flex items-baseline justify-between text-xs">
            <span className="font-medium text-slate-200">{t.task}</span>
            <span className="text-slate-500">{[t.language, t.repo_size, t.category].filter(Boolean).join(' · ')}</span>
          </div>
          {cfgs.map((c) => {
            const k = t.configurations[c]
            if (!k) return null
            const mean = k.total_tokens?.mean
            const comp = t.comparisons[c]
            const ps = comp?.paired_savings
            const tip = `${CONFIG_LABEL[c]}: ${fmt.n(mean)} tokens mean (${k.completed} runs, ${k.blocked} blocked, success ${fmt.pct(k.success_rate)})` +
              (ps?.n ? ` · paired saving ${ps.mean}% (n=${ps.n})` : '')
            return (
              <div key={c} className="group flex items-center gap-2 py-px text-xs" title={tip}>
                <div className="relative h-3 flex-1 rounded-sm bg-ink-800/60">
                  {mean != null && <div className="h-3 rounded-r" style={{ width: `${(mean / max) * 100}%`, background: CONFIG_COLOR[c], minWidth: 2 }} />}
                </div>
                <span className="w-16 text-right tabular-nums text-slate-300">{mean == null ? (k.blocked ? 'blocked' : '—') : fmt.n(Math.round(mean))}</span>
                <span className={`w-28 text-right tabular-nums ${c === 'baseline' ? 'text-slate-600' : ps?.n ? (ps.mean >= 0 ? 'text-slate-200' : 'text-rose-300') : 'text-slate-500'}`}>
                  {c === 'baseline' ? '' : ps?.n ? `${ps.mean >= 0 ? '▼' : '▲'} ${sign(ps.mean)}` : 'n/a'}
                </span>
              </div>
            )
          })}
        </div>
      ))}
      <p className="text-xs text-slate-500">Bar = mean tokens over completed runs. ▼ fewer / ▲ more tokens than baseline, paired over repetitions where both runs succeeded; n/a = no comparable pair (a run failed or was blocked).</p>
    </div>
  )
}

/** Where the tokens go: planner / coder / repair, mean per task summed over tasks; input vs output split. */
function StageBars({ tasks, cfgs }: { tasks: Task[]; cfgs: string[] }) {
  const rows = cfgs.map((c) => {
    const pick = (key: string) => tasks.reduce((s, t) => s + (t.configurations[c]?.[key]?.mean ?? 0), 0)
    return { c, stages: STAGES.map(([k]) => pick(k)), input: pick('input_tokens'), output: pick('output_tokens') }
  })
  const max = Math.max(1, ...rows.map((r) => r.input + r.output))
  const tones = ['opacity-100', 'opacity-60', 'opacity-35']
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <div className="mb-1 text-xs text-slate-400">By pipeline stage (sum of per-task means)</div>
        {rows.map((r) => (
          <div key={r.c} className="flex items-center gap-2 py-0.5 text-xs" title={`${CONFIG_LABEL[r.c]}: ` + STAGES.map(([, l], i) => `${l} ${fmt.n(Math.round(r.stages[i]))}`).join(', ')}>
            <span className="w-24 truncate text-slate-400">{CONFIG_LABEL[r.c]?.split(' (')[0]}{r.c === 'vericode_full' ? ' full' : r.c === 'vericode_adaptive' ? ' adaptive' : ''}</span>
            <div className="flex h-3 flex-1 gap-[2px]">
              {r.stages.map((v, i) => v > 0 && <div key={i} className={`h-3 first:rounded-l-sm last:rounded-r ${tones[i]}`} style={{ width: `${(v / max) * 100}%`, background: CONFIG_COLOR[r.c] }} />)}
            </div>
            <span className="w-14 text-right tabular-nums text-slate-300">{fmt.n(Math.round(r.stages.reduce((a, b) => a + b, 0)))}</span>
          </div>
        ))}
        <div className="mt-1 flex gap-3 text-[11px] text-slate-500">{STAGES.map(([, l], i) => <span key={l} className="flex items-center gap-1"><span className={`inline-block h-2 w-3 rounded-sm bg-slate-300 ${tones[i]}`} />{l}</span>)}</div>
      </div>
      <div>
        <div className="mb-1 text-xs text-slate-400">Input vs output tokens</div>
        {rows.map((r) => (
          <div key={r.c} className="flex items-center gap-2 py-0.5 text-xs" title={`${CONFIG_LABEL[r.c]}: input ${fmt.n(Math.round(r.input))}, output ${fmt.n(Math.round(r.output))}`}>
            <span className="w-24 truncate text-slate-400">{r.c.replace('vericode_', '')}</span>
            <div className="flex h-3 flex-1 gap-[2px]">
              <div className="h-3 rounded-l-sm" style={{ width: `${(r.input / max) * 100}%`, background: CONFIG_COLOR[r.c] }} />
              <div className="h-3 rounded-r" style={{ width: `${(r.output / max) * 100}%`, background: `repeating-linear-gradient(45deg, ${CONFIG_COLOR[r.c]} 0 3px, transparent 3px 6px)` }} />
            </div>
            <span className="w-24 text-right tabular-nums text-slate-300">{fmt.n(Math.round(r.input))} / {fmt.n(Math.round(r.output))}</span>
          </div>
        ))}
        <div className="mt-1 flex gap-3 text-[11px] text-slate-500"><span>solid = input</span><span>hatched = output</span></div>
      </div>
    </div>
  )
}

/** Success rate vs mean tokens, one dot per task x configuration. */
function Scatter({ tasks, cfgs }: { tasks: Task[]; cfgs: string[] }) {
  const pts = tasks.flatMap((t) => cfgs.filter((c) => t.configurations[c]?.success_rate != null && t.configurations[c]?.total_tokens?.mean != null)
    .map((c) => ({ t: t.task, c, x: t.configurations[c].total_tokens.mean, y: t.configurations[c].success_rate })))
  if (!pts.length) return <Empty>No completed runs.</Empty>
  const W = 560, H = 200, P = 34
  const xmax = Math.max(...pts.map((p) => p.x)) * 1.08
  const sx = (x: number) => P + (x / xmax) * (W - P - 10)
  const sy = (y: number) => H - P + 4 - y * (H - P - 14)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Success rate versus mean tokens per task and configuration">
      {[0, 0.5, 1].map((y) => <g key={y}><line x1={P} x2={W - 10} y1={sy(y)} y2={sy(y)} stroke="#2a3552" strokeWidth={1} /><text x={P - 6} y={sy(y) + 3} textAnchor="end" fontSize={10} fill="#94a3b8">{y * 100}%</text></g>)}
      <text x={W - 10} y={H - 4} textAnchor="end" fontSize={10} fill="#94a3b8">mean tokens per run →</text>
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={sx(p.x)} cy={sy(p.y)} r={5} fill={CONFIG_COLOR[p.c]} stroke="#10172a" strokeWidth={2}>
            <title>{`${p.t} · ${CONFIG_LABEL[p.c]}: ${fmt.n(Math.round(p.x))} tokens, success ${fmt.pct(p.y)}`}</title>
          </circle>
          <circle cx={sx(p.x)} cy={sy(p.y)} r={11} fill="transparent"><title>{`${p.t} · ${CONFIG_LABEL[p.c]}: ${fmt.n(Math.round(p.x))} tokens, success ${fmt.pct(p.y)}`}</title></circle>
        </g>
      ))}
    </svg>
  )
}

function GroupTable({ tasks, cfgs, by, label }: { tasks: Task[]; cfgs: string[]; by: 'repo_size' | 'language'; label: string }) {
  const groups = [...new Set(tasks.map((t) => t[by] ?? '—'))]
  const others = cfgs.filter((c) => c !== 'baseline')
  const med = (xs: number[]) => (xs.length ? [...xs].sort((a, b) => a - b)[Math.floor((xs.length - 1) / 2)] : null)
  return (
    <table className="w-full text-xs">
      <caption className="pb-1 text-left text-slate-400">Median per-task paired saving by {label} (tasks with a comparable pair)</caption>
      <thead className="text-left text-slate-500"><tr><th className="py-1">{label}</th>{others.map((c) => <th key={c}>{CONFIG_LABEL[c]}</th>)}</tr></thead>
      <tbody>{groups.map((g) => (
        <tr key={g} className="border-t border-ink-700"><td className="py-1 text-slate-300">{g}</td>
          {others.map((c) => {
            const xs = tasks.filter((t) => (t[by] ?? '—') === g).map((t) => t.comparisons[c]?.mean_token_savings_pct).filter((x) => x != null)
            const m = med(xs)
            return <td key={c} className={`tabular-nums ${m != null && m < 0 ? 'text-rose-300' : 'text-slate-200'}`}>{m == null ? '—' : `${sign(m)} (${xs.length} task${xs.length === 1 ? '' : 's'})`}</td>
          })}
        </tr>
      ))}</tbody>
    </table>
  )
}

function PathTable({ tasks }: { tasks: Task[] }) {
  const rows = ['fast', 'full'].map((p) => {
    const ts = tasks.filter((t) => t.configurations.vericode_adaptive?.execution_paths?.[p])
    const sav = ts.map((t) => t.comparisons.vericode_adaptive?.mean_token_savings_pct).filter((x) => x != null)
    const succ = ts.map((t) => t.configurations.vericode_adaptive.success_rate).filter((x) => x != null)
    return { p, n: ts.length, sav, succ: succ.length ? succ.reduce((a: number, b: number) => a + b, 0) / succ.length : null }
  })
  return (
    <table className="w-full text-xs">
      <caption className="pb-1 text-left text-slate-400">Adaptive VeriCode: fast path (planner skipped) vs full verification path</caption>
      <thead className="text-left text-slate-500"><tr><th className="py-1">Path</th><th>Tasks</th><th>Mean success</th><th>Per-task savings vs baseline</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.p} className="border-t border-ink-700"><td className="py-1 text-slate-300">{r.p === 'fast' ? 'Fast path' : 'Full verification'}</td><td>{r.n}</td><td>{fmt.pct(r.succ)}</td>
          <td className="tabular-nums">{r.sav.length ? r.sav.map((x: number, i: number) => <span key={i} className={`mr-2 ${x < 0 ? 'text-rose-300' : 'text-slate-200'}`}>{sign(x)}</span>) : '—'}</td></tr>
      ))}</tbody>
    </table>
  )
}

export default function BenchmarkAnalytics({ summary, labels }: { summary: { tasks: Task[]; overall: Record<string, any> }; labels: string[] }) {
  const tasks = summary?.tasks ?? []
  if (!tasks.length) return <Empty>No benchmark runs in this result.</Empty>
  const cfgs = ORDER.filter((c) => tasks.some((t) => t.configurations[c]))
  return (
    <div className="space-y-5">
      <MeasurementBanner labels={labels} />
      <table className="w-full text-xs">
        <caption className="pb-1 text-left text-slate-400">Overall, paired successful runs only (exploratory for n &lt; 10)</caption>
        <thead className="text-left text-slate-500"><tr><th className="py-1">Configuration</th><th>Tasks compared</th><th>Pairs</th><th>Token-weighted saving</th><th>Median task saving</th><th>Tasks with more tokens than baseline</th></tr></thead>
        <tbody>{Object.entries(summary.overall).map(([c, o]: any) => (
          <tr key={c} className="border-t border-ink-700"><td className="py-1"><span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: CONFIG_COLOR[c] }} />{CONFIG_LABEL[c] ?? c}</td>
            <td>{o.tasks_compared}/{o.tasks_total}</td><td>{o.pairs}</td>
            <td className={`tabular-nums ${o.token_weighted_savings_pct < 0 ? 'text-rose-300' : 'text-slate-200'}`}>{sign(o.token_weighted_savings_pct)}</td>
            <td className="tabular-nums">{sign(o.median_task_savings_pct)}</td><td>{o.tasks_with_negative_savings}</td></tr>
        ))}</tbody>
      </table>
      <Legend cfgs={cfgs} />
      <TaskBars tasks={tasks} cfgs={cfgs} />
      <StageBars tasks={tasks} cfgs={cfgs} />
      <div><div className="mb-1 text-xs text-slate-400">Success rate vs token consumption</div><Scatter tasks={tasks} cfgs={cfgs} /><Legend cfgs={cfgs} /></div>
      <div className="grid gap-4 md:grid-cols-2">
        <GroupTable tasks={tasks} cfgs={cfgs} by="repo_size" label="repository size" />
        <GroupTable tasks={tasks} cfgs={cfgs} by="language" label="language" />
      </div>
      {cfgs.includes('vericode_adaptive') && <PathTable tasks={tasks} />}
    </div>
  )
}
