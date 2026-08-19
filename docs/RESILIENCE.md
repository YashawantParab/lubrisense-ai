# Resilience (Phase 27)

## Purpose

Ensure one failing dependency degrades gracefully rather than taking down the whole
product (CLAUDE.md "Graceful Degradation" — a foundational principle since Phase 1, not
new to this sprint). This document consolidates that guarantee across every dependency
and records what was newly verified/added.

## Dependency degradation matrix

| Dependency | Affected capability | Unaffected capability | Fallback | Recovery |
|---|---|---|---|---|
| ML (`MLInferenceResult` absent) | ML-derived evidence inside `ConditionAssessment` | Rules-based condition/decision, quality, baselines, incidents, maintenance | `ConditionEngine` synthesizes from remaining evidence sources with lower confidence and an explicit limitation — never reports HEALTHY merely because ML is absent | Next `MLInferenceResult` resumes normal synthesis automatically |
| State estimation (`StateEstimate` absent) | Prognostics/forecasts, state-derived condition evidence | Rules/quality/ML-only condition synthesis | `PrognosticEngine` returns `NO_RELIABLE_FORECAST` (a first-class outcome, not a fabricated number); condition assessment continues from remaining evidence | Next `StateEstimate` resumes automatically |
| Approved knowledge / RAG (no sufficient match) | Authoritative, cited procedural answers | Condition/decision/incident explanation from persisted platform data; all non-RAG tool calls | Exact `INSUFFICIENT_DOCUMENTATION_TEXT` fallback — never a hallucinated answer | Ingesting/approving a relevant document resolves it immediately |
| LLM provider (`compose_answer`) | Natural-language answer composition/fluency | All persisted-evidence retrieval, tool execution, RAG citations, draft generation | Deterministic fallback sentence + a `limitations` entry; `app.core.resilience.CircuitBreaker` (`_LLM_CIRCUIT_BREAKER`, 3-failure threshold) trips after repeated failures so a known-broken provider isn't retried on every turn | Breaker half-opens after 30s and closes on the next successful call |
| CMMS adapter | External work-order draft creation/read | The underlying `MaintenanceCase` workflow itself (plan/start/finding/action/complete/cancel) | `CMMSUnavailableError`, `MaintenanceCase` left completely untouched (reverified: `test_cmms_adapter_failure_isolated_from_maintenance_case`) | Caller retries `create_draft`; idempotent per case |
| Redis | Nothing load-bearing — connectivity/health-probe only, no business logic depends on it yet | Everything else | `/ready` reports it unhealthy; `/health` unaffected | Reconnects automatically via `redis.asyncio` |
| Kafka | Real-time telemetry ingestion during the outage | Edge-local buffering, all intelligence/workflow layers operating over already-persisted data | MQTT bridge spools to a local SQLite file (`PIPELINE_BRIDGE_SPOOL_PATH`) until Kafka recovers | Automatic drain on reconnect (Phase 5/6, unchanged) |
| Postgres | Everything requiring persistence — effectively the whole platform | Process liveness (`/health`) | `/ready` reports 503; any in-flight request touching the DB gets a clean structured 500, never a raw traceback (reverified: `test_unhandled_exception_returns_clean_error_envelope_not_a_traceback`) | Standard Postgres recovery; no manual application-level repair needed |

## Failure principle (unchanged, reconfirmed)

- ML down → rules/state/basic monitoring still operate where possible.
- LLM down → intelligence/incident/maintenance continue; the agent degrades to
  deterministic evidence retrieval.
- RAG down (insufficient documentation) → no authoritative procedural answer, but the
  core product continues.
- CMMS down → local maintenance workflow continues unaffected.
- Database unavailable → clean, structured failure at the API layer; no crash, no leaked
  internals.
- Kafka temporarily unavailable → existing spool/retry behavior (Phase 5/6) remains.

## Circuit breaker (new this sprint)

`app.core.resilience.CircuitBreaker` — a minimal, in-process closed/open/half-open
breaker (stdlib only, no new dependency). Deliberately **not** wrapped around this
platform's local, deterministic services (the demo CMMS adapter, the hashing embedding
provider, `DemoLLMProvider` itself) — CLAUDE.md is explicit that circuit-breaking a call
that never does I/O is ceremony with no benefit. The one place it's wired in today is
`AgentService`'s call into whichever `LLMProvider` is configured — the seam that becomes
a real external network call the moment an `ExternalLLMProvider` implementation is
configured. It is a module-level singleton (`_LLM_CIRCUIT_BREAKER`), not a per-request
instance, so consecutive-failure state genuinely accumulates across turns. Process-local,
not shared across replicas — acceptable for this reference platform's single-backend
-process demo deployment; a multi-replica production deployment would want this state in
a shared store (e.g. Redis) — documented as a known limitation, not silently assumed
solved.

## Retries

No uncontrolled/nested retry exists anywhere in the request path (reviewed alongside
docs/BACKEND_HARDENING.md "Retry policy"). The MQTT bridge's spool-and-drain retry
(Phase 5/6) remains the one place retry-with-backoff genuinely applies, and was already
centralized and documented before this sprint.

## Database outage — not rebuilt, reverified

Phase 6 already built the outage/store-and-forward architecture at the ingestion layer;
this sprint did not rebuild it (brief §27.5: "Do not rebuild Phase 6 outage
architecture"). What Phase 27 adds is a reverification at the **synchronous API layer**:
forcing a real exception inside a request confirms the response stays a clean structured
500 rather than leaking internals — see the matrix row above and
`test_unhandled_exception_returns_clean_error_envelope_not_a_traceback`.

## Focused failure tests (§27.12)

Deliberately not a chaos-testing platform. `tests/test_resilience.py` (circuit breaker
unit tests) and `tests/test_resilience_degradation.py` (CMMS isolation, DB-outage-proxy)
cover what's genuinely new this sprint. ML-unavailable and state-estimation-unavailable
degradation are already exercised throughout the entirety of
`tests/condition_intelligence/test_condition_engine.py` (every test there runs with no
`MLInferenceResult`/`StateEstimate` present — structurally identical to "unavailable"
from `ConditionEngine`'s perspective) and RAG/LLM-unavailable degradation is already
covered by `tests/knowledge/test_retrieval.py` and `tests/agent/test_agent_service.py` —
re-running or duplicating that coverage here would be exactly the "rerun every historical
scenario" this sprint's own testing strategy says not to do.

## Recovery

No dependency listed above requires manual database repair to recover — every fallback
path above is either automatic (spool drain, breaker half-open, reconnect) or resumes on
the very next successful call (§27.11).
