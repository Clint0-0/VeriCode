import { Badge, toneOf } from './ui'

const LEGEND = ['VERIFIED_LOCAL', 'VERIFIED_LIVE', 'STALE', 'DEPRECATED', 'INCOMPATIBLE', 'NOT_FOUND', 'UNCERTAIN', 'NOT_CHECKED']
const BAR: Record<string, string> = { green: 'bg-ok', amber: 'bg-warn', red: 'bg-err', blue: 'bg-info', gray: 'bg-fg-subtle' }

/** API confidence overview: one row per planned library, one cell per planned API with its verification status.
 *  "VERIFIED" appears only for APIs found in installed code / official docs — never for guesses. */
export function ConfidenceHeatmap({ findings, corrections }: { findings: any[]; corrections?: any[] }) {
  if (!findings?.length) return null
  const corr = Object.fromEntries((corrections ?? []).map((c) => [c.planned_api, c.result]))
  const byPkg: Record<string, any[]> = {}
  for (const f of findings) (byPkg[`${f.package}@${f.installed_version ?? 'not installed'}`] ??= []).push(f)
  const counts = LEGEND.map((s) => [s, findings.filter((f) => f.status === s).length] as const).filter(([, n]) => n)
  const total = findings.length
  return (
    <div className="space-y-3">
      <div>
        <div className="flex h-2 overflow-hidden rounded-full bg-subtle" aria-hidden>
          {counts.map(([s, n]) => <div key={s} className={`${BAR[toneOf(s)]} border-r-2 border-surface last:border-r-0`} style={{ width: `${(n / total) * 100}%` }} />)}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
          {counts.map(([s, n]) => (
            <span key={s} className="inline-flex items-center gap-1.5"><span aria-hidden className={`h-2 w-2 rounded-full ${BAR[toneOf(s)]}`} /><span className="font-mono text-[11px]">{s} · {n}</span></span>
          ))}
          {corrections && corrections.length > 0 && <span className="text-fg-muted">· auto-corrected {corrections.filter((c) => c.result === 'corrected').length}/{corrections.length} flagged APIs</span>}
        </div>
      </div>
      <div className="divide-y divide-line rounded-md border border-line" role="table" aria-label="API confidence heatmap">
        {Object.entries(byPkg).map(([pkg, fs]) => (
          <div key={pkg} role="row" className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-start">
            <div role="rowheader" className="w-44 shrink-0 pt-0.5 font-mono text-xs font-medium text-fg">{pkg}</div>
            <div className="flex min-w-0 flex-wrap gap-1.5">
              {fs.map((f) => {
                const name = f.planned_api.split(/[.:]/).slice(1).join('.') || f.planned_api
                const c = corr[f.planned_api]
                return (
                  <div key={f.planned_api + f.arguments?.join(',')} role="cell"
                    title={`${f.planned_api}: ${f.status} (risk ${f.risk_score}, confidence ${f.verification_confidence})\n${f.explanation}`}
                    className="inline-flex max-w-full items-center gap-2 rounded border border-line bg-surface px-2 py-1 font-mono text-[11px]">
                    <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${BAR[toneOf(f.status)]}`} />
                    <span className="truncate text-fg">{name}</span>
                    <span className="text-fg-subtle">{f.status}{c ? (c === 'corrected' ? ' → corrected ✓' : c === 'still_used' ? ' → still used ✗' : '') : ''}</span>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CorrectionsList({ corrections }: { corrections: any[] }) {
  if (!corrections?.length) return null
  return (
    <ul className="mt-2 space-y-1.5 text-xs">
      {corrections.map((c) => (
        <li key={c.planned_api} className="flex flex-wrap items-center gap-2"><Badge tone={c.result === 'corrected' ? 'green' : c.result === 'still_used' ? 'red' : 'gray'}>{c.result}</Badge> <span className="font-mono text-fg">{c.planned_api}</span> <span className="text-fg-muted">({c.status}) {c.detail}</span></li>
      ))}
    </ul>
  )
}
