# LubriSense AI — Frontend

Next.js (App Router) + TypeScript + Tailwind CSS + TanStack Query. Renders product surfaces
for all personas in `docs/DOMAIN_MODEL.md`. All production-like values must originate from
backend APIs (`TECHNICAL_DECISIONS.md` ADR-008) — this app contains no business logic and no
hardcoded telemetry, health scores, or AI output.

Phase 1 added a minimal platform-status page proving the frontend runs, can reach the
backend, and handles environment configuration correctly. Phase 2 adds a minimal asset
hierarchy UI (`/hierarchy`, `/machines/[machineId]`, `/sensors`) proving the backend's
domain data is real, navigable, and backend-driven — still not the final product UI, which
is built in Phase 28. See `IMPLEMENTATION_STATUS.md` and `docs/ASSET_HIERARCHY.md` §13.

## Structure

```
src/
  app/            App Router pages, layout, providers (TanStack Query)
                  /, /hierarchy, /machines/[machineId], /sensors
  components/     Shared presentational components
  hooks/          Client-side data hooks (wrap TanStack Query)
  lib/api/        Typed backend API client (tenantScopedFetch for asset-hierarchy routes)
  lib/env/        Environment configuration — public.ts (browser-safe) vs
                  server.ts (server-only, guarded by the `server-only` package)
```

Asset-hierarchy pages require a tenant context — see `publicEnv.demoTenantId`
(`NEXT_PUBLIC_DEMO_TENANT_ID`), a development-only stand-in for authentication documented
in `docs/ASSET_HIERARCHY.md` §3.2.

## Local development

```bash
cd frontend
npm install
npm run dev
```

Requires the backend reachable at `NEXT_PUBLIC_API_BASE_URL` (defaults to
`http://localhost:8000`; see root `.env.example`).

```bash
npm run lint
npm run typecheck
npm run format:check
npm run build
```

See `docs/DEVELOPER_SETUP.md` for the full local environment walkthrough.
