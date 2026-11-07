import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'

// Network boundary is stubbed per-test; components themselves contain no mock data.
type Handler = (url: string, init?: RequestInit) => any
function stubFetch(handler: Handler) {
  globalThis.fetch = vi.fn(async (url: any, init?: any) => {
    const out = handler(String(url), init)
    if (out instanceof Error) throw out
    const { status = 200, body } = out ?? {}
    return new Response(JSON.stringify(body ?? null), { status })
  }) as any
}

const integrations = {
  llm: { provider: 'mock', ready: true, missing: [], real: false, planner_model: 'mock-scripted', coder_model: 'mock-scripted' },
  tavily: { configured: false, missing: ['TAVILY_API_KEY'] },
  sandbox: { configured: 'auto', active: 'docker', error: null, docker_available: true, process_network_isolation: true },
  typescript_checker: { available: true }, auth: { enabled: true, host: '127.0.0.1', allow_remote: false }, schema_version: 7,
}

const base: Handler = (url) => {
  if (url.endsWith('/api/auth/status')) return { body: { authenticated: true, csrf: 'csrf-1' } }
  if (url.endsWith('/api/health')) return { body: { ok: true, provider: 'mock', tavily_configured: false, network_isolation: false } }
  if (url.endsWith('/api/dashboard')) return { body: { coding_tasks: 0, successful_tasks: 0, preflight_runs: 0, stale_claims: 0, claims_checked: 0, total_tokens: 0, llm_calls: 0, estimated_calls: 0, latest_benchmark: null, recent_tasks: [], provider: 'mock', tavily_configured: false, rules: 0, partial_tasks: 0, tokens_by_measurement: [], latest_real_benchmark: null, integrations } }
  if (url.endsWith('/api/tasks')) return { body: [] }
  if (url.endsWith('/api/stale')) return { body: [] }
  if (url.endsWith('/api/workspaces')) return { body: [{ name: 'sample_project', path: '/x/sample_project' }] }
  if (url.endsWith('/api/catalog')) return { body: [] }
  return { status: 404, body: { detail: 'not found' } }
}

beforeEach(() => { window.location.hash = '' })

test('dashboard renders measured stats, mock notice, integrations and empty states', async () => {
  stubFetch(base)
  render(<App />)
  expect(screen.getByRole('status')).toBeInTheDocument() // loading
  expect(await screen.findByText(/LLM provider is the/i)).toBeInTheDocument()
  expect(screen.getByText(/missing: TAVILY_API_KEY/)).toBeInTheDocument()
  expect(screen.getByText(/No benchmark yet/)).toBeInTheDocument()
  expect(screen.getByText(/No tasks yet/)).toBeInTheDocument()
})

test('navigation switches screens', async () => {
  stubFetch(base)
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: 'Task History' }))
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Task History'))
  expect(await screen.findByText('No tasks yet.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('link', { name: 'Coding Workspace' }))
  expect(await screen.findByLabelText('Instruction')).toBeInTheDocument()
})

test('unauthenticated users see the login screen; wrong token shows an error, right token signs in', async () => {
  let authed = false
  let csrfSent: string | null = null
  stubFetch((url, init) => {
    if (url.endsWith('/api/auth/status')) return { body: { authenticated: authed, csrf: authed ? 'c1' : null } }
    if (url.endsWith('/api/auth/login')) {
      const tok = JSON.parse(String(init?.body)).token
      if (tok !== 'good') return { status: 401, body: { detail: 'invalid access token' } }
      authed = true
      return { body: { authenticated: true, csrf: 'c1' } }
    }
    if (url.endsWith('/api/tasks') && init?.method === 'POST') { csrfSent = (init.headers as any)['X-CSRF-Token']; return { body: { task_id: 't1' } } }
    if (!authed) return { status: 401, body: { detail: 'authentication required', code: 'auth' } }
    return base(url, init)
  })
  render(<App />)
  const input = await screen.findByLabelText('Access token')
  await userEvent.type(input, 'bad')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/invalid access token/)
  await userEvent.clear(input)
  await userEvent.type(input, 'good')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Dashboard')
  window.location.hash = 'workspace'
  await userEvent.type(await screen.findByLabelText('Instruction'), 'Add a helper')
  await userEvent.click(screen.getByRole('button', { name: 'Run task' }))
  await waitFor(() => expect(csrfSent).toBe('c1'))
})

test('error state when backend unreachable', async () => {
  stubFetch((url) => (url.endsWith('/api/auth/status') ? { body: { authenticated: true, csrf: 'x' } } : new TypeError('Failed to fetch')))
  render(<App />)
  expect(await screen.findByRole('alert')).toHaveTextContent(/Backend unreachable/)
})

