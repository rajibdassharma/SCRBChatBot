# Project: Acme Platform

A multi-tenant SaaS web app. Next.js frontend, Node/Express API, PostgreSQL
database, Redis cache. Monorepo managed with Turborepo.

See @README.md for full product overview.
See @docs/architecture.md for system design decisions.

---

## Repo structure

```
/apps
  /web          # Next.js 14 frontend (App Router)
  /api          # Express REST API
  /workers      # Background job processors (BullMQ)
/packages
  /db           # Prisma schema + migrations + seed scripts
  /ui           # Shared component library (shadcn/ui base)
  /shared       # Shared types, utils, constants
  /config       # ESLint, TypeScript, Tailwind configs
/infra          # Terraform + Docker configs
/docs           # Architecture docs, ADRs, API contracts
```

---

## Essential commands

```bash
# Install everything (run from root)
pnpm install

# Dev servers (runs all apps in parallel)
pnpm dev

# Run a specific app only
pnpm dev --filter=web
pnpm dev --filter=api

# Build
pnpm build

# Typecheck (run this after every set of changes)
pnpm typecheck

# Lint
pnpm lint

# Format
pnpm format

# Run all tests
pnpm test

# Run tests for a specific package
pnpm test --filter=api

# Run a single test file
pnpm --filter=api test -- src/auth/auth.service.test.ts

# DB: generate Prisma client after schema changes
pnpm --filter=db generate

# DB: create and apply a migration
pnpm --filter=db migrate:dev --name <migration_name>

# DB: reset and reseed local DB
pnpm --filter=db db:reset
```

**IMPORTANT:** Always run `pnpm typecheck` after making a series of code changes.
Always prefer running a single test file over the full test suite for speed.

---

## Stack

**Frontend (apps/web)**
- Next.js 14 with App Router (NOT Pages Router — never use pages/)
- TypeScript (strict mode)
- Tailwind CSS for styling
- shadcn/ui for base components (see packages/ui)
- React Query (TanStack Query v5) for server state
- Zustand for client-only state
- React Hook Form + Zod for forms and validation
- next-auth v5 for authentication

**API (apps/api)**
- Node.js + Express
- TypeScript
- Prisma ORM (see packages/db for schema)
- BullMQ for background jobs (see apps/workers)
- Zod for request validation
- Winston for logging

**Infrastructure**
- PostgreSQL (primary DB)
- Redis (caching + BullMQ queues)
- AWS S3 for file storage
- Vercel for frontend deployment
- Railway for API + workers deployment

---

## Code style

- Use ES modules (import/export) everywhere — never CommonJS require()
- Use named exports, not default exports (exception: Next.js page components)
- Always use TypeScript — no `any` types, no type assertions unless absolutely necessary
- Prefer `const` over `let`; never use `var`
- Use `async/await` — never raw `.then()` chains
- Use early returns to reduce nesting — avoid deeply nested if/else
- Destructure props and function arguments
- All React components must be functional — no class components

**Naming conventions**
- Components: PascalCase (`UserCard.tsx`)
- Hooks: camelCase prefixed with `use` (`useUserProfile.ts`)
- Utilities: camelCase (`formatCurrency.ts`)
- Types/interfaces: PascalCase, no `I` prefix (`UserProfile`, not `IUserProfile`)
- Database models: singular PascalCase (Prisma convention) — `User`, `Post`
- API routes: kebab-case (`/api/user-profiles`)
- Environment variables: SCREAMING_SNAKE_CASE

---

## Architecture rules

**Frontend data fetching**
- Use React Query for ALL server data — no manual fetch() in components
- Query keys live in `apps/web/src/lib/query-keys.ts` — always add new ones there
- Mutations must invalidate relevant query keys on success
- Never fetch data in Client Components if it can be done in a Server Component

**API structure**
- Every route file exports a router: `apps/api/src/routes/<resource>.routes.ts`
- Business logic lives in service files: `apps/api/src/services/<resource>.service.ts`
- Controllers are thin — they validate input with Zod and call service methods
- All DB access goes through Prisma in service files — no raw SQL unless necessary

**Authentication**
- Auth is handled by next-auth in the frontend and verified via JWT in the API
- API routes check the `Authorization: Bearer <token>` header
- Use the `requireAuth` middleware in `apps/api/src/middleware/auth.ts`
- Multi-tenancy: every DB query must be scoped to `organizationId` — never forget this

**Error handling**
- API: use the `AppError` class in `packages/shared/src/errors.ts` — not raw `new Error()`
- Frontend: React Query's `onError` callback for mutations, error boundaries for render errors
- Always log errors with Winston before returning a response

**Shared types**
- Types shared between frontend and API go in `packages/shared/src/types/`
- Never duplicate types — if it exists in shared, use it

---

## Testing

- Unit tests: Vitest (co-located with source files as `*.test.ts`)
- Integration tests: Vitest + Supertest for API routes (in `apps/api/src/__tests__/`)
- E2E tests: Playwright (in `apps/web/e2e/`)
- Every new service method needs a unit test
- Every new API route needs an integration test
- Test files must not import from other test files

---

## Database / Prisma

- Schema file: `packages/db/prisma/schema.prisma`
- Always run `pnpm --filter=db generate` after changing the schema
- Never edit migration files manually — always use `migrate:dev`
- Seed script: `packages/db/prisma/seed.ts`
- Soft deletes: use `deletedAt` timestamps — never hard delete user data
- All tables have `createdAt` and `updatedAt` fields (Prisma handles updatedAt)

---

## Environment variables

- Local env files: `apps/web/.env.local`, `apps/api/.env`
- Example files (committed): `apps/web/.env.example`, `apps/api/.env.example`
- NEVER commit `.env` or `.env.local` files
- Add new variables to the example file immediately when you add them to the code

---

## Git workflow

- Branch naming: `feat/<ticket-id>-short-description` or `fix/<ticket-id>-short-description`
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`)
- PRs require passing typecheck, lint, and tests before merging
- Never commit directly to `main` or `develop`

---

## Things Claude often gets wrong on this project

- Do NOT use the Pages Router — this project uses App Router exclusively
- Do NOT use `useEffect` to fetch data — use React Query
- Do NOT write raw SQL — always use Prisma
- Do NOT forget `organizationId` scoping on DB queries (multi-tenant!)
- Do NOT use default exports except in Next.js page/layout files
- When adding a new API route, ALWAYS add the corresponding Zod validator
- When adding a new env variable, ALWAYS update the `.env.example` file