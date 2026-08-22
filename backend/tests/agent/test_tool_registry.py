"""Tool allowlist tests (Phase 19 brief §19.2/§19.3/§19.19) — an unknown tool must fail
closed, and no mutating lifecycle method may ever be registered as a tool."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools.context import ToolContext
from app.agent.tools.registry import ALLOWED_TOOLS, call_tool
from tests.factories import make_tenant

_FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "acknowledge_incident",
        "resolve_incident",
        "close_incident",
        "plan_case",
        "start_case",
        "complete_case",
        "record_finding",
        "record_action",
        "submit_work_order",
        "retrain_model",
        "promote_model",
        "stop_machine",
        "reset_controller",
    }
)


def test_no_mutating_lifecycle_tool_is_registered() -> None:
    assert ALLOWED_TOOLS.keys().isdisjoint(_FORBIDDEN_TOOL_NAMES)


def test_allowed_tools_match_the_brief() -> None:
    expected = {
        # `list_fleet_attention` (release-pass addition): the one tool not scoped to a
        # single machine/incident/case — a read-only, never-recomputing fleet-wide
        # snapshot (mirrors `GET /conditions/fleet-latest`/`GET /decisions/fleet-latest`)
        # gated by `app.agent.policy.is_fleet_wide_query` so it only runs for a message
        # that plausibly asks about the fleet, never merely because context is absent.
        "list_fleet_attention",
        "get_asset_context",
        "get_current_condition",
        "get_current_decision",
        "get_current_prognostic",
        "get_incident",
        "get_incident_timeline",
        "get_maintenance_case",
        "get_telemetry_summary",
        "search_approved_documentation",
        "search_similar_service_cases",
        "generate_checklist_draft",
        "draft_work_order",
    }
    assert set(ALLOWED_TOOLS.keys()) == expected


@pytest.mark.asyncio
async def test_unknown_tool_is_denied(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    ctx = ToolContext(session=db_session, tenant_id=tenant.id)
    result = await call_tool("delete_everything", ctx, {})
    assert result.status == "DENIED"


@pytest.mark.asyncio
async def test_tool_failure_returns_error_status_not_a_crash(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    ctx = ToolContext(session=db_session, tenant_id=tenant.id)
    result = await call_tool("get_current_condition", ctx, {})  # missing required machine_id
    assert result.status == "ERROR"