test('stale detector submits answer and shows claim-level report', async () => {
  const analysis = {
    id: 'ans_1', answer: 'Python 3.12 is the latest stable version of Python.',
    summary: { total_claims: 1, requiring_verification: 1, by_status: { CONTRADICTED: 1 }, evidence_mode: 'fixture', search_calls: 1, tavily_configured: false, url_errors: [] },
    claims: [{ claim: { claim_id: 'claim_001', claim: 'Python 3.12 is the latest stable version of Python.', category: 'software_version', volatility: 'high', span: [0, 51], source_text: 'Python 3.12 is the latest stable version of Python.', temporal_sensitivity: 'present_state', verifiability: 'verifiable', evidence_type: 'official_release_notes' },
      status: 'CONTRADICTED', freshness: 4.7, freshness_note: 'from source date', confidence: 84.8, confidence_breakdown: { authority: 29.8 },
      explanation: 'Newer authoritative evidence contradicts the claim.', correction: '3.14', search_status: 'ok',
      evidence: [{ outcome: 'contradict', origin: 'fixture', method: 'value', url: 'https://www.python.org/downloads/release/python-3140/', title: 'Python 3.14.0', domain: 'python.org', source_type: 'official', authority: 0.85, published_date: '2025-10-07', retrieved_at: 'now', excerpt: 'Python 3.14.0 ...', relevance_explanation: '100% overlap' }] }],
  }
  let posted: any = null
  stubFetch((url, init) => {
    if (url.endsWith('/api/stale/analyze')) { posted = JSON.parse(String(init?.body)); return { body: analysis } }
    return base(url, init)
  })
  window.location.hash = 'stale'
  render(<App />)
  await userEvent.type(await screen.findByLabelText('LLM answer'), 'Python 3.12 is the latest stable version of Python.')
  await userEvent.click(screen.getByLabelText(/Offline fixture/))
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: /Extract & verify/ })) })
  expect(posted.mode).toBe('fixture')
  expect(await screen.findByText(/Evidence below comes from the/)).toBeInTheDocument()
  // traceability: clicking the highlighted span in the original answer opens that claim
  await userEvent.click(screen.getByTitle('claim_001: CONTRADICTED'))
  expect(screen.getByText(/Evidence-based replacement value/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Python 3.14.0' })).toHaveAttribute('href', 'https://www.python.org/downloads/release/python-3140/')
})

test('coding workspace surfaces missing-credential errors from the API', async () => {
  stubFetch((url, init) => {
    if (url.endsWith('/api/tasks') && init?.method === 'POST') return { status: 503, body: { detail: 'No LLM provider configured', code: 'llm_unavailable' } }
    return base(url, init)
  })
  window.location.hash = 'workspace'
  render(<App />)
  await userEvent.type(await screen.findByLabelText('Instruction'), 'Add a helper')
  await userEvent.click(screen.getByRole('button', { name: 'Run task' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/No LLM provider configured.*Configure an LLM provider/)
})

test('pre-flight shows the confidence heatmap with real statuses', async () => {
  const findings = [
    { package: 'pydantic', installed_version: '2.9.2', planned_api: 'pydantic.Field', status: 'INCOMPATIBLE', risk_score: 70, verification_confidence: 'high', explanation: 'regex rejected', arguments: ['regex'], verification_method: ['static_ast'], risk_factors: [], argument_checks: [] },
    { package: 'pydantic', installed_version: '2.9.2', planned_api: 'pydantic.BaseModel', status: 'VERIFIED_LOCAL', risk_score: 0, verification_confidence: 'high', explanation: 'found', arguments: [], verification_method: ['static_ast'], risk_factors: [], argument_checks: [] },
  ]
  stubFetch((url, init) => {
    if (url.endsWith('/api/preflight')) return { body: { skeleton: { packages: [] }, skeleton_errors: [], findings, briefing: 'PRE-FLIGHT BRIEFING', tokens: { by_stage: {}, input: 1, output: 1, total: 2, calls: 1, estimated: true, measurement: 'MOCK' } } }
    return base(url, init)
  })
  window.location.hash = 'preflight'
  render(<App />)
  await userEvent.type(await screen.findByLabelText('Task'), 'add a user model')
  await userEvent.click(screen.getByRole('button', { name: 'Run pre-flight' }))
  const table = await screen.findByRole('table', { name: 'API confidence heatmap' })
  expect(table).toHaveTextContent('INCOMPATIBLE')
  expect(table).toHaveTextContent('VERIFIED_LOCAL')
  expect(screen.getByText('INCOMPATIBLE · 1')).toBeInTheDocument()
})

test('settings save sends persisted fields with CSRF and shows confirmation', async () => {
  let body: any = null
  const settingsBody = { llm_provider: 'mock', planner_model: '', coder_model: '', max_repair_attempts: 3, command_timeout: 120, cache_ttl_seconds: 86400, tavily_timeout: 20, tavily_max_retries: 2, cost_input_per_mtok: 3, cost_output_per_mtok: 15, half_lives: { pricing: 60 }, sandbox_backend: 'auto', use_llm_judge: true, tavily_search_depth: 'basic', default_workspace: 'sample_project', authority_rules: { pricing: [] }, model_prices: {}, llm_stream: true, workspaces_root: '/x', tavily_configured: false, anthropic_configured: false, openai_configured: false, integrations }
  stubFetch((url, init) => {
    if (url.endsWith('/api/settings') && init?.method === 'PUT') { body = JSON.parse(String(init.body)); return { body: settingsBody } }
    if (url.endsWith('/api/settings')) return { body: settingsBody }
    if (url.endsWith('/api/rules')) return { body: [] }
    return base(url, init)
  })
  window.location.hash = 'settings'
  render(<App />)
  const sel = await screen.findByLabelText('Execution sandbox')
  await userEvent.selectOptions(sel, 'docker')
  await userEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByText(/persist across restarts/)).toBeInTheDocument()
  expect(body.sandbox_backend).toBe('docker')
  expect(body.authority_rules).toEqual({ pricing: [] })
})
