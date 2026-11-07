import { Badge } from './ui'

const CELL: Record<string, string> = {
  VERIFIED_LOCAL: 'bg-emerald-500/25 ring-emerald-400/40 text-emerald-100',
  VERIFIED_LIVE: 'bg-emerald-500/25 ring-emerald-400/40 text-emerald-100',
  STALE: 'bg-amber-400/15 ring-amber-300/30 text-amber-100',
  DEPRECATED: 'bg-amber-500/30 ring-amber-400/50 text-amber-50',
  INCOMPATIBLE: 'bg-rose-500/30 ring-rose-400/50 text-rose-50',
  NOT_FOUND: 'bg-rose-600/40 ring-rose-400/60 text-rose-50',
  UNCERTAIN: 'bg-slate-500/25 ring-slate-400/40 text-slate-100',
  NOT_CHECKED: 'bg-ink-800 ring-ink-600 text-slate-400',
}
const LEGEND = ['VERIFIED_LOCAL', 'VERIFIED_LIVE', 'STALE', 'DEPRECATED', 'INCOMPATIBLE', 'NOT_FOUND', 'UNCERTAIN', 'NOT_CHECKED']

/** Confidence heatmap: one row per planned library, one cell per planned API, coloured by verification status.
 *  "VERIFIED" appears only for APIs found in installed code / official docs — never for guesses. */
export function ConfidenceHeatmap({ findings, corrections }: { findings: any[]; corrections?: any[] }) {
  if (!findings?.length) return null
  const corr = Object.fromEntries((corrections ?? []).map((c) => [c.planned_api, c.result]))
  const byPkg: Record<string, any[]> = {}
  for (const f of findings) (byPkg[`${f.package}@${f.installed_version ?? 'not installed'}`] ??= []).push(f)
  const counts = LEGEND.map((s) => [s, findings.filter((f) => f.status === s).length] as const).filter(([, n]) => n)
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
        {counts.map(([s, n]) => <span key={s} className={`rounded px-1.5 py-0.5 ring-1 ring-inset ${CELL[s]}`}>{s} · {n}</span>)}
        {corrections && corrections.length > 0 && <span className="text-slate-400">· auto-corrected {corrections.filter((c) => c.result === 'corrected').length}/{corrections.length} flagged APIs</span>}
      </div>
      <div className="space-y-2" role="table" aria-label="API confidence heatmap">
        {Object.entries(byPkg).map(([pkg, fs]) => (
          <div key={pkg} role="row" className="flex flex-wrap items-stretch gap-1.5">
            <div role="rowheader" className="w-40 shrink-0 py-1 font-mono text-xs text-slate-300">{pkg}</div>
            {fs.map((f) => {
              const name = f.planned_api.split(/[.:]/).slice(f.planned_api.includes(':') ? 1 : 1).join('.') || f.planned_api
              const c = corr[f.planned_api]
              return (
                <div key={f.planned_api + f.arguments?.join(',')} role="cell"
                  title={`${f.planned_api}: ${f.status} (risk ${f.risk_score}, confidence ${f.verification_confidence})\n${f.explanation}`}
                  className={`min-w-28 rounded px-2 py-1 font-mono text-[11px] ring-1 ring-inset ${CELL[f.status] ?? CELL.NOT_CHECKED}`}>
                  <div className="truncate">{name}</div>
                  <div className="text-[10px] opacity-80">{f.status}{c ? (c === 'corrected' ? ' → corrected ✓' : c === 'still_used' ? ' → still used ✗' : '') : ''}</div>
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

export function CorrectionsList({ corrections }: { corrections: any[] }) {
  if (!corrections?.length) return null
  return (
    <ul className="mt-2 space-y-1 text-xs">
      {corrections.map((c) => (
        <li key={c.planned_api}><Badge tone={c.result === 'corrected' ? 'green' : c.result === 'still_used' ? 'red' : 'gray'}>{c.result}</Badge> <span className="font-mono">{c.planned_api}</span> <span className="text-slate-500">({c.status}) {c.detail}</span></li>
      ))}
    </ul>
  )
}
