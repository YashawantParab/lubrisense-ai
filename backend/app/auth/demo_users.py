"""A small, deterministic demo identity per role (Phase 24 brief §24.6).

*** DEMO USERS — NOT REAL ACCOUNTS. *** These exist so `POST /api/v1/auth/demo-login`
can issue a token for a role without a real user-management system. `user_id` values are
stable, greppable, and obviously synthetic — see docs/SECURITY.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import UserRole


@dataclass(frozen=True)
class DemoUser:
    user_id: str
    display_name: str
    role: UserRole


DEMO_USERS: dict[UserRole, DemoUser] = {
    UserRole.VIEWER: DemoUser("demo-viewer", "Viewer", UserRole.VIEWER),
    UserRole.TECHNICIAN: DemoUser("demo-technician", "Technician", UserRole.TECHNICIAN),
    UserRole.RELIABILITY_ENGINEER: DemoUser(
        "demo-reliability-engineer", "Reliability Engineer", UserRole.RELIABILITY_ENGINEER
    ),
    UserRole.PLANT_MANAGER: DemoUser("demo-plant-manager", "Plant Manager", UserRole.PLANT_MANAGER),
    UserRole.DATA_SCIENTIST: DemoUser(
        "demo-data-scientist", "Data Scientist", UserRole.DATA_SCIENTIST
    ),
    UserRole.ADMIN: DemoUser("demo-admin", "Admin", UserRole.ADMIN),
}
