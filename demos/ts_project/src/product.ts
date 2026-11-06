import { z } from 'zod'

export const Product = z.object({
  sku: z.string().min(3).max(32),
  name: z.string().min(1),
  priceCents: z.number().int().nonnegative(),
  tags: z.array(z.string()).default([]),
})

export type Product = z.infer<typeof Product>

export function parseProduct(input: unknown): Product {
  return Product.parse(input)
}
