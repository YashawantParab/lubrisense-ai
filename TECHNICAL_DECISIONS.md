# LubriSense AI — Technical Decisions

This document records important architectural and product-engineering decisions.

Do not use this as a general notes file.

Record only decisions that materially influence the architecture, implementation, product behavior, security, scalability, or maintainability.

---

# Decision Format

For every decision use:

## ADR-XXX — Title

### Status

PROPOSED / ACCEPTED / SUPERSEDED / REJECTED

### Context

Why this decision is needed.

### Decision

What was chosen.

### Alternatives Considered

Other reasonable options.

### Why This Option

Why the selected option is preferred.

### Consequences

Positive and negative consequences.

### Revisit When

Conditions that may require reconsideration.

---

# ADR-001 — Production-Grade Reference Implementation

### Status

ACCEPTED

### Context

LubriSense AI is being built using synthetic industrial data because real proprietary industrial telemetry, controller interfaces, asset data, CMMS configuration, enterprise identity, and validated lubrication-domain parameters are unavailable.

The architecture should nevertheless represent how a commercial industrial condition-monitoring system would be structured.

### Decision

Build LubriSense AI as a production-grade reference implementation.

Internal platform capabilities must be functional.

External/proprietary dependencies must be isolated behind adapters or configuration boundaries.

Synthetic values must be explicitly identified as demo engineering assumptions.

### Alternatives Considered

1. Build only a portfolio demo.
2. Create only frontend visualizations.
3. Pretend synthetic integrations are real production integrations.

### Why This Option

It provides a credible industrial product architecture without falsely claiming proprietary production integration.

### Consequences

Positive:

- architecture can demonstrate enterprise product thinking
- real integrations can later replace adapters
- backend can be evaluated independently from synthetic data

Negative:

- some production connectors remain stubs/interfaces
- real field validation cannot be claimed

### Revisit When

Real industrial hardware, telemetry, enterprise systems, or validated domain parameters become available.

---

# ADR-002 — Three-Layer Intelligence Architecture

### Status

ACCEPTED

### Context

The product must clearly separate physical-data intelligence, maintenance decision logic, and GenAI-assisted workflow.

Combining all intelligence into one AI service would reduce explainability and create unsafe boundaries.

### Decision

Use three intelligence layers:

1. Machine & Sensor Intelligence
2. Decision Intelligence
3. Workflow Intelligence

Machine & Sensor Intelligence determines what is happening.

Decision Intelligence determines what it means and what action is appropriate.

Workflow Intelligence helps humans execute the action using RAG and guarded tools.

### Alternatives Considered

1. One generic AI service.
2. LLM-based diagnosis.
3. ML model directly producing maintenance work orders.

### Why This Option

The separation improves:

- safety
- explainability
- maintainability
- model governance
- graceful degradation

### Consequences

Requires more explicit interfaces between services, but produces a stronger industrial architecture.

### Revisit When

Only if strong evidence shows one layer should be merged without compromising safety or explainability.

---

# ADR-003 — Rules Before ML Where Physics Is Clear

### Status

ACCEPTED

### Context

Many industrial states can be identified using known deterministic conditions.

ML should not replace obvious physical rules merely to increase AI usage.

### Decision

Use deterministic rules where physical thresholds or known states are clear.

Use ML where:

- patterns are multivariable
- baselines vary
- fixed thresholds create excessive false alerts
- forecasting or anomaly detection provides additional value

### Alternatives Considered

1. ML for every condition.
2. Rules only.
3. LLM-based anomaly reasoning.

### Why This Option

Hybrid logic gives better explainability and resilience.

### Consequences

Requires maintaining both rule and model versions.

### Revisit When

Real domain validation indicates a different boundary.

---

# ADR-004 — LLMs Are Not Physical Control Systems

### Status

ACCEPTED

### Context

GenAI is useful for knowledge retrieval and maintenance workflow, but is non-deterministic and inappropriate as a direct machine controller.

### Decision

LLMs and agents may:

- retrieve documentation
- explain diagnoses
- summarize evidence
- find similar incidents
- generate inspection checklists
- draft work orders

LLMs and agents may not:

- start/stop machinery
- activate pumps
- change lubrication intervals
- change lubricant quantity
- override PLC logic
- modify safety parameters
- automatically close critical incidents

