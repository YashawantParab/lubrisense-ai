"""`ScenarioScheduler` — owns every `ScenarioInstance` for one simulation run, steps their
lifecycles each tick, and aggregates their effects (Phase 4 brief §2). Also owns the
standalone `AutoRefillPolicy` (§24 — refill is an operational event, not a failure mode, so
it lives independently of any scenario instance and works even with zero scenarios active).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from simulator.config.loader import EngineeringConfig
from simulator.domain.topology import MachineTopology
from simulator.scenarios.effects import ScenarioEffects
from simulator.scenarios.effects import build_effects as _build_effects
from simulator.scenarios.instance import ScenarioInstance


@dataclass(slots=True)
class AutoRefillPolicy:
    """Triggers a reservoir refill once its level has stayed at or below
    `threshold_percent` for `delay_seconds` of simulated time — independent of whether a
    Low Reservoir (or any other) scenario is active."""

    threshold_percent: float
    to_percent: float = 100.0
    delay_seconds: float = 0.0
    _below_since: float | None = field(default=None, init=False, repr=False)

    def step(self, level_percent: float, sim_seconds: float) -> bool:
        if level_percent > self.threshold_percent:
            self._below_since = None
            return False
        if self._below_since is None:
            self._below_since = sim_seconds
        if sim_seconds - self._below_since >= self.delay_seconds:
            self._below_since = None
            return True
        return False


class ScenarioScheduler:
    def __init__(
        self,
        instances: list[ScenarioInstance],
        topology: MachineTopology,
        config: EngineeringConfig,
        refill_policy: AutoRefillPolicy | None = None,
    ) -> None:
        self._instances = instances
        self._topology = topology
        self._config = config
        self._refill_policy = refill_policy
        self._previously_active: set[str] = set()
        self.last_activation_edge: set[str] = set()

    @property
    def instances(self) -> list[ScenarioInstance]:
        return self._instances

    def advance(self, sim_seconds: float, dt_s: float) -> None:
        """Step every instance's lifecycle/severity and update `last_activation_edge`.
        Call this, let the engine react to newly-activated instances (e.g. capturing a
        Sensor Drift instance's `drift_base_bias` from the live sensor state — see
        `SimulationEngine._activate_new_scenarios`), then call `build_effects()`."""
        for instance in self._instances:
            instance.step(sim_seconds, dt_s)

        currently_active = {i.instance_id for i in self._instances if i.is_active}
        self.last_activation_edge = currently_active - self._previously_active
        self._previously_active = currently_active

    def build_effects(self) -> ScenarioEffects:
        return _build_effects(
            self._instances, self._topology, self._config, self.last_activation_edge
        )

    def check_refill(self, reservoir_level_percent: float, sim_seconds: float) -> bool:
        if self._refill_policy is None:
            return False
        return self._refill_policy.step(reservoir_level_percent, sim_seconds)

    @property
    def refill_to_percent(self) -> float:
        assert self._refill_policy is not None
        return self._refill_policy.to_percent
