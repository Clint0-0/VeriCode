import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConfidenceHeatmap } from '../components/Heatmap'

describe('ConfidenceHeatmap', () => {
  it('counts verification-tool ERROR separately from NOT_FOUND', () => {
    render(<ConfidenceHeatmap findings={[
      { package: 'zod', installed_version: '3.23.8', planned_api: 'zod:z.object', status: 'VERIFIED_LOCAL' },
      { package: 'zod', installed_version: '3.23.8', planned_api: 'zod:z.string', status: 'ERROR' },
      { package: 'zod', installed_version: '3.23.8', planned_api: 'zod:z.objekt', status: 'NOT_FOUND' },
    ]} />)
    expect(screen.getByText('ERROR · 1')).toBeInTheDocument()
    expect(screen.getByText('NOT_FOUND · 1')).toBeInTheDocument()
  })
})
