import { Fragment, useState } from 'react'
import { ChevronRight, ExternalLink } from 'lucide-react'
import { Badge, Empty, Mono } from './ui'

function Detail({ f }: { f: any }) {
  return (
    <div className="space-y-3">
      <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <KV k="Installed version" v={`${f.package} ${f.installed_version ?? 'not installed'}`} />
        <KV k="Plan assumed" v={f.assumed_version ?? '—'} />
        <KV k="API compatibility" v={f.api_compatibility} />
        <KV k="Verification confidence" v={f.verification_confidence} />
        <KV k="Evidence freshness" v={f.evidence_freshness ?? 'n/a (local source)'} />
        <KV k="Risk score (index, not probability)" v={String(f.risk_score)} />
        <KV k="Method" v={(f.verification_method ?? []).join(' → ')} />
        <KV k="Location" v={f.local?.location ?? '—'} />
      </div>
      <p className="text-[13px] leading-relaxed text-fg">{f.explanation}</p>
      {f.suggested_correction && <div className="rounded-md border border-ok/25 bg-ok-soft px-3 py-2 text-[13px] text-fg"><b className="font-semibold text-ok">Correction:</b> {f.suggested_correction}</div>}
      {f.risk_factors?.length > 0 && (
        <ul className="space-y-0.5 text-xs text-fg-muted">
          {f.risk_factors.map((r: any, j: number) => <li key={j}><span className="font-mono text-warn">+{r.weight}</span> {r.factor}: {r.detail}</li>)}
        </ul>
      )}
      {f.argument_checks?.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="w-full text-xs">
            <thead className="bg-subtle/60 text-left text-[11px] uppercase tracking-wide text-fg-subtle"><tr><th className="px-2 py-1.5 font-medium">Argument</th><th className="px-2 font-medium">Status</th><th className="px-2 font-medium">Detail</th></tr></thead>
            <tbody>{f.argument_checks.map((a: any) => (
              <tr key={a.argument} className="border-t border-line"><td className="px-2 py-1.5 font-mono">{a.argument}</td><td className="px-2"><Badge tone={a.status === 'supported' ? 'green' : a.status === 'uncertain' ? 'amber' : 'red'}>{a.status}</Badge></td><td className="px-2 text-fg-muted">{a.detail}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {f.live && (
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs font-medium text-fg-muted">Live documentation (Tavily) <Badge tone={f.live.status === 'ok' ? 'green' : 'amber'}>{f.live.status}</Badge> {f.live.detail && <span className="font-normal text-fg-subtle">{f.live.detail}</span>}</div>
          {f.live.query && <div className="text-xs text-fg-subtle">query: <span className="font-mono">{f.live.query}</span>{f.live.domains?.length ? ` · domains: ${f.live.domains.join(', ')}` : ''}</div>}
          {f.live.sources?.map((s: any, k: number) => (
            <div key={k} className="mt-2 rounded-md border border-line p-2.5 text-xs">
              <a className="inline-flex items-center gap-1 font-medium" href={s.url} target="_blank" rel="noreferrer noopener">{s.title || s.url}<ExternalLink aria-hidden className="h-3 w-3" /></a>
              <span className="ml-2 text-fg-subtle">{s.domain}{s.official ? ' · official' : ''}{s.published_date ? ` · ${s.published_date}` : ''}</span>
              <p className="mt-1 text-fg-muted">{s.excerpt}</p>
            </div>
          ))}
        </div>
      )}
      {f.local?.signatures?.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium text-fg-muted">Installed signature(s) — TypeScript compiler API {f.local.package ? `(${f.local.package.name}@${f.local.package.version})` : ''}</div>
          {f.local.signatures.map((sg: any, k: number) => (
            <div key={k} className="mb-1 break-words font-mono text-xs text-fg">{sg.text} <span className="text-fg-subtle">· args {sg.min_args}–{sg.max_args ?? '∞'}{sg.type_params?.length ? ` · generics ${sg.type_params.map((t: any) => t.name + (t.constraint ? ' extends ' + t.constraint : '')).join(', ')}` : ''}</span></div>
          ))}
        </div>
      )}
      {f.local?.call_check && (
        <div className="text-xs"><span className="text-fg-muted">Type-checked call: </span><span className="font-mono text-fg">{f.local.call_check.source}</span> <Badge tone={f.local.call_check.ok ? 'green' : 'red'}>{f.local.call_check.ok ? 'ok' : 'type error'}</Badge>
          {f.local.call_check.diagnostics?.map((d: any, k: number) => <div key={k} className="mt-1 font-mono text-err">TS{d.code}: {d.message}</div>)}
        </div>
      )}
      {f.local?.similar_exports?.length > 0 && <div className="text-xs text-fg-muted">Similar exports: <span className="font-mono">{f.local.similar_exports.join(', ')}</span></div>}
      {f.local?.doc && <Mono>{f.local.doc}</Mono>}
    </div>
  )
}

/** Structured findings table; each row expands to the full verification evidence. */
export function FindingsList({ findings }: { findings: any[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  if (!findings?.length) return <Empty>No third-party APIs were planned for this task.</Empty>
  const toggle = (i: number) => setOpen((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n })
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full min-w-[720px] text-left text-[13px]">
        <thead className="bg-subtle/60 text-[11px] uppercase tracking-wide text-fg-subtle">
          <tr>
            <th className="w-8 px-2 py-2" aria-label="Details" />
            <th className="px-2 py-2 font-medium">Package</th>
            <th className="px-2 py-2 font-medium">Installed</th>
            <th className="px-2 py-2 font-medium">Planned API</th>
            <th className="px-2 py-2 font-medium">Status</th>
            <th className="px-2 py-2 font-medium">Compatibility details</th>
            <th className="px-2 py-2 font-medium">Suggested correction</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => {
            const isOpen = open.has(i)
            return (
              <Fragment key={i}>
                <tr className={`border-t border-line align-top ${isOpen ? 'bg-subtle/40' : 'hover:bg-subtle/40'}`}>
                  <td className="px-2 py-2">
                    <button type="button" aria-expanded={isOpen} aria-label={`Details for ${f.planned_api}`} onClick={() => toggle(i)} className="rounded p-0.5 text-fg-subtle hover:bg-hover hover:text-fg">
                      <ChevronRight aria-hidden className={`h-3.5 w-3.5 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    </button>
                  </td>
                  <td className="px-2 py-2 font-mono text-xs text-fg">{f.package}</td>
                  <td className="px-2 py-2 font-mono text-xs text-fg-muted">{f.installed_version ?? (f.environment_status && !['AVAILABLE', 'AMBIGUOUS'].includes(f.environment_status) ? <span title="no usable environment">unknown · env {f.environment_status.toLowerCase()}</span> : 'not installed')}</td>
                  <td className="px-2 py-2">
                    <button type="button" onClick={() => toggle(i)} className="text-left font-mono text-xs font-medium text-fg hover:text-accent">{f.planned_api}</button>
                    {f.arguments?.length > 0 && <div className="font-mono text-[11px] text-fg-subtle">({f.arguments.join(', ')})</div>}
                  </td>
                  <td className="px-2 py-2"><Badge>{f.status}</Badge>{f.verdict && f.verdict !== f.status && <div className="mt-0.5 text-[11px] text-fg-subtle" title="existence in the installed package">exists: {f.verdict === 'VERIFIED' ? 'yes' : f.verdict.toLowerCase()}</div>}</td>
                  <td className="max-w-[22rem] px-2 py-2 text-xs text-fg-muted"><span className="line-clamp-2">{f.explanation}</span></td>
                  <td className="max-w-[18rem] px-2 py-2 text-xs text-fg"><span className="line-clamp-2">{f.suggested_correction || '—'}</span></td>
                </tr>
                {isOpen && <tr className="border-t border-line bg-surface"><td /><td colSpan={6} className="px-2 py-3"><Detail f={f} /></td></tr>}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function KV({ k, v }: { k: string; v: any }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">{k}</div>
      <div className="mt-0.5 break-words font-mono text-xs text-fg">{String(v)}</div>
    </div>
  )
}
