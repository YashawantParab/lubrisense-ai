# Industrial Adoption Boundary

This document draws a hard, explicit line between what LubriSense AI genuinely
demonstrates as working reference architecture and what a real, revenue-bearing
industrial deployment inside an enterprise customer's production environment would still
require. It exists because `CLAUDE.md`'s own product principle is unambiguous: *"This is
a production-grade reference implementation using synthetic data. Do not claim real
deployment readiness inside an enterprise customer's production environment until [these
things] are replaced or validated."*

Nothing in this repository should be read as a claim of production deployment against a
real customer's assets. Every synthetic component below is built behind a replaceable
interface specifically so it *can* be swapped for a real integration without redesigning
the platform (`docs/ARCHITECTURE.md` §10) — but swapping it is real, unfinished work, not
a configuration flag.

## What is genuinely real in this reference implementation

These are not mocked, not hardcoded, and not simplified for the demo — they are the actual
production-shaped logic a real deployment would keep:

- The full backend domain model, persistence layer, and API surface (FastAPI + PostgreSQL/
  TimescaleDB/pgvector, Alembic migrations, tenant-scoped RBAC, structured audit logging).
- The deterministic rules engine, baseline engine, feature engine, and Kalman-filter state
  estimator — real algorithms operating on real (if synthetic) telemetry rows, not
  scripted outputs.
- Condition Intelligence / Decision Intelligence / Workflow Intelligence as genuinely
  separate, evidence-weighted layers (`app/condition_intelligence`,
  `app/decision_intelligence`, `app/incidents`, `app/maintenance`) — not one LLM call
  pretending to be all three.
- The incident and maintenance-case lifecycle, technician finding/action/feedback
  workflow, and the CMMS draft-adapter boundary (draft-only, never an automatic external
  write — `docs/CMMS_INTEGRATION.md`).
