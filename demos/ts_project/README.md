# ts_project (VeriCode TypeScript demo)

Uses zod 3.23.8 (installed in node_modules, pinned by package-lock.json). Demo task: add a signup schema;
the planner proposes `ZodString.nonempty()` (deprecated in 3.23) and `ZodString.min("3")` (wrong argument type),
which VeriCode's TypeScript compiler-API checker catches before code generation.
Setup: `npm ci`
