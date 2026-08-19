# Hosted Release Gate

A pre-launch checklist for the actual public URLs, to be worked through **after** the
frontend and backend are deployed to their real hosted addresses and **before** sharing
the link with reviewers. This document is not itself a deployment step — see
`docs/HOSTED_DEPLOYMENT.md` for how to deploy.

This work is tracked as **POST-ROADMAP HOSTED DEPLOYMENT PREPARATION** — it sits after
Phase 39 (`IMPLEMENTATION_STATUS.md`) and is deliberately not a new numbered roadmap
phase.

**This checklist has not been run against live public URLs as part of this
POST-ROADMAP HOSTED DEPLOYMENT PREPARATION work.** No external deployment was performed
— everything below is either verified locally against equivalent conditions (noted per
item) or left unchecked, pending an actual deploy.

## How to use this checklist

Check each item only after verifying it against the real, publicly reachable URLs — not
against `localhost`. An item verified only locally is marked **(local-verified)** below;
re-verify it against the real deployment before checking it off for real.

## Infrastructure

- [ ] Backend `/health` returns `200` on the public backend URL.
- [ ] Backend `/ready` returns `200` (or a documented, accepted `503` if Redis was
      deliberately not provisioned — see `docs/HOSTED_DEPLOYMENT.md` §7) on the public
      backend URL.
- [ ] Frontend loads on the public Vercel URL with no console errors.
- [ ] `alembic upgrade head` has been run against the real hosted database and completed
      without error. **(local-verified** against an equivalent standard Postgres+pgvector
      target — ADR-175, `docs/HOSTED_DEPLOYMENT.md` §1.**)**
- [ ] `scripts/seed_hosted_demo.py` has been run against the real hosted database and
      completed without error. **(local-verified** — see "Local hosted-mode test result"
      in the POST-ROADMAP HOSTED DEPLOYMENT PREPARATION final report.**)**

## Security

- [ ] `APP_ENV=hosted_demo` (or `production`) is actually set on the real backend
      deployment — `Settings.model_post_init` should have already refused to boot
      otherwise, but confirm the process is actually running, not crash-looping.
- [ ] `AUTH_ENFORCEMENT_MODE=strict` confirmed (a request with no `Authorization` header
      to a protected endpoint returns `401`, not a silently-granted admin response).
      **(local-verified** via `backend/tests/test_api_auth_rbac.py`'s `strict_client`
      suite and the new `backend/tests/test_config.py` added for this work.**)**
- [ ] `DEMO_AUTH_SECRET` is a real generated secret, not the repository's insecure
      default (enforced at startup, but confirm the actual deployed value was rotated,
      not left as some other guessable placeholder).
- [ ] `CORS_ALLOWED_ORIGINS` is the real Vercel domain only, not `*` (enforced at
      startup).
- [ ] `TRUSTED_HOSTS` is the real backend hostname only, not `*` (enforced at startup).
- [ ] No secret value appears in any committed file, build log, or client-visible
      response. **(local-verified** — repository-wide secret-pattern scan re-run clean
      as part of this work, see final report.**)**
- [ ] `POST /api/v1/auth/demo-login` only ever issues tokens scoped to the one fixed demo
      tenant — confirm no way to request a token for a different `tenant_id` exists
      (it doesn't today: the endpoint resolves `tenant_id` from the validated
      `X-Tenant-ID` header, never a caller-supplied claim).

## Reviewer-facing functionality

- [ ] Overview page loads with real fleet counts.
- [ ] Fleet page loads and lists real machines.
- [ ] Flagship machine page (`/machines/88551bef-3149-5a8d-9645-bcd9502f4795`) loads,
      shows a resolved incident and the full telemetry story (healthy → deviation →
      recovery) in the charts.
- [ ] Healthy comparison machine page (Motor 001) loads and shows `NORMAL_OPERATION`
      with no incident.
- [ ] Incident detail page shows the full chronological timeline.
- [ ] Maintenance case page shows checklist, findings, actions, feedback, and the seeded
      CMMS draft.
- [ ] Knowledge page lists the approved corpus.
- [ ] Assistant answers a real question about the flagship machine with a citation to an
      approved document (not a fabricated procedure, not "insufficient documentation" for
      a question genuinely covered by the corpus).
- [ ] Metrics page loads with real, provenance-labeled numbers (no unlabeled figure).
- [ ] Device/Configuration panel on the flagship machine shows the seeded gateway
      snapshot instead of the empty state.
- [ ] Demo identity switcher works (can switch roles; RBAC visibly changes what actions
      are available).
- [ ] A hard refresh on a deep link (e.g. directly loading the incident detail URL, not
      navigating to it from the app) works correctly.

## Known, accepted limitations (do not block launch on these — see `docs/
HOSTED_DEPLOYMENT.md` §13 for detail)

- Industrial ingestion path (simulator/MQTT/Kafka/workers) is intentionally not publicly
  hosted.
- Redis is a soft dependency; its absence only affects `/ready`'s own accuracy.
- ~1-in-8 flake in the flagship recovery phase's cosmetic post-action condition label
  (ADR-172 addendum) — incident/maintenance outcomes are correct regardless; re-seed if
  the cosmetic label matters for a specific showing.
- No application-level rate limiting yet.

## Verdict

**Not marked passed.** This checklist must be worked through against real public URLs
after an actual deployment before this gate can be considered passed. See the
POST-ROADMAP HOSTED DEPLOYMENT PREPARATION summary in `IMPLEMENTATION_STATUS.md` for what
was and was not verified as of this document's authoring.
