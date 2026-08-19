# Security / Authorization (Phase 24)

## Purpose

A production-faithful authorization boundary for this demo/reference platform — not a
fake enterprise identity integration (CLAUDE.md "Do not build fake enterprise identity
integrations").

## Auth architecture

`app.auth.demo_tokens.DemoTokenProvider` issues and verifies a self-signed,
JWT-*shaped* bearer token (base64url header.payload.signature, HMAC-SHA256, an expiry
claim) — deliberately shaped like a real OIDC/JWT token so the seam this replaces is
obvious: a production deployment swaps this provider for real OIDC/JWT verification
against an external IdP's JWKS, and nothing downstream of `app.api
.deps.get_current_principal` changes. **This is demo authentication, not a real identity
provider** — no paid IdP is required or assumed (Phase 24 brief §24.1).

`POST /api/v1/auth/demo-login` (body: `{"role": "..."}`) issues a token for one of six
fixed demo identities (`app.auth.demo_users.DEMO_USERS`), scoped to the tenant resolved
from `X-Tenant-ID`. The response is clearly a demo artifact — `demo-viewer`,
`demo-admin`, etc. — never presented as a real user.

## Roles

`UserRole` (`app.domain.enums`) — `VIEWER`, `TECHNICIAN`, `RELIABILITY_ENGINEER`,
`PLANT_MANAGER`, `DATA_SCIENTIST`, `ADMIN`.

## Role / permission matrix

`app.auth.permissions.ROLE_PERMISSIONS` — the single source of truth (ADR-149):

| Role | Read incidents/maintenance/knowledge | Manage incidents | Write maintenance | Knowledge admin | CMMS | Assistant | Metrics | Audit read |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| VIEWER | ✅ | | | | | | ✅ | |
| TECHNICIAN | ✅ | | ✅ | | | ✅ | ✅ | |
| RELIABILITY_ENGINEER | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PLANT_MANAGER | ✅ | ✅ | ✅ | | ✅ | ✅ | ✅ | ✅ |
| DATA_SCIENTIST | ✅ | | | | | | ✅ | |
| ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Rationale for the deliberately narrow rows:

- **VIEWER** — read-only dashboards/intelligence only (§24.3), matching the brief
  exactly.
- **DATA_SCIENTIST** — model/feature/knowledge metadata visibility, explicitly *no*
  operational mutation and *no* assistant access — the brief's "no operational machinery
  control" is interpreted narrowly here as "no ability to change the state of a
  maintenance workflow," which also excludes triggering agent tool calls (§24.3).
- **PLANT_MANAGER** gets operational oversight and CMMS but not `KNOWLEDGE_ADMIN` —
  knowledge lifecycle curation is a reliability-engineering/admin function in this model,
  not a plant-management one; a real deployment may reasonably grant it more broadly —
  the matrix is a policy choice, not a technical constraint.
- **ADMIN** is the only role with `Permission.ADMIN_CONFIG`, and gets every other
  permission (`frozenset(Permission)`) — CLAUDE.md §24.3 explicitly warns "Do not assume
  ADMIN means physical machine control"; no permission in this matrix grants any (no
  physical-control capability exists anywhere in this platform).

## Authorization service

`app.auth.service.AuthorizationService.require(principal, permission)` is the **only**
place a role is compared against a permission — no endpoint anywhere does a raw
`if principal.role == "ADMIN"` string check (Phase 24 brief §24.4). `app.api.deps
.require_permission(permission)` wraps it as a FastAPI dependency, applied to exactly the
mutating/admin surfaces enumerated in §24.7:

- Incident acknowledge / start-investigation / resolve / close / reopen — `INCIDENT_MANAGE`
- Maintenance case create / plan / start / finding / action / complete / cancel — `MAINTENANCE_WRITE`
- CMMS draft creation — `CMMS_MANAGE`
- Knowledge ingest / submit-for-review / approve / retire — `KNOWLEDGE_ADMIN`
- Agent chat — `AGENT_USE`
- Customer/site/fleet overview, product metrics — `METRICS_READ`
- Audit event read — `AUDIT_READ`

Plain read endpoints predating Phase 24 (asset hierarchy, telemetry, rules, features, ML,
condition/decision/prognostic reads, etc.) remain tenant-scoped-only, unchanged — see
"Known limitation" below.

## Backward compatibility

`get_current_principal` resolves identity from `Authorization: Bearer <token>` when
present. When **absent**:

- `AUTH_ENFORCEMENT_MODE=strict` (mandatory in production, enforced by `Settings
  .model_post_init` — see docs/BACKEND_HARDENING.md) → `401 AUTH_REQUIRED`.
- `AUTH_ENFORCEMENT_MODE=permissive` (the local/demo default) → a full-access fallback
  `Principal` (`role=ADMIN`) bound to the already-validated tenant.

This is what let all 600 tests written before Phase 24 keep passing completely unchanged
— none of them ever sent an `Authorization` header, and permissive mode treats that
exactly as it always implicitly did (full access once a valid `X-Tenant-ID` is
presented). It is **not** a bypass for a caller that *does* present a token: a token
whose `tenant_id` claim doesn't match the resolved tenant is rejected with `403` in
*both* modes (`test_token_rejected_for_a_different_tenant`). New RBAC-restriction tests
(`tests/test_api_auth_rbac.py`) run their own `strict_client` fixture with
`AUTH_ENFORCEMENT_MODE=strict` set explicitly, so real role restriction is genuinely
exercised, not just asserted.

## Tenant isolation (§24.5)

Re-verified across every layer this sprint touches, in addition to the extensive
pre-existing tenant-isolation coverage from Phases 2–20: `test_token_rejected_for_a_
different_tenant`, `test_audit_events_are_tenant_scoped`, and the
`instrumented_asset_coverage` cross-tenant bug (found and fixed — see
docs/PRODUCT_METRICS.md) all confirm cross-tenant access fails closed.

## Agent authorization (§24.8)

The guarded agent's tool functions (`app.agent.tools.tool_functions`) all take an
explicit `tenant_id` from the already-authenticated request context — the agent has no
code path that accepts a client-supplied tenant id independent of the authenticated
principal's own tenant, and (per docs/GUARDED_AGENT.md) no tool exists that could mutate
state even if it wanted to. `POST /agent/chat` itself requires `Permission.AGENT_USE`
like any other endpoint — the agent cannot be used as an authorization bypass because it
sits *behind* the same `require_permission` gate as everything else, not beside it.

## CORS / security headers

`CORSMiddleware`/`TrustedHostMiddleware` (Phase 1) already read from
`CORS_ALLOWED_ORIGINS`/`TRUSTED_HOSTS`; Phase 24 adds the fail-fast production check that
neither may be a wildcard in production (see docs/BACKEND_HARDENING.md).

## Secret scan

Repository-wide scan for hardcoded credentials/API keys/passwords/tokens in the Phase
21–27 diff found none. `demo_auth_secret`'s local-dev default is intentionally
recognizable as insecure (`local-dev-insecure-demo-auth-secret-do-not-use-in-
production`) and is refused outright in production by config validation.

## Known limitation

Authentication/authorization is enforced everywhere `require_permission` is used (every
Phase 21–25 mutating/admin/metrics/audit endpoint) but **not** retrofitted onto the
~90 pre-existing read endpoints from Phases 2–20 (asset hierarchy, telemetry, rules,
features, ML, condition/decision/prognostic/incident/maintenance reads). Those remain
tenant-scoped-only, exactly as before this sprint. Extending `require_permission` to
every read endpoint in the platform is a larger, separable follow-up — documented here
rather than silently left unstated.

See docs/THREAT_MODEL.md for the full threat model this design was built against.
