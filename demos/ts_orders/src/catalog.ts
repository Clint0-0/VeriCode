import { type Money, money } from './money'

export interface Product {
  sku: string
  name: string
  price: Money
  weightGrams: number
  active: boolean
}

const PRODUCTS: Product[] = [
  { sku: 'MUG-001', name: 'Stoneware mug', price: money(1290), weightGrams: 420, active: true },
  { sku: 'TEA-010', name: 'Loose leaf tea, 100 g', price: money(850), weightGrams: 120, active: true },
  { sku: 'POT-002', name: 'Cast-iron teapot', price: money(4990), weightGrams: 1650, active: true },
  { sku: 'CUP-003', name: 'Espresso cup set', price: money(2400), weightGrams: 640, active: false },
]

export class UnknownProductError extends Error {
  constructor(sku: string) {
    super(`unknown product ${sku}`)
    this.name = 'UnknownProductError'
  }
}

export function findProduct(sku: string): Product {
  const p = PRODUCTS.find((x) => x.sku === sku)
  if (!p) throw new UnknownProductError(sku)
  return p
}

export function listActive(): Product[] {
  return PRODUCTS.filter((p) => p.active)
}
