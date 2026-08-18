#!/usr/bin/env python3
"""Engineering validation plotting utility (Phase 3 brief §27; extended Phase 4 §29).

Reads a `--readings` JSONL file (produced by `python -m simulator run`) and plots
per-measurement-type time series for visual inspection: pressure, flow, pump current,
reservoir level, vibration, bearing temperature, RPM/load. With `--ground-truth`, also
plots the hidden-state ground truth (scenario severity, restriction/leakage factor) in a
leading panel — for engineering validation only, never merged with the observed-telemetry
panels below it (docs/SYNTHETIC_DATA_MODEL.md). This is a validation tool, not the product
UI (CLAUDE.md — "charts support the product decision, charts are not the product").

Usage:
    uv run python scripts/validate_plots.py --readings data/run.readings.jsonl \\
        --ground-truth data/run.ground_truth.jsonl --output data/run.png
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_PANELS: list[tuple[str, list[str]]] = [
    ("Pressure (bar)", ["PRESSURE"]),
    ("Flow (cm3/min)", ["FLOW"]),
    ("Pump current (A)", ["PUMP_CURRENT"]),
    ("Reservoir level (%)", ["RESERVOIR_LEVEL"]),
    ("Vibration RMS (mm/s)", ["VIBRATION_RMS", "VIBRATION_PEAK"]),
    ("Bearing temperature (degC)", ["BEARING_TEMPERATURE"]),
    ("RPM / Load (%)", ["RPM", "LOAD"]),
]


def _seconds_between(t0: str, t1: str) -> float:
    fmt = "%Y-%m-%dT%H:%M:%S.%f%z"
    a = datetime.strptime(t0, fmt) if "." in t0 else datetime.fromisoformat(t0)
    b = datetime.strptime(t1, fmt) if "." in t1 else datetime.fromisoformat(t1)
    return (b - a).total_seconds()


def load_series(path: Path) -> dict[str, dict[str, list[tuple[float, float]]]]:
    """measurement_type -> component_id -> [(t_seconds, observed_value), ...]. Rows with no
    observation (Sensor Dropout/Network Failure — observed_value is null) are skipped for
    plotting purposes; true_value is still available in the file for closer inspection."""
    series: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    t0 = None
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            ts = row["simulation_timestamp"]
            if t0 is None:
                t0 = ts
            if row["observed_value"] is None:
                continue
            series[row["measurement_type"]][row["component_id"]].append(
                (_seconds_between(t0, ts), row["observed_value"])
            )
    return series


def load_ground_truth_series(path: Path) -> dict[str, list[tuple[float, float]]]:
    """label (e.g. "GRADUAL_RESTRICTION severity" or "circuit <id> restriction_factor") ->
    [(t_seconds, value), ...]."""
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    t0 = None
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            ts = row["simulation_timestamp"]
            if t0 is None:
                t0 = ts
            t = _seconds_between(t0, ts)
            for scenario in row.get("scenarios", []):
                label = f"{scenario['scenario_type']} severity"
                series[label].append((t, scenario["severity"]))
            for circuit in row.get("circuits", []):
                label = f"circuit {circuit['circuit_id'][:8]} restriction_factor"
                series[label].append((t, circuit["restriction_factor"]))
                label = f"circuit {circuit['circuit_id'][:8]} leakage_factor"
                series[label].append((t, circuit["leakage_factor"]))
    return series


def plot(
    series: dict[str, dict[str, list[tuple[float, float]]]],
    output: Path,
    title: str,
    ground_truth: dict[str, list[tuple[float, float]]] | None = None,
) -> None:
    panels = list(_PANELS)
    n_panels = len(panels) + (1 if ground_truth else 0)
    fig, axes = plt.subplots(n_panels, 1, figsize=(12, 3 * n_panels), sharex=True)

    fig.suptitle(f"{title}\nDEMO / SYNTHETIC ENGINEERING DATA — not validated production telemetry")

    axes_iter = iter(axes)
    if ground_truth:
        gt_ax = next(axes_iter)
        for label, points in ground_truth.items():
            points.sort(key=lambda p: p[0])
            xs = [p[0] / 3600.0 for p in points]
            ys = [p[1] for p in points]
            gt_ax.plot(xs, ys, linewidth=0.8, label=label)
        gt_ax.set_ylabel("Ground truth (0-1)", fontsize=8)
        gt_ax.legend(fontsize=6, loc="upper right")
        gt_ax.set_title("GROUND TRUTH — never observable telemetry", fontsize=8, style="italic")

    for ax, (label, measurement_types) in zip(axes_iter, panels, strict=True):
        plotted = False
        for mt in measurement_types:
            for component_id, points in series.get(mt, {}).items():
                if not points:
                    continue
                points.sort(key=lambda p: p[0])
                xs = [p[0] / 3600.0 for p in points]
                ys = [p[1] for p in points]
                ax.plot(xs, ys, linewidth=0.8, label=f"{mt}:{component_id[:8]}")
                plotted = True
        ax.set_ylabel(label, fontsize=8)
        if plotted:
            ax.legend(fontsize=6, loc="upper right")
        else:
            ax.text(
                0.5, 0.5, "no data for this measurement type", transform=ax.transAxes, ha="center"
            )

    axes[-1].set_xlabel("simulated time (hours)")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=120)
    print(f"Wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readings", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="LubriSense simulator validation")
    args = parser.parse_args()

    series = load_series(args.readings)
    ground_truth = load_ground_truth_series(args.ground_truth) if args.ground_truth else None
    plot(series, args.output, args.title, ground_truth=ground_truth)


if __name__ == "__main__":
    main()
