# Observability (Phase 26)

## Purpose

Make the platform diagnosable — mostly a **review** of what Phase 1–20 already built,
plus targeted additions where a real gap existed.

## Structured logging — reviewed, unchanged

`app.core.logging` (Phase 1) already emits one JSON object per log line — `timestamp`,
`level`, `service`, `message`, `logger`, and `correlation_id` when available in request
context — with a human-readable console formatter for local development. No secrets or
sensitive payloads are logged anywhere in the Phase 21–27 diff (reviewed alongside the
docs/THREAT_MODEL.md "Secret leakage" review).

## Metrics

Every phase package already exposes its own `GET .../metrics` route rendering
`app.observability.metrics.WorkerMetrics` as Prometheus text (`/incidents/metrics`,
`/maintenance/cases/metrics`, `/knowledge/metrics`, `/agent/metrics`, and the workers'
own health-port `/metrics`). What was genuinely missing was a **cross-cutting HTTP
-request-layer** view — added this sprint:

`app.observability.http_metrics.HTTPMetricsMiddleware` wraps every request (registered
outermost in `app.main.create_app`, so it counts even TrustedHost/CORS-rejected
requests) and renders at the new `GET /api/v1/system/metrics`:

- `http_requests_total` — every request handled
- `http_requests_total_2xx` / `_4xx` / `_5xx` — by status class
- `http_requests_errors_total` — 5xx and unhandled exceptions
- `http_request_duration_seconds_avg` — incrementally-updated mean latency (no
  per-sample storage)
- `auth_failures_total` — incremented in `app.api.deps.get_current_principal` on any
  malformed header, invalid token, tenant mismatch, or missing-token-in-strict-mode
- `authorization_failures_total` — incremented in `app.auth.service
  .AuthorizationService.require` on a 403

New Phase 21–27 counters added to existing package metrics where relevant (no new
package-specific dashboard was needed — `cmms_draft_failures`, `agent_chat_turns`, etc.
from earlier phases already cover their own domains and were left unchanged).

`audit_write_failures` was deliberately **not** added as a separate counter: an
`AuditService.record()` failure is a database write failure like any other, and already
surfaces as the enclosing request's own `http_requests_total_5xx` — adding a redundant,
narrower counter for the same underlying event would be speculative instrumentation with
no distinguishing value, not a real gap (CLAUDE.md "no half-finished implementations" cuts
both ways — better to not add ceremony that adds nothing).

## Health / readiness — reviewed, unchanged

`GET /health` (liveness — always 200 if the process can serve requests at all) and
`GET /ready` (readiness — 503 if Postgres or Redis is unreachable) were already correct
per Phase 26 brief §26.3's own requirement ("liveness must not require every
dependency") since Phase 1. Reverified this sprint (`test_health_and_readiness_
endpoints`).

## Correlation / tracing

`CorrelationIdMiddleware` (Phase 1) already propagates a correlation id through every
request's logs and echoes it in the response header; `AuditEvent.correlation_id` and
`AgentToolCall.correlation_id` both default to the same request-scoped value, so a single
correlation id can trace HTTP request → log lines → audit event → agent tool call for one
turn.

No OpenTelemetry exporter was added this sprint — brief §26.5 explicitly says "do not
spend hours building a complex tracing stack" and offers "a documented optional exporter"
as sufficient when a full collector setup is disproportionate. The existing
`correlation_id` context var (`app.core.context`) is exactly the seam a real OTel
integration would extend (trace_id/span_id alongside it) without changing any call site
that already depends on `get_correlation_id()` — this was noted as the intended future
seam as far back as Phase 1's own module docstring, and remains accurate; no new work was
needed to keep that true.

## Operations view

`GET /api/v1/system/metrics`, `GET /api/v1/audit-events`, `GET /api/v1/fleet/overview`,
and `GET /api/v1/product-metrics` together give a later Phase 28 operational-status UI
everything it needs (request health, audit trail, fleet coverage, product metrics)
without building that UI now (brief explicitly: "Do not build the final observability
frontend now").

## Known limitations

- `HTTPMetricsMiddleware`'s counters are process-local (in-memory), like every
  `WorkerMetrics` instance in this codebase — restarting the backend resets them. A real
  deployment would scrape `/system/metrics` on an interval into a real Prometheus/Grafana
  stack (already an architectural goal per CLAUDE.md "Observability", unchanged by this
  sprint).
- No distributed tracing exporter is wired up — see "Correlation / tracing" above.
