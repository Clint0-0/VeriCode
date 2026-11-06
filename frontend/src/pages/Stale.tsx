import { useEffect, useState } from 'react'
import { api, fmt } from '../api'
import { KV } from '../components/Findings'
import { Badge, Button, Card, Empty, ErrorBox, Expand, Field, inputCls, Notice, Spinner, Stat } from '../components/ui'

export function ClaimCard({ c }: { c: any }) {
  const cl = c.claim
  return (
    <Expand head={<>
      <Badge>{c.status}</Badge>
      <span className="font-mono text-[11px] text-slate-500">{cl.claim_id}</span>
      <span className="min-w-0 flex-1 truncate text-slate-200">{cl.claim}</span>
      <span className="text-xs text-slate-500">{cl.category} · {cl.volatility}</span>
    </>}>
      <p className="text-slate-200">“{cl.claim}”</p>
      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <KV k="Category / volatility" v={`${cl.category} / ${cl.volatility}`} />
        <KV k="Evidence freshness" v={c.freshness == null ? 'unknown' : `${c.freshness} / 100`} />
        <KV k="Verification confidence (index)" v={c.confidence == null ? 'n/a' : `${c.confidence} / 100`} />
        <KV k="Search" v={c.search_status ?? '—'} />
      </div>
      <p className="mt-2 text-xs text-slate-500">Freshness: {c.freshness_note}</p>
      <p className="mt-3 text-slate-300">{c.explanation}</p>
      {c.correction && <div className="mt-2 rounded border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-emerald-200">Evidence-based replacement value: <b>{c.correction}</b></div>}
      {c.confidence_breakdown && Object.keys(c.confidence_breakdown).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-400">
          {Object.entries(c.confidence_breakdown).map(([k, v]: any) => <span key={k} className="rounded bg-ink-800 px-1.5 py-0.5 font-mono">{k}: {String(v)}</span>)}
        </div>
      )}
      <div className="mt-3 space-y-2">
        {c.evidence.length === 0 && <div className="text-xs text-slate-500">No sources retrieved.</div>}
        {c.evidence.map((e: any, i: number) => (
          <div key={i} className="rounded border border-ink-700 p-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={e.outcome === 'support' ? 'green' : e.outcome === 'contradict' ? 'red' : 'gray'}>{e.outcome}</Badge>
              <Badge tone={e.origin === 'fixture' ? 'amber' : 'blue'}>{e.origin}</Badge>
              <a className="text-sky-300 hover:underline" href={e.url} target="_blank" rel="noreferrer noopener">{e.title || e.url}</a>
              <span className="text-slate-500">{e.domain} · {e.source_type} · authority {e.authority}</span>
            </div>
            <div className="mt-1 text-slate-500">published/updated: {e.published_date ?? 'unknown'} · retrieved: {e.retrieved_at}{e.freshness != null ? ` · freshness ${e.freshness}` : ''}</div>
            <p className="mt-1 text-slate-300">{e.excerpt}</p>
            <p className="mt-1 text-slate-500">{e.relevance_explanation}</p>
          </div>
        ))}
      </div>
    </Expand>
  )
}

