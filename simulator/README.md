# Simulator

A physics-informed industrial simulator for a centralized lubrication system and the
machine it protects. Stands in for real sensors and lubrication controllers
(`docs/DOMAIN_MODEL.md` §2) so real industrial integrations (real sensors, OPC UA/MQTT
device schemas — `docs/ARCHITECTURE.md` §10) can replace it later without redesigning the
platform (`TECHNICAL_DECISIONS.md` ADR-001).

**Phase 3 status: implemented.** Maintains hidden physical state per machine (operating
profile, lubrication cycles, reservoir/pump/circuit/bearing physics) and derives sensor
observations from it, reading real asset topology from the Phase 2 database rather than a
disconnected synthetic universe. See `docs/SIMULATOR.md` for the full design and
`docs/SYNTHETIC_DATA_MODEL.md` for the ground-truth/observed-telemetry separation.

Not yet implemented: failure injection (Phase 4), MQTT/Kafka telemetry publishing
(Phase 6), time-series persistence.

## Setup

```
cd simulator
uv sync --extra dev
```

## Run

```
uv run python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \
    --mode DEMO --output data/conveyor_000_24h
```

Writes `<output>.readings.jsonl`, `<output>.ground_truth.jsonl`, `<output>.meta.json` (and
`<output>.readings.csv` with `--csv`). Requires the Phase 1/2 Docker Compose stack running
(`docker compose up -d` from the repo root) with demo data seeded (`make seed`).

## Validate

```
uv run python scripts/validate_plots.py --readings data/conveyor_000_24h.readings.jsonl \
    --output data/conveyor_000_24h.png
```

## Test / lint / typecheck

```
uv run pytest
uv run ruff check .
uv run mypy simulator
```

Generated datasets under `data/` are not committed — see the repo root `.gitignore`.
