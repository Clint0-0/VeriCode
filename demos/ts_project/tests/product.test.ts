import { describe, expect, it } from 'vitest'
import { parseProduct } from '../src/product'
import { formatPrice } from '../src/format'

describe('product', () => {
  it('parses a valid product', () => {
    expect(parseProduct({ sku: 'ABC1', name: 'Mug', priceCents: 1299 }).tags).toEqual([])
  })
  it('formats prices', () => {
    expect(formatPrice(1299)).toBe('$12.99')
  })
})
