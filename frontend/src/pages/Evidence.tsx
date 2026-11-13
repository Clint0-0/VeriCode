import { useState } from 'react'
import { Badge, Card, Empty, ErrorBox, inputCls, Select, Spinner, useApi } from '../components/ui'

export default function Evidence({ param }: { param?: string }) {
  const { data, error, loading } = useApi<any[]>(param ? `/evidence?analysis_id=${param}` : '/evidence')
  const [q, setQ] = useState('')
  const [outcome, setOutcome] = useState('')
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const rows = (data ?? []).filter((e) => (!outcome || e.outcome === outcome) && (!q || `${e.claim} ${e.title} ${e.domain}`.toLowerCase().includes(q.toLowerCase())))
  return (
    <Card title={param ? `Evidence for analysis ${param}` : 'All retrieved evidence'} actions={<>
      <input aria-label="Filter" className={`${inputCls} w-56 py-1`} placeholder="Filter claim/domain…" value={q} onChange={(e) => setQ(e.target.value)} />
      <Select size="sm" aria-label="Outcome" className="w-36" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
        <option value="">all outcomes</option>{['support', 'contradict', 'neutral', 'irrelevant'].map((o) => <option key={o}>{o}</option>)}
      </Select>
    </>}>
      {!rows.length ? <Empty>No evidence yet. Run the Stale-Answer Detector.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-slate-500"><tr>{['Claim', 'Source', 'Domain / type', 'Retrieved', 'Published/updated', 'Excerpt', 'Explanation', 'Outcome', 'Claim status'].map((h) => <th key={h} className="px-2 py-1 font-medium">{h}</th>)}</tr></thead>
            <tbody>{rows.map((e) => (
              <tr key={e.id} className="border-t border-ink-700 align-top">
                <td className="max-w-xs px-2 py-2 text-slate-300">{e.claim}</td>
                <td className="max-w-[14rem] px-2 py-2">{e.url?.startsWith('installed://') ? <span className="font-mono text-emerald-200" title={e.url}>{e.title}</span> : <a className="text-sky-300 hover:underline" href={e.url} target="_blank" rel="noreferrer noopener">{e.title || e.url}</a>} <Badge tone={e.origin?.startsWith('fixture') ? 'amber' : 'blue'}>{e.origin}</Badge></td>
                <td className="px-2 py-2 text-slate-400">{e.domain}<br />{e.source_type} ({e.authority})</td>
                <td className="whitespace-nowrap px-2 py-2 text-slate-400">{e.retrieved_at}</td>
                <td className="whitespace-nowrap px-2 py-2 text-slate-400">{e.published_date ?? 'unknown'}</td>
                <td className="max-w-sm px-2 py-2 text-slate-300">{e.excerpt}</td>
                <td className="max-w-xs px-2 py-2 text-slate-500">{e.relevance}</td>
                <td className="px-2 py-2"><Badge tone={e.outcome === 'support' ? 'green' : e.outcome === 'contradict' ? 'red' : 'gray'}>{e.outcome}</Badge></td>
                <td className="px-2 py-2"><Badge>{e.status}</Badge></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
