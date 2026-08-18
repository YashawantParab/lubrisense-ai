from __future__ import annotations

import uuid

from simulator.scenarios.definition import (
    LifecycleSpec,
    ProgressionSpec,
    RecoverySpec,
    ScenarioDefinition,
)
from simulator.scenarios.instance import ScenarioInstance
from simulator.scenarios.types import (
    ProgressionType,
    ScenarioLifecycleState,
    ScenarioTargetType,
    ScenarioType,
)


def _definition(
    *,
    progression: ProgressionSpec | None = None,
    lifecycle: LifecycleSpec | None = None,
    recovery: RecoverySpec | None = None,
) -> ScenarioDefinition:
    return ScenarioDefinition(
        name="test_scenario",
        scenario_type=ScenarioType.GRADUAL_RESTRICTION,
        target_type=ScenarioTargetType.CIRCUIT,
        description="unit test scenario",
        progression=progression
        or ProgressionSpec(type=ProgressionType.LINEAR, onset_seconds=100.0),
        lifecycle=lifecycle or LifecycleSpec(developing_threshold=0.2, severe_threshold=0.7),
        recovery=recovery or RecoverySpec(enabled=False),
    )


def _instance(definition: ScenarioDefinition, start_seconds: float = 0.0) -> ScenarioInstance:
    return ScenarioInstance(
        instance_id="test",
        definition=definition,
        target_id=uuid.uuid4(),
        start_seconds=start_seconds,
        severity_max=1.0,
    )


def test_scheduled_before_start_time() -> None:
    instance = _instance(_definition(), start_seconds=500.0)
    instance.step(100.0, 5.0)
    assert instance.lifecycle_state == ScenarioLifecycleState.SCHEDULED
    assert instance.severity == 0.0
    assert not instance.is_active


def test_activates_at_start_time() -> None:
    instance = _instance(_definition(), start_seconds=100.0)
    instance.step(100.0, 5.0)
    assert instance.lifecycle_state != ScenarioLifecycleState.SCHEDULED
    assert instance.is_active


def test_progresses_active_to_developing_to_severe() -> None:
    instance = _instance(_definition())
    seen = []
    t = 0.0
    while t < 150.0:
        instance.step(t, 5.0)
        seen.append(instance.lifecycle_state)
        t += 5.0
    assert ScenarioLifecycleState.ACTIVE in seen
    assert ScenarioLifecycleState.DEVELOPING in seen
    assert ScenarioLifecycleState.SEVERE in seen


def test_severity_increases_monotonically_without_recovery() -> None:
    instance = _instance(_definition())
    prev = -1.0
    t = 0.0
    while t < 200.0:
        instance.step(t, 5.0)
        assert instance.severity >= prev - 1e-9
        prev = instance.severity
        t += 5.0
    assert instance.severity == 1.0  # fully ramped, no recovery


def test_not_every_scenario_reaches_severe() -> None:
    """Phase 4 brief §3: not every scenario needs all states."""
    definition = _definition(
        lifecycle=LifecycleSpec(developing_threshold=0.2, severe_threshold=None)
    )
    instance = _instance(definition)
    t = 0.0
    while t < 300.0:
        instance.step(t, 5.0)
        t += 5.0
    assert instance.lifecycle_state != ScenarioLifecycleState.SEVERE
    assert instance.severity == 1.0


def test_recovery_decays_severity_back_to_zero_and_completes() -> None:
    definition = _definition(
        progression=ProgressionSpec(type=ProgressionType.LINEAR, onset_seconds=50.0),
        recovery=RecoverySpec(enabled=True, hold_seconds=0.0, duration_seconds=50.0),
    )
    instance = _instance(definition)
    t = 0.0
    saw_recovering = False
    while t < 300.0:
        instance.step(t, 5.0)
        if instance.lifecycle_state == ScenarioLifecycleState.RECOVERING:
            saw_recovering = True
        t += 5.0
    assert saw_recovering
    assert instance.lifecycle_state == ScenarioLifecycleState.COMPLETED
    assert instance.severity == 0.0
    assert not instance.is_active


def test_completed_instance_stays_completed() -> None:
    definition = _definition(
        progression=ProgressionSpec(type=ProgressionType.LINEAR, onset_seconds=10.0),
        recovery=RecoverySpec(enabled=True, hold_seconds=0.0, duration_seconds=10.0),
    )
    instance = _instance(definition)
    t = 0.0
    while t < 100.0:
        instance.step(t, 5.0)
        t += 5.0
    assert instance.lifecycle_state == ScenarioLifecycleState.COMPLETED
    instance.step(1000.0, 5.0)
    assert instance.lifecycle_state == ScenarioLifecycleState.COMPLETED
    assert instance.severity == 0.0


def test_step_progression_reaches_full_severity_immediately() -> None:
    definition = _definition(
        progression=ProgressionSpec(type=ProgressionType.STEP, onset_seconds=0.0),
        lifecycle=LifecycleSpec(developing_threshold=0.1, severe_threshold=0.5),
    )
    instance = _instance(definition)
    instance.step(0.0, 5.0)
    assert instance.severity == 1.0
    assert instance.lifecycle_state == ScenarioLifecycleState.SEVERE
