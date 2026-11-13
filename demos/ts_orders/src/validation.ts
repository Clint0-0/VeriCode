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
