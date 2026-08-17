# LubriSense AI — Development Loop

This file defines how implementation work must be executed.

The goal is not to generate code once.

The goal is to:

BUILD
→ RUN
→ TEST
→ INSPECT
→ FIX
→ VERIFY
→ DOCUMENT
→ CONTINUE

---

# Before Every Phase

Always read:

1. CLAUDE.md
2. IMPLEMENTATION_STATUS.md
3. TECHNICAL_DECISIONS.md
4. relevant architecture/domain documentation
5. actual implementation

Do not assume documentation reflects reality.

Inspect the repository.

---

# Phase Loop

For the current phase:

## Step 1 — Understand

Identify:

- objective
- current implementation
- acceptance criteria
- dependencies
- risks
- blockers

---

## Step 2 — Plan

Create a short implementation plan.

Do not create a huge speculative roadmap.

Only plan the current phase.

---

## Step 3 — Implement

Implement the highest-priority incomplete acceptance criterion.

Do not jump into the next phase.

---

## Step 4 — Run

Actually execute the system or affected component.

Do not assume code compiles.

---

## Step 5 — Verify

Run relevant:

- unit tests
- integration tests
- type checks
- lint
- migrations
- API checks
- container health checks

For ML:

- verify feature pipeline
- verify train/test split
- verify model metrics
- verify model artifact
- verify inference

For telemetry:

- verify source
- verify event path
- verify persistence
- verify duplicates/out-of-order handling

---

## Step 6 — Diagnose

If something fails:

1. inspect logs
2. identify root cause
3. modify implementation
4. rerun affected test
5. rerun broader verification

Do not hide failing tests.

---

## Step 7 — Loop

Repeat:

IMPLEMENT
→ RUN
→ TEST
→ FIX

until acceptance criteria pass.

---

# Intelligence Feature Verification

For any intelligence capability, verify the entire chain.

## Machine & Sensor Intelligence

SENSOR / SIMULATOR
→ TELEMETRY
→ DATA QUALITY
→ FEATURE
→ RULE / ML / STATE ESTIMATION

Do not count a hardcoded prediction as intelligence.

---

## Decision Intelligence

RULE / MODEL OUTPUT
→ CONDITION ASSESSMENT
→ ASSET CONTEXT
→ DECISION ENGINE
→ RECOMMENDATION

Do not allow an LLM to replace this layer.

---

## Workflow Intelligence

DECISION
→ INCIDENT CONTEXT
→ RAG
→ APPROVED KNOWLEDGE
→ COPILOT
→ CHECKLIST / WORK ORDER
→ HUMAN APPROVAL

Do not allow GenAI to execute physical actions.

---

# Frontend Verification

For every value visible in the frontend verify:

1. Where does this value originate?
2. Is it from an API?
3. Does backend logic compute it?
4. Is it persisted where necessary?
5. Can it be reproduced?
6. Is it synthetic/demo clearly labelled if appropriate?

Never generate production-like health values inside React.

---

# Backend Verification

For every backend feature consider:

- domain ownership
- data validation
- persistence
- error handling
- idempotency
- authorization
- tenant scope
- observability
- tests
- failure behavior

---

# Failure Handling

If ML is unavailable:

rules must continue.

If LLM is unavailable:

monitoring and decisions must continue.

If Redis is unavailable:

critical monitoring should degrade safely.

If cloud is unavailable:

edge basic monitoring should continue.

If external CMMS is unavailable:

work order should remain in local draft/pending state.

---

# Blockers

If blocked by unavailable proprietary or enterprise integration:

1. document the blocker
2. create a clean interface/adapter
3. create a realistic demo implementation if appropriate
4. clearly label it as synthetic/mock external integration
5. continue all unblocked work

Do not invent proprietary APIs.

---

# Current Phase Completion

A phase is complete only when:

- all acceptance criteria pass
- critical tests pass
- no known critical runtime error remains
- implementation is not only a mock
- documentation reflects implementation
- IMPLEMENTATION_STATUS.md is updated
- meaningful architecture decisions are recorded

---

# Stop Rule

Do not automatically continue into the next phase unless explicitly instructed.

At the end of each phase report:

WHAT WAS BUILT

WHAT WAS VERIFIED

TEST RESULTS

KNOWN ISSUES

TECHNICAL DEBT

DECISIONS

NEXT PHASE

Then stop.

---

# Anti-Placeholder Rule

Do not treat the following as complete:

- TODO comments
- pass statements
- fake JSON
- random numbers
- static frontend arrays
- unconnected APIs
- untrained ML classes
- mock results shown as real results
- documentation without implementation

---

# Code Quality Loop

Before finishing a phase:

Backend:

- format
- lint
- type check
- test

Frontend:

- lint
- type check
- build where practical
- test

Containers:

- build
- start
- health check

Database:

- migrations
- constraints
- connectivity

---

# Final Loop Principle

The system must always move toward:

SENSOR
→ SIGNAL
→ CONDITION
→ DECISION
→ ACTION
→ OUTCOME
→ LEARNING

If a new feature does not strengthen that flow, question whether it belongs in the current scope.