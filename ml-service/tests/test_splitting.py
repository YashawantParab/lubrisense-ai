import uuid
from datetime import UTC, datetime, timedelta

import pytest

from ml_service.datasets.splitting import (
    apply_splits,
    assign_run_splits,
    assign_stratified_run_splits,
    verify_no_run_crosses_splits,
)
from ml_service.domain.dataset import DatasetSample, RunManifest, SplitName
from ml_service.domain.labels import FailureLabel

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()


def _run(run_id: str, start_offset_hours: int, scenario_types: tuple[str, ...] = ()) -> RunManifest:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=start_offset_hours)
    return RunManifest(
        run_id=run_id,
        tenant_id=TENANT,
        machine_id=MACHINE,
        asset_code="L1-7B43-M000",
        seed=1,
        scenario_types=scenario_types,
        start_timestamp=start,
        end_timestamp=start + timedelta(hours=6),
        ground_truth_path="/dev/null",
        is_healthy=not scenario_types,
    )


def test_assign_run_splits_is_time_ordered_and_grouped() -> None:
    runs = [_run(f"run-{i}", i * 6) for i in range(10)]
    split = assign_run_splits(runs, train_ratio=0.6, validation_ratio=0.2)

    assert len(split) == 10
    train_runs = [r for r in runs if split[r.run_id] == SplitName.TRAIN]
    val_runs = [r for r in runs if split[r.run_id] == SplitName.VALIDATION]
    test_runs = [r for r in runs if split[r.run_id] == SplitName.TEST]

    assert len(train_runs) == 6
    assert len(val_runs) == 2
    assert len(test_runs) == 2
    # earliest runs go to train, latest go to test
    assert max(r.start_timestamp for r in train_runs) < min(r.start_timestamp for r in val_runs)
    assert max(r.start_timestamp for r in val_runs) < min(r.start_timestamp for r in test_runs)


def test_forced_test_run_ids_always_land_in_test_even_if_earliest() -> None:
    runs = [_run(f"run-{i}", i * 6) for i in range(6)]
    forced = frozenset({"run-0"})
    split = assign_run_splits(
        runs, train_ratio=0.6, validation_ratio=0.2, force_test_run_ids=forced
    )
    assert split["run-0"] == SplitName.TEST


def test_invalid_ratios_rejected() -> None:
    runs = [_run("run-0", 0)]
    with pytest.raises(ValueError):
        assign_run_splits(runs, train_ratio=0.9, validation_ratio=0.3)


def test_force_train_run_ids_always_land_in_train_even_if_latest() -> None:
    runs = [_run(f"run-{i}", i * 6) for i in range(6)]
    split = assign_run_splits(
        runs, train_ratio=0.6, validation_ratio=0.2, force_train_run_ids=frozenset({"run-5"})
    )
    assert split["run-5"] == SplitName.TRAIN


def test_force_train_and_force_test_conflict_rejected() -> None:
    runs = [_run("run-0", 0)]
    with pytest.raises(ValueError):
        assign_run_splits(
            runs,
            force_test_run_ids=frozenset({"run-0"}),
            force_train_run_ids=frozenset({"run-0"}),
        )


def test_stratified_split_prevents_a_rare_label_from_being_excluded_from_train() -> None:
    """A pure time-ordered global split can accidentally push every run for a rare scenario
    type outside TRAIN just because they happen to be scheduled late. Stratifying by label
    must keep that from happening as long as the label has more than one run."""
    runs = [
        _run("healthy-1", 0),
        _run("healthy-2", 6),
        _run("healthy-3", 12),
        _run("healthy-4", 18),
        _run("bearing-1", 24, ("INDEPENDENT_BEARING_FAULT",)),
        _run("bearing-2", 30, ("INDEPENDENT_BEARING_FAULT",)),
    ]
    split = assign_stratified_run_splits(
        runs, lambda r: r.scenario_types[0] if r.scenario_types else "HEALTHY"
    )

    bearing_splits = {split["bearing-1"], split["bearing-2"]}
    assert SplitName.TRAIN in bearing_splits
    assert SplitName.TEST in bearing_splits


def test_stratified_split_puts_a_singleton_group_entirely_in_train() -> None:
    runs = [_run("healthy-1", 0), _run("rare-fault-1", 6, ("RARE_FAULT",))]
    split = assign_stratified_run_splits(
        runs, lambda r: r.scenario_types[0] if r.scenario_types else "HEALTHY"
    )
    assert split["rare-fault-1"] == SplitName.TRAIN


def test_stratified_split_respects_forced_overrides() -> None:
    runs = [_run("healthy-1", 0), _run("rare-fault-1", 6, ("RARE_FAULT",))]
    split = assign_stratified_run_splits(
        runs,
        lambda r: r.scenario_types[0] if r.scenario_types else "HEALTHY",
        force_test_run_ids=frozenset({"rare-fault-1"}),
    )
    assert split["rare-fault-1"] == SplitName.TEST


def test_stratified_split_never_crosses_a_run() -> None:
    runs = [_run(f"run-{i}", i * 6, ("A",) if i % 2 else ("B",)) for i in range(8)]
    split = assign_stratified_run_splits(runs, lambda r: r.scenario_types[0])
    assert len(split) == len(runs)
    for run in runs:
        assert run.run_id in split


def _sample(run_id: str, split: SplitName) -> DatasetSample:
    return DatasetSample(
        feature_vector_id=uuid.uuid4(),
        run_id=run_id,
        tenant_id=TENANT,
        machine_id=MACHINE,
        asset_code="L1-7B43-M000",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        feature_set="LUBRICATION_ANOMALY_V1",
        feature_set_version="1.0.2",
        feature_values={"pressure.current": 5.0},
        missing_features=(),
        quality_summary={},
        label=FailureLabel.NORMAL,
        source_scenario_type=None,
        ground_truth_severity=0.0,
        split=split,
    )


def test_apply_splits_assigns_from_run_mapping() -> None:
    samples = [_sample("run-a", SplitName.TRAIN), _sample("run-b", SplitName.TRAIN)]
    result = apply_splits(samples, {"run-a": SplitName.TRAIN, "run-b": SplitName.TEST})
    assert result[0].split == SplitName.TRAIN
    assert result[1].split == SplitName.TEST


def test_apply_splits_raises_for_unknown_run() -> None:
    samples = [_sample("run-unknown", SplitName.TRAIN)]
    with pytest.raises(ValueError):
        apply_splits(samples, {})


def test_verify_no_run_crosses_splits_detects_violation() -> None:
    consistent = [_sample("run-a", SplitName.TRAIN), _sample("run-a", SplitName.TRAIN)]
    assert verify_no_run_crosses_splits(consistent) is True

    violating = [_sample("run-a", SplitName.TRAIN), _sample("run-a", SplitName.TEST)]
    assert verify_no_run_crosses_splits(violating) is False
