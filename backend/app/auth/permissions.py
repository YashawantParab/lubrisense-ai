"""The fixed six-role permission matrix (Phase 24 brief §24.2/§24.3).

`Permission` is deliberately coarse — one flag per *capability category*, not one per
endpoint — matching this reference platform's actual number of genuinely distinct
mutating surfaces. `ROLE_PERMISSIONS` is the single source of truth: nothing outside this
module compares a role string directly (§24.4) — see `app.auth.service
.AuthorizationService.require` and `app.api.deps.require_permission`.

No permission here grants physical machine control — none exists anywhere in this
platform (CLAUDE.md "Workflow Intelligence" boundary) — so `ADMIN` does not need special
treatment beyond "every permission a demo tenant admin plausibly needs" (§24.3: "Do not
assume ADMIN means physical machine control").
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.enums import UserRole


class Permission(StrEnum):
    INCIDENT_READ = "INCIDENT_READ"
    INCIDENT_MANAGE = "INCIDENT_MANAGE"  # acknowledge, investigate, plan, resolve, close
    MAINTENANCE_READ = "MAINTENANCE_READ"
    MAINTENANCE_WRITE = "MAINTENANCE_WRITE"  # create case, plan/start/finding/action/complete
    KNOWLEDGE_READ = "KNOWLEDGE_READ"
    KNOWLEDGE_ADMIN = "KNOWLEDGE_ADMIN"  # ingest/submit/approve/retire lifecycle
    CMMS_MANAGE = "CMMS_MANAGE"  # draft creation / retry
    AGENT_USE = "AGENT_USE"
    METRICS_READ = "METRICS_READ"  # customer/fleet overview + product metrics
    AUDIT_READ = "AUDIT_READ"
    ADMIN_CONFIG = "ADMIN_CONFIG"
    ASSET_MANAGE = "ASSET_MANAGE"  # commissioning workflow, device/config management


#: Explicit, reviewable capability matrix — see docs/SECURITY.md §"Role / permission
#: matrix" for the rationale behind each row (ADR-149).
ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.VIEWER: frozenset(
        {
            Permission.INCIDENT_READ,
            Permission.MAINTENANCE_READ,
            Permission.KNOWLEDGE_READ,
            Permission.METRICS_READ,
        }
    ),
    UserRole.TECHNICIAN: frozenset(
        {
            Permission.INCIDENT_READ,
            Permission.MAINTENANCE_READ,
            Permission.MAINTENANCE_WRITE,
            Permission.KNOWLEDGE_READ,
            Permission.AGENT_USE,
            Permission.METRICS_READ,
        }
    ),
    UserRole.RELIABILITY_ENGINEER: frozenset(
        {
            Permission.INCIDENT_READ,
            Permission.INCIDENT_MANAGE,
            Permission.MAINTENANCE_READ,
            Permission.MAINTENANCE_WRITE,
            Permission.KNOWLEDGE_READ,
            Permission.KNOWLEDGE_ADMIN,
            Permission.CMMS_MANAGE,
            Permission.AGENT_USE,
            Permission.METRICS_READ,
            Permission.AUDIT_READ,
            Permission.ASSET_MANAGE,
        }
    ),
    UserRole.PLANT_MANAGER: frozenset(
        {
            Permission.INCIDENT_READ,
            Permission.INCIDENT_MANAGE,
            Permission.MAINTENANCE_READ,
            Permission.MAINTENANCE_WRITE,
            Permission.KNOWLEDGE_READ,
            Permission.CMMS_MANAGE,
            Permission.AGENT_USE,
            Permission.METRICS_READ,
            Permission.AUDIT_READ,
            Permission.ASSET_MANAGE,
        }
    ),
    UserRole.DATA_SCIENTIST: frozenset(
        {
            Permission.INCIDENT_READ,
            Permission.MAINTENANCE_READ,
            Permission.KNOWLEDGE_READ,
            Permission.METRICS_READ,
        }
    ),
    UserRole.ADMIN: frozenset(Permission),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]
