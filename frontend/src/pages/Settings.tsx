import { useEffect, useState, type ReactNode } from 'react'
import { Save } from 'lucide-react'
import { api, fmt } from '../api'
import { IntegrationStatus } from '../components/Integrations'
import { Badge, Button, Card, Checkbox, DataTable, Empty, ErrorBox, Field, inputCls, Mono, Select, Spinner, useApi } from '../components/ui'

const SAVED = ['llm_provider', 'planner_model', 'coder_model', 'max_repair_attempts', 'command_timeout', 'cache_ttl_seconds', 'tavily_timeout',
  'tavily_max_retries', 'cost_input_per_mtok', 'cost_output_per_mtok', 'half_lives', 'sandbox_backend', 'use_llm_judge', 'tavily_search_depth',
  'default_workspace', 'llm_stream', 'adaptive_execution']

/** Settings group: title + explanation on the left, controls on the right (stacks on small screens). */
function Group({ id, title, description, children }: { id: string; title: string; description: ReactNode; children: ReactNode }) {
  return (
    <section id={`settings-${id}`} className="grid gap-4 border-b border-line px-4 py-5 last:border-b-0 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div>
        <h2 className="text-[13px] font-semibold text-fg">{title}</h2>
        <p className="mt-1 text-xs leading-relaxed text-fg-muted">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}

function KeyState({ name, set, required }: { name: string; set: boolean; required?: boolean }) {
  return <span className="inline-flex items-center gap-2 text-xs"><span className="font-mono text-fg">{name}</span><Badge tone={set ? 'green' : required ? 'amber' : 'gray'}>{set ? 'set' : 'missing'}</Badge></span>
}

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
      for (const k of SAVED) if (form[k] !== undefined) body[k] = form[k]
      try { body.model_prices = typeof form.model_prices === 'string' ? JSON.parse(form.model_prices || '{}') : form.model_prices } catch { throw new Error('Model prices must be JSON: {"model-id": {"input": 3, "output": 15}}') }
      body.authority_rules = Object.fromEntries(Object.entries(form.authority_rules ?? {}).map(([k, v]: any) => [k, Array.isArray(v) ? v : String(v).split(',').map((x) => x.trim()).filter(Boolean)]))
      s.setData(await api('/settings', { method: 'PUT', body }))
      setMsg('Saved to the local database — settings persist across restarts.')
    } catch (e) { setErr(e) }
  }
  const set = (k: string, v: any) => setForm({ ...form, [k]: v })
  const num = (k: string) => <input aria-label={k} type="number" className={inputCls} value={form[k]} onChange={(e) => set(k, e.target.value)} />
  const txt = (k: string, ph = '') => <input aria-label={k} className={`${inputCls} font-mono`} value={form[k] ?? ''} placeholder={ph} onChange={(e) => set(k, e.target.value)} />
  const delRule = async (id: string) => { await api(`/rules/${id}`, { method: 'DELETE' }); rules.reload() }
  const toggle = async (r: any) => { await api(`/rules/${r.id}`, { method: 'PUT', body: { active: r.active ? 0 : 1 } }); rules.reload() }
  const exportRules = async () => {
    try { const r = await api<any>('/rules/export', { body: { path: 'sample_project' } }); setExported(r.content) } catch (e) { setErr(e) }
  }
  const saveBar = (
    <Button onClick={save} icon={<Save aria-hidden className="h-3.5 w-3.5" />}>Save</Button>
  )
  return (
    <div className="space-y-5">
      <Card title="Configuration" description="API keys are read only from the backend environment / .env — never stored in the database or sent to the browser." actions={saveBar} flush>
        <Group id="provider" title="LLM provider" description="Which provider runs the planner and coder. Credentials are only shown as present or missing.">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Model provider">
              <Select aria-label="Model provider" className="w-full" value={form.llm_provider} onChange={(e) => set('llm_provider', e.target.value)}>
                {['anthropic', 'openai', 'mock'].map((p) => <option key={p}>{p}</option>)}
              </Select>
            </Field>
            <Field label="OpenAI-compatible endpoint"><input className={`${inputCls} font-mono`} value={form.openai_base_url ?? ''} disabled /></Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
            <KeyState name="OPENAI_API_KEY" set={form.openai_configured} />
            <KeyState name="ANTHROPIC_API_KEY" set={form.anthropic_configured} />
          </div>
        </Group>

        <Group id="models" title="Model configuration" description="Identical settings apply to baseline and VeriCode runs, so benchmarks stay comparable.">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Coder model id">{txt('coder_model', 'set VERICODE_CODER_MODEL')}</Field>
            <Field label="Planner model id">{txt('planner_model', 'defaults to coder model')}</Field>
          </div>
          <div className="mt-3 space-y-2">
            <Checkbox checked={!!form.llm_stream} onChange={(v) => set('llm_stream', v)}>Stream coder/repair responses (usage from stream events)</Checkbox>
            <Checkbox checked={!!form.use_llm_judge} onChange={(v) => set('use_llm_judge', v)}>LLM evidence judge for claims without concrete values (real provider only)</Checkbox>
          </div>
        </Group>

        <Group id="tavily" title="Tavily integration" description="Live documentation and evidence retrieval. Search credits are tracked separately from LLM tokens.">
          <div className="mb-3"><KeyState name="TAVILY_API_KEY" set={form.tavily_configured} required /></div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Search depth">
              <Select aria-label="Tavily search depth" className="w-full" value={form.tavily_search_depth} onChange={(e) => set('tavily_search_depth', e.target.value)}>
                {['basic', 'advanced', 'fast', 'ultra-fast'].map((p) => <option key={p}>{p}</option>)}
              </Select>
            </Field>
            <Field label="Timeout (s)">{num('tavily_timeout')}</Field>
            <Field label="Max retries">{num('tavily_max_retries')}</Field>
          </div>
        </Group>

        <Group id="api" title="API and workspaces" description="Where workspaces are read from and how long environment/search results are cached.">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Field label="Search provider"><input className={inputCls} value="tavily" disabled /></Field>
            <Field label="Workspace root"><input className={`${inputCls} font-mono`} value={form.workspaces_root} disabled /></Field>
            <Field label="Default workspace">{txt('default_workspace')}</Field>
            <Field label="Cache TTL (s)">{num('cache_ttl_seconds')}</Field>
          </div>
        </Group>

        <Group id="sandbox" title="Sandbox" description="Where generated changes are tested. Docker: no network, read-only root, unprivileged user; process: rlimits and network isolation when available.">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Execution sandbox" hint="auto = Docker when the daemon is reachable">
              <Select aria-label="Execution sandbox" className="w-full" value={form.sandbox_backend} onChange={(e) => set('sandbox_backend', e.target.value)}>
                {['auto', 'docker', 'process'].map((p) => <option key={p}>{p}</option>)}
              </Select>
            </Field>
            <Field label="Command timeout (s)">{num('command_timeout')}</Field>
          </div>
        </Group>

        <Group id="benchmark" title="Execution and benchmark preferences" description="Repair budget and adaptive execution apply to every run; prices are only used for cost estimates of real-provider calls.">
          <div className="mb-3">
            <Checkbox checked={form.adaptive_execution !== false} onChange={(v) => set('adaptive_execution', v)}>Adaptive execution: skip the planner when the task shows no third-party API risk (generated code is still audited)</Checkbox>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Repair attempt limit">{num('max_repair_attempts')}</Field>
            <Field label="Cost $/Mtok input">{num('cost_input_per_mtok')}</Field>
            <Field label="Cost $/Mtok output">{num('cost_output_per_mtok')}</Field>
          </div>
          <div className="mt-3">
            <Field label="Per-model prices (USD per 1M tokens, JSON)" hint='{"model-id": {"input": 3, "output": 15}} — used for cost; no prices are assumed'>
              <input aria-label="Model prices" className={`${inputCls} font-mono`} value={typeof form.model_prices === 'string' ? form.model_prices : JSON.stringify(form.model_prices ?? {})} onChange={(e) => set('model_prices', e.target.value)} />
            </Field>
          </div>
        </Group>

        <Group id="verification" title="Claim verification" description="Freshness = 100 × 2^(−age / half-life), per claim category. Primary domains decide source authority (“.gov” matches any .gov domain).">
          <div className="text-xs font-medium text-fg-muted">Freshness half-lives (days)</div>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {Object.entries(form.half_lives).map(([k, v]: any) => (
              <Field key={k} label={k}><input aria-label={`half-life ${k}`} type="number" className={inputCls} value={v} onChange={(e) => set('half_lives', { ...form.half_lives, [k]: +e.target.value })} /></Field>
            ))}
          </div>
          <div className="mt-4 text-xs font-medium text-fg-muted">Primary domains per claim category (comma separated)</div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            {Object.entries(form.authority_rules ?? {}).map(([k, v]: any) => (
              <Field key={k} label={k}><input aria-label={`authority ${k}`} className={`${inputCls} font-mono text-xs`} value={Array.isArray(v) ? v.join(', ') : v}
                onChange={(e) => set('authority_rules', { ...form.authority_rules, [k]: e.target.value })} /></Field>
            ))}
          </div>
        </Group>

        <Group id="security" title="Security" description="Local single-user access: one-time token, HttpOnly session cookie, CSRF on every write, Host allowlist; loopback only unless remote access is enabled on the server.">
          <IntegrationStatus i={form.integrations} />
        </Group>

        {(err || msg) && (
          <div className="border-t border-line px-4 py-3">
            <ErrorBox error={err} />
            {msg && <div className="text-xs text-ok">{msg}</div>}
          </div>
        )}
      </Card>

      <Card title="Project memory — verified compatibility rules" description="Created from pre-flight findings verified against installed source; re-checked when package versions change."
        actions={<Button variant="ghost" size="sm" onClick={exportRules}>Export to sample_project/.agent-rules.md</Button>} flush>
        {rules.loading ? <div className="p-4"><Spinner /></div> : !rules.data?.length ? <div className="p-4"><Empty>No verified rules yet. They are created from pre-flight findings verified against installed source.</Empty></div> : (
          <DataTable label="Verified rules" dense>
            <thead><tr><th>Package</th><th>Version</th><th>API</th><th>Correction</th><th>Evidence</th><th>Last verified</th><th>Expires</th><th /></tr></thead>
            <tbody>{rules.data.map((r) => (
              <tr key={r.id} className={r.active ? '' : 'opacity-50'}>
                <td>{r.package}</td><td className="font-mono">{r.version_spec}</td><td className="font-mono">{r.api}</td>
                <td className="max-w-xs text-fg">{r.correction}</td><td className="max-w-[12rem] text-fg-muted">{r.evidence_source}</td>
                <td className="whitespace-nowrap">{fmt.time(r.last_verified)}</td><td className="whitespace-nowrap">{fmt.time(r.expires_at)}</td>
                <td className="whitespace-nowrap"><div className="flex gap-1"><Button variant="ghost" size="sm" onClick={() => toggle(r)}>{r.active ? 'Disable' : 'Enable'}</Button><Button variant="danger" size="sm" onClick={() => delRule(r.id)}>Delete</Button></div></td>
              </tr>
            ))}</tbody>
          </DataTable>
        )}
        {exported && <div className="p-4"><Mono>{exported}</Mono></div>}
      </Card>
    </div>
  )
}
