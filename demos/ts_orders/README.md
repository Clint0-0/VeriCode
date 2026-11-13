# ts_orders (benchmark repository, medium, TypeScript)

Original code written for the VeriCode benchmark (no third-party source copied). A small shop checkout library:
money in integer minor units, a product catalog, a cart, discounts, shipping rules, zod input validation and an
order summary. Pinned dependencies: zod 3.23.8, vitest 2.1.9, typescript 5.9.3 (see package-lock.json).

`npm test` runs vitest; `npm run typecheck` runs `tsc --noEmit`.
