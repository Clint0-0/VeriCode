import { describe, expect, it } from 'vitest'
import { applyDiscounts, describe as describeDiscount, type Discount } from '../src/discounts'
import { money } from '../src/money'

const tenPercent: Discount = { kind: 'percent', code: 'TEN', percent: 10 }
const fiveOff: Discount = { kind: 'fixed', code: 'FIVE', amount: money(500) }

describe('applyDiscounts (benchmark acceptance)', () => {
  it('applies percentage discounts before fixed ones, whatever the order given', () => {
    // 10000 -> 10% -> 9000 -> -500 -> 8500 (the old order-dependent code gave 8550 for the second call)
    expect(applyDiscounts(money(10000), [tenPercent, fiveOff]).amount).toBe(8500)
    expect(applyDiscounts(money(10000), [fiveOff, tenPercent]).amount).toBe(8500)
  })

  it('combines several discounts of each kind', () => {
    const twenty: Discount = { kind: 'percent', code: 'TWENTY', percent: 20 }
    const oneOff: Discount = { kind: 'fixed', code: 'ONE', amount: money(100) }
    expect(applyDiscounts(money(10000), [fiveOff, twenty, oneOff, tenPercent]).amount).toBe(6600)
  })

  it('never drops below zero and keeps the currency', () => {
    expect(applyDiscounts(money(300, 'GBP'), [fiveOff].map((d) => ({ ...d, amount: money(500, 'GBP') })))).toEqual({ amount: 0, currency: 'GBP' })
    expect(applyDiscounts(money(400), [fiveOff, tenPercent]).amount).toBe(0)
  })

  it('leaves the subtotal unchanged without discounts and keeps describe()', () => {
    expect(applyDiscounts(money(1234), []).amount).toBe(1234)
    expect(describeDiscount(tenPercent)).toBe('TEN: 10% off')
  })
})
