"""`ScenarioInstance` — the mutable runtime state of one scheduled/active fault (Phase 4
brief §2, §3). Owns only *timing and severity*; it never touches `simulator.domain.state`
directly — `simulator.scenarios.effects` translates an instance's current severity into
hidden-physical-state adjustments, keeping "when/how severe" separate from "what physical
consequence" (see docs/SCENARIO_ENGINE.md §3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from simulator.domain.topology import MachineTopology
from simulator.scenarios.definition import ProgressionSpec, ScenarioDefinition
from simulator.scenarios.progression import compute_severity
from simulator.scenarios.targeting import resolve_target
from simulator.scenarios.types import VALID_TARGET_TYPES, ScenarioLifecycleState, ScenarioType


@dataclass(slots=True)
class ScenarioInstance:
    instance_id: str
    definition: ScenarioDefinition
    target_id: uuid.UUID
    start_seconds: float
    severity_max: float

    lifecycle_state: ScenarioLifecycleState = ScenarioLifecycleState.SCHEDULED
    severity: float = 0.0
    peak_severity: float = 0.0
    active_since_seconds: float | None = None
    severe_since_seconds: float | None = None
    recovery_started_seconds: float | None = None

    #: Sensor Drift only: the bias value captured at activation, so drift is computed as an
    #: offset from *that* fixed point rather than compounding every tick — see
    #: `simulator.scenarios.effects.sensor_drift_bias`.
    drift_base_bias: float | None = None
    extra: dict[str, float] = field(default_factory=dict)

    #: CLI/test override for `definition.progression` (Phase 4 brief §20 `--progression`);
    #: `None` means use the definition's own default.
    progression_override: ProgressionSpec | None = None

    @property
    def scenario_type(self) -> ScenarioType:
        return self.definition.scenario_type

    def step(self, sim_seconds: float, dt_s: float) -> None:
        if self.lifecycle_state == ScenarioLifecycleState.COMPLETED:
            return

        if sim_seconds < self.start_seconds:
            self.lifecycle_state = ScenarioLifecycleState.SCHEDULED
            return

        if self.active_since_seconds is None:
            self.active_since_seconds = sim_seconds

        recovery = self.definition.recovery

        if self.recovery_started_seconds is not None:
            self._step_recovery(sim_seconds)
            return

        prog = self.progression_override or self.definition.progression
        elapsed = sim_seconds - self.active_since_seconds
        raw = compute_severity(
            prog.type,
            elapsed,
            prog.onset_seconds,
            period_s=prog.period_s,
            duty_cycle=prog.duty_cycle,
            sigmoid_steepness=prog.sigmoid_steepness,
        )
        self.severity = self.severity_max * raw
        self.peak_severity = max(self.peak_severity, self.severity)

        lifecycle = self.definition.lifecycle
        if lifecycle.severe_threshold is not None and self.severity >= lifecycle.severe_threshold:
            if self.severe_since_seconds is None:
                self.severe_since_seconds = sim_seconds
            self.lifecycle_state = ScenarioLifecycleState.SEVERE
        elif self.severity >= lifecycle.developing_threshold:
            self.lifecycle_state = ScenarioLifecycleState.DEVELOPING
        else:
            self.lifecycle_state = ScenarioLifecycleState.ACTIVE

        if recovery.enabled:
            onset_complete_at = (
                self.active_since_seconds + prog.onset_seconds + recovery.hold_seconds
            )
            if sim_seconds >= onset_complete_at:
                self.recovery_started_seconds = sim_seconds

    def _step_recovery(self, sim_seconds: float) -> None:
        assert self.recovery_started_seconds is not None
        duration = self.definition.recovery.duration_seconds
        elapsed_recovery = sim_seconds - self.recovery_started_seconds
        progress = 1.0 if duration <= 0 else min(1.0, elapsed_recovery / duration)
        self.severity = self.peak_severity * (1.0 - progress)
        if progress >= 1.0:
            self.severity = 0.0
            self.lifecycle_state = ScenarioLifecycleState.COMPLETED
        else:
            self.lifecycle_state = ScenarioLifecycleState.RECOVERING

    @property
    def is_active(self) -> bool:
        return self.lifecycle_state not in (
            ScenarioLifecycleState.SCHEDULED,
            ScenarioLifecycleState.COMPLETED,
        )


def create_instance(
    definition: ScenarioDefinition,
    topology: MachineTopology,
    *,
    instance_id: str | None = None,
    start_seconds: float | None = None,
    severity_max: float | None = None,
    target: str | None = None,
    progression_override: ProgressionSpec | None = None,
) -> ScenarioInstance:
    """Build a `ScenarioInstance` from a `ScenarioDefinition`, resolving its target against
    the real loaded topology and applying any CLI/test overrides on top of the definition's
    defaults (Phase 4 brief §20). Raises `simulator.scenarios.targeting.ScenarioTargetError`
    if `target` is incompatible or does not exist."""
    target_type = VALID_TARGET_TYPES[definition.scenario_type]
    target_id = resolve_target(topology, target_type, target)
    return ScenarioInstance(
        instance_id=instance_id or f"{definition.name}:{target_id}",
        definition=definition,
        target_id=target_id,
        start_seconds=(
            start_seconds if start_seconds is not None else definition.default_start_seconds
        ),
        severity_max=severity_max if severity_max is not None else definition.default_severity_max,
        progression_override=progression_override,
    )