- The RAG/knowledge-retrieval pipeline (embedding, chunking, `DRAFT → REVIEW → APPROVED →
  RETIRED` document lifecycle, citation-grounded answers, honest "insufficient approved
  documentation" fallback — `docs/RAG_KNOWLEDGE_SYSTEM.md`).
- The guarded agent's tool allowlist and draft-vs-action boundary (`docs/GUARDED_AGENT.md`)
  — it explains, retrieves, and drafts; it cannot operate machinery or change lubrication
  quantity, enforced structurally, not by prompt instruction alone.
- MLOps discipline: model registry with checksummed artifacts, an explicit human-gated
  promotion workflow, and an honest result — neither of the two trained models has
  actually cleared its own promotion gate (`docs/MODEL_CARD.md`), which this platform
  reports plainly rather than hiding.
- CI/CD, observability scaffolding (`/health`, `/ready`, `/metrics`, structured JSON
  logs), and resilience/degradation handling for ML/LLM/RAG/CMMS failures
  (`docs/RESILIENCE.md`).

## What is synthetic, and where

| Component | What's synthetic | Where |
|---|---|---|
| Sensor telemetry | All pressure/pump-current/reservoir-level/RPM/bearing-temperature/vibration readings | `simulator/`, `backend/scripts/seed_flagship_story.py`, `edge/scripts/generate_ml_training_data.py` |
| Asset hierarchy | Fictional but realistically-shaped customer/site/plant/line/machine topology | `backend/scripts/seed_demo_data.py` |
| Failure scenarios | Scripted degradation narratives (developing restriction, sudden blockage, leakage, pump degradation, sensor drift/dropout, etc.) | `docs/FAILURE_MODE_CATALOG.md`, `simulator/` scenario engine |
| Knowledge corpus | Synthetic reference documents (inspection procedures, fault-pattern references) | `backend/app/knowledge/corpus/documents.py` |
| Engineering thresholds/ranges | Demo-labeled physical limits (pressure bands, MAD multipliers, etc.) — explicitly *not* claimed as proprietary industrial specifications, per `CLAUDE.md` | `backend/app/*/config/*.yaml` |
| Demo identity/auth | Self-issued JWT-shaped demo tokens, a fixed six-role permission matrix | `backend/app/auth/demo_tokens.py`, `docs/SECURITY.md` |
| ROI/business-value figures | Labeled `DEMO / ESTIMATED VALUE` wherever shown (Metrics page) | `backend/app/product_metrics/` |
| Trained ML models | Trained on synthetic simulator output; explicitly not promoted to production status | `docs/MODEL_CARD.md`, `docs/MLOPS.md` |

## What a real deployment would require

Directly from `CLAUDE.md`'s own adoption boundary, made concrete to this codebase's
interfaces:

1. **Actual sensors** — real pressure/vibration/temperature/current transducers wired to
   real lubrication-system hardware, replacing `simulator`'s synthetic signal generation.
2. **Actual lubrication controller / PLC / edge protocol interfaces** — `edge/` currently
   implements a reference `TelemetrySource` interface
   (`docs/EDGE_ARCHITECTURE.md`) with only a synthetic source; a real deployment needs a
   real OPC-UA/Modbus/vendor-protocol adapter behind that same interface.
3. **Real asset hierarchy** — the customer's actual site/plant/machine topology, sensor
   inventory, and criticality data, replacing `seed_demo_data.py`.
4. **Real lubricant and application parameters** — actual lubricant types, delivery
   volumes, and duty cycles for the customer's real equipment.
5. **Validated physical limits** — the engineering thresholds in every
   `backend/app/*/config/*.yaml` policy file are demo assumptions; real deployment needs
   them reviewed and set by a qualified reliability engineer against the real asset, not
   inherited from this repository's synthetic defaults.
6. **Real failure history** — the rules/ML/state-estimation layers need to be validated
   (and the ML models specifically retrained and re-evaluated) against real historical
   failure data from the customer's fleet, not `simulator`-generated scenarios.
7. **Real historical telemetry** — enough real sensor history to build trustworthy
   baselines (`docs/BASELINES.md`) before condition intelligence can be trusted.
8. **Enterprise IAM** — replacing the demo token/role system (`docs/SECURITY.md`) with the
   customer's real identity provider (OIDC/SSO), consistent with the OIDC/OAuth2-compatible
   architecture this platform is already designed around.
9. **Real CMMS integration** — replacing the draft-only CMMS adapter boundary
   (`docs/CMMS_INTEGRATION.md`) with a live, authenticated integration to the customer's
   actual CMMS, still respecting the same "draft, never automatic action" boundary.
10. **Real ERP integration** — for the business/commercial data this platform currently
    models with synthetic customer accounts and service tiers.
11. **Internal API gateway** — this platform's API is deployment-ready in shape
    (versioned, authenticated, rate-limited — `docs/BACKEND_HARDENING.md`) but has not been
    placed behind or validated against a real enterprise API gateway/WAF.
12. **Cybersecurity approval** — a full security review/pentest against the customer's own
    standards; `docs/THREAT_MODEL.md` documents the threats this reference design
    considers, not an external audit result.
13. **Model validation** — a formal validation of any ML model against real, held-out
    customer data before it could be trusted for a real maintenance decision — beyond this
    platform's own internal promotion gate (`docs/MLOPS.md`), which is itself intentionally
    strict (and, honestly, not yet cleared by either trained model).
14. **Field validation** — a pilot period on real equipment with real technicians
    confirming the condition/decision outputs are actually useful and actionable before
    wider rollout.
15. **Functional-safety review** — for any lubrication system where a failure has safety
    (not just maintenance-cost) consequences, a functional-safety assessment independent
    of this platform's own guardrails (which are designed for maintenance decision support,
    not safety-instrumented control).

## Design principle already in place

Every item above is deliberately isolated behind an interface or configuration boundary in
this codebase — `TelemetrySource`, the CMMS draft adapter, the knowledge-document lifecycle
gate, the model-promotion gate, the OIDC-compatible auth boundary — precisely so that
closing this gap is a matter of implementing a real adapter behind an existing interface,
not re-architecting the platform. That is what "reference architecture" means here: the
shape is real and load-bearing; the data behind it, for now, is not.
