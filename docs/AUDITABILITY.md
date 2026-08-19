# Auditability (Phase 25)

## Purpose

Answer, for any consequential action: who did it, when, to which entity, and why.

## Architecture

`app.domain.models.AuditEvent` (migration `12a414daf64c`) — a tenant-scoped, append-only
table. `app.audit.service.AuditService.record()` is the **only** write path; no
update/delete method exists anywhere in `app.audit`, and there is no `PUT`/`DELETE
/audit-events` route (§25.4). `app.audit.repository.AuditEventRepository.search()`
provides the only read path, always tenant-scoped.

Fields: `actor_id`, `actor_type`, `role`, `action`, `entity_type`, `entity_id`,
`correlation_id`, `request_id`, `before_summary`, `after_summary`, `reason`, `source`,
`occurred_at`, plus the standard `id`/`tenant_id`/`created_at`/`updated_at`. No secrets
are ever stored — `before_summary`/`after_summary`/`reason` are short strings populated
explicitly by application code, never a serialized request/response body.

## Actor types

`AuditActorType` — `HUMAN`, `SYSTEM`, `AGENT` (§25.3). `AuditActor.from_principal()`
builds a `HUMAN` actor from the authenticated `Principal` (Phase 24); `AuditActor
.system(name)` and `AuditActor.agent(name)` build the other two explicitly. A `SYSTEM`
event is never recorded as if a person performed it — e.g. incident creation from a
periodic/triggered evaluation is always `actor_type=SYSTEM`, `actor_id="incident
-service"`, regardless of who (if anyone) triggered the evaluation via the API.

## What is audited

| Action | Actor type | Where |
|---|---|---|
| Incident created | `SYSTEM` | `IncidentService._create_incident` |
| Incident acknowledged / investigation started / resolved / closed / reopened | `HUMAN` | `api/v1/incidents.py` |
| Maintenance case created / planned / started / finding recorded / action recorded / completed / cancelled | `HUMAN` | `api/v1/maintenance.py` |
| CMMS draft created | `HUMAN` | `api/v1/maintenance.py` |
| Knowledge document ingested / submitted / approved / retired | `HUMAN` | `api/v1/knowledge.py` |
| Agent draft artifact generated (checklist/work-order) | `AGENT` | `api/v1/agent.py` |

This is the exact list Phase 25 brief §25.2 enumerates as the minimum ("incident
acknowledgement/state changes, maintenance state changes, technician findings, feedback
classification, knowledge approval/retirement, CMMS draft creation, agent draft
generation"). Technician findings and feedback classification are both covered under the
maintenance-case audit calls (`MAINTENANCE_FINDING_RECORDED`,
`MAINTENANCE_CASE_COMPLETED` carrying the feedback classification as `reason`), rather
than as separate audit actions, since both are already sub-events of a maintenance-case
mutation the audit call already captures.

## Correlation

Every `AuditEvent.correlation_id` defaults to the request's own correlation id
(`app.core.context.get_correlation_id()`, propagated by `CorrelationIdMiddleware` since
Phase 1) when not explicitly supplied — so an audit row can always be cross-referenced
against the structured log lines for the same request.

## Immutability

Append-only through the normal application API (§25.4) — verified structurally (no
update/delete code path exists) rather than only by convention.

## API

`GET /api/v1/audit-events` — tenant-scoped, filterable by `actor_id`, `entity_type`,
`entity_id`, `action`, `correlation_id`, `since`/`until`; paginated (`PageParams`, same
mechanism as every other list endpoint). `GET /api/v1/audit-events/{id}` for a single
record. Both require `Permission.AUDIT_READ` (granted to `RELIABILITY_ENGINEER`,
`PLANT_MANAGER`, `ADMIN` — not `VIEWER`/`TECHNICIAN`/`DATA_SCIENTIST`, per
docs/SECURITY.md's role matrix).

## Known limitations

- Not every mutating action in the platform is audited — the list above is the Phase 25
  brief's explicit minimum, not exhaustive coverage of every write endpoint that predates
  Phase 25 (e.g. asset-hierarchy CRUD from Phase 2). Extending audit coverage there is a
  separable follow-up.
- Storage is a normal Postgres table, not write-once/WORM-backed storage — a real
  production deployment handling regulated audit requirements would want additional
  tamper-evidence (e.g. periodic hash-chaining, external log shipping) beyond "no
  update/delete API exists." Documented, not silently assumed solved (see
  docs/THREAT_MODEL.md "Audit tampering").
- No automatic retention/archival policy exists yet for `audit_event` — it grows
  unbounded, same as every other append-only table in this platform
  (`condition_assessment`, `incident_event`, etc.).
