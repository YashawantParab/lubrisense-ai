"""Plain-data snapshots baseline computation operates on — never live ORM objects, so the
same pure-function-testability convention as `app.data_quality.domain.context` applies
here (Phase 8 brief §21/§22).

`BaselineContext` intentionally carries only `operating_state` and `cycle_phase`. Load and
RPM are *not* separate dimensions: this reference implementation's Phase 3 operating-state
state machine already derives `RUNNING_{LOW,NORMAL,HIGH}_LOAD` from configured load bands
(`simulator/simulator/physics/machine.py::OperatingProfile`), so `operating_state` already
carries the load/RPM signal a real deployment would otherwise need a separate LOAD/RPM
sensor correlation join to reconstruct — see docs/BASELINES.md "Context dimensions" for the
full rationale and TECHNICAL_DECISIONS.md, baseline-context-dimensions ADR. Ambient/lubricant
temperature is deliberately not used as a conditioning dimension for other sensors either
(no distinct ambient-temperature measurement type exists in this system — see the same doc
section) — it is used only via `LUBRICANT_TEMPERATURE` having its own baseline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BaselineContext:
    """One segmentation bucket. `None` in a field means "not used for this measurement
    type" (`app.baselines.config.policy.BaselinePolicy.context_dimensions_for`), not
    "wildcard" — a profile with `operating_state=None` never matches a query that asked
    for a specific operating state; see `app.baselines.services.fallback` for how the
    fallback hierarchy walks from a specific context down to a less specific one."""

    operating_state: str | None = None
    cycle_phase: str | None = None


def context_key(context: BaselineContext) -> str:
    """Deterministic canonical string for `BaselineProfile.context_key` — stable field
    order so the same logical context always hashes to the same key regardless of how the
    `BaselineContext` was constructed. Empty string for a context-free (sensor-level)
    profile, matching the column's NOT NULL default."""
    parts = []
    if context.operating_state is not None:
        parts.append(f"operating_state={context.operating_state}")
    if context.cycle_phase is not None:
        parts.append(f"cycle_phase={context.cycle_phase}")
    return "|".join(parts)


@dataclass(frozen=True)
class TelemetrySample:
    """One `telemetry` row, as baseline computation needs it — built from a
    `TelemetryRepository` query result, never a live ORM row (see module docstring)."""

    event_id: uuid.UUID
    sensor_id: uuid.UUID
    source_timestamp: datetime
    value: float | None
    operating_state: str
    quality: str
    eligible: bool
    caution: bool
    """`eligible=False` samples must already be filtered out before reaching a strategy
    function — kept on the dataclass anyway so a strategy can assert its own input
    invariant in tests rather than silently trusting the caller. `caution=True` marks an
    `ELIGIBLE_WITH_CAUTION` sample: included in statistics, but tracked separately
    (`RobustStatistics.caution_count`) rather than excluded outright or silently
    down-weighted — Phase 8 brief §5's "explicit weighting or exclusion rules"."""
