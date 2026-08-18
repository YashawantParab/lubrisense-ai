"""Read-only topology loader — resolves a `MachineTopology` from the live Phase 2 Postgres
schema (Phase 3 brief §2: "do not create a separate disconnected asset universe").

Deliberately plain `psycopg` + hand-written SQL rather than importing the backend's
SQLAlchemy ORM: the simulator is a separate service with its own `pyproject.toml`/venv
(TECHNICAL_DECISIONS.md ADR-011); depending on `backend.app.*` would couple two services
that are supposed to be independently deployable. This module only ever reads — it never
writes to the domain schema.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row

from simulator.domain.topology import (
    BearingTopology,
    CircuitTopology,
    ControllerTopology,
    DistributorTopology,
    LubricationPointTopology,
    LubricationSystemTopology,
    MachineTopology,
    PumpTopology,
    ReservoirTopology,
    SensorTopology,
)

DEFAULT_DATABASE_URL = "postgresql://lubrisense:lubrisense@localhost:5432/lubrisense"

_SENSOR_ATTACHMENT_COLUMNS = (
    "machine_id",
    "bearing_id",
    "lubrication_system_id",
    "reservoir_id",
    "pump_id",
    "circuit_id",
)


def resolve_database_url() -> str:
    """`DATABASE_URL` (same variable name as `backend/app/core/config.py::Settings`) with
    the `+psycopg` SQLAlchemy driver qualifier stripped — plain `psycopg` doesn't use it."""
    raw = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    return raw.replace("postgresql+psycopg://", "postgresql://")


def _sensor_from_row(row: dict[str, Any]) -> SensorTopology:
    attached_type = next(c for c in _SENSOR_ATTACHMENT_COLUMNS if row[c] is not None)
    return SensorTopology(
        id=row["id"],
        sensor_code=row["sensor_code"],
        sensor_type=row["sensor_type"],
        unit=row["unit"],
        attached_entity_type=attached_type.removesuffix("_id"),
        attached_entity_id=row[attached_type],
    )


