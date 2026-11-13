import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useApi } from '../components/ui'

function Show({ path }: { path: string }) {
  const r = useApi<any>(path)
  return <div data-testid="v">{r.data ? r.data.id : 'none'}</div>
}

afterEach(() => vi.restoreAllMocks())

describe('useApi', () => {
  it('never shows a previous run’s data after the path changes, even if the old response arrives late', async () => {
    const resolvers: Record<string, (v: any) => void> = {}
    vi.spyOn(globalThis, 'fetch').mockImplementation((url: any) => new Promise((res) => {
      const id = String(url).split('/').pop()!
      resolvers[id] = (body) => res(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    }) as any)
    const { rerender } = render(<Show path="/tasks/old" />)
    rerender(<Show path="/tasks/new" />)
    await act(async () => { resolvers['new']({ id: 'new' }) })
    expect(screen.getByTestId('v')).toHaveTextContent('new')
    await act(async () => { resolvers['old']({ id: 'old' }) })  // stale response for the old task id
    expect(screen.getByTestId('v')).toHaveTextContent('new')
  })
})
