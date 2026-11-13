import { describe, expect, it } from 'vitest'
import { money } from '../src/money'
import { calculateShipping } from '../src/shipping'

describe('calculateShipping', () => {
  it('charges the base price for light parcels', () => {
    expect(calculateShipping(money(1000), 800).amount).toBe(490)
  })

  it('charges every started kilogram above the first', () => {
    expect(calculateShipping(money(1000), 1001).amount).toBe(640)
    expect(calculateShipping(money(1000), 2500).amount).toBe(790)
  })

  it('ships for free from the threshold', () => {
    expect(calculateShipping(money(6000), 5000).amount).toBe(0)
    expect(calculateShipping(money(5000), 400).amount).toBe(0)
  })
})
