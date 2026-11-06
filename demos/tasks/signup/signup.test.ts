import { describe, expect, it } from 'vitest'
import { Signup } from '../src/signup'

describe('signup schema (demo task acceptance)', () => {
  it('accepts a valid signup', () => {
    expect(Signup.parse({ username: 'dev42', email: 'dev@example.com' }).username).toBe('dev42')
  })
  it('rejects short usernames and bad emails', () => {
    expect(Signup.safeParse({ username: 'ab', email: 'dev@example.com' }).success).toBe(false)
    expect(Signup.safeParse({ username: 'dev42', email: 'nope' }).success).toBe(false)
    expect(Signup.safeParse({ username: '', email: 'dev@example.com' }).success).toBe(false)
  })
})
