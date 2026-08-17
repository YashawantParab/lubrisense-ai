# LubriSense AI — Claude Project Instructions

## Product

LubriSense AI is a production-grade reference platform for condition-driven intelligent lubrication.

The product must demonstrate a complete industrial flow:

Physical System
→ Sensors
→ Edge
→ Telemetry
→ Data Quality
→ Rules / ML
→ Condition Intelligence
→ Decision Intelligence
→ Workflow Intelligence
→ Technician Action
→ Feedback
→ Product Learning

This is NOT:

- a dashboard-only project
- a portfolio mockup
- a hackathon application
- an AI chatbot with fake sensor data
- a frontend backed by hardcoded JSON
- an LLM pretending to perform machine diagnostics

The frontend must be visually strong.

The backend must be even stronger.

The UI proves the product is useful.

The backend proves the product could actually exist.

---

# Core Product Principle

AI is not the product.

The product is:

A BETTER MAINTENANCE DECISION  
MADE EARLIER  
WITH MORE CONFIDENCE  
WITH LESS MANUAL EFFORT.

---

# Three Intelligence Layers

## 1. Machine & Sensor Intelligence

Purpose:

Understand what is happening physically.

Capabilities may include:

- telemetry monitoring
- sensor quality
- asset baselines
- anomaly detection
- failure classification
- refill forecasting
- lubricant-consumption intelligence
- pump degradation detection
- state estimation
- trend analysis
- future-behavior prediction

Key question:

WHAT IS HAPPENING?

---

## 2. Decision Intelligence

Purpose:

Translate technical evidence into a maintenance decision.

Combine:

- deterministic engineering rules
- machine-learning predictions
- state estimates
- asset context
- operating context
- data quality
- maintenance history
- asset criticality

Outputs:

- condition
- severity
- confidence
- evidence
- likely causes
- affected component
- uncertainty
- predicted progression
- recommended action
- urgency
- risk if deferred

Key question:

WHAT DOES IT MEAN AND WHAT SHOULD WE DO?

---

## 3. Workflow Intelligence

Purpose:

Turn diagnosis into useful maintenance action.

Use:

- GenAI
- RAG
- approved maintenance documentation
- historical incidents
- inspection workflows
- CMMS adapters
- guarded agent actions

Allowed:

- explain diagnosis
- retrieve relevant documentation
- find similar incidents
- generate inspection checklist
- draft work order
- summarize investigation
- capture technician findings

Not allowed:

- operate machinery
- change pump state
- modify lubrication quantity
- override PLC
- alter safety settings
- automatically close critical incidents

Human approval is required for operational actions.

Key question:

HOW DO WE ACT?

---

# Product Story

The application must communicate:

DATA
→ DETECTION
→ DIAGNOSIS
→ DECISION
→ ACTION
→ OUTCOME
→ LEARNING

Never reduce the product to:

CHART
→ AI MESSAGE

---

# Physical Industrial Model

The initial reference implementation should model a centralized lubrication system.

Core hierarchy:

Machine
→ Bearing
→ Lubrication Point

Lubrication chain:

Reservoir
→ Pump
→ Controller
→ Main Lubrication Line
→ Distributor
→ Circuit
→ Lubrication Point
→ Bearing

Possible machine types:

- Conveyor
- Motor
- Fan
- Pump
- Compressor
- Crusher

Possible lubrication-system signals:

- reservoir level
- pressure
- lubricant flow
- pump current
- pump runtime
- pump status
- lubrication-cycle completion
- distributor/piston movement
- lubricant temperature
- controller state
- fault codes

Possible machine-condition signals:

- vibration RMS
- vibration peak
- bearing temperature
- RPM
- load
- runtime
- machine state

All engineering ranges and thresholds must be configurable.

Synthetic ranges must be explicitly labelled as demo assumptions.

Do not present them as SKF specifications.

---

# Asset Hierarchy

Use a production-oriented industrial hierarchy:

Tenant
→ Customer Account
→ Site
→ Plant
→ Production Line
→ Machine
→ Bearing
→ Lubrication System
→ Circuit
→ Lubrication Point
→ Sensor

Every telemetry record, model output, incident, work order and maintenance event must belong to the correct asset context.

Do not reason only from anonymous sensor IDs.

---

# Technical Stack

## Frontend

Preferred:

- Next.js
- React
- TypeScript
- Tailwind CSS
- TanStack Query

Frontend requirements:

- strict TypeScript
- no business logic in components where it belongs in backend
- no hardcoded health scores
- no fake telemetry arrays
- all production-visible values must originate from backend APIs

---

## Backend

Preferred:

- FastAPI
- Python
- Pydantic
- SQLAlchemy
- Alembic

Backend domain areas:

