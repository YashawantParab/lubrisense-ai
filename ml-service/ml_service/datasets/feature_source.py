"""Read-only reader of persisted Phase 10 `feature_vector` rows.

Deliberately plain `psycopg` + hand-written SQL, mirroring
`simulator.engine.repository.TopologyRepository` (ADR-011): `ml-service` is a separate
service and must not import the backend's SQLAlchemy ORM. This is mandatory for train/serve
parity (Phase 11 brief §3) — the exact same persisted `FeatureVector` rows the Phase 10
`FeatureEngine` computed (online or via `app.features.materialize`) are what this dataset
builder consumes; no feature is recomputed here.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

DEFAULT_DATABASE_URL = "postgresql://lubrisense:lubrisense@localhost:5432/lubrisense"


def resolve_database_url() -> str:
    raw = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    return raw.replace("postgresql+psycopg://", "postgresql://")


@dataclass(frozen=True, slots=True)
class PersistedFeatureVector:
    id: uuid.UUID
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    feature_set: str
    feature_set_version: str
    as_of_timestamp: datetime
    feature_values: dict[str, Any]
    missing_features: list[str]
    quality_summary: dict[str, Any]


class FeatureVectorSource:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or resolve_database_url()

    def fetch(
        self,
        *,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        feature_set: str,
        start: datetime,
        end: datetime,
    ) -> list[PersistedFeatureVector]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as conn,
            conn.cursor() as cur,
        ):
            cur.execute(
                """
                SELECT id, tenant_id, machine_id, feature_set, feature_set_version,
                       as_of_timestamp, feature_values, missing_features, quality_summary
                FROM feature_vector
                WHERE tenant_id = %s AND machine_id = %s AND feature_set = %s
                  AND as_of_timestamp >= %s AND as_of_timestamp <= %s
                ORDER BY as_of_timestamp ASC
                """,
                (str(tenant_id), str(machine_id), feature_set, start, end),
            )
            rows = cur.fetchall()
        return [
            PersistedFeatureVector(
                id=row["id"],
                tenant_id=row["tenant_id"],
                machine_id=row["machine_id"],
                feature_set=row["feature_set"],
                feature_set_version=row["feature_set_version"],
                as_of_timestamp=row["as_of_timestamp"],
                feature_values=row["feature_values"],
                missing_features=row["missing_features"],
                quality_summary=row["quality_summary"],
            )
            for row in rows
        ]
