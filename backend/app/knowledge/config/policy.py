"""`KnowledgePolicy` — versioned retrieval-sufficiency configuration (Phase 18 brief).
Fail-fast, same convention as every prior phase's config module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

DEFAULT_POLICY_PATH = Path(__file__).with_name("knowledge_v1.yaml")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KnowledgePolicy(_Frozen):
    policy_version: str
    similarity_weight: float
    lexical_weight: float
    sufficient_min_score: float
    partial_min_score: float
    max_results: int


_ENV_OVERRIDE = "KNOWLEDGE_POLICY_PATH"


def load_knowledge_policy(path: Path | None = None) -> KnowledgePolicy:
    target = path or (Path(p) if (p := os.environ.get(_ENV_OVERRIDE)) else DEFAULT_POLICY_PATH)
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    return KnowledgePolicy.model_validate(raw)
