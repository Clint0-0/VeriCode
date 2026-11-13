import { describe, expect, it } from 'vitest'
import { money } from '../src/money'
import { calculateShipping } from '../src/shipping'

describe('shipping edge cases (benchmark acceptance)', () => {
  it('is free exactly at the threshold, in the order currency', () => {
    expect(calculateShipping(money(5000, 'USD'), 300)).toEqual({ amount: 0, currency: 'USD' })
    expect(calculateShipping(money(4999), 300).amount).toBe(490)
  })

  it('charges per started kilogram above the first', () => {
    expect(calculateShipping(money(100), 0).amount).toBe(490)
    expect(calculateShipping(money(100), 1000).amount).toBe(490)
    expect(calculateShipping(money(100), 1001).amount).toBe(640)
    expect(calculateShipping(money(100), 2000).amount).toBe(640)
    expect(calculateShipping(money(100), 3999).amount).toBe(940)
  })
})