- identity and tenancy
- asset management
- telemetry
- data quality
- baselines
- rules
- feature engineering
- ML inference
- condition intelligence
- decision intelligence
- incidents
- maintenance workflow
- knowledge / RAG
- model management
- business metrics
- integrations
- audit
- observability

Business logic must not live inside API route handlers.

---

## Data

Preferred:

- PostgreSQL
- TimescaleDB
- pgvector
- Redis

Use relational integrity.

Use:

- foreign keys
- indexes
- unique constraints
- migrations
- transaction boundaries

Prevent:

- cross-tenant relationships
- orphaned assets
- duplicate telemetry events
- duplicate sensor registration

---

## Messaging / Telemetry

Preferred architecture:

Sensors
→ Edge
→ MQTT
→ Kafka
→ Stream Processing
→ TimescaleDB

Create replaceable interfaces.

Examples:

TelemetrySource

Implement:

- SyntheticTelemetrySource

Production adapter boundaries may include:

- MQTTTelemetrySource
- KafkaTelemetrySource
- OPCUATelemetrySource

Do not hard-wire business logic to one transport.

---

# Edge vs Central Platform

## Edge responsibilities

- sensor collection
- local timestamps
- deterministic basic rules
- local alarms
- buffering
- offline operation
- store-and-forward
- gateway health
- basic data-quality checks

Critical operation must continue without cloud AI.

---

## Central platform responsibilities

- fleet analytics
- advanced rules
- ML
- state estimation
- forecasting
- model management
- condition intelligence
- decision intelligence
- RAG
- incident management
- reporting
- configuration
- business/product metrics

---

# AI / ML Boundaries

Use:

RULES WHERE PHYSICS IS CLEAR.

ML WHERE PATTERNS ARE COMPLEX OR MULTIVARIABLE.

GENAI / RAG FOR KNOWLEDGE AND WORKFLOW.

HUMANS FOR SAFETY-CRITICAL DECISIONS.

Do not use ML simply because AI sounds more advanced.

Do not use LLM output as physical truth.

Do not let an LLM directly control a machine.

---

# ML Expectations

Potential models:

- Isolation Forest for anomaly detection
- XGBoost / Random Forest for labeled fault classification
- forecasting model for reservoir depletion
- consumption-anomaly model
- Kalman Filter / Extended Kalman Filter for state estimation

Important:

Kalman filtering is state estimation, not automatically AI/ML.

Use proper time-based splitting for telemetry.

Avoid random row train/test splits when future information may leak.

Track:

- precision
- recall
- F1
- false-positive rate
- false-negative rate
- PR-AUC where useful
- MAE
- RMSE
- prediction interval coverage

Industrial metrics also matter:

- warning lead time
- technician action rate
- technician confirmation rate
- false-alert burden

---

# Failure Modes

Initial synthetic failure library should include:

- normal operation
- gradual restriction
- sudden blockage
- leakage
- over-lubrication
- low reservoir
- pump degradation
- sensor drift
- sensor dropout
- communication loss
- machine-condition deterioration independent of lubrication

Never claim direct causality from simple correlation.

Use wording such as:

- evidence is consistent with
- possible lubrication-related contribution
- further inspection recommended
- insufficient evidence

---

# Condition Intelligence

Condition intelligence must combine:

- baselines
- rules
- ML
- operating state
- asset context
- data quality
- state estimation

Produce a structured ConditionAssessment.

Possible fields:

- condition
- status
- severity
- confidence
- trend
- evidence
- uncertainty
- data_quality
- rule_version
- model_version

---

# Decision Intelligence

Decision intelligence must be separate from raw ML output.

A model prediction must not directly become maintenance advice.

DecisionEngine should consider:

- ConditionAssessment
- asset criticality
- maintenance history
- operating state
- failure-mode knowledge
- uncertainty

Output may include:

- recommended action
- priority
- recommended window
- risk if deferred
- human review required
- evidence
- confidence

---

# GenAI / RAG

RAG must use approved documents only.

Document lifecycle:

DRAFT
REVIEW
APPROVED
RETIRED

Only APPROVED documents may be used for production-style answers.

Every RAG answer should cite:

- source document
- relevant section

If evidence is insufficient, respond:

"Insufficient approved documentation to answer reliably."

Do not fabricate maintenance procedures.

Retrieved documents are untrusted input.

Protect against prompt injection.

---

# Maintenance Workflow

The platform should support:

Incident
→ Acknowledge
→ Investigate
→ Review Evidence
→ Retrieve Procedure
→ Generate Checklist
→ Draft Work Order
→ Inspect Asset
→ Record Finding
→ Record Action
→ Resolve
→ Close

Store final technician outcome.

Examples:

