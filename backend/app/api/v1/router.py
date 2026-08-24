"""Aggregates all /api/v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    agent,
    audit,
    auth,
    baselines,
    cmms,
    commissioning,
    conditions,
    customer_overview,
    customers,
    data_quality,
    decisions,
    device_management,
    energy,
    features,
    fleet,
    gateways,
    hierarchy,
    incidents,
    intelligence,
    knowledge,
    lubrication_systems,
    machines,
    maintenance,
    ml,
    plants,
    product_metrics,
    production_lines,
    prognostics,
    rules,
    sensors,
    site_overview,
    sites,
    state_estimation,
    system,
    telemetry,
)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(system.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(customers.router)
api_v1_router.include_router(sites.router)
api_v1_router.include_router(plants.router)
api_v1_router.include_router(production_lines.router)
api_v1_router.include_router(machines.router)
api_v1_router.include_router(lubrication_systems.router)
api_v1_router.include_router(sensors.router)
api_v1_router.include_router(hierarchy.router)
api_v1_router.include_router(gateways.router)
api_v1_router.include_router(telemetry.router)
api_v1_router.include_router(data_quality.router)
api_v1_router.include_router(baselines.router)
api_v1_router.include_router(rules.router)
api_v1_router.include_router(features.router)
api_v1_router.include_router(ml.router)
api_v1_router.include_router(energy.router)
api_v1_router.include_router(state_estimation.router)
api_v1_router.include_router(conditions.router)
api_v1_router.include_router(prognostics.router)
api_v1_router.include_router(decisions.router)
api_v1_router.include_router(intelligence.router)
api_v1_router.include_router(incidents.router)
api_v1_router.include_router(maintenance.router)
api_v1_router.include_router(cmms.router)
api_v1_router.include_router(knowledge.router)
api_v1_router.include_router(agent.router)
api_v1_router.include_router(customer_overview.router)
api_v1_router.include_router(site_overview.router)
api_v1_router.include_router(fleet.router)
api_v1_router.include_router(product_metrics.router)
api_v1_router.include_router(audit.router)
api_v1_router.include_router(commissioning.router)
api_v1_router.include_router(device_management.router)
