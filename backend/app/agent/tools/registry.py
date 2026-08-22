"""The explicit tool allowlist (Phase 19 brief §19.2/§19.19). An unknown tool name fails
closed — `call_tool` never falls back to executing anything not in `ALLOWED_TOOLS`, and
there is no code path anywhere in this package that runs arbitrary SQL or an unregistered
function."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.agent.domain.models import ToolResult
from app.agent.tools import tool_functions
from app.agent.tools.context import ToolContext

ToolFunc = Callable[[ToolContext, dict[str, Any]], Awaitable[ToolResult]]

ALLOWED_TOOLS: dict[str, ToolFunc] = {
    "list_fleet_attention": tool_functions.list_fleet_attention,
    "get_asset_context": tool_functions.get_asset_context,
    "get_current_condition": tool_functions.get_current_condition,
    "get_current_decision": tool_functions.get_current_decision,
    "get_current_prognostic": tool_functions.get_current_prognostic,
    "get_incident": tool_functions.get_incident,
    "get_incident_timeline": tool_functions.get_incident_timeline,
    "get_maintenance_case": tool_functions.get_maintenance_case,
    "get_telemetry_summary": tool_functions.get_telemetry_summary,
    "search_approved_documentation": tool_functions.search_approved_documentation,
    "search_similar_service_cases": tool_functions.search_similar_service_cases,
    "generate_checklist_draft": tool_functions.generate_checklist_draft,
    "draft_work_order": tool_functions.draft_work_order,
}


async def call_tool(name: str, ctx: ToolContext, arguments: dict[str, Any]) -> ToolResult:
    func = ALLOWED_TOOLS.get(name)
    if func is None:
        return ToolResult(
            tool_name=name, status="DENIED", summary=f"Tool '{name}' is not on the allowlist."
        )
    try:
        return await func(ctx, arguments)
    except Exception as exc:  # noqa: BLE001 — a tool failure must never crash the whole
        # chat turn; it becomes one ERROR-status ToolResult the agent can still explain.
        return ToolResult(tool_name=name, status="ERROR", summary=str(exc))
