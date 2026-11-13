import { findProduct, type Product } from './catalog'
import { type Money, multiply, sum } from './money'

export interface CartLine {
  product: Product
  quantity: number
}

export class Cart {
  private lines = new Map<string, CartLine>()

  add(sku: string, quantity = 1): void {
    if (!Number.isInteger(quantity) || quantity <= 0) throw new RangeError('quantity must be a positive integer')
    const product = findProduct(sku)
    if (!product.active) throw new Error(`product ${sku} is not available`)
    const line = this.lines.get(sku)
    this.lines.set(sku, { product, quantity: (line?.quantity ?? 0) + quantity })
  }

  remove(sku: string): void {
    this.lines.delete(sku)
  }

  items(): CartLine[] {
    return [...this.lines.values()]
  }

  subtotal(): Money {
    return sum(this.items().map((l) => multiply(l.product.price, l.quantity)))
  }

  weightGrams(): number {
    return this.items().reduce((g, l) => g + l.product.weightGrams * l.quantity, 0)
  }

  isEmpty(): boolean {
    return this.lines.size === 0
  }
}
