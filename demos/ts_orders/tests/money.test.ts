import { describe, expect, it } from 'vitest'
import { add, CurrencyMismatchError, format, fromMajor, money, multiply } from '../src/money'

describe('money', () => {
  it('formats minor units', () => {
    expect(format(money(1290))).toBe('€12.90')
    expect(format(money(-5, 'USD'))).toBe('-$0.05')
  })

  it('rounds when multiplying', () => {
    expect(multiply(money(999), 0.9).amount).toBe(899)
    expect(fromMajor(12.345).amount).toBe(1235)
  })

  it('refuses mixed currencies', () => {
    expect(() => add(money(1, 'EUR'), money(1, 'USD'))).toThrow(CurrencyMismatchError)
  })
})