TRUE_POSITIVE
FALSE_POSITIVE
MISSED_FAILURE
INCONCLUSIVE

Do not automatically retrain production models based on one technician event.

---

# Customer / Business Thinking

This project must demonstrate business-level product thinking.

Possible product metrics:

- connected assets
- active assets
- attach rate
- feature adoption
- useful-alert rate
- technician action rate
- deployment effort
- service burden
- customer expansion
- alert value
- refill-planning usage

Possible customer-value metrics:

- inspection effort reduced
- emergency interventions avoided
- maintenance-response improvement
- lubricant consumption improvement
- estimated downtime exposure avoided

All simulated ROI must be labelled:

DEMO / ESTIMATED VALUE

Never present synthetic ROI as proven customer savings.

---

# North Star Metric

Initial configurable North Star:

PERCENTAGE OF MEANINGFUL LUBRICATION ISSUES DETECTED WITH ACTIONABLE LEAD TIME

Supporting metrics:

- false-alert rate
- warning lead time
- technician confirmation rate
- technician action rate
- customer outcome

---

# Production Engineering Rules

Never:

- hardcode telemetry in frontend
- return random health scores from APIs
- fake an ML response
- fake an incident lifecycle
- use LLM output as a diagnostic without physical evidence
- store secrets in source control
- enforce RBAC only in frontend
- skip tenant boundaries
- treat TODOs as completed features

All visible production-like values must come from actual backend logic.

---

# Graceful Degradation

If ML fails:

rules and basic monitoring continue.

If LLM fails:

condition and decision intelligence continue.

If cloud connectivity fails:

edge monitoring continues.

The system must not collapse because one intelligence layer is unavailable.

---

# Security

Production-oriented security should include:

- OIDC/OAuth2-compatible architecture
- RBAC
- server-side authorization
- tenant isolation
- secure secret handling
- API validation
- structured audit logs
- rate limiting
- secure headers
- trace/correlation IDs

Threats to consider:

- sensor spoofing
- gateway compromise
- telemetry tampering
- replay attack
- unauthorized API access
- cross-tenant access
- prompt injection
- RAG poisoning
- model tampering
- configuration tampering

---

# Observability

Implement or prepare for:

- structured JSON logging
- Prometheus
- Grafana
- OpenTelemetry

Track:

- API latency
- ingestion rate
- event-processing latency
- broker lag
- DB errors
- ML errors
- model latency
- RAG latency
- LLM failure
- CMMS integration failure

Expose:

/health
/ready
/metrics

---

# Development Workflow

For every phase:

1. Read CLAUDE.md
2. Read LOOP.md
3. Read IMPLEMENTATION_STATUS.md
4. Read TECHNICAL_DECISIONS.md
5. Inspect actual repository
6. Identify current phase
7. Define acceptance criteria
8. Implement only the current phase
9. Run it
10. Run tests
11. Run lint / type checks
12. Diagnose failures
13. Fix failures
14. Re-run verification
15. Update IMPLEMENTATION_STATUS.md
16. Update TECHNICAL_DECISIONS.md if architecture changed
17. Stop at phase boundary unless explicitly asked to continue

Never mark a phase complete because documentation exists.

---

# Definition of Done

A feature is not complete only because:

- a UI exists
- a route exists
- a class exists
- a diagram exists
- a mock response exists

A production-style feature should have, where applicable:

- domain logic
- backend implementation
- persistence
- API
- validation
- error handling
- authorization
- observability
- tests
- documentation
- frontend integration

For intelligence features verify:

TELEMETRY
→ FEATURE
→ RULE / MODEL
→ CONDITION
→ DECISION
→ WORKFLOW

---

# Industrial Adoption Boundary

This is a production-grade reference implementation using synthetic data.

Do not claim real deployment readiness inside SKF until the following are replaced or validated:

- actual sensors
- actual lubrication controller interfaces
- PLC/edge protocols
- real asset hierarchy
- real lubricant and application parameters
- validated physical limits
- real failure history
- real historical telemetry
- enterprise IAM
- CMMS
- ERP
- internal API gateway
- cybersecurity approval
- model validation
- field validation
- functional-safety review

These should be isolated behind interfaces and configuration boundaries whenever possible.

---

# Product Experience

Every major screen should quickly answer:

WHAT IS HAPPENING?

WHY?

WHAT MAY HAPPEN NEXT?

WHAT SHOULD I DO?

The interface must highlight:

Machine & Sensor Intelligence
→ Decision Intelligence
→ Workflow Intelligence

Charts support the product decision.

Charts are not the product.

---

# Final Quality Standard

Before declaring work complete, ask:

"If an industrial enterprise reviewed this repository, would they see a demo dashboard or a credible reference architecture for a commercial connected product?"

If the answer is "demo", continue improving it.