import { describe, expect, it } from 'vitest'
import { BusinessAddressSchema, CheckoutSchema, parseCheckout } from '../src/validation'

const address = { name: 'Ada Lovelace', street: '12 Analytical St', city: 'London', postcode: 'N1 9GU', country: 'GB' }
const valid = { email: 'ada@example.com', shippingAddress: address, items: [{ sku: 'MUG-001', quantity: 2 }] }

describe('checkout validation (benchmark acceptance)', () => {
  it('accepts a valid checkout, with and without a coupon', () => {
    expect(CheckoutSchema.parse(valid).items[0].quantity).toBe(2)
    expect(CheckoutSchema.parse({ ...valid, couponCode: 'SPRING24' }).couponCode).toBe('SPRING24')
  })

  it('rejects bad emails, empty carts and out-of-range quantities', () => {
    expect(CheckoutSchema.safeParse({ ...valid, email: 'not-an-email' }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, items: [] }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, items: [{ sku: 'MUG-001', quantity: 0 }] }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, items: [{ sku: 'MUG-001', quantity: 100 }] }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, items: [{ sku: 'MUG-001', quantity: 1.5 }] }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, items: [{ sku: 'mug-1', quantity: 1 }] }).success).toBe(false)
  })

  it('validates coupon codes', () => {
    expect(CheckoutSchema.safeParse({ ...valid, couponCode: 'abc' }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, couponCode: 'spring24' }).success).toBe(false)
    expect(CheckoutSchema.safeParse({ ...valid, couponCode: 'WAYTOOLONGCODE1' }).success).toBe(false)
  })

  it('parseCheckout never throws and reports path-prefixed errors', () => {
    const ok = parseCheckout(valid)
    expect(ok.ok).toBe(true)
    const bad = parseCheckout({ ...valid, email: 'x', items: [] })
    expect(bad.ok).toBe(false)
    if (!bad.ok) {
      expect(bad.errors.length).toBeGreaterThanOrEqual(2)
      expect(bad.errors.some((e) => e.startsWith('email'))).toBe(true)
      expect(bad.errors.some((e) => e.startsWith('items'))).toBe(true)
    }
    expect(() => parseCheckout(null)).not.toThrow()
  })

  it('business addresses need a company name and a VAT id', () => {
    expect(BusinessAddressSchema.parse({ ...address, companyName: 'Engines Ltd', vatId: 'GB123456789' }).companyName).toBe('Engines Ltd')
    expect(BusinessAddressSchema.safeParse({ ...address, companyName: '', vatId: 'GB123456789' }).success).toBe(false)
    expect(BusinessAddressSchema.safeParse({ ...address, companyName: 'Engines Ltd', vatId: '123' }).success).toBe(false)
    expect(BusinessAddressSchema.safeParse({ ...address, vatId: 'GB123456789' }).success).toBe(false)
  })
})
