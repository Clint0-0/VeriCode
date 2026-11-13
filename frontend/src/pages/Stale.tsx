import { useEffect, useState } from 'react'
import { api, fmt } from '../api'
import { KV } from '../components/Findings'
import { Badge, Button, Card, Empty, ErrorBox, Expand, Field, inputCls, Notice, Select, Spinner, Stat } from '../components/ui'

const STATUS_BG: Record<string, string> = {
  CURRENT_SUPPORTED: 'bg-emerald-500/15 decoration-emerald-400', CONTRADICTED: 'bg-rose-500/20 decoration-rose-400',
  POTENTIALLY_STALE: 'bg-amber-500/15 decoration-amber-400', CONFLICTING_EVIDENCE: 'bg-amber-500/15 decoration-amber-400',
  UNVERIFIED: 'bg-slate-500/15 decoration-slate-400', NOT_APPLICABLE: '',
}

/** Original answer with each claim's source span highlighted by status (traceability). */
export function HighlightedAnswer({ answer, claims, onPick }: { answer: string; claims: any[]; onPick: (id: string) => void }) {
  const spans = new Map<string, any[]>()
  for (const c of claims) {
    const sp = c.claim.span
    if (!sp || sp.length !== 2) continue
    const k = `${sp[0]}:${sp[1]}`
    spans.set(k, [...(spans.get(k) ?? []), c])
  }
  const ordered = [...spans.entries()].map(([k, cs]) => ({ s: +k.split(':')[0], e: +k.split(':')[1], cs })).sort((a, b) => a.s - b.s)
  const out: any[] = []
  let last = 0
  const rank = ['CONTRADICTED', 'CONFLICTING_EVIDENCE', 'POTENTIALLY_STALE', 'UNVERIFIED', 'CURRENT_SUPPORTED', 'NOT_APPLICABLE']
  for (const seg of ordered) {
    if (seg.s < last) continue
    out.push(answer.slice(last, seg.s))
    const worst = seg.cs.map((c: any) => c.status).sort((a: string, b: string) => rank.indexOf(a) - rank.indexOf(b))[0]
    out.push(
      <button key={seg.s} type="button" onClick={() => onPick(seg.cs[0].claim.claim_id)} title={seg.cs.map((c: any) => `${c.claim.claim_id}: ${c.status}`).join('\n')}
        className={`rounded px-0.5 text-left underline decoration-dotted underline-offset-4 ${STATUS_BG[worst] ?? ''}`}>
        {answer.slice(seg.s, seg.e)}
        <sup className="ml-0.5 font-mono text-[10px] text-slate-400">{seg.cs.map((c: any) => c.claim.claim_id.replace('claim_0', '')).join(',')}</sup>
      </button>,
    )
    last = seg.e
  }
  out.push(answer.slice(last))
  return <p className="whitespace-pre-wrap text-sm leading-7 text-slate-300">{out}</p>
}

function EvidenceItem({ e }: { e: any }) {
  return (
    <div className="rounded border border-ink-700 p-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={e.outcome === 'support' ? 'green' : e.outcome === 'contradict' ? 'red' : 'gray'}>{e.outcome}</Badge>
        {e.method && e.method !== 'none' && <Badge tone="blue">{e.method}</Badge>}
        <Badge tone={e.origin?.startsWith('fixture') ? 'amber' : 'blue'}>{e.origin}</Badge>
        {e.url?.startsWith('installed://') ? <span className="font-mono text-emerald-200" title={e.url}>{e.title}</span>
          : <a className="text-sky-300 hover:underline" href={e.url} target="_blank" rel="noreferrer noopener">{e.title || e.url}</a>}
        <span className="text-slate-500">{e.domain} · {e.source_type} · authority {e.authority}</span>
        {e.authority_tier && <Badge tone={e.authority_tier === 'primary' ? 'green' : e.authority_tier === 'suspicious' ? 'red' : e.authority_tier === 'secondary' ? 'amber' : 'gray'}>{e.authority_tier}</Badge>}
      </div>
      {e.authority_explanation && <div className="mt-1 text-[11px] text-slate-500">authority: {e.authority_explanation}</div>}
      <div className="mt-1 text-slate-500">published/updated: <b className="text-slate-400">{e.published_date ?? 'unknown'}</b> · retrieved: {e.retrieved_at}{e.freshness != null ? ` · freshness ${e.freshness}` : ' · freshness unknown'}</div>
      <p className="mt-1 text-slate-300">“{e.excerpt}”</p>
      <p className="mt-1 text-slate-500">{e.relevance_explanation}</p>
    </div>
  )
}

