# Infrastructure

Local-development and reference-deployment infrastructure configuration, orchestrated by
the root `docker-compose.yml`.

```
infrastructure/
  postgres/    (reserved for init scripts if the bootstrap migration is ever insufficient)
  mosquitto/config/mosquitto.conf   local MQTT broker configuration
  kafka/       (reserved for broker configuration beyond docker-compose env vars)
```

## PostgreSQL / TimescaleDB / pgvector

Image: `timescale/timescaledb-ha:pg16`. See `TECHNICAL_DECISIONS.md` ADR-014 for why this
single image was chosen over separate images/extensions: it bundles both `timescaledb` and
`vector` (pgvector) cleanly in one Postgres instance, verified by creating both extensions
in the same database (`backend/alembic/versions/0001_initial_schema.py`).

## Redis

Image: `redis:7-alpine`. Connectivity/health only in Phase 1 — no caching or business logic
yet (`backend/app/infrastructure/redis_client.py`).

## MQTT (Eclipse Mosquitto)

Image: `eclipse-mosquitto:2`, configured via `mosquitto/config/mosquitto.conf`. Anonymous
access is enabled for local development only — see the comment in that file. Verified with
`scripts/verify_mqtt.sh`.

## Kafka (KRaft, single-node)

Image: `apache/kafka:3.7.0`, running in KRaft mode (`process.roles=broker,controller`) —
no ZooKeeper. See `TECHNICAL_DECISIONS.md` ADR-015 for why KRaft was chosen over a
ZooKeeper-based setup. Verified with `scripts/verify_kafka.sh`.
