from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CustomerServicePolicy:
    """Thresholds for `CustomerOperationalStatus` classification — a deliberately
    cautious, categorical policy, not an opaque numeric score (Phase 21 brief §21.4). See
    docs/CUSTOMER_SERVICES.md for the exact precedence and rationale (ADR-153)."""

    #: how recent telemetry must be for a machine to count as "currently reporting".
    telemetry_freshness_window_minutes: int = 60
    #: below this fraction of machines instrumented/reporting, visibility is degraded.
    minimum_visibility_ratio: float = 0.5
    #: how far back "recent technician-confirmed findings" looks.
    recent_findings_window_days: int = 30


DEFAULT_POLICY = CustomerServicePolicy()
