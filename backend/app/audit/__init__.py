"""Central auditability (Phase 25) — "who did what, when, to which entity, and why."

`app.audit.service.AuditService.record()` is the only way an `AuditEvent` row is ever
written; there is deliberately no update/delete method anywhere in this package (Phase 25
brief §25.4 — append-only through normal application APIs). See docs/AUDITABILITY.md.
"""