### Why This Option

Maintains a clear industrial safety boundary.

### Consequences

Human approval remains part of operational workflows.

---

# ADR-005 — Edge for Resilience, Central Platform for Fleet Intelligence

### Status

PROPOSED

### Context

Industrial systems must maintain essential monitoring during connectivity loss.

### Decision

Proposed responsibilities:

EDGE:

- sensor collection
- deterministic alarms
- buffering
- store-and-forward
- offline operation
- basic data-quality checks

CENTRAL PLATFORM:

- fleet analytics
- ML
- forecasting
- state estimation
- decision intelligence
- RAG
- model management
- business metrics

### Alternatives Considered

1. Cloud-only processing.
2. Full ML inference at edge.
3. Edge-only architecture.

### Why This Option

Provides resilience while keeping complex fleet intelligence centrally manageable.

### Consequences

Requires explicit synchronization and event-handling strategy.

### Revisit When

Actual target hardware and latency requirements are known.

---

# ADR-006 — MQTT and Kafka Have Different Responsibilities

### Status

PROPOSED

### Context

MQTT is commonly useful for device/gateway communication, while Kafka is better suited to scalable internal event streaming.

### Decision

Proposed:

Sensors / Edge
→ MQTT

Platform Ingestion
→ Kafka

Internal consumers use Kafka for:

- data-quality evaluation
- feature updates
- rule evaluation
- ML processing
- incident generation
- downstream analytics

### Alternatives Considered

1. MQTT only.
2. Kafka directly at device layer.
3. REST-only telemetry.

### Why This Option

Separates device communication from enterprise event processing.

### Consequences

Adds infrastructure complexity in local development.

### Revisit When

Phase 1 resource usage and architecture validation are completed.

---

# ADR-007 — PostgreSQL + TimescaleDB + pgvector

### Status

PROPOSED

### Context

LubriSense requires:

- relational domain data
- time-series telemetry
- vector retrieval

### Decision

Use:

PostgreSQL for domain/business data

TimescaleDB for telemetry

pgvector for RAG embeddings

### Alternatives Considered

- InfluxDB + PostgreSQL + external vector DB
- MongoDB
- Elasticsearch
- separate vector service

### Why This Option

Reduces infrastructure sprawl while providing required data capabilities.

### Consequences

Requires careful schema/index/retention design.

### Revisit When

Scale testing identifies a bottleneck.

---

# ADR-008 — Frontend Does Not Generate Product Truth

### Status

ACCEPTED

### Context

A polished UI can hide fake or disconnected backend functionality.

### Decision

All production-like values visible in the frontend must originate from backend APIs.

Examples:

- health scores
- conditions
- predictions
- confidence
- evidence
- work orders
- incidents
- business metrics

Frontend may only contain static content for:

- labels
- help text
- formatting
- navigation

### Consequences

Backend APIs must exist before final UI integration.

---

# ADR-009 — Technician Feedback Is Stored but Does Not Automatically Retrain Models

### Status

ACCEPTED

### Context

Technician findings are valuable labels but can be noisy, incomplete or incorrect.

### Decision

Store technician outcomes such as:

TRUE_POSITIVE
FALSE_POSITIVE
MISSED_FAILURE
INCONCLUSIVE

Use them as candidate future training data.

Do not automatically retrain or promote a production model based directly on operational feedback.

### Consequences

Requires model-governance workflow.

---

# ADR-010 — Asset Context Is Mandatory

### Status

ACCEPTED

### Context

Industrial sensor values are difficult to interpret without knowing the physical asset and operating context.

### Decision

Every relevant measurement and diagnosis must resolve through the asset hierarchy.

Required context may include:

- customer
- plant
- production line
- machine
- bearing
- lubrication system
- circuit
- lubrication point
- sensor
- firmware
- operating state
- maintenance history

### Consequences

Domain model is more complex but much more realistic.

---

# Pending Phase 0 Decisions

To evaluate during architecture work:

- exact service boundaries
- Kafka deployment approach
- event schema versioning format
- telemetry retention strategy
- health-score calculation strategy
- model registry implementation
- job queue implementation
- authentication approach for demo environment
- frontend charting library
- RAG embedding provider/model
- LLM provider abstraction
- Kubernetes packaging strategy

Do not accept these decisions without reviewing their trade-offs.