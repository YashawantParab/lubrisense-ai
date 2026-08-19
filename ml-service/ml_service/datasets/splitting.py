"""Leakage-safe dataset splitting (Phase 11 brief §6-§8).

Naive random row splitting is never used. Splitting is grouped by simulator run identity
(`run_id`) — every sample from one scenario run stays in exactly one split — and additionally
time-ordered, so TRAIN is built from earlier runs, VALIDATION from different/later runs, and
TEST from the latest and/or explicitly held-out (unseen-asset) runs. `run_id` is used only
here, for grouping; it is never a feature (`ml_service.domain.dataset.DatasetSample` keeps it
in a separate field from `feature_values`).
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Callable

from ml_service.domain.dataset import DatasetSample, RunManifest, SplitName


def assign_run_splits(
    runs: list[RunManifest],
    *,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    force_test_run_ids: frozenset[str] = frozenset(),
    force_train_run_ids: frozenset[str] = frozenset(),
) -> dict[str, SplitName]:
    """Time-ordered, grouped split at the RUN level. Runs in `force_test_run_ids` (e.g. a
    run on an asset never seen in TRAIN/VALIDATION, for the generalization test, Phase 11
    brief §31) are always TEST, regardless of their timestamp order.

    Runs in `force_train_run_ids` are always TRAIN, regardless of timestamp order. This
    exists for the same reason `force_test_run_ids` exists: with only a handful of runs per
    scenario type, a pure time-ordered split can accidentally place *every* run for a rare
    scenario type outside TRAIN, making its label structurally unlearnable (the classifier
    never sees a single example) rather than merely hard to learn. `build_dataset.py` uses
    this to guarantee at least one run per label reaches TRAIN for the rarest scenario
    types, while still leaving other runs of the same type free to land in
    VALIDATION/TEST for a genuine held-out evaluation of that label.
    """
    if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1:
        raise ValueError("train_ratio and validation_ratio must be in (0, 1)")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio + validation_ratio must leave room for TEST")
    if force_test_run_ids & force_train_run_ids:
        raise ValueError("a run_id cannot be in both force_test_run_ids and force_train_run_ids")

    forced_test = [r for r in runs if r.run_id in force_test_run_ids]
    forced_train = [r for r in runs if r.run_id in force_train_run_ids]
    orderable = sorted(
        (
            r
            for r in runs
            if r.run_id not in force_test_run_ids and r.run_id not in force_train_run_ids
        ),
        key=lambda r: r.start_timestamp,
    )

    split = _proportional_split(orderable, train_ratio, validation_ratio)
    for run in forced_test:
        split[run.run_id] = SplitName.TEST
    for run in forced_train:
        split[run.run_id] = SplitName.TRAIN
    return split


def _proportional_split(
    ordered: list[RunManifest], train_ratio: float, validation_ratio: float
) -> dict[str, SplitName]:
    """Time-ordered 60/20/20-style split of an already-filtered, already-sorted run list."""
    n = len(ordered)
    n_train = max(1, round(n * train_ratio)) if n else 0
    n_val = max(1, round(n * validation_ratio)) if n - n_train > 0 else 0
    n_train = min(n_train, n)
    n_val = min(n_val, n - n_train)

    split: dict[str, SplitName] = {}
    for run in ordered[:n_train]:
        split[run.run_id] = SplitName.TRAIN
    for run in ordered[n_train : n_train + n_val]:
        split[run.run_id] = SplitName.VALIDATION
    for run in ordered[n_train + n_val :]:
        split[run.run_id] = SplitName.TEST
    return split


def assign_stratified_run_splits(
    runs: list[RunManifest],
    group_key_fn: Callable[[RunManifest], str],
    *,
    train_ratio: float = 0.6,
    validation_ratio: float = 0.2,
    force_test_run_ids: frozenset[str] = frozenset(),
    force_train_run_ids: frozenset[str] = frozenset(),
) -> dict[str, SplitName]:
    """Like `assign_run_splits`, but the time-ordered proportional split is applied
    independently within each group produced by `group_key_fn`, rather than once across all
    runs.

    With only a handful of runs total, a single global time-ordered split can accidentally
    place every run for a rare label entirely outside TRAIN (structurally unlearnable) or
    entirely outside TEST (untestable) — not because that label is hard, but because the
    chronological order of unrelated scenario types happened to bunch that label's few runs
    together on one side of a global cut point. Stratifying the same time-ordered/grouped
    logic per label avoids that accident while still never splitting a single run's samples
    across two splits, and still never using row-random shuffling.

    A group with exactly one run goes entirely to TRAIN by default (there is no way to hold
    out a run for TEST without making the label unlearnable, and TRAIN coverage matters more
    than TEST coverage for a label the model must be able to produce at all) — callers that
    need an evaluable, TEST-only case for a singleton group (e.g. the multi-fault-composition
    evaluation) should route that specific run_id through `force_test_run_ids` instead. A
    group with exactly two runs splits 1 TRAIN / 1 TEST (earlier run to TRAIN), skipping
    VALIDATION, because VALIDATION only matters at the dataset level for the anomaly model's
    NORMAL-only threshold calibration — a rare fault label having zero VALIDATION rows costs
    nothing, whereas having zero TEST rows would silently hide that label from every
    per-class TEST metric. Groups of three or more runs use the standard 60/20/20 rounding.
    """
    if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1:
        raise ValueError("train_ratio and validation_ratio must be in (0, 1)")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio + validation_ratio must leave room for TEST")
    if force_test_run_ids & force_train_run_ids:
        raise ValueError("a run_id cannot be in both force_test_run_ids and force_train_run_ids")

    forced_test = [r for r in runs if r.run_id in force_test_run_ids]
    forced_train = [r for r in runs if r.run_id in force_train_run_ids]
    groupable = [
        r
        for r in runs
        if r.run_id not in force_test_run_ids and r.run_id not in force_train_run_ids
    ]

    groups: dict[str, list[RunManifest]] = defaultdict(list)
    for run in groupable:
        groups[group_key_fn(run)].append(run)

    split: dict[str, SplitName] = {}
    for members in groups.values():
        ordered = sorted(members, key=lambda r: r.start_timestamp)
        if len(ordered) == 1:
            split[ordered[0].run_id] = SplitName.TRAIN
        elif len(ordered) == 2:
            split[ordered[0].run_id] = SplitName.TRAIN
            split[ordered[1].run_id] = SplitName.TEST
        else:
            split.update(_proportional_split(ordered, train_ratio, validation_ratio))

    for run in forced_test:
        split[run.run_id] = SplitName.TEST
    for run in forced_train:
        split[run.run_id] = SplitName.TRAIN
    return split


def apply_splits(
    samples: list[DatasetSample], run_split: dict[str, SplitName]
) -> list[DatasetSample]:
    result = []
    for sample in samples:
        split = run_split.get(sample.run_id)
        if split is None:
            raise ValueError(f"no split assignment for run_id={sample.run_id!r}")
        result.append(dataclasses.replace(sample, split=split))
    return result


def verify_no_run_crosses_splits(samples: list[DatasetSample]) -> bool:
    """Proves the grouping invariant directly on assembled samples, independent of
    `assign_run_splits`'s own logic — used by tests as an end-to-end guarantee."""
    seen: dict[str, SplitName] = {}
    for sample in samples:
        prior = seen.get(sample.run_id)
        if prior is not None and prior != sample.split:
            return False
        seen[sample.run_id] = sample.split
    return True
