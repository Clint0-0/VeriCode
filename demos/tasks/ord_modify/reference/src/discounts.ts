import { type Money, money, multiply, subtract } from './money'

export type Discount =
  | { kind: 'percent'; code: string; percent: number }
  | { kind: 'fixed'; code: string; amount: Money }

// Percentage discounts first, then fixed amounts; never below zero.
export function applyDiscounts(subtotal: Money, discounts: Discount[]): Money {
  let total = subtotal
  for (const d of discounts) if (d.kind === 'percent') total = multiply(total, 1 - d.percent / 100)
  for (const d of discounts) if (d.kind === 'fixed') total = subtract(total, d.amount)
  return total.amount < 0 ? money(0, total.currency) : total
}

export function describe(d: Discount): string {
  return d.kind === 'percent' ? `${d.code}: ${d.percent}% off` : `${d.code}: ${d.amount.amount / 100} off`
}

export const NO_DISCOUNT: Money = money(0)