class TopologyRepository:
    """One connection, read-only, used only at simulation setup (not per-tick)."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or resolve_database_url()

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def load_machine_topology(
        self, *, asset_code: str | None = None, machine_id: uuid.UUID | None = None
    ) -> MachineTopology:
        if not asset_code and not machine_id:
            raise ValueError("Provide either asset_code or machine_id")

        with self._connect() as conn:
            machine_row = self._fetch_machine(conn, asset_code=asset_code, machine_id=machine_id)
            machine_pk: uuid.UUID = machine_row["id"]
            tenant_id: uuid.UUID = machine_row["tenant_id"]

            bearings = self._fetch_bearings(conn, machine_pk)
            lubrication_system = self._fetch_lubrication_system(conn, machine_pk)
            sensors = self._fetch_sensors(conn, machine_pk, bearings, lubrication_system)

        return MachineTopology(
            id=machine_pk,
            tenant_id=tenant_id,
            name=machine_row["name"],
            asset_code=machine_row["asset_code"],
            machine_type=machine_row["machine_type"],
            criticality=machine_row["criticality"],
            bearings=bearings,
            lubrication_system=lubrication_system,
            sensors=sensors,
        )

    def _fetch_machine(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        *,
        asset_code: str | None,
        machine_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        query: str
        params: tuple[object, ...]
        if machine_id is not None:
            query, params = "SELECT * FROM machine WHERE id = %s", (machine_id,)
        else:
            query, params = "SELECT * FROM machine WHERE asset_code = %s", (asset_code,)
        row = conn.execute(query, params).fetchone()
        if row is None:
            identifier = machine_id or asset_code
            raise LookupError(f"No machine found for {identifier!r} in the live database")
        return row

    def _fetch_bearings(
        self, conn: psycopg.Connection[dict[str, Any]], machine_id: uuid.UUID
    ) -> tuple[BearingTopology, ...]:
        rows = conn.execute(
            "SELECT id, name, position, criticality FROM bearing "
            "WHERE machine_id = %s ORDER BY position",
            (machine_id,),
        ).fetchall()
        return tuple(
            BearingTopology(
                id=r["id"], name=r["name"], position=r["position"], criticality=r["criticality"]
            )
            for r in rows
        )

    def _fetch_lubrication_system(
        self, conn: psycopg.Connection[dict[str, Any]], machine_id: uuid.UUID
    ) -> LubricationSystemTopology | None:
        ls_row = conn.execute(
            "SELECT * FROM lubrication_system WHERE machine_id = %s LIMIT 1", (machine_id,)
        ).fetchone()
        if ls_row is None:
            return None

        reservoir_row = conn.execute(
            "SELECT * FROM reservoir WHERE lubrication_system_id = %s LIMIT 1", (ls_row["id"],)
        ).fetchone()
        pump_row = conn.execute(
            "SELECT * FROM pump WHERE lubrication_system_id = %s LIMIT 1", (ls_row["id"],)
        ).fetchone()
        controller_row = conn.execute(
            "SELECT * FROM controller WHERE lubrication_system_id = %s LIMIT 1", (ls_row["id"],)
        ).fetchone()
        distributor_row = conn.execute(
            "SELECT * FROM distributor WHERE lubrication_system_id = %s LIMIT 1", (ls_row["id"],)
        ).fetchone()
        if reservoir_row is None or pump_row is None or controller_row is None:
            raise LookupError(
                f"Lubrication system {ls_row['id']} is missing a required "
                "reservoir/pump/controller row"
            )

        circuit_rows = conn.execute(
            "SELECT * FROM circuit WHERE lubrication_system_id = %s ORDER BY code",
            (ls_row["id"],),
        ).fetchall()
        circuits = []
        for c_row in circuit_rows:
            lp_rows = conn.execute(
                "SELECT id, code, bearing_id FROM lubrication_point "
                "WHERE circuit_id = %s ORDER BY code",
                (c_row["id"],),
            ).fetchall()
            circuits.append(
                CircuitTopology(
                    id=c_row["id"],
                    code=c_row["code"],
                    lubrication_points=tuple(
                        LubricationPointTopology(
                            id=lp["id"], code=lp["code"], bearing_id=lp["bearing_id"]
                        )
                        for lp in lp_rows
                    ),
                )
            )

        return LubricationSystemTopology(
            id=ls_row["id"],
            name=ls_row["name"],
            system_type=ls_row["system_type"],
            reservoir=ReservoirTopology(
                id=reservoir_row["id"],
                name=reservoir_row["name"],
                capacity_demo=(
                    float(reservoir_row["capacity_demo"])
                    if reservoir_row["capacity_demo"] is not None
                    else None
                ),
                capacity_unit=reservoir_row["capacity_unit"],
            ),
            pump=PumpTopology(
                id=pump_row["id"], name=pump_row["name"], pump_type=pump_row["pump_type"]
            ),
            controller=ControllerTopology(
                id=controller_row["id"],
                name=controller_row["name"],
                controller_type=controller_row["controller_type"],
            ),
            distributor=(
                DistributorTopology(id=distributor_row["id"], name=distributor_row["name"])
                if distributor_row is not None
                else None
            ),
            circuits=tuple(circuits),
        )

    def _fetch_sensors(
        self,
        conn: psycopg.Connection[dict[str, Any]],
        machine_id: uuid.UUID,
        bearings: tuple[BearingTopology, ...],
        lubrication_system: LubricationSystemTopology | None,
    ) -> tuple[SensorTopology, ...]:
        entity_ids = [machine_id, *[b.id for b in bearings]]
        if lubrication_system is not None:
            entity_ids += [
                lubrication_system.id,
                lubrication_system.reservoir.id,
                lubrication_system.pump.id,
                *[c.id for c in lubrication_system.circuits],
            ]
        if not entity_ids:
            return ()

        where_clause = " OR ".join(f"{col} = ANY(%s)" for col in _SENSOR_ATTACHMENT_COLUMNS)
        rows = conn.execute(
            f"SELECT * FROM sensor WHERE {where_clause} ORDER BY sensor_code",
            tuple([entity_ids] * len(_SENSOR_ATTACHMENT_COLUMNS)),
        ).fetchall()
        return tuple(_sensor_from_row(r) for r in rows)
