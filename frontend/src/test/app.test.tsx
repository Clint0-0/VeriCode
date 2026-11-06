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

const base: Handler = (url) => {
  if (url.endsWith('/api/health')) return { body: { ok: true, provider: 'mock', tavily_configured: false, network_isolation: false } }
  if (url.endsWith('/api/dashboard')) return { body: { coding_tasks: 0, successful_tasks: 0, preflight_runs: 0, stale_claims: 0, claims_checked: 0, total_tokens: 0, llm_calls: 0, estimated_calls: 0, latest_benchmark: null, recent_tasks: [], provider: 'mock', tavily_configured: false, rules: 0 } }
  if (url.endsWith('/api/tasks')) return { body: [] }
  if (url.endsWith('/api/stale')) return { body: [] }
  if (url.endsWith('/api/workspaces')) return { body: [{ name: 'sample_project', path: '/x/sample_project' }] }
  if (url.endsWith('/api/catalog')) return { body: [] }
  return { status: 404, body: { detail: 'not found' } }
}

beforeEach(() => { window.location.hash = '' })

test('dashboard renders measured stats, mock notice and empty states', async () => {
  stubFetch(base)
  render(<App />)
  expect(screen.getByRole('status')).toBeInTheDocument() // loading
  expect(await screen.findByText(/scripted mock/i)).toBeInTheDocument()
  expect(screen.getByText(/No benchmark yet/)).toBeInTheDocument()
  expect(screen.getByText(/No tasks yet/)).toBeInTheDocument()
})

test('navigation switches screens', async () => {
  stubFetch(base)
  render(<App />)
  await userEvent.click(screen.getByRole('link', { name: 'Task History' }))
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Task History'))
  expect(await screen.findByText('No tasks yet.')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('link', { name: 'Coding Workspace' }))
  expect(await screen.findByLabelText('Instruction')).toBeInTheDocument()
})

test('error state when backend unreachable', async () => {
  stubFetch(() => new TypeError('Failed to fetch'))
  render(<App />)
  expect(await screen.findByRole('alert')).toHaveTextContent(/Backend unreachable/)
})

test('stale detector submits answer and shows claim-level report', async () => {
  const analysis = {
    id: 'ans_1', answer: 'Python 3.12 is the latest stable version of Python.',
    summary: { total_claims: 1, requiring_verification: 1, by_status: { CONTRADICTED: 1 }, evidence_mode: 'fixture', search_calls: 1, tavily_configured: false, url_errors: [] },
    claims: [{ claim: { claim_id: 'claim_001', claim: 'Python 3.12 is the latest stable version of Python.', category: 'software_version', volatility: 'high' },
      status: 'CONTRADICTED', freshness: 4.7, freshness_note: 'from source date', confidence: 84.8, confidence_breakdown: { authority: 29.8 },
      explanation: 'Newer authoritative evidence contradicts the claim.', correction: '3.14', search_status: 'ok',
      evidence: [{ outcome: 'contradict', origin: 'fixture', url: 'https://www.python.org/downloads/release/python-3140/', title: 'Python 3.14.0', domain: 'python.org', source_type: 'official', authority: 0.85, published_date: '2025-10-07', retrieved_at: 'now', excerpt: 'Python 3.14.0 ...', relevance_explanation: '100% overlap' }] }],
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
  const head = screen.getAllByText('CONTRADICTED')[0]
  await userEvent.click(head.closest('button')!)
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