export default function Stale({ param }: { param?: string }) {
  const [answer, setAnswer] = useState('')
  const [question, setQuestion] = useState('')
  const [urls, setUrls] = useState('')
  const [domains, setDomains] = useState('')
  const [mode, setMode] = useState<'live' | 'fixture'>('live')
  const [res, setRes] = useState<any>(null)
  const [corr, setCorr] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (param) api(`/stale/${param}`).then((r: any) => { setRes(r); setAnswer(r.answer); setCorr(r.corrected) }).catch(setErr)
  }, [param])

  const loadDemo = async () => {
    const d = await api<any>('/stale/demo')
    setAnswer(d.answer)
  }
  const analyze = async () => {
    setBusy(true); setErr(null); setRes(null); setCorr(null)
    try {
      const split = (s: string) => s.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean)
      setRes(await api('/stale/analyze', { body: { answer, question: question || null, urls: split(urls), preferred_domains: split(domains), mode }, timeoutMs: 300_000 }))
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const correct = async () => {
    try { setCorr(await api(`/stale/${res.id}/correct`, { method: 'POST' })) } catch (e) { setErr(e) }
  }
  const s = res?.summary
  return (
    <div className="space-y-5">
      <Card title="Analyze an LLM answer" actions={<Button variant="ghost" onClick={loadDemo}>Load Demo 2 answer</Button>}>
        <Field label="LLM-generated answer"><textarea aria-label="LLM answer" className={`${inputCls} h-32`} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Paste any LLM response…" /></Field>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <Field label="Original question (optional)"><input className={inputCls} value={question} onChange={(e) => setQuestion(e.target.value)} /></Field>
          <Field label="Source URLs (optional)" hint="Fetched with SSRF protection"><input className={inputCls} value={urls} onChange={(e) => setUrls(e.target.value)} /></Field>
          <Field label="Preferred domains (optional)"><input className={inputCls} value={domains} onChange={(e) => setDomains(e.target.value)} placeholder="python.org, irs.gov" /></Field>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <div className="flex gap-4 text-sm text-slate-400">
            <label className="flex items-center gap-1.5"><input type="radio" checked={mode === 'live'} onChange={() => setMode('live')} /> Live (Tavily)</label>
            <label className="flex items-center gap-1.5"><input type="radio" checked={mode === 'fixture'} onChange={() => setMode('fixture')} /> Offline fixture (labelled, reproducible)</label>
          </div>
          <Button onClick={analyze} disabled={busy || answer.length < 10}>{busy ? 'Verifying…' : 'Extract & verify claims'}</Button>
        </div>
        <div className="mt-3"><ErrorBox error={err} /></div>
      </Card>
      {busy && <Spinner label="Extracting claims and retrieving evidence…" />}
      {res && (
        <>
          {s.evidence_mode === 'fixture' && <Notice>Evidence below comes from the <b>offline fixture</b> (demos/stale_fixtures), not live retrieval.</Notice>}
          {s.evidence_mode === 'live_tavily' && !s.tavily_configured && <Notice>TAVILY_API_KEY is not set — live verification was not performed, so volatile claims are reported as UNVERIFIED.</Notice>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Claims" value={s.total_claims} sub={`${s.requiring_verification} time-sensitive`} />
            <Stat label="Supported" value={s.by_status.CURRENT_SUPPORTED ?? 0} tone="green" />
            <Stat label="Contradicted" value={s.by_status.CONTRADICTED ?? 0} tone="red" />
            <Stat label="Stale / conflicting" value={(s.by_status.POTENTIALLY_STALE ?? 0) + (s.by_status.CONFLICTING_EVIDENCE ?? 0)} tone="amber" />
            <Stat label="Unverified" value={s.by_status.UNVERIFIED ?? 0} sub={`${s.search_calls} searches`} tone="amber" />
          </div>
          <Card title="Claim-by-claim report" actions={<>
            <a className="text-xs text-sky-300 hover:underline" href={`#evidence/${res.id}`}>Evidence Explorer</a>
            <Button onClick={correct}>Generate corrected answer</Button>
          </>}>
            <div className="space-y-2">{res.claims.map((c: any) => <ClaimCard key={c.claim.claim_id} c={c} />)}</div>
            {s.url_errors?.length > 0 && <div className="mt-3 text-xs text-amber-300">URL errors: {s.url_errors.map((u: any) => `${u.url}: ${u.error}`).join('; ')}</div>}
          </Card>
          {corr && (
            <Card title="Evidence-backed corrected answer">
              <div className="grid gap-4 md:grid-cols-2">
                <div><div className="mb-1 text-xs text-slate-500">Original</div><p className="rounded border border-ink-700 p-3 text-sm text-slate-300">{corr.original}</p></div>
                <div><div className="mb-1 text-xs text-slate-500">Corrected</div><p className="rounded border border-emerald-500/30 p-3 text-sm text-slate-100">{corr.corrected}</p></div>
              </div>
              <ul className="mt-3 space-y-1 text-xs text-slate-400">
                {corr.changes.map((ch: any, i: number) => <li key={i}><span className="font-mono">{ch.claim_id}</span>: {ch.corrected ? <>“{ch.original}” → “{ch.corrected}” [{ch.citation}]</> : <>marked {ch.marked}</>}</li>)}
                {corr.citations.map((ci: any) => <li key={ci.n}>[{ci.n}] <a className="text-sky-300 hover:underline" href={ci.url} target="_blank" rel="noreferrer noopener">{ci.title}</a> <Badge tone={ci.origin === 'fixture' ? 'amber' : 'blue'}>{ci.origin}</Badge></li>)}
              </ul>
              <p className="mt-2 text-xs text-slate-500">{corr.policy}</p>
            </Card>
          )}
        </>
      )}
      {!res && !busy && <PastAnalyses />}
    </div>
  )
}

function PastAnalyses() {
  const [list, setList] = useState<any[] | null>(null)
  useEffect(() => { api<any[]>('/stale').then(setList).catch(() => setList([])) }, [])
  if (!list) return null
  return (
    <Card title="Previous analyses">
      {!list.length ? <Empty>No analyses yet.</Empty> : (
        <ul className="space-y-1 text-sm">{list.map((a) => (
          <li key={a.id} className="flex items-center gap-2"><a className="font-mono text-xs text-sky-300 hover:underline" href={`#stale/${a.id}`}>{a.id}</a><Badge tone={a.evidence_mode === 'fixture' ? 'amber' : 'blue'}>{a.evidence_mode}</Badge><span className="truncate text-slate-400">{a.answer}</span><span className="ml-auto text-xs text-slate-500">{fmt.time(a.created_at)}</span></li>
        ))}</ul>
      )}
    </Card>
  )
}
