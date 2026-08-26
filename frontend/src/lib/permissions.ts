import type { DemoRole } from "@/lib/api/auth-types";

/**
 * Presentation-only mirror of `app.auth.permissions.ROLE_PERMISSIONS`
 * (backend/app/auth/permissions.py) — used to hide/disable UI actions a role cannot
 * perform, purely for a coherent experience. The backend is the actual authorization
 * boundary in every case: a hidden button here is not a security control, and every
 * mutating request still goes through `require_permission` server-side regardless of
 * what this file says (Phase 29 brief "AUTH / ROLE UX" — "Backend remains the security
 * authority").
 */
export type Permission =
  | "INCIDENT_READ"
  | "INCIDENT_MANAGE"
  | "MAINTENANCE_READ"
  | "MAINTENANCE_WRITE"
  | "KNOWLEDGE_READ"
  | "KNOWLEDGE_ADMIN"
  | "CMMS_MANAGE"
  | "AGENT_USE"
  | "METRICS_READ"
  | "AUDIT_READ"
  | "ADMIN_CONFIG"
  | "ASSET_MANAGE";

const ALL_PERMISSIONS: Permission[] = [
  "INCIDENT_READ",
  "INCIDENT_MANAGE",
  "MAINTENANCE_READ",
  "MAINTENANCE_WRITE",
  "KNOWLEDGE_READ",
  "KNOWLEDGE_ADMIN",
  "CMMS_MANAGE",
  "AGENT_USE",
  "METRICS_READ",
  "AUDIT_READ",
  "ADMIN_CONFIG",
  "ASSET_MANAGE",
];

const ROLE_PERMISSIONS: Record<DemoRole, Permission[]> = {
  VIEWER: ["INCIDENT_READ", "MAINTENANCE_READ", "KNOWLEDGE_READ", "METRICS_READ"],
  TECHNICIAN: [
    "INCIDENT_READ",
    "MAINTENANCE_READ",
    "MAINTENANCE_WRITE",
    "KNOWLEDGE_READ",
    "AGENT_USE",
    "METRICS_READ",
  ],
  RELIABILITY_ENGINEER: [
    "INCIDENT_READ",
    "INCIDENT_MANAGE",
    "MAINTENANCE_READ",
    "MAINTENANCE_WRITE",
    "KNOWLEDGE_READ",
    "KNOWLEDGE_ADMIN",
    "CMMS_MANAGE",
    "AGENT_USE",
    "METRICS_READ",
    "AUDIT_READ",
    "ASSET_MANAGE",
  ],
  PLANT_MANAGER: [
    "INCIDENT_READ",
    "INCIDENT_MANAGE",
    "MAINTENANCE_READ",
    "MAINTENANCE_WRITE",
    "KNOWLEDGE_READ",
    "CMMS_MANAGE",
    "AGENT_USE",
    "METRICS_READ",
    "AUDIT_READ",
    "ASSET_MANAGE",
  ],
  DATA_SCIENTIST: ["INCIDENT_READ", "MAINTENANCE_READ", "KNOWLEDGE_READ", "METRICS_READ"],
  ADMIN: ALL_PERMISSIONS,
};

export function roleHasPermission(role: DemoRole, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role].includes(permission);
}

export const ROLE_LABELS: Record<DemoRole, string> = {
  VIEWER: "Viewer",
  TECHNICIAN: "Technician",
  RELIABILITY_ENGINEER: "Reliability Engineer",
  PLANT_MANAGER: "Plant Manager",
  DATA_SCIENTIST: "Data Scientist",
  ADMIN: "Admin",
};

export const ALL_ROLES: DemoRole[] = [
  "VIEWER",
  "TECHNICIAN",
  "RELIABILITY_ENGINEER",
  "PLANT_MANAGER",
  "DATA_SCIENTIST",
  "ADMIN",
];

/** The identity selector's visible option list (Live Demo Quality Cleanup §1) — the
 * external product experience only ever needs to demonstrate the two roles the rest of
 * the product actually differentiates on (`can()` checks, permission-gated actions):
 * a technician who can act on maintenance, and an admin with full access. The other four
 * `ALL_ROLES` values stay fully defined and permissioned above — required by
 * `app/auth/permissions.py`'s real RBAC matrix and by `tests/auth/test_permissions.py`
 * — this constant only trims what the demo *selector* shows, never what the backend
 * accepts or authorizes. */
export const VISIBLE_DEMO_ROLES: DemoRole[] = ["TECHNICIAN", "ADMIN"];