export function ClaimCard({ c, corrected, open }: { c: any; corrected?: any; open?: boolean }) {
  const cl = c.claim
  const sup = c.evidence.filter((e: any) => e.outcome === 'support')
  const con = c.evidence.filter((e: any) => e.outcome === 'contradict')
  const other = c.evidence.filter((e: any) => e.outcome !== 'support' && e.outcome !== 'contradict')
  return (
    <div id={`claim-${cl.claim_id}`}>
      <Expand defaultOpen={open} head={<>
        <Badge>{c.status}</Badge>
        <span className="font-mono text-[11px] text-slate-500">{cl.claim_id}</span>
        <span className="min-w-0 flex-1 truncate text-slate-200">{cl.claim}</span>
        <span className="hidden text-xs text-slate-500 sm:inline">{cl.category} · {cl.volatility}</span>
      </>}>
        <p className="text-slate-200">“{cl.claim}”</p>
        {cl.source_text && cl.source_text !== cl.claim && <p className="mt-1 text-xs text-slate-500">from: “{cl.source_text}” (chars {cl.span?.[0]}–{cl.span?.[1]}){cl.derived ? ' · subject carried over from the same sentence' : ''}{cl.relation && cl.relation !== 'main' ? ` · ${cl.relation}` : ''}</p>}
        {(cl.hedged || cl.features?.qualifiers?.length > 0 || cl.features?.comparison?.length > 0 || cl.features?.temporal_markers?.length > 0 || cl.notes?.length > 0) && (
          <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
            {cl.hedged && <Badge tone="amber">hedged: {cl.features?.hedges?.join(', ')}</Badge>}
            {cl.features?.qualifiers?.map((q: string) => <Badge key={q} tone="gray">qualifier: {q}</Badge>)}
            {cl.features?.comparison?.map((q: string) => <Badge key={q} tone="gray">comparison: {q}</Badge>)}
            {cl.features?.temporal_markers?.map((q: string) => <Badge key={q} tone="blue">{q}</Badge>)}
            {cl.notes?.map((n: string) => <span key={n} className="text-slate-500">{n}</span>)}
          </div>
        )}
        <div className="mt-3 grid gap-3 sm:grid-cols-2 md:grid-cols-4">
          <KV k="Category / volatility" v={`${cl.category} / ${cl.volatility}`} />
          <KV k="Temporal sensitivity" v={cl.temporal_sensitivity ?? '—'} />
          <KV k="Verifiability" v={`${cl.verifiability ?? '—'}${cl.negated ? ' · negated' : ''}${cl.conditional ? ' · conditional' : ''}`} />
          <KV k="Required evidence" v={cl.evidence_type ?? '—'} />
          <KV k="Evidence freshness" v={c.freshness == null ? 'unknown' : `${c.freshness} / 100`} />
          <KV k="Verification confidence (index)" v={c.confidence == null ? 'n/a' : `${c.confidence} / 100`} />
          <KV k="Search" v={c.search_status ?? '—'} />
          <KV k="Extraction" v={cl.extraction ?? 'deterministic'} />
        </div>
        <p className="mt-2 text-xs text-slate-500">Freshness: {c.freshness_note}</p>
        <p className="mt-3 text-slate-300">{c.explanation}</p>
        {c.missing_evidence && <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200"><b>Missing evidence:</b> {c.missing_evidence}</div>}
        {corrected?.corrected && <div className="mt-2 rounded border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-emerald-200"><b>Corrected claim:</b> “{corrected.corrected}” [{corrected.citation}]</div>}
        {!corrected && c.correction && <div className="mt-2 rounded border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-emerald-200">Evidence-based replacement value: <b>{c.correction}</b></div>}
        {c.confidence_breakdown && Object.keys(c.confidence_breakdown).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-400">
            {Object.entries(c.confidence_breakdown).map(([k, v]: any) => <span key={k} className="rounded bg-ink-800 px-1.5 py-0.5 font-mono">{k}: {String(v)}</span>)}
          </div>
        )}
        {c.judge && <div className="mt-2 text-xs text-slate-400">LLM evidence judge: <Badge tone={c.judge.verdict === 'supports' ? 'green' : c.judge.verdict === 'contradicts' ? 'red' : 'gray'}>{c.judge.verdict}</Badge>{c.judge.discarded ? ' (discarded: ' + c.judge.reason + ')' : ''}{c.judge.missing_context ? ` · missing: ${c.judge.missing_context}` : ''}</div>}
        {c.conflict && (
          <div className="mt-3 rounded border border-amber-500/30 p-3">
            <div className="text-xs font-medium text-amber-200">Conflicting evidence — {c.conflict.reason}</div>
            <div className="mt-2 grid gap-3 md:grid-cols-2">
              {(['supporting', 'contradicting'] as const).map((side) => (
                <div key={side}>
                  <div className={`mb-1 text-[11px] uppercase tracking-wide ${side === 'supporting' ? 'text-emerald-300' : 'text-rose-300'}`}>{side}</div>
                  {c.conflict[side].map((s: any) => (
                    <div key={s.url} className="mb-2 rounded border border-ink-700 p-2 text-xs">
                      <a className="text-sky-300 hover:underline" href={s.url} target="_blank" rel="noreferrer noopener">{s.domain}</a>
                      <div className="text-slate-500">date {s.published_date ?? 'unknown'} · authority {s.authority} ({s.source_type})</div>
                      <p className="mt-1 text-slate-300">“{s.excerpt}”</p>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}
        {!c.conflict && (sup.length > 0 || con.length > 0) && (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div><div className="mb-1 text-[11px] uppercase tracking-wide text-emerald-300">Supporting evidence ({sup.length})</div><div className="space-y-2">{sup.map((e: any, i: number) => <EvidenceItem key={i} e={e} />)}</div></div>
            <div><div className="mb-1 text-[11px] uppercase tracking-wide text-rose-300">Contradicting evidence ({con.length})</div><div className="space-y-2">{con.map((e: any, i: number) => <EvidenceItem key={i} e={e} />)}</div></div>
          </div>
        )}
        {other.length > 0 && (
          <details className="mt-3 text-xs text-slate-400"><summary className="cursor-pointer">Other retrieved sources ({other.length}) — related but not decisive</summary>
            <div className="mt-2 space-y-2">{other.map((e: any, i: number) => <EvidenceItem key={i} e={e} />)}</div>
          </details>
        )}
        {c.evidence.length === 0 && <div className="mt-3 text-xs text-slate-500">No sources retrieved.</div>}
      </Expand>
    </div>
  )
}

export default function Stale({ param }: { param?: string }) {
  const [answer, setAnswer] = useState('')
  const [question, setQuestion] = useState('')
  const [urls, setUrls] = useState('')
  const [domains, setDomains] = useState('')
  const [mode, setMode] = useState<'live' | 'fixture'>('live')
  const [llmExtract, setLlmExtract] = useState(false)
  const [workspace, setWorkspace] = useState('')
  const [workspaces, setWorkspaces] = useState<any[]>([])
  useEffect(() => { api<any[]>('/workspaces').then(setWorkspaces).catch(() => setWorkspaces([])) }, [])
  const [res, setRes] = useState<any>(null)
  const [corr, setCorr] = useState<any>(null)
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [picked, setPicked] = useState<string | null>(null)

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
      setRes(await api('/stale/analyze', { body: { answer, question: question || null, urls: split(urls), preferred_domains: split(domains), mode, llm_extraction: llmExtract, workspace: workspace || null }, timeoutMs: 300_000 }))
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const correct = async () => {
    try { setCorr(await api(`/stale/${res.id}/correct`, { method: 'POST' })) } catch (e) { setErr(e) }
  }
  const pick = (id: string) => {
    setPicked(id)
    setTimeout(() => document.getElementById(`claim-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50)
  }
  const s = res?.summary
  const corrByClaim = Object.fromEntries((corr?.changes ?? []).filter((c: any) => c.corrected).map((c: any) => [c.claim_id, c]))
  return (
    <div className="space-y-5">
      <Card title="Analyze an LLM answer" actions={<Button variant="ghost" onClick={loadDemo}>Load Demo 2 answer</Button>}>
        <Field label="LLM-generated answer"><textarea aria-label="LLM answer" className={`${inputCls} h-32`} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Paste any LLM response…" /></Field>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <Field label="Original question (optional)"><input className={inputCls} value={question} onChange={(e) => setQuestion(e.target.value)} /></Field>
          <Field label="Source URLs (optional)" hint="Fetched with SSRF protection"><input className={inputCls} value={urls} onChange={(e) => setUrls(e.target.value)} /></Field>
          <Field label="Preferred domains (optional)"><input className={inputCls} value={domains} onChange={(e) => setDomains(e.target.value)} placeholder="python.org, irs.gov" /></Field>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-4 text-sm text-slate-400">
            <label className="flex items-center gap-1.5"><input type="radio" checked={mode === 'live'} onChange={() => setMode('live')} /> Live (Tavily)</label>
            <label className="flex items-center gap-1.5"><input type="radio" checked={mode === 'fixture'} onChange={() => setMode('fixture')} /> Offline fixture (labelled, reproducible)</label>
            <label className="flex items-center gap-1.5" title="Uses the planner model; requires a real LLM provider"><input type="checkbox" checked={llmExtract} onChange={(e) => setLlmExtract(e.target.checked)} /> LLM claim extraction</label>
            <label className="flex items-center gap-1.5" title="Check claims about libraries against the packages installed in this workspace (combined workflow)">Check API claims against installed packages of
              <Select size="sm" aria-label="Installed packages workspace" className="inline-block w-40" value={workspace} onChange={(e) => setWorkspace(e.target.value)}>
                <option value="">— none —</option>{workspaces.map((w) => <option key={w.name} value={w.name}>{w.name}</option>)}
              </Select>
            </label>
          </div>
          <Button onClick={analyze} disabled={busy || answer.length < 10}>{busy ? 'Verifying…' : 'Extract & verify claims'}</Button>
        </div>
        <div className="mt-3"><ErrorBox error={err} /></div>
      </Card>
      {busy && <Spinner label="Extracting claims and retrieving evidence…" />}
      {res && (
        <>
          {s.workspace && <Notice tone="blue">API claims were also checked against the packages installed in <b>{s.workspace}</b> (evidence labelled <span className="font-mono">installed_source</span>; it describes the installed version, not necessarily the latest release).</Notice>}
          {s.evidence_mode === 'fixture' && <Notice>Evidence below comes from the <b>offline fixture</b> (demos/stale_fixtures), not live retrieval.</Notice>}
          {s.evidence_mode === 'live_tavily' && !s.tavily_configured && <Notice>TAVILY_API_KEY is not set — live verification was not performed, so volatile claims are reported as UNVERIFIED.</Notice>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Claims" value={s.total_claims} sub={`${s.requiring_verification} time-sensitive`} />
            <Stat label="Supported" value={s.by_status.CURRENT_SUPPORTED ?? 0} tone="green" />
            <Stat label="Contradicted" value={s.by_status.CONTRADICTED ?? 0} tone="red" />
            <Stat label="Stale / conflicting" value={(s.by_status.POTENTIALLY_STALE ?? 0) + (s.by_status.CONFLICTING_EVIDENCE ?? 0)} tone="amber" />
            <Stat label="Unverified" value={s.by_status.UNVERIFIED ?? 0} sub={`${s.search_calls} searches${s.search_credits ? ` · ${s.search_credits} credits` : ''}`} tone="amber" />
          </div>
          <div className="text-xs text-slate-500">Extraction: {s.extraction ?? 'deterministic'} · LLM evidence judge: {s.llm_judge ?? 'n/a'}{s.llm_tokens?.calls ? ` · ${fmt.n(s.llm_tokens.total)} LLM tokens (${s.llm_tokens.measurement})` : ''}</div>
          <Card title="Original answer — click a highlighted claim">
            <HighlightedAnswer answer={res.answer} claims={res.claims} onPick={pick} />
          </Card>
          <Card title="Claim-by-claim report" actions={<>
            <a className="text-xs text-sky-300 hover:underline" href={`#evidence/${res.id}`}>Evidence Explorer</a>
            <Button onClick={correct}>Generate corrected answer</Button>
          </>}>
            <div className="space-y-2">{res.claims.map((c: any) => <ClaimCard key={`${c.claim.claim_id}-${picked === c.claim.claim_id}`} c={c} corrected={corrByClaim[c.claim.claim_id]} open={picked === c.claim.claim_id} />)}</div>
            {s.url_errors?.length > 0 && <div className="mt-3 text-xs text-amber-300">URL errors: {s.url_errors.map((u: any) => `${u.url}: ${u.error}`).join('; ')}</div>}
          </Card>
          {corr && (
            <Card title="Evidence-backed corrected answer">
              <div className="grid gap-4 md:grid-cols-2">
                <div><div className="mb-1 text-xs text-slate-500">Original (preserved)</div><p className="whitespace-pre-wrap rounded border border-ink-700 p-3 text-sm text-slate-300">{corr.original}</p></div>
                <div><div className="mb-1 text-xs text-slate-500">Corrected</div><p className="whitespace-pre-wrap rounded border border-emerald-500/30 p-3 text-sm text-slate-100">{corr.corrected}</p></div>
              </div>
              <ul className="mt-3 space-y-1 text-xs text-slate-400">
                {corr.changes.map((ch: any, i: number) => <li key={i}><span className="font-mono">{ch.claim_id}</span>: {ch.corrected ? <>“{ch.original}” → “{ch.corrected}” [{ch.citation}]</> : <>kept and marked {ch.marked}{ch.missing_evidence ? ` — ${ch.missing_evidence}` : ''}</>}</li>)}
                {corr.citations.map((ci: any) => <li key={ci.n}>[{ci.n}] <a className="text-sky-300 hover:underline" href={ci.url} target="_blank" rel="noreferrer noopener">{ci.title}</a> {ci.published_date && <span className="text-slate-500">({ci.published_date})</span>} <Badge tone={ci.origin?.startsWith('fixture') ? 'amber' : 'blue'}>{ci.origin}</Badge></li>)}
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
          <li key={a.id} className="flex items-center gap-2"><a className="font-mono text-xs text-sky-300 hover:underline" href={`#stale/${a.id}`}>{a.id}</a><Badge tone={a.evidence_mode?.startsWith('fixture') ? 'amber' : 'blue'}>{a.evidence_mode}</Badge><span className="truncate text-slate-400">{a.answer}</span><span className="ml-auto shrink-0 text-xs text-slate-500">{fmt.time(a.created_at)}</span></li>
        ))}</ul>
      )}
    </Card>
  )
}
