import { Fragment, useState } from 'react'
import { ChevronRight, ExternalLink, Search } from 'lucide-react'
import { fmt } from '../api'
import { Badge, Card, Empty, ErrorBox, inputCls, Select, Spinner, useApi } from '../components/ui'

const OUTCOMES = ['support', 'contradict', 'neutral', 'irrelevant']

export default function Evidence({ param }: { param?: string }) {
  const { data, error, loading } = useApi<any[]>(param ? `/evidence?analysis_id=${param}` : '/evidence')
  const [q, setQ] = useState('')
  const [outcome, setOutcome] = useState('')
  const [open, setOpen] = useState<Set<string>>(new Set())
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const all = data ?? []
  const rows = all.filter((e) => (!outcome || e.outcome === outcome) && (!q || `${e.claim} ${e.title} ${e.domain}`.toLowerCase().includes(q.toLowerCase())))
  const counts = Object.fromEntries(OUTCOMES.map((o) => [o, all.filter((e) => e.outcome === o).length]))
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  return (
    <Card title={param ? <>Evidence for analysis <span className="font-mono">{param}</span></> : 'All retrieved evidence'}
      description={all.length ? `${all.length} sources · ${counts.support} supporting · ${counts.contradict} contradicting · ${counts.neutral + counts.irrelevant} not decisive` : undefined}
      actions={<>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2 h-3.5 w-3.5 -translate-y-1/2 text-fg-subtle" />
          <input aria-label="Filter" className={`${inputCls} h-7 w-56 py-0 pl-7 text-xs`} placeholder="Filter claim, title or domain…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select size="sm" aria-label="Outcome" className="w-36" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">all outcomes</option>{OUTCOMES.map((o) => <option key={o}>{o}</option>)}
        </Select>
      </>} flush>
      {!rows.length ? <div className="p-4"><Empty>{all.length ? 'No evidence matches the filter.' : 'No evidence yet. Run the Stale-Answer Detector.'}</Empty></div> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-[13px]">
            <thead className="border-b border-line bg-subtle/60 text-[11px] uppercase tracking-wide text-fg-subtle">
              <tr>{['', 'Source', 'Claim', 'Authority', 'Published', 'Retrieved', 'Type', 'Outcome'].map((h, i) => <th key={i} className={`whitespace-nowrap px-3 py-2 font-medium ${i === 0 ? 'w-8' : ''}`}>{h}</th>)}</tr>
            </thead>
            <tbody>{rows.map((e) => {
              const isOpen = open.has(e.id)
              const installed = e.url?.startsWith('installed://')
              return (
                <Fragment key={e.id}>
                  <tr className={`border-b border-line align-top ${isOpen ? 'bg-subtle/40' : 'hover:bg-subtle/40'}`}>
                    <td className="px-3 py-2">
                      <button type="button" aria-expanded={isOpen} aria-label={`Details for ${e.title || e.url}`} onClick={() => toggle(e.id)} className="rounded p-0.5 text-fg-subtle hover:bg-hover hover:text-fg">
                        <ChevronRight aria-hidden className={`h-3.5 w-3.5 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                      </button>
                    </td>
                    <td className="max-w-[16rem] px-3 py-2">
                      {installed ? <span className="font-mono text-xs font-medium text-ok" title={e.url}>{e.title}</span>
                        : <a className="inline-flex items-start gap-1 font-medium" href={e.url} target="_blank" rel="noreferrer noopener"><span className="line-clamp-2">{e.title || e.url}</span><ExternalLink aria-hidden className="mt-0.5 h-3 w-3 shrink-0" /></a>}
                      <div className="mt-0.5 font-mono text-[11px] text-fg-subtle">{e.domain}</div>
                    </td>
                    <td className="max-w-[18rem] px-3 py-2 text-fg"><span className="line-clamp-2">{e.claim}</span></td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-fg-muted">{e.authority}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-fg-muted">{e.published_date ?? 'unknown'}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-fg-muted" title={e.retrieved_at}>{fmt.ts(e.retrieved_at)}</td>
                    <td className="px-3 py-2"><div className="text-xs text-fg-muted">{e.source_type}</div><div className="mt-1"><Badge tone={e.origin?.startsWith('fixture') ? 'amber' : 'blue'}>{e.origin}</Badge></div></td>
                    <td className="px-3 py-2"><Badge tone={e.outcome === 'support' ? 'green' : e.outcome === 'contradict' ? 'red' : 'gray'}>{e.outcome}</Badge></td>
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-line bg-surface">
                      <td />
                      <td colSpan={7} className="px-3 py-3">
                        <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                          <div>
                            <div className="text-[11px] font-medium uppercase tracking-wide text-fg-subtle">Excerpt</div>
                            <p className="mt-1 border-l-2 border-line-strong pl-2 text-[13px] text-fg">{e.excerpt}</p>
                            <div className="mt-3 text-[11px] font-medium uppercase tracking-wide text-fg-subtle">Why it counts</div>
                            <p className="mt-1 text-xs text-fg-muted">{e.relevance}</p>
                          </div>
                          <div className="space-y-2 text-xs">
                            <div><span className="text-fg-subtle">Claim status </span><Badge>{e.status}</Badge></div>
                            <div className="break-all font-mono text-[11px] text-fg-muted">{e.url}</div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}</tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
