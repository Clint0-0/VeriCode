import { describe, expect, it } from 'vitest'
import { Cart } from '../src/cart'
import { summarize } from '../src/orders'

describe('Cart', () => {
  it('merges quantities of the same product', () => {
    const c = new Cart()
    c.add('MUG-001')
    c.add('MUG-001', 2)
    expect(c.items()).toHaveLength(1)
    expect(c.items()[0].quantity).toBe(3)
    expect(c.subtotal().amount).toBe(3870)
  })

  it('rejects inactive products and bad quantities', () => {
    const c = new Cart()
    expect(() => c.add('CUP-003')).toThrow(/not available/)
    expect(() => c.add('MUG-001', 0)).toThrow(RangeError)
  })

  it('summarizes with shipping', () => {
    const c = new Cart()
    c.add('TEA-010', 2)
    const s = summarize(c)
    expect(s.subtotal.amount).toBe(1700)
    expect(s.shipping.amount).toBe(490)
    expect(s.total.amount).toBe(2190)
  })
})
