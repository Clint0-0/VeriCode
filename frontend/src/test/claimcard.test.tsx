import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClaimCard } from '../pages/Stale'

const claim = {
  claim: { claim_id: 'claim_002', claim: 'Python 3.12 added a per-interpreter GIL.', category: 'software_version', volatility: 'high',
    span: [0, 60], source_text: 'Python 3.12, which was released in 2023, added a per-interpreter GIL.', derived: true, relation: 'main',
    hedged: true, features: { hedges: ['reportedly'], qualifiers: ['except'], comparison: [], temporal_markers: ['recently'] },
    notes: ['subject shared with relative clause'] },
  status: 'CONTRADICTED', freshness: null, freshness_note: 'unknown', confidence: 40, confidence_breakdown: {}, explanation: 'x',
  evidence: [
    { outcome: 'contradict', origin: 'fixture', method: 'value', url: 'https://python.org.example.net/x', title: 'Look-alike', domain: 'python.org.example.net',
      source_type: 'suspected_impersonation', authority: 0.1, authority_tier: 'suspicious', authority_explanation: 'contains trusted domain python.org',
      published_date: null, retrieved_at: 'now', excerpt: 'e', relevance_explanation: 'r' },
    { outcome: 'support', origin: 'installed_source', method: 'installed_source', url: 'installed://pydantic@2.9.2/main.py:1', title: 'Installed source: pydantic 2.9.2 — dict',
      domain: 'pydantic@2.9.2', source_type: 'installed_package_source (version-specific)', authority: 1, authority_tier: 'primary', authority_explanation: 'installed package code',
      published_date: null, retrieved_at: 'now', excerpt: 'e2', relevance_explanation: 'r2' },
  ],
}

test('claim card shows derivation, linguistic features, authority tiers and non-link installed sources', async () => {
  render(<ClaimCard c={claim} />)
  await userEvent.click(screen.getByRole('button'))
  expect(screen.getByText(/subject carried over from the same sentence/)).toBeInTheDocument()
  expect(screen.getByText('hedged: reportedly')).toBeInTheDocument()
  expect(screen.getByText('qualifier: except')).toBeInTheDocument()
  expect(screen.getByText('suspicious')).toBeInTheDocument()
  expect(screen.getByText(/authority: contains trusted domain/)).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Installed source/ })).toBeNull()
  expect(screen.getByText('Installed source: pydantic 2.9.2 — dict')).toBeInTheDocument()
})
