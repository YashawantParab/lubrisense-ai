"""Resolve a scenario's target to a real Phase 2 entity id from the loaded `MachineTopology`
(Phase 4 brief §17). Every scenario target is a real, live-database id — never a synthetic
one — and an incompatible or unresolvable target fails loudly here, before the simulation
starts, rather than silently doing nothing at runtime.
"""

from __future__ import annotations

import uuid

from simulator.domain.topology import MachineTopology
from simulator.scenarios.types import ScenarioTargetType


class ScenarioTargetError(ValueError):
    """Raised when a scenario's target cannot be resolved against the loaded topology —
    either the requested id/code doesn't exist, or it exists but is the wrong entity type
    for this scenario (Phase 4 brief §17: "Invalid or incompatible target types must fail
    validation")."""


def _candidates(topology: MachineTopology, target_type: ScenarioTargetType) -> dict[str, uuid.UUID]:
    """entity "code" (a human-typeable identifier) -> id, for every entity of `target_type`
    available on this machine."""
    if target_type == ScenarioTargetType.MACHINE:
        return {topology.asset_code: topology.id}
    if target_type == ScenarioTargetType.BEARING:
        return {b.position: b.id for b in topology.bearings}
    ls = topology.lubrication_system
    if ls is None:
        return {}
    if target_type == ScenarioTargetType.LUBRICATION_SYSTEM:
        return {ls.name: ls.id}
    if target_type == ScenarioTargetType.PUMP:
        return {ls.pump.name: ls.pump.id}
    if target_type == ScenarioTargetType.RESERVOIR:
        return {ls.reservoir.name: ls.reservoir.id}
    if target_type == ScenarioTargetType.CIRCUIT:
        return {c.code: c.id for c in ls.circuits}
    if target_type == ScenarioTargetType.SENSOR:
        return {s.sensor_code: s.id for s in topology.sensors}
    raise AssertionError(f"unhandled target type {target_type}")  # pragma: no cover


def resolve_target(
    topology: MachineTopology,
    target_type: ScenarioTargetType,
    explicit_target: str | None = None,
) -> uuid.UUID:
    """Resolve one entity of `target_type` on `topology`.

    `explicit_target` may be a human-readable code (bearing position, circuit code, sensor
    code, ...) or a UUID string; when omitted, the first available entity of the required
    type is used (Phase 4 brief §20: "avoid a fragile CLI ... defaults should come from
    configuration"). Raises `ScenarioTargetError` if nothing of the required type exists on
    this machine, or if `explicit_target` does not match any candidate.
    """
    candidates = _candidates(topology, target_type)
    if not candidates:
        raise ScenarioTargetError(
            f"Machine {topology.asset_code!r} has no {target_type.value} entity to target"
        )

    if explicit_target is None:
        return next(iter(candidates.values()))

    if explicit_target in candidates:
        return candidates[explicit_target]

    try:
        requested_id = uuid.UUID(explicit_target)
    except ValueError:
        raise ScenarioTargetError(
            f"{explicit_target!r} is not a known {target_type.value} code on "
            f"{topology.asset_code!r} (known: {sorted(candidates)}) and is not a valid UUID"
        ) from None

    if requested_id in candidates.values():
        return requested_id

    raise ScenarioTargetError(
        f"{explicit_target!r} does not resolve to a {target_type.value} on "
        f"{topology.asset_code!r} — it may be the wrong entity type, or not exist on this "
        f"machine at all (known {target_type.value} codes: {sorted(candidates)})"
    )
