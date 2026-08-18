# Tests

Cross-cutting and integration tests that span multiple services.

Per-service test suites live alongside their service (e.g. `backend/tests/`) and are the
primary test suite in Phase 1. This directory is reserved for tests that exercise more
than one service together (e.g. frontend-to-backend, edge-to-platform) once those flows
exist — starting from Phase 2 onward.
