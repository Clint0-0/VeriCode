import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExecutionError } from '../components/TaskReport'

describe('ExecutionError', () => {
  it('shows category, stage, fix and safe details instead of a traceback', () => {
    render(<ExecutionError detail={{
      category: 'executable_not_found', stage: 'tests',
      message: "'npm' was not found on the PATH of the VeriCode server process",
      action: 'Install Node.js (it provides npm and npx) ...',
      details: { executable: 'npm', resolved: null, args: ['test'], cwd: 'C:\\runs\\abc', cwd_exists: true, os: 'Windows', backend: 'process' },
    }} />)
    const box = screen.getByRole('alert')
    expect(box).toHaveTextContent('Required program not found')
    expect(box).toHaveTextContent('stage tests')
    expect(box).toHaveTextContent('Fix: Install Node.js')
    expect(box).toHaveTextContent('Windows')
    expect(box).not.toHaveTextContent('resolved')  // empty values hidden
    expect(box).not.toHaveTextContent('Traceback')
  })
})
