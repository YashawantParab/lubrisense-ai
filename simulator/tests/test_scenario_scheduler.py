from __future__ import annotations

from simulator.scenarios.instance import create_instance
from simulator.scenarios.loader import load_scenario_definition
from simulator.scenarios.scheduler import AutoRefillPolicy, ScenarioScheduler
from tests.factories import make_topology


def test_activation_edge_fires_once(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    definition = load_scenario_definition("gradual_restriction")
    instance = create_instance(definition, topology, start_seconds=10.0)
    scheduler = ScenarioScheduler([instance], topology, engineering_config)

    scheduler.advance(0.0, 5.0)
    assert instance.instance_id not in scheduler.last_activation_edge

    scheduler.advance(10.0, 5.0)
    assert instance.instance_id in scheduler.last_activation_edge

    scheduler.advance(15.0, 5.0)
    assert instance.instance_id not in scheduler.last_activation_edge


def test_build_effects_reflects_advanced_instances(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    definition = load_scenario_definition("gradual_restriction")
    instance = create_instance(definition, topology, start_seconds=0.0, severity_max=1.0)
    scheduler = ScenarioScheduler([instance], topology, engineering_config)

    for t in range(0, 200, 5):
        scheduler.advance(float(t), 5.0)
    effects = scheduler.build_effects()
    assert instance.target_id in effects.circuit_restriction_offset
    assert effects.circuit_restriction_offset[instance.target_id] > 0.0


def test_auto_refill_policy_triggers_after_delay() -> None:
    policy = AutoRefillPolicy(threshold_percent=10.0, to_percent=100.0, delay_seconds=30.0)
    assert policy.step(50.0, 0.0) is False  # above threshold
    assert policy.step(9.0, 100.0) is False  # just crossed, delay not elapsed
    assert policy.step(9.0, 120.0) is False  # 20s elapsed, still short of 30s
    assert policy.step(9.0, 131.0) is True  # 31s elapsed


def test_auto_refill_policy_resets_if_level_recovers() -> None:
    policy = AutoRefillPolicy(threshold_percent=10.0, delay_seconds=30.0)
    assert policy.step(9.0, 0.0) is False
    assert policy.step(50.0, 10.0) is False  # recovered above threshold, timer resets
    assert policy.step(9.0, 40.0) is False  # only 0s elapsed since the *new* below-threshold start


def test_no_refill_policy_never_triggers(engineering_config) -> None:  # type: ignore[no-untyped-def]
    topology = make_topology()
    scheduler = ScenarioScheduler([], topology, engineering_config, refill_policy=None)
    assert scheduler.check_refill(0.5, 100.0) is False
