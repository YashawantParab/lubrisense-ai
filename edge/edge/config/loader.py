"""YAML + env-var config loader, mirroring `simulator.config.loader`'s pattern: the YAML
file is the single source of truth, this module only adds type safety/validation. Env vars
prefixed `EDGE_` override individual scalar fields for container/Compose deployment
(`docs/EDGE_ARCHITECTURE.md` §Configuration)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from edge.config.models import EdgeConfig

DEFAULT_CONFIG_PATH = Path(__file__).with_name("demo_edge.yaml")

_ENV_OVERRIDES = {
    "EDGE_GATEWAY_ID": ("gateway_id",),
    "EDGE_GATEWAY_CODE": ("gateway_code",),
    "EDGE_TENANT_ID": ("tenant_id",),
    "EDGE_ASSET_CODE": ("asset_code",),
    "EDGE_POLL_INTERVAL_SECONDS": ("poll_interval_seconds",),
    "EDGE_TRANSPORT_MODE": ("transport", "mode"),
    "EDGE_BROKER_HOST": ("transport", "broker_host"),
    "EDGE_BROKER_PORT": ("transport", "broker_port"),
    "EDGE_DB_PATH": ("buffer", "db_path"),
}


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    for env_var, path in _ENV_OVERRIDES.items():
        value = os.environ.get(env_var)
        if value is None:
            continue
        cursor = raw
        for key in path[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[path[-1]] = value
    return raw


def load_edge_config(path: Path | None = None) -> EdgeConfig:
    """Load and validate edge config. Raises `pydantic.ValidationError` on a malformed or
    out-of-range file rather than silently starting with unintended behavior (Phase 5 brief
    §20 — fail-fast startup validation)."""
    target = path or DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    raw = _apply_env_overrides(raw)
    return EdgeConfig.model_validate(raw)
