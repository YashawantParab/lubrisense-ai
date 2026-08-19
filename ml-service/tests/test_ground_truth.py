import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ml_service.datasets.ground_truth import GroundTruthTimeline
from ml_service.domain.labels import FailureLabel


def _write_jsonl(path: Path, ticks: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for tick in ticks:
            fh.write(json.dumps(tick))
            fh.write("\n")


def test_label_at_or_before_never_looks_into_the_future(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ticks = [
        {"simulation_timestamp": base.isoformat(), "scenarios": []},
        {
            "simulation_timestamp": (base + timedelta(minutes=10)).isoformat(),
            "scenarios": [
                {
                    "scenario_type": "GRADUAL_RESTRICTION",
                    "lifecycle_state": "SEVERE",
                    "severity": 0.9,
                }
            ],
        },
    ]
    path = tmp_path / "gt.jsonl"
    _write_jsonl(path, ticks)
    timeline = GroundTruthTimeline.load(path)

    # A sample timestamped at T=5min (between the two ticks) must resolve to the OLDER
    # tick's label (NORMAL), never peek at the future SEVERE restriction tick.
    label, source, severity = timeline.label_at_or_before(
        base + timedelta(minutes=5), max_staleness_seconds=600.0
    )
    assert label == FailureLabel.NORMAL
    assert source is None

    label2, source2, severity2 = timeline.label_at_or_before(
        base + timedelta(minutes=10), max_staleness_seconds=600.0
    )
    assert label2 == FailureLabel.RESTRICTION
    assert source2 == "GRADUAL_RESTRICTION"
    assert severity2 == 0.9


def test_label_before_first_tick_is_none(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    path = tmp_path / "gt.jsonl"
    _write_jsonl(path, [{"simulation_timestamp": base.isoformat(), "scenarios": []}])
    timeline = GroundTruthTimeline.load(path)

    label, source, severity = timeline.label_at_or_before(
        base - timedelta(minutes=1), max_staleness_seconds=600.0
    )
    assert label is None
    assert source is None


def test_stale_ground_truth_beyond_max_staleness_is_dropped(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    path = tmp_path / "gt.jsonl"
    _write_jsonl(path, [{"simulation_timestamp": base.isoformat(), "scenarios": []}])
    timeline = GroundTruthTimeline.load(path)

    label, _, _ = timeline.label_at_or_before(base + timedelta(hours=2), max_staleness_seconds=60.0)
    assert label is None


def test_network_failure_tick_is_dropped_not_normal(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    path = tmp_path / "gt.jsonl"
    _write_jsonl(
        path,
        [
            {
                "simulation_timestamp": base.isoformat(),
                "scenarios": [
                    {
                        "scenario_type": "NETWORK_FAILURE",
                        "lifecycle_state": "SEVERE",
                        "severity": 0.95,
                    }
                ],
            }
        ],
    )
    timeline = GroundTruthTimeline.load(path)
    label, source, _ = timeline.label_at_or_before(base, max_staleness_seconds=60.0)
    assert label is None
    assert source is None
