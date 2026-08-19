"""`IncidentCorrelationPolicy` — versioned condition-family correlation configuration
(Phase 16 brief). Fail-fast, same convention as every prior phase's config module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_POLICY_PATH = Path(__file__).with_name("incident_correlation_v1.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IncidentCorrelationPolicy(_Frozen):
    policy_version: str
    engine_version: str
    condition_family_map: dict[str, str]


_ENV_OVERRIDE = "INCIDENT_CORRELATION_POLICY_PATH"


def load_incident_correlation_policy(path: Path | None = None) -> IncidentCorrelationPolicy:
    """Load and validate the incident-correlation policy. Raises `pydantic.
    ValidationError` on a malformed file rather than silently starting with unintended
    family groupings."""
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return IncidentCorrelationPolicy.model_validate(raw)
