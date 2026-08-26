import { describe, expect, it } from "vitest";

import { ALL_ROLES, ROLE_LABELS, VISIBLE_DEMO_ROLES, roleHasPermission } from "@/lib/permissions";

/**
 * Live Demo Quality Cleanup §1 — the external product's identity selector must only
 * ever show Technician/Admin, with no "Demo" prefix, while every other backend RBAC
 * role stays fully defined (required by app/auth/permissions.py's real matrix and by
 * tests/auth/test_permissions.py) — this only trims what the selector *shows*.
 */
describe("VISIBLE_DEMO_ROLES", () => {
  it("exposes only Technician and Admin", () => {
    expect(VISIBLE_DEMO_ROLES).toEqual(["TECHNICIAN", "ADMIN"]);
  });

  it("every visible role has a plain label with no 'Demo' prefix/suffix", () => {
    for (const role of VISIBLE_DEMO_ROLES) {
      expect(ROLE_LABELS[role]).not.toMatch(/demo/i);
    }
    expect(ROLE_LABELS.TECHNICIAN).toBe("Technician");
    expect(ROLE_LABELS.ADMIN).toBe("Admin");
  });

  it("does not delete the other backend RBAC roles — they stay fully defined", () => {
    expect(ALL_ROLES).toEqual([
      "VIEWER",
      "TECHNICIAN",
      "RELIABILITY_ENGINEER",
      "PLANT_MANAGER",
      "DATA_SCIENTIST",
      "ADMIN",
    ]);
  });

  it("Technician and Admin still receive their existing, correct permissions", () => {
    expect(roleHasPermission("TECHNICIAN", "MAINTENANCE_WRITE")).toBe(true);
    expect(roleHasPermission("TECHNICIAN", "AGENT_USE")).toBe(true);
    expect(roleHasPermission("TECHNICIAN", "INCIDENT_MANAGE")).toBe(false);
    expect(roleHasPermission("TECHNICIAN", "AUDIT_READ")).toBe(false);

    expect(roleHasPermission("ADMIN", "INCIDENT_MANAGE")).toBe(true);
    expect(roleHasPermission("ADMIN", "ASSET_MANAGE")).toBe(true);
    expect(roleHasPermission("ADMIN", "AUDIT_READ")).toBe(true);
    expect(roleHasPermission("ADMIN", "ADMIN_CONFIG")).toBe(true);
  });
});
