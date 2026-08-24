"""Machine operating-profile scheduler and ambient/rpm derivation.

Drives `MachineState.operating_state`/`load_percent`/`rpm` through smooth,
physically-plausible transitions (Phase 3 brief §5): STOPPED -[ramp]-> STARTING ->
RUNNING_{LOW,NORMAL,HIGH}_LOAD -[ramp]-> SHUTTING_DOWN -> STOPPED, driven by a configurable
demo shift schedule. All randomness is drawn from the engine-owned seeded RNG so the whole
simulation stays deterministic for a given seed (docs/SIMULATOR.md §16).
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable

from simulator.config.loader import MachineConfig, OperatingProfileConfig
from simulator.domain.enums import OperatingState
from simulator.domain.state import BearingState, MachineState
from simulator.physics.util import clip, exp_relax


class OperatingProfile:
    def __init__(
        self,
        config: OperatingProfileConfig,
        machine_config: MachineConfig,
        machine_type: str,
        rng: random.Random,
    ) -> None:
        self._config = config
        self._machine_config = machine_config
        self._nominal_rpm = machine_config.nominal_rpm.get(machine_type, 1000.0)
        self._rng = rng
        self._next_target_change_s = 0.0

    def in_shift(self, sim_seconds: float) -> bool:
        hour_of_day = (sim_seconds / 3600.0) % 24.0
        return any(start <= hour_of_day < end for start, end in self._config.shift_windows_hours)

    def _running_state_for(self, load_percent: float) -> OperatingState:
        if load_percent < self._config.load_band_low_max:
            return OperatingState.RUNNING_LOW_LOAD
        if load_percent >= self._config.load_band_high_min:
            return OperatingState.RUNNING_HIGH_LOAD
        return OperatingState.RUNNING_NORMAL_LOAD

    def _schedule_next_target_change(self, sim_seconds: float) -> None:
        self._next_target_change_s = sim_seconds + self._config.load_target_change_interval_s

    def step(self, state: MachineState, sim_seconds: float, dt_s: float) -> None:
        shift_active = self.in_shift(sim_seconds)
        prev_state = state.operating_state

        if state.operating_state == OperatingState.STOPPED:
            if shift_active:
                state.operating_state = OperatingState.STARTING
                state.state_seconds = 0.0
                state.load_target_percent = self._config.load_band_low_max

        elif state.operating_state == OperatingState.STARTING:
            if state.state_seconds >= self._config.ramp_up_seconds:
                state.operating_state = self._running_state_for(state.load_target_percent)
                state.state_seconds = 0.0
                self._schedule_next_target_change(sim_seconds)

        elif state.operating_state.is_running:
            if not shift_active:
                state.operating_state = OperatingState.SHUTTING_DOWN
                state.state_seconds = 0.0
                state.load_target_percent = 0.0
            else:
                if sim_seconds >= self._next_target_change_s:
                    lo, hi = self._config.load_bounds_percent
                    state.load_target_percent = self._rng.uniform(lo, hi)
                    self._schedule_next_target_change(sim_seconds)
                state.operating_state = self._running_state_for(state.load_percent)

        elif (
            state.operating_state == OperatingState.SHUTTING_DOWN
            and state.load_percent < 1.0
            and state.state_seconds >= self._config.ramp_down_seconds
        ):
            state.operating_state = OperatingState.STOPPED
            state.state_seconds = 0.0
            state.load_target_percent = 0.0

        # MAINTENANCE: held externally (Phase 4+ failure-injection hook); no autonomous
        # transition out of it here.

        if state.operating_state == prev_state:
            state.state_seconds += dt_s

        state.load_percent = exp_relax(
            state.load_percent,
            state.load_target_percent,
            dt_s,
            self._machine_config.load_lag_time_constant_s,
        )

        if state.operating_state == OperatingState.STOPPED:
            state.rpm = 0.0
        else:
            state.rpm = self._nominal_rpm * clip(state.load_percent / 100.0, 0.0, 1.1)


def step_power(
    state: MachineState,
    config: MachineConfig,
    machine_type: str,
    bearings: Iterable[BearingState],
    dt_s: float,
) -> None:
    """Driveline power model (Lubrication Efficiency Intelligence,
    docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §12, ADR-176) — same target-plus-lag shape
    `simulator.physics.bearing.step_temperature`/`step_vibration` already use: a baseline
    plus a load-driven term plus a friction/degradation term, relaxed toward that target
    through a first-order lag rather than jumping instantly.

    The friction term is the mean `(1 - health)` across every bearing on this machine —
    the exact same real state variable `step_temperature`/`step_vibration` already use for
    their own `_degradation` terms, not a separately invented "friction" concept. A
    machine with no bearings yet (still commissioning) contributes zero friction term,
    same as a healthy fleet.
    """
    nominal = config.nominal_power_kw.get(machine_type, 30.0)
    bearing_list = list(bearings)
    friction_term = (
        sum(1.0 - b.health for b in bearing_list) / len(bearing_list) if bearing_list else 0.0
    )
    target = (
        nominal
        + config.power_load_gain_kw_per_percent * state.load_percent
        + config.power_friction_gain_kw * friction_term
    )
    state.power_kw = exp_relax(state.power_kw, target, dt_s, config.power_lag_time_constant_s)


def step_ambient_temperature(
    state: MachineState, machine_config: MachineConfig, sim_seconds: float, rng: random.Random
) -> None:
    """Slow diurnal-shaped ambient temperature: a daily sine wave plus small noise. Purely
    environmental context — not itself a monitored lubrication/machine-condition signal."""
    cfg = machine_config.ambient_temperature_c
    hour_of_day = (sim_seconds / 3600.0) % 24.0
    phase = (hour_of_day - 15.0) / 24.0 * 2.0 * math.pi  # peak mid-afternoon
    seasonal = cfg.daily_amplitude_c * math.sin(phase)
    noise = rng.gauss(0.0, cfg.noise_std_c)
    state.ambient_temperature_c = cfg.mean + seasonal + noise
