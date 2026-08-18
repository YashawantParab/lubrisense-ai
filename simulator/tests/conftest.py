from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from simulator.config.loader import EngineeringConfig, load_engineering_config
from simulator.engine.repository import TopologyRepository

FLAGSHIP_ASSET_CODE = "L1-7B43-M000"  # "Conveyor 000" — seeded Phase 2 demo tenant


@pytest.fixture(scope="session")
def engineering_config() -> EngineeringConfig:
    return load_engineering_config()


@pytest.fixture(scope="session")
def flagship_topology():  # type: ignore[no-untyped-def]
    """Requires the live Phase 2 Postgres stack (docker compose) with demo data seeded.
    Skips instead of failing if unavailable, so unit-only test runs still work."""
    try:
        repo = TopologyRepository()
        return repo.load_machine_topology(asset_code=FLAGSHIP_ASSET_CODE)
    except Exception as exc:  # noqa: BLE001 - environment probe, not app logic
        pytest.skip(f"live database unavailable: {exc}")


@pytest.fixture
def fixed_start_time() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
