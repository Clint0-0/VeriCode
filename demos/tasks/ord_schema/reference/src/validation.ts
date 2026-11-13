import { z } from 'zod'

export const CountrySchema = z.enum(['DE', 'FR', 'NL', 'GB', 'US'])

export const AddressSchema = z.object({
  name: z.string().min(1),
  street: z.string().min(3),
  city: z.string().min(1),
  postcode: z.string().regex(/^[A-Z0-9 -]{3,10}$/i),
  country: CountrySchema,
})

export type Address = z.infer<typeof AddressSchema>

export function parseAddress(input: unknown): Address {
  return AddressSchema.parse(input)
}

export const BusinessAddressSchema = AddressSchema.extend({
  companyName: z.string().min(1),
  vatId: z.string().regex(/^[A-Z]{2}[0-9A-Z]{8,12}$/),
})

export const CheckoutSchema = z.object({
  email: z.string().email(),
  shippingAddress: AddressSchema,
  items: z.array(z.object({ sku: z.string().regex(/^[A-Z]{3}-\d{3}$/), quantity: z.number().int().min(1).max(99) })).min(1),
  couponCode: z.string().regex(/^[A-Z0-9]{4,12}$/).optional(),
})

export type Checkout = z.infer<typeof CheckoutSchema>

export function parseCheckout(input: unknown): { ok: true; data: Checkout } | { ok: false; errors: string[] } {
  const r = CheckoutSchema.safeParse(input)
  if (r.success) return { ok: true, data: r.data }
  return { ok: false, errors: r.error.issues.map((i) => `${i.path.join('.') || '(root)'}: ${i.message}`) }
}
