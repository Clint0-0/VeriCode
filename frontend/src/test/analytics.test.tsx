import { render, screen } from '@testing-library/react'
import BenchmarkAnalytics from '../components/BenchmarkAnalytics'

const stats = (mean: number | null) => ({ mean, median: mean, stdev: 0, n: mean == null ? 0 : 3 })
const cfg = (mean: number, extra: any = {}) => ({
  runs: 3, completed: 3, blocked: 0, success_rate: 1, first_pass_rate: 1, total_tokens: stats(mean), input_tokens: stats(mean * 0.8),
  output_tokens: stats(mean * 0.2), planner_tokens: stats(0), coder_tokens: stats(mean), repair_tokens: stats(0), ...extra,
})
const summary = {
  tasks: [{
    task: 'signup', title: 'signup', language: 'typescript', repo_size: 'small', category: 'feature',
    configurations: { baseline: cfg(767), vericode_full: cfg(1838), vericode_adaptive: cfg(1700, { execution_paths: { full: 3 } }) },
    comparisons: {
      vericode_full: { paired_savings: { mean: -139.6, n: 3 }, mean_token_savings_pct: -139.6 },
      vericode_adaptive: { paired_savings: { mean: -121.6, n: 3 }, mean_token_savings_pct: -121.6 },
    },
  }],
  overall: {
    vericode_full: { tasks_compared: 1, tasks_total: 1, pairs: 3, token_weighted_savings_pct: -139.6, median_task_savings_pct: -139.6, tasks_with_negative_savings: 1 },
  },
}

test('negative savings stay visible as more tokens', () => {
  render(<BenchmarkAnalytics summary={summary as any} labels={['ACTUAL_PROVIDER_USAGE']} />)
  expect(screen.getAllByText(/\+139\.6% tokens/).length).toBeGreaterThan(0)
  expect(screen.queryByRole('alert')).toBeNull()
})

test('mock or estimated results carry an unmistakable warning', () => {
  render(<BenchmarkAnalytics summary={summary as any} labels={['MOCK']} />)
  expect(screen.getByRole('alert')).toHaveTextContent(/Not provider-measured/)
  expect(screen.getByRole('alert')).toHaveTextContent(/mock provider/)
})
