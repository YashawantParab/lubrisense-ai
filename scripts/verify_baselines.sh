#!/usr/bin/env bash
# Proves the Phase 8 baseline engine builds real, contextual, contamination-protected
# baselines end to end against the live stack: seeds hand-crafted (but realistic)
# telemetry directly into TimescaleDB for a real seeded sensor/machine (baselines don't
# consume Kafka — app.baselines.workers.worker's own docstring explains why — so this
# mirrors verify_data_quality.sh's "synthetic, hand-built cases" convention rather than a
# real MQTT publish), runs the backfill CLI inside the real backend image, then verifies
# the resulting baseline_profile rows directly via psql and through the live read API.
#
# Requires the full stack running: `docker compose up -d`.
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-lubrisense-postgres}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-lubrisense-backend}"
BASELINE_WORKER_CONTAINER="${BASELINE_WORKER_CONTAINER:-lubrisense-baseline-worker}"
PG_USER="${POSTGRES_USER:-lubrisense}"
PG_DB="${POSTGRES_DB:-lubrisense}"
API_BASE="${API_BASE:-http://localhost:8000}"

FAILURES=0
pass() { echo "  PASS: $1"; }
fail() {
  echo "  FAIL: $1" >&2
  FAILURES=$((FAILURES + 1))
}

require_running() {
  if ! docker inspect -f '{{.State.Running}}' "$1" >/dev/null 2>&1; then
    echo "verify_baselines FAILED: container '$1' is not running. Run 'docker compose up -d' first." >&2
    exit 1
  fi
}

for c in "$POSTGRES_CONTAINER" "$BACKEND_CONTAINER" "$BASELINE_WORKER_CONTAINER"; do
  require_running "$c"
done

psql_query() {
  docker exec "$POSTGRES_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -t -A -c "$1"
}

echo "== 0. baseline-worker health =="
WORKER_HEALTH="$(docker inspect -f '{{.State.Health.Status}}' "$BASELINE_WORKER_CONTAINER" 2>/dev/null || echo "unknown")"
if [ "$WORKER_HEALTH" = "healthy" ]; then
  pass "baseline-worker container reports healthy"
else
  fail "baseline-worker container health is '$WORKER_HEALTH' (expected healthy)"
fi

echo "== 1. find a real seeded BEARING_TEMPERATURE sensor + seed synthetic telemetry =="
# A real seeded sensor from the demo seed (make seed) — mirrors verify_data_quality.sh's
# own convention. Only SQL + `app.*` modules are used here (never `tests.factories`), since
# the runtime image doesn't include the `tests/` package.
#
# Per ADR-023 (exactly-one-attachment), a BEARING_TEMPERATURE sensor attaches to `bearing`,
# not directly to `machine` — the demo seed has zero BEARING_TEMPERATURE sensors with
# sensor.machine_id set (all 24 attach via bearing_id), so the machine must be resolved
# through the bearing's own `machine_id`, matching what `BaselineEngine.refresh_sensor`
# itself does via the *telemetry* row's resolved `machine_id`, not `Sensor.machine_id`.
SENSOR_ROW="$(psql_query "SELECT s.tenant_id, s.id, COALESCE(s.machine_id, b.machine_id) FROM sensor s JOIN tenant t ON t.id = s.tenant_id LEFT JOIN bearing b ON b.tenant_id = s.tenant_id AND b.id = s.bearing_id WHERE s.sensor_type = 'BEARING_TEMPERATURE' AND t.slug = 'lubrisense-demo' AND COALESCE(s.machine_id, b.machine_id) IS NOT NULL ORDER BY s.id LIMIT 1;")"
TENANT_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f1)"
SENSOR_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f2)"
MACHINE_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f3)"
if [ -z "$TENANT_ID" ] || [ -z "$SENSOR_ID" ]; then
  echo "verify_baselines FAILED: no seeded BEARING_TEMPERATURE sensor found — run 'make seed' first." >&2
  exit 1
fi

SEED_OUTPUT="$(docker exec "$BACKEND_CONTAINER" python -c "
import asyncio, uuid
from datetime import UTC, datetime, timedelta
from app.core.config import get_settings
from app.infrastructure.database import Database
from app.repositories.telemetry import TelemetryRepository
from app.domain.enums import SensorType, TelemetryQuality

TENANT_ID = uuid.UUID('$TENANT_ID')
SENSOR_ID = uuid.UUID('$SENSOR_ID')
MACHINE_ID = uuid.UUID('$MACHINE_ID')

async def main():
    settings = get_settings()
    db = Database(settings)
    async with db.session() as session:
        now = datetime.now(UTC)
        start = now - timedelta(hours=1)

        def row(t, value, operating_state):
            return {
                'event_id': uuid.uuid4(), 'schema_version': '1', 'correlation_id': str(uuid.uuid4()),
                'tenant_id': TENANT_ID, 'site_id': None, 'plant_id': None, 'production_line_id': None,
                'machine_id': MACHINE_ID, 'bearing_id': None, 'lubrication_system_id': None,
                'circuit_id': None, 'lubrication_point_id': None, 'sensor_id': SENSOR_ID,
                'measurement_type': SensorType.BEARING_TEMPERATURE, 'value': value, 'unit': 'degC',
                'quality': TelemetryQuality.GOOD, 'operating_state': operating_state,
                'source_timestamp': t, 'edge_received_timestamp': t, 'edge_emitted_timestamp': None,
                'mqtt_received_timestamp': now, 'kafka_published_timestamp': now,
                'consumer_received_timestamp': now, 'sequence_number': 1, 'gateway_id': 'GW-VERIFY',
                'device_id': 'sim-device', 'firmware_version': None, 'controller_version': None,
                'source': 'synthetic', 'metadata': {}, 'kafka_partition': 0, 'kafka_offset': 0,
            }

        rows = []
        for i in range(40):
            rows.append(row(start + timedelta(seconds=5 * i), 35.0, 'RUNNING_LOW_LOAD'))
        for i in range(40):
            rows.append(row(start + timedelta(minutes=20, seconds=5 * i), 85.0, 'RUNNING_HIGH_LOAD'))

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f'{start.isoformat()}|{now.isoformat()}')
    await db.dispose()

