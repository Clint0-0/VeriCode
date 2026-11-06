import { useEffect, useState } from 'react'
import { api, fmt } from '../api'
import { IntegrationStatus } from '../components/Integrations'
import { Badge, Button, Card, Empty, ErrorBox, Field, inputCls, Mono, Spinner, useApi } from '../components/ui'

export default function Settings(_: { param?: string }) {
  const s = useApi<any>('/settings')
  const rules = useApi<any[]>('/rules')
  const [form, setForm] = useState<any>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<unknown>(null)
  const [exported, setExported] = useState<string | null>(null)
  useEffect(() => { if (s.data) setForm(s.data) }, [s.data])
  if (s.loading || !form) return s.error ? <ErrorBox error={s.error} /> : <Spinner />
  const save = async () => {
    setErr(null); setMsg(null)
    try {
      const body: any = {}
      for (const k of ['llm_provider', 'planner_model', 'coder_model', 'max_repair_attempts', 'command_timeout', 'cache_ttl_seconds', 'tavily_timeout', 'tavily_max_retries', 'cost_input_per_mtok', 'cost_output_per_mtok', 'half_lives', 'sandbox_backend', 'use_llm_judge', 'tavily_search_depth', 'default_workspace']) body[k] = form[k]
      body.authority_rules = Object.fromEntries(Object.entries(form.authority_rules ?? {}).map(([k, v]: any) => [k, Array.isArray(v) ? v : String(v).split(',').map((x) => x.trim()).filter(Boolean)]))
      s.setData(await api('/settings', { method: 'PUT', body }))
      setMsg('Saved to the local database — settings persist across restarts.')
    } catch (e) { setErr(e) }
  }
  const num = (k: string) => <input aria-label={k} type="number" className={inputCls} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
  const txt = (k: string, ph = '') => <input aria-label={k} className={inputCls} value={form[k] ?? ''} placeholder={ph} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
  const delRule = async (id: string) => { await api(`/rules/${id}`, { method: 'DELETE' }); rules.reload() }
  const toggle = async (r: any) => { await api(`/rules/${r.id}`, { method: 'PUT', body: { active: r.active ? 0 : 1 } }); rules.reload() }
  const exportRules = async () => {
    try { const r = await api<any>('/rules/export', { body: { path: 'sample_project' } }); setExported(r.content) } catch (e) { setErr(e) }
  }
  return (
    <div className="space-y-5">
      <Card title="Integrations & credentials">
        <IntegrationStatus i={form.integrations} />
        <p className="mt-3 text-xs text-slate-500">API keys are read only from the backend environment / .env (never stored in the database, never sent to the browser). Only their presence is shown:</p>
        <div className="mt-2 flex flex-wrap gap-3 text-sm">
          <span>TAVILY_API_KEY <Badge tone={form.tavily_configured ? 'green' : 'amber'}>{form.tavily_configured ? 'set' : 'missing'}</Badge></span>
          <span>ANTHROPIC_API_KEY <Badge tone={form.anthropic_configured ? 'green' : 'gray'}>{form.anthropic_configured ? 'set' : 'missing'}</Badge></span>
          <span>OPENAI_API_KEY <Badge tone={form.openai_configured ? 'green' : 'gray'}>{form.openai_configured ? 'set' : 'missing'}</Badge></span>
        </div>
      </Card>
      <Card title="Runtime configuration" actions={<Button onClick={save}>Save</Button>}>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Model provider">
            <select aria-label="Model provider" className={inputCls} value={form.llm_provider} onChange={(e) => setForm({ ...form, llm_provider: e.target.value })}>
              {['anthropic', 'openai', 'mock'].map((p) => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Coder model id">{txt('coder_model', 'set VERICODE_CODER_MODEL')}</Field>
          <Field label="Planner model id">{txt('planner_model', 'defaults to coder model')}</Field>
          <Field label="Search provider"><input className={inputCls} value="tavily" disabled /></Field>
          <Field label="Workspace root"><input className={inputCls} value={form.workspaces_root} disabled /></Field>
          <Field label="Repair attempt limit">{num('max_repair_attempts')}</Field>
          <Field label="Command timeout (s)">{num('command_timeout')}</Field>
          <Field label="Cache TTL (s)">{num('cache_ttl_seconds')}</Field>
          <Field label="Tavily timeout (s)">{num('tavily_timeout')}</Field>
          <Field label="Tavily max retries">{num('tavily_max_retries')}</Field>
          <Field label="Cost $/Mtok input">{num('cost_input_per_mtok')}</Field>
          <Field label="Cost $/Mtok output">{num('cost_output_per_mtok')}</Field>
          <Field label="Execution sandbox" hint="auto = Docker when the daemon is reachable">
            <select aria-label="Execution sandbox" className={inputCls} value={form.sandbox_backend} onChange={(e) => setForm({ ...form, sandbox_backend: e.target.value })}>
              {['auto', 'docker', 'process'].map((p) => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Tavily search depth">
            <select aria-label="Tavily search depth" className={inputCls} value={form.tavily_search_depth} onChange={(e) => setForm({ ...form, tavily_search_depth: e.target.value })}>
              {['basic', 'advanced', 'fast', 'ultra-fast'].map((p) => <option key={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Default workspace">{txt('default_workspace')}</Field>
          <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={!!form.use_llm_judge} onChange={(e) => setForm({ ...form, use_llm_judge: e.target.checked })} /> LLM evidence judge for claims without concrete values (real provider only)</label>
        </div>
        <div className="mt-4 text-xs font-medium text-slate-400">Freshness half-lives (days) — Freshness = 100 × 2^(−age / half-life)</div>
        <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-6">
          {Object.entries(form.half_lives).map(([k, v]: any) => (
            <Field key={k} label={k}><input aria-label={`half-life ${k}`} type="number" className={inputCls} value={v} onChange={(e) => setForm({ ...form, half_lives: { ...form.half_lives, [k]: +e.target.value } })} /></Field>
          ))}
        </div>
        <div className="mt-4 text-xs font-medium text-slate-400">Source authority — primary domains per claim category (comma separated; ".gov" matches any .gov domain)</div>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {Object.entries(form.authority_rules ?? {}).map(([k, v]: any) => (
            <Field key={k} label={k}><input aria-label={`authority ${k}`} className={inputCls} value={Array.isArray(v) ? v.join(', ') : v}
              onChange={(e) => setForm({ ...form, authority_rules: { ...form.authority_rules, [k]: e.target.value } })} /></Field>
          ))}
        </div>
        <div className="mt-3"><ErrorBox error={err} />{msg && <div className="text-xs text-emerald-300">{msg}</div>}</div>
      </Card>
      <Card title="Project memory — verified compatibility rules" actions={<Button variant="ghost" onClick={exportRules}>Export to sample_project/.agent-rules.md</Button>}>
        {rules.loading ? <Spinner /> : !rules.data?.length ? <Empty>No verified rules yet. They are created from pre-flight findings verified against installed source.</Empty> : (
          <table className="w-full text-xs">
            <thead className="text-left text-slate-500"><tr><th className="py-1">Package</th><th>Version</th><th>API</th><th>Correction</th><th>Evidence</th><th>Last verified</th><th>Expires</th><th></th></tr></thead>
            <tbody>{rules.data.map((r) => (
              <tr key={r.id} className={`border-t border-ink-700 ${r.active ? '' : 'opacity-50'}`}>
                <td className="py-1">{r.package}</td><td className="font-mono">{r.version_spec}</td><td className="font-mono">{r.api}</td>
                <td className="max-w-xs text-slate-300">{r.correction}</td><td className="max-w-[12rem] text-slate-500">{r.evidence_source}</td>
                <td className="whitespace-nowrap">{fmt.time(r.last_verified)}</td><td className="whitespace-nowrap">{fmt.time(r.expires_at)}</td>
                <td className="whitespace-nowrap space-x-1"><Button variant="ghost" onClick={() => toggle(r)}>{r.active ? 'Disable' : 'Enable'}</Button><Button variant="danger" onClick={() => delRule(r.id)}>Delete</Button></td>
              </tr>
            ))}</tbody>
          </table>
        )}
        {exported && <Mono className="mt-3">{exported}</Mono>}
      </Card>
    </div>
  )
}
