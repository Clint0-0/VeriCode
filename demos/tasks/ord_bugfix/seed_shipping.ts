import { type Money, money } from './money'

export interface ShippingRule {
  freeFrom: Money // orders whose subtotal reaches this amount ship for free
  basePrice: Money
  perKilo: Money // charged for every started kilogram above the first
}

export const DEFAULT_RULE: ShippingRule = { freeFrom: money(5000), basePrice: money(490), perKilo: money(150) }

export function calculateShipping(subtotal: Money, weightGrams: number, rule: ShippingRule = DEFAULT_RULE): Money {
  if (subtotal.amount > rule.freeFrom.amount) return money(0, subtotal.currency)
  const extraKilos = Math.max(0, Math.floor(weightGrams / 1000) - 1)
  return money(rule.basePrice.amount + extraKilos * rule.perKilo.amount, subtotal.currency)
}