asyncio.run(main())
" 2>&1)"

if ! echo "$SEED_OUTPUT" | tail -1 | grep -q '|'; then
  echo "seeding failed:" >&2
  echo "$SEED_OUTPUT" >&2
  exit 1
fi
IFS='|' read -r START END <<<"$(echo "$SEED_OUTPUT" | tail -1)"
pass "seeded synthetic telemetry for tenant=$TENANT_ID machine=$MACHINE_ID sensor=$SENSOR_ID"

echo "== 2. run backfill twice (stability-gate confirmation) =="
for i in 1 2; do
  docker exec "$BACKEND_CONTAINER" python -m app.baselines.workers.backfill \
    --tenant-id "$TENANT_ID" --sensor-id "$SENSOR_ID" --start "$START" --end "$END" >/tmp/baseline_backfill_$i.log 2>&1 \
    || { fail "backfill run $i failed"; cat /tmp/baseline_backfill_$i.log >&2; }
done
pass "backfill ran twice without error"

echo "== 3. static engineering reference is immediately ACTIVE =="
STATIC_STATE="$(psql_query "select state from baseline_profile where sensor_id='$SENSOR_ID' and strategy='STATIC_ENGINEERING_REFERENCE';")"
[ "$STATIC_STATE" = "ACTIVE" ] && pass "STATIC_ENGINEERING_REFERENCE is ACTIVE" || fail "STATIC_ENGINEERING_REFERENCE state='$STATIC_STATE' (expected ACTIVE)"

echo "== 4. rolling baseline activates after two stable cycles =="
ROLLING_STATE="$(psql_query "select state from baseline_profile where sensor_id='$SENSOR_ID' and strategy='ROLLING_ASSET_BASELINE' and context_key='';")"
[ "$ROLLING_STATE" = "ACTIVE" ] && pass "ROLLING_ASSET_BASELINE is ACTIVE" || fail "ROLLING_ASSET_BASELINE state='$ROLLING_STATE' (expected ACTIVE)"

echo "== 5. load-dependent contextual profiles exist and genuinely differ =="
LOW_MEDIAN="$(psql_query "select statistics->>'median' from baseline_profile where sensor_id='$SENSOR_ID' and strategy='CONTEXTUAL_ASSET_BASELINE' and context_key='operating_state=RUNNING_LOW_LOAD';")"
HIGH_MEDIAN="$(psql_query "select statistics->>'median' from baseline_profile where sensor_id='$SENSOR_ID' and strategy='CONTEXTUAL_ASSET_BASELINE' and context_key='operating_state=RUNNING_HIGH_LOAD';")"
if [ -n "$LOW_MEDIAN" ] && [ -n "$HIGH_MEDIAN" ]; then
  DIFFERS="$(psql_query "select ($HIGH_MEDIAN - $LOW_MEDIAN) > 10;")"
  [ "$DIFFERS" = "t" ] && pass "RUNNING_HIGH_LOAD median ($HIGH_MEDIAN) > RUNNING_LOW_LOAD median ($LOW_MEDIAN)" \
    || fail "load-dependent profiles did not differ meaningfully (low=$LOW_MEDIAN high=$HIGH_MEDIAN)"
else
  fail "contextual profiles missing (low='$LOW_MEDIAN' high='$HIGH_MEDIAN')"
fi

echo "== 6. idempotency: a third identical backfill does not create a new version =="
docker exec "$BACKEND_CONTAINER" python -m app.baselines.workers.backfill \
  --tenant-id "$TENANT_ID" --sensor-id "$SENSOR_ID" --start "$START" --end "$END" >/tmp/baseline_backfill_3.log 2>&1 \
  || { fail "backfill run 3 failed"; cat /tmp/baseline_backfill_3.log >&2; }
VERSION_COUNT="$(psql_query "select count(*) from baseline_profile where sensor_id='$SENSOR_ID' and strategy='ROLLING_ASSET_BASELINE' and context_key='';")"
[ "$VERSION_COUNT" = "1" ] && pass "still exactly one ROLLING_ASSET_BASELINE row (no duplicate version)" \
  || fail "expected exactly 1 row, found $VERSION_COUNT"

echo "== 7. live API returns the same result =="
API_RESPONSE="$(curl -s -H "X-Tenant-ID: $TENANT_ID" "$API_BASE/api/v1/baselines/sensors/$SENSOR_ID")"
if echo "$API_RESPONSE" | grep -q '"READY"'; then
  pass "GET /api/v1/baselines/sensors/{id} reports READY readiness"
else
  fail "API response did not report READY: $API_RESPONSE"
fi

SUMMARY_RESPONSE="$(curl -s -H "X-Tenant-ID: $TENANT_ID" "$API_BASE/api/v1/baselines/summary")"
if echo "$SUMMARY_RESPONSE" | grep -q '"ACTIVE"'; then
  pass "GET /api/v1/baselines/summary reports ACTIVE profiles"
else
  fail "summary response missing ACTIVE profiles: $SUMMARY_RESPONSE"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "verify_baselines: ALL CHECKS PASSED"
  exit 0
else
  echo "verify_baselines: $FAILURES CHECK(S) FAILED"
  exit 1
fi
