import { Cart } from './cart'
import { applyDiscounts, type Discount } from './discounts'
import { add, format, type Money } from './money'
import { calculateShipping } from './shipping'
import { type Address } from './validation'

export interface OrderSummary {
  subtotal: Money
  discounted: Money
  shipping: Money
  total: Money
  lines: { sku: string; quantity: number }[]
}

export function summarize(cart: Cart, discounts: Discount[] = []): OrderSummary {
  if (cart.isEmpty()) throw new Error('cannot summarize an empty cart')
  const subtotal = cart.subtotal()
  const discounted = applyDiscounts(subtotal, discounts)
  const shipping = calculateShipping(discounted, cart.weightGrams())
  return {
    subtotal,
    discounted,
    shipping,
    total: add(discounted, shipping),
    lines: cart.items().map((l) => ({ sku: l.product.sku, quantity: l.quantity })),
  }
}

export function receipt(summary: OrderSummary, to: Address): string {
  return [
    `Ship to: ${to.name}, ${to.city} (${to.country})`,
    ...summary.lines.map((l) => `${l.quantity} x ${l.sku}`),
    `Subtotal: ${format(summary.subtotal)}`,
    `Shipping: ${format(summary.shipping)}`,
    `Total: ${format(summary.total)}`,
  ].join('\n')
}
