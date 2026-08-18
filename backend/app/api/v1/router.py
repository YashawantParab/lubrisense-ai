"""Aggregates all /api/v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    baselines,
    customers,
    data_quality,
    hierarchy,
    lubrication_systems,
    machines,
    plants,
    production_lines,
    rules,
    sensors,
    sites,
    system,
    telemetry,
)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(system.router)
api_v1_router.include_router(customers.router)
api_v1_router.include_router(sites.router)
api_v1_router.include_router(plants.router)
api_v1_router.include_router(production_lines.router)
api_v1_router.include_router(machines.router)
api_v1_router.include_router(lubrication_systems.router)
api_v1_router.include_router(sensors.router)
api_v1_router.include_router(hierarchy.router)
api_v1_router.include_router(telemetry.router)
api_v1_router.include_router(data_quality.router)
api_v1_router.include_router(baselines.router)
api_v1_router.include_router(rules.router)
