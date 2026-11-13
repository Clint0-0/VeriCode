// Money is stored in integer minor units (cents) to avoid floating-point drift.
export type Currency = 'EUR' | 'USD' | 'GBP'

export interface Money {
  readonly amount: number // minor units
  readonly currency: Currency
}

export class CurrencyMismatchError extends Error {
  constructor(a: Currency, b: Currency) {
    super(`cannot combine ${a} and ${b}`)
    this.name = 'CurrencyMismatchError'
  }
}

export function money(amount: number, currency: Currency = 'EUR'): Money {
  if (!Number.isInteger(amount)) throw new RangeError(`amount must be an integer number of minor units, got ${amount}`)
  return { amount, currency }
}

export function fromMajor(major: number, currency: Currency = 'EUR'): Money {
  return money(Math.round(major * 100), currency)
}

export function add(a: Money, b: Money): Money {
  if (a.currency !== b.currency) throw new CurrencyMismatchError(a.currency, b.currency)
  return money(a.amount + b.amount, a.currency)
}

export function subtract(a: Money, b: Money): Money {
  if (a.currency !== b.currency) throw new CurrencyMismatchError(a.currency, b.currency)
  return money(a.amount - b.amount, a.currency)
}

export function multiply(a: Money, factor: number): Money {
  return money(Math.round(a.amount * factor), a.currency)
}

export function sum(items: Money[], currency: Currency = 'EUR'): Money {
  return items.reduce((acc, m) => add(acc, m), money(0, currency))
}

export function format(m: Money): string {
  const symbol = { EUR: '€', USD: '$', GBP: '£' }[m.currency]
  const sign = m.amount < 0 ? '-' : ''
  const abs = Math.abs(m.amount)
  return `${sign}${symbol}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}
