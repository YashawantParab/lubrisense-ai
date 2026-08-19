"""Pure correlation-key/family logic tests (Phase 16 brief §16.4/§16.5)."""

from __future__ import annotations

import uuid

from app.incidents.config.policy import load_incident_correlation_policy
from app.incidents.services.correlation import build_correlation_key, family_for_condition_type

POLICY = load_incident_correlation_policy()


def test_developing_restriction_and_blockage_share_a_family() -> None:
    """Evolving evidence within the same problem must correlate to one incident."""
    assert family_for_condition_type(
        "DEVELOPING_RESTRICTION_PATTERN", POLICY
    ) == family_for_condition_type("DELIVERY_BLOCKAGE_PATTERN", POLICY)


def test_lubrication_delivery_and_bearing_are_different_families() -> None:
    """Independent problems must never correlate into the same incident."""
    delivery_family = family_for_condition_type("DEVELOPING_RESTRICTION_PATTERN", POLICY)
    bearing_family = family_for_condition_type("INDEPENDENT_BEARING_CONDITION", POLICY)
    assert delivery_family is not None
    assert bearing_family is not None
    assert delivery_family != bearing_family


def test_normal_operation_never_creates_an_incident() -> None:
    assert family_for_condition_type("NORMAL_OPERATION", POLICY) is None


def test_insufficient_evidence_never_creates_an_incident() -> None:
    assert family_for_condition_type("INSUFFICIENT_EVIDENCE", POLICY) is None


def test_sensor_or_data_quality_limitation_never_creates_an_incident() -> None:
    assert family_for_condition_type("SENSOR_OR_DATA_QUALITY_LIMITATION", POLICY) is None


def test_ambiguous_condition_never_creates_an_incident() -> None:
    assert family_for_condition_type("AMBIGUOUS_CONDITION", POLICY) is None


def test_correlation_key_is_deterministic_for_same_inputs() -> None:
    machine_id = uuid.uuid4()
    key_a = build_correlation_key(machine_id, None, "LUBRICATION_DELIVERY")
    key_b = build_correlation_key(machine_id, None, "LUBRICATION_DELIVERY")
    assert key_a == key_b


def test_correlation_key_differs_by_family() -> None:
    machine_id = uuid.uuid4()
    delivery_key = build_correlation_key(machine_id, None, "LUBRICATION_DELIVERY")
    bearing_key = build_correlation_key(machine_id, None, "BEARING_CONDITION")
    assert delivery_key != bearing_key


def test_correlation_key_differs_by_machine() -> None:
    key_a = build_correlation_key(uuid.uuid4(), None, "LUBRICATION_DELIVERY")
    key_b = build_correlation_key(uuid.uuid4(), None, "LUBRICATION_DELIVERY")
    assert key_a != key_b


def test_every_fault_condition_type_has_a_family() -> None:
    """Every genuine fault-pattern ConditionType (Phase 13) must be routed to an
    incident family — an unmapped fault type would silently never create an incident."""
    fault_types = [
        "LUBRICATION_DELIVERY_DEGRADATION",
        "DEVELOPING_RESTRICTION_PATTERN",
        "DELIVERY_BLOCKAGE_PATTERN",
        "POSSIBLE_LEAKAGE_PATTERN",
        "PUMP_PERFORMANCE_DEGRADATION",
        "LOW_LUBRICANT_AVAILABILITY",
        "BEARING_CONDITION_DEGRADATION",
        "INDEPENDENT_BEARING_CONDITION",
    ]
    for condition_type in fault_types:
        assert family_for_condition_type(condition_type, POLICY) is not None, condition_type
