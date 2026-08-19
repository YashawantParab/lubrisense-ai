# CMMS Integration — Phase 20

## Purpose

`app.cmms` is the integration boundary between LubriSense's own maintenance workflow and
an enterprise CMMS (Computerized Maintenance Management System), without inventing a
proprietary vendor API (Phase 20 brief §20.1).

## Adapter boundary

`app.cmms.domain.adapter.CMMSAdapter` is a `Protocol` with four operations:
`create_work_order_draft`, `get_work_order`, `update_work_order_status`, `add_note`. Core
`app.maintenance`/`app.incidents` domain logic never binds directly to one vendor — it
only ever talks to this protocol through `CMMSService`.

## Demo CMMS

`app.cmms.adapters.demo_adapter.DemoCMMSAdapter` is the only adapter this reference
implementation actually calls. It persists `DemoCMMSWorkOrder` rows locally
(tenant-scoped), generating a demo external reference (`DEMO-WO-XXXXXXXXXX`).

## External adapter stubs

`app.cmms.adapters.external_stubs.SAPPMAdapterStub`/`MaximoAdapterStub` exist purely to
demonstrate the adapter boundary is real — every method raises `NotImplementedError`
naming exactly what a real integration would need (authentication, endpoint URL, payload
field mapping). **No real endpoint paths, auth schemes, or payload formats are invented**
(Phase 20 brief §20.3).

## Draft-first

Every work order created here is a **local draft** (`CMMSWorkOrderStatus.DRAFT`) — never
an automatic external submission. `MaintenanceCase`/`DecisionAssessment` may recommend
creating a draft; a human remains responsible for any real external submission (Phase 20
brief §20.4). The API surface reflects this: there is no "submit externally" endpoint in
this reference implementation.

## Idempotency

Exactly one `DemoCMMSWorkOrder` per `MaintenanceCase` — enforced by a real database
`UniqueConstraint(tenant_id, maintenance_case_id)` (`uq_demo_cmms_work_order_case`), with
`DemoCMMSAdapter.create_work_order_draft()` also checking for an existing draft first
(get-before-insert), matching the idempotent-persistence pattern established since Phase
10's `FeatureRepository`.

## Failure isolation

`CMMSService` wraps every adapter call in a broad `try/except`, converting any adapter
failure into a single `CMMSUnavailableError` — the underlying `MaintenanceCase`/
`Incident` are **never** touched by a CMMS failure (Phase 20 brief §20.6). Verified live
via `tests/cmms/test_cmms_service.py::test_cmms_failure_is_isolated_and_case_remains_
usable`: a simulated adapter outage leaves the case/incident state completely unchanged,
and a subsequent retry with a working adapter succeeds.

## API

- `POST /api/v1/maintenance/cases/{id}/cmms-draft` — idempotent draft creation
- `GET /api/v1/cmms/work-orders/{external_reference}`
- `GET /api/v1/cmms/metrics`

## Known limitations

`DemoCMMSAdapter.add_note()` has no dedicated notes table yet — a real adapter would post
to the external system's own notes/comments API; this is a documented gap, not silently
swallowed. No work-order status sync loop (a real CMMS's own status changes are not
polled back into `DemoCMMSWorkOrder`) — `update_work_order_status()` exists on the
adapter/service but nothing calls it automatically yet.
