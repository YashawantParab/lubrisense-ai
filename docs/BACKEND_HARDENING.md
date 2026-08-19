# Backend Hardening (Phase 23)

## Purpose

Harden the backend without rewriting working architecture (CLAUDE.md "Preserve the
current architecture and working functionality"). Much of this section's brief was
already satisfied by decisions made as early as Phase 1–2; this document records what
was **reviewed and confirmed already correct**, and what was **newly added** this sprint.

## Error handling — already correct, reviewed

`app.core.errors` (Phase 1) already gives every error response — deliberate
(`ApplicationError` and its `NotFoundError`/`ConflictError`/`InvalidHierarchyError`/
`ServiceUnavailableError` subclasses) or unexpected — the same envelope:

```json
{"code": "...", "message": "...", "details": {}, "correlation_id": "..."}
```

`handle_unexpected_error` logs the full exception server-side but never returns a stack
trace or exception text in the response body — reverified this sprint with
`test_unhandled_exception_returns_clean_error_envelope_not_a_traceback`
(`tests/test_resilience_degradation.py`), which forces a real `ConnectionError` deep in a
request and confirms the response body contains neither the exception message nor the
word "Traceback".

New this sprint: `403 FORBIDDEN` (RBAC), `401` (`AUTH_REQUIRED`/`AUTH_TOKEN_INVALID`/
`AUTH_HEADER_MALFORMED`), and `413 REQUEST_ENTITY_TOO_LARGE` (request-size limits, below)
all flow through the identical envelope — no special-cased response shape for Phase 24's
new error paths.

## Timeouts

- Database: `database_pool_timeout_seconds` (Phase 1) already bounds how long a request
  waits for a pool connection.
- Redis: connectivity/health-probe only (`app.infrastructure.redis_client`) — no
  business logic depends on it yet, so a hung Redis call cannot block a request; the
  `/ready` probe reports it unhealthy without affecting `/health`.
- CMMS adapter / LLM provider: both are in-process, local, deterministic calls today (no
  real external network call exists in either — see docs/CMMS_INTEGRATION.md and
  docs/GUARDED_AGENT.md). A per-call timeout on a call that never does I/O would be
  ceremony with no effect; the seam that will need one — `ExternalLLMProvider` /  a real
  CMMS vendor adapter — is exactly where `app.core.resilience.CircuitBreaker` (Phase 27)
  is already wired in, so a hanging or repeatedly-failing real implementation trips the
  breaker rather than blocking every subsequent request.

## Retry policy

No nested/uncontrolled retries exist anywhere in the request path. The one place a retry
concept applies — the MQTT bridge's store-and-forward spool (Phase 5/6,
`pipeline_retry_max_backoff_seconds`) — was already centralized and documented before
this sprint; reviewed, unchanged.

## Request limits (new this sprint)

- `AGENT_MESSAGE_MAX_LENGTH` (default 2000 chars) — `POST /agent/chat` returns `413` over
  the limit, checked before any tool call or LLM composition is attempted.
- `KNOWLEDGE_DOCUMENT_MAX_CONTENT_LENGTH` (default 200,000 chars) — `POST
  /knowledge/documents` returns `413` over the limit.
- History-range/result-count limits already existed broadly before this sprint (e.g.
  `Query(ge=1, le=1000)` on incident/case listing, `Query(ge=1, le=200)` on customer
  listing) — reviewed, unchanged.

## Pagination

`app.repositories.pagination.PageParams`/`Page` (Phase 2) already caps `limit` at 200 and
is used by every new Phase 21/25 list endpoint (`GET /audit-events`, `GET /customers`) —
no new pagination mechanism was introduced; the existing one was reused, per CLAUDE.md
"preserve the current architecture."

## Idempotency — reviewed, unchanged

Every mutating endpoint whose duplicate-request risk is realistic was already made
idempotent in its owning phase: `POST /customers` (unique code), `POST
/maintenance/cases` (one active case per incident), `POST /knowledge/documents` (same
key/version/content returns the existing row), `POST
/maintenance/cases/{id}/cmms-draft` (one draft per case). No gaps were found this sprint.

## Configuration validation (new this sprint)

`Settings.model_post_init()` fails fast at process startup when `APP_ENV=production`
and any of the following hold — never silently starting with an unsafe default:

- `AUTH_ENFORCEMENT_MODE` is not `strict`
- `DEMO_AUTH_SECRET` is left at its insecure local-dev default
- `CORS_ALLOWED_ORIGINS` or `TRUSTED_HOSTS` contains a wildcard

## Database review — reviewed, no redesign

Indexes, unique constraints, tenant-scoped composite foreign keys, cascade behavior, and
nullable fields were reviewed table-by-table across the schema added since Phase 2; no
gap was found that warranted a new migration this sprint beyond the two genuinely new
tables (`audit_event`) and the RBAC/audit wiring itself. The one pre-existing, already
-documented autogenerate false positive (three DESC-index diffs `alembic check` always
reports) remains unchanged and is not a real drift (ADR-022).

## Backpressure / expensive work

No new synchronous, unbounded, heavy operation was introduced this sprint. Phase 21/22's
aggregation queries are bounded by the tenant's own row counts (no cross-tenant scans);
`FleetOverview.customers_by_status` is the one place that runs O(customers) queries
rather than a single grouped query — acceptable at this reference platform's scale,
documented as a known limitation in docs/CUSTOMER_SERVICES.md rather than silently
accepted. No new task queue was introduced (CLAUDE.md "Do not introduce a task queue
unless genuinely necessary").

## Backward compatibility

Every one of the 600 pre-Phase-21 tests still passes unchanged after this sprint's RBAC
introduction — see docs/SECURITY.md "Backward compatibility" for how the permissive-mode
default principal makes this possible without touching any existing test's request
headers.
