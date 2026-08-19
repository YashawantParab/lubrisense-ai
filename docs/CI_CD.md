# CI/CD (Phase 34)

## Purpose

Make every change automatically verifiable — `.github/workflows/ci.yml` runs on every
push to `main` and every pull request.

## Pipeline structure

| Job | What it verifies | Services provisioned |
|---|---|---|
| `hygiene` | Prohibited-name scan, secret-pattern scan (fast, runs first, no deps installed) | none |
| `backend` | ruff, mypy, migrations reach head on a clean DB, full pytest suite | Postgres, Redis |
| `frontend` | eslint, tsc, prettier format check, production build | none |
| `ml-service` | ruff, mypy, full pytest suite | none (pure Python, no live Docker dependency) |
| `simulator` | ruff, mypy, full pytest suite against real seeded demo data | Postgres (+ backend deps for migrate/seed) |
| `edge` | ruff, mypy, full pytest suite including MQTT-integration tests | Postgres, Mosquitto |
| `docker-build` | backend/frontend/edge Docker images actually build | none |

The `hygiene` job intentionally has no dependency installation step and runs in
parallel with everything else — a prohibited-name or secret-pattern hit fails fast
without waiting for the (much slower) service-container jobs, satisfying the brief's
"separate fast PR checks from slower integration checks" §34.2 as far as this
platform's actual job graph allows (GitHub Actions runs independent jobs in parallel by
default; `hygiene` has no `needs:` dependency on anything, so it never blocks on the
slower jobs and typically finishes first).

## Test layers

Every job above already *is* the platform's real test suite for that package — there is
no separate "smoke test" tier maintained independently of the real suite, since
duplicating assertions across two tiers would be its own maintenance burden. The
`hygiene` job is the closest thing to a fast pre-check tier.

## Docker build verification

`docker-build` builds the backend, frontend, and edge images from their real
Dockerfiles on every CI run — catching a broken Dockerfile (a missing COPY, a stale
build arg) before it reaches `main`, independent of whether the images are ever run.
`ml-service` and `simulator` do not have their own Dockerfiles (consumed as local path
dependencies by `backend`/`edge` respectively — ADR-090) so there is nothing separate to
build-verify for them.

## Migration safety

The `backend` job's Postgres service container always starts empty, so
`uv run alembic upgrade head` running successfully *is* the clean-database
verification — not a separate step.

## Artifact policy

ML model binaries (`ml-service/artifacts/`) and generated datasets
(`ml-service/data/datasets/`, `ml-service/data/runs/`) are `.gitignore`d — never
committed. They are recreated deterministically via the real training/dataset-build
scripts documented in `docs/MLOPS.md` and `docs/ML_ARCHITECTURE.md`
(`python scripts/build_dataset.py`, `python -m ml_service.training.train_classifier`,
`python -m ml_service.training.train_anomaly`), not fetched from anywhere. CI does not
build or train models — that remains an explicitly human-invoked local step per the
project's no-auto-retraining rule.

## Dependency caching

`astral-sh/setup-uv@v3` runs with `enable-cache: true` in every uv-based job
(backend/ml-service/simulator/edge), keyed off each package's own `uv.lock`. The
frontend job caches npm via `actions/setup-node@v4`'s built-in `cache: npm`.

## Deployment boundary

**No external deployment workflow exists, and none was created this phase.** This
repository has no configured cloud provider, container registry, Kubernetes manifests,
or hosting target anywhere — inventing one now would be fabricated infrastructure, not
a real deployment boundary. What a real deployment workflow would need before it could
be added honestly:

- a named target (which cloud/host, which container registry)
- real, non-demo secrets management (this platform's `demo-login` auth is explicitly
  not production-grade — see `docs/SECURITY.md`)
- a decision on single-instance vs. multi-instance backend (Phase 33's per-worker
  connection-pool sizing, ADR-166, would need re-deriving per instance)
- the review items in `docs/INDUSTRIAL_ADOPTION.md`

Until those exist, `docker compose up` (this repository's actual, working local/demo
deployment mechanism) remains the only supported way to run the full stack — see the
root `README.md` "Local setup."

## Known limitations

- No CI job runs the ml-service *training* scripts (only its test suite) — training is
  explicitly a human-invoked local step (`docs/MLOPS.md`), not something CI reproduces
  on every push.
- The `docker-build` job builds images but does not run them or execute
  `docker compose up` against the full stack in CI — that remains a local verification
  step (this session's own workflow) rather than an automated CI gate, to keep CI
  runtime reasonable.
- No dependency-vulnerability scanning (e.g. `pip-audit`, `npm audit`) is wired into CI
  yet — run manually; see `docs/PRODUCTION_READINESS.md` "Dependency / security scan."
