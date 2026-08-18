# ML Service

Owns model training, evaluation, and inference for Machine & Sensor Intelligence:
anomaly detection, failure-mode classification, refill/consumption forecasting, and
Kalman/state estimation (`docs/ARCHITECTURE.md` §4.1, §7). Kept as a separate service from
`backend/` so model logic never lives inside API route handlers
(`TECHNICAL_DECISIONS.md` ADR-011).

**Phase 1 status: inactive scaffold.** There is no telemetry, feature pipeline, or labeled
data yet for a model to train on or serve against — this service starts in Phase 11 (ML
Intelligence), after telemetry (Phase 6), data quality (Phase 7), and feature engineering
(Phase 10) exist.
