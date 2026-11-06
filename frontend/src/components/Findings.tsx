import { Badge, Empty, Expand, Mono } from './ui'

export function FindingsList({ findings }: { findings: any[] }) {
  if (!findings?.length) return <Empty>No third-party APIs were planned for this task.</Empty>
  return (
    <div className="space-y-2">
      {findings.map((f, i) => (
        <Expand key={i} head={<>
          <Badge>{f.status}</Badge>
          <span className="font-mono text-sm text-slate-100">{f.planned_api}</span>
          {f.arguments?.length > 0 && <span className="font-mono text-xs text-slate-500">({f.arguments.join(', ')})</span>}
          <span className="ml-auto text-xs text-slate-500">risk {f.risk_score}</span>
        </>}>
          <div className="grid gap-3 md:grid-cols-4">
            <KV k="Installed version" v={`${f.package} ${f.installed_version ?? 'not installed'}`} />
            <KV k="Plan assumed" v={f.assumed_version ?? '—'} />
            <KV k="API compatibility" v={f.api_compatibility} />
            <KV k="Verification confidence" v={f.verification_confidence} />
            <KV k="Evidence freshness" v={f.evidence_freshness ?? 'n/a (local source)'} />
            <KV k="Risk score (index, not probability)" v={String(f.risk_score)} />
            <KV k="Method" v={f.verification_method.join(' → ')} />
            <KV k="Location" v={f.local?.location ?? '—'} />
          </div>
          <p className="mt-3 text-slate-300">{f.explanation}</p>
          {f.suggested_correction && <div className="mt-2 rounded border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-emerald-200"><b>Correction:</b> {f.suggested_correction}</div>}
          {f.risk_factors?.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-slate-400">
              {f.risk_factors.map((r: any, j: number) => <li key={j}><span className="font-mono text-amber-300">+{r.weight}</span> {r.factor}: {r.detail}</li>)}
            </ul>
          )}
          {f.argument_checks?.length > 0 && (
            <table className="mt-3 w-full text-xs">
              <thead className="text-left text-slate-500"><tr><th className="py-1">Argument</th><th>Status</th><th>Detail</th></tr></thead>
              <tbody>{f.argument_checks.map((a: any) => (
                <tr key={a.argument} className="border-t border-ink-700"><td className="py-1 font-mono">{a.argument}</td><td><Badge tone={a.status === 'supported' ? 'green' : a.status === 'uncertain' ? 'amber' : 'red'}>{a.status}</Badge></td><td className="text-slate-400">{a.detail}</td></tr>
              ))}</tbody>
            </table>
          )}
          {f.live && (
            <div className="mt-3">
              <div className="mb-1 text-xs font-medium text-slate-400">Live documentation (Tavily) — <Badge tone={f.live.status === 'ok' ? 'green' : 'amber'}>{f.live.status}</Badge> {f.live.detail && <span className="text-xs text-slate-500">{f.live.detail}</span>}</div>
              {f.live.query && <div className="text-xs text-slate-500">query: <span className="font-mono">{f.live.query}</span>{f.live.domains?.length ? ` · domains: ${f.live.domains.join(', ')}` : ''}</div>}
              {f.live.sources?.map((s: any, k: number) => (
                <div key={k} className="mt-2 rounded border border-ink-700 p-2 text-xs">
                  <a className="text-sky-300 hover:underline" href={s.url} target="_blank" rel="noreferrer noopener">{s.title || s.url}</a>
                  <span className="ml-2 text-slate-500">{s.domain}{s.official ? ' · official' : ''}{s.published_date ? ` · ${s.published_date}` : ''}</span>
                  <p className="mt-1 text-slate-400">{s.excerpt}</p>
                </div>
              ))}
            </div>
          )}
          {f.local?.signatures?.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-xs font-medium text-slate-400">Installed signature(s) — TypeScript compiler API {f.local.package ? `(${f.local.package.name}@${f.local.package.version})` : ''}</div>
              {f.local.signatures.map((sg: any, k: number) => (
                <div key={k} className="mb-1 font-mono text-xs text-slate-300">{sg.text} <span className="text-slate-500">· args {sg.min_args}–{sg.max_args ?? '∞'}{sg.type_params?.length ? ` · generics ${sg.type_params.map((t: any) => t.name + (t.constraint ? ' extends ' + t.constraint : '')).join(', ')}` : ''}</span></div>
              ))}
            </div>
          )}
          {f.local?.call_check && (
            <div className="mt-2 text-xs"><span className="text-slate-400">Type-checked call: </span><span className="font-mono text-slate-200">{f.local.call_check.source}</span> <Badge tone={f.local.call_check.ok ? 'green' : 'red'}>{f.local.call_check.ok ? 'ok' : 'type error'}</Badge>
              {f.local.call_check.diagnostics?.map((d: any, k: number) => <div key={k} className="mt-1 font-mono text-rose-300">TS{d.code}: {d.message}</div>)}
            </div>
          )}
          {f.local?.similar_exports?.length > 0 && <div className="mt-2 text-xs text-slate-400">Similar exports: <span className="font-mono">{f.local.similar_exports.join(', ')}</span></div>}
          {f.local?.doc && <Mono className="mt-3">{f.local.doc}</Mono>}
        </Expand>
      ))}
    </div>
  )
}

export function KV({ k, v }: { k: string; v: any }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{k}</div>
      <div className="mt-0.5 break-words font-mono text-xs text-slate-200">{String(v)}</div>
    </div>
  )
}
