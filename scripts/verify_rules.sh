#!/usr/bin/env bash
# Proves the Phase 9 rules engine builds real, quality-gated, baseline-aware evidence
# findings end to end against the live stack: seeds hand-crafted (but realistic) telemetry
# directly into TimescaleDB for real seeded flagship sensors (mirrors verify_baselines.sh's
# own "synthetic, hand-built cases" convention — the rules engine doesn't consume Kafka
# either, see app.rules_engine.workers.worker's own docstring), builds a real Phase 8
# baseline via the backfill CLI, runs the Phase 9 reprocess CLI inside the real backend
# image, then verifies the resulting rule_finding rows directly via psql and through the
# live read API.
#
# NOTE on scope: the flagship (Conveyor 000) has 8 real registered sensors — PRESSURE,
# PUMP_CURRENT, RESERVOIR_LEVEL, RPM, BEARING_TEMPERATURE (x2), VIBRATION_RMS (x2) — no
# FLOW, PUMP_RUNTIME, or CYCLE_COMPLETION sensor exists in the Phase 2 demo seed topology.
# FLOW_PRESSURE_RESTRICTION_PATTERN/FLOW_PRESSURE_LEAKAGE_PATTERN (which require a FLOW
# signal by definition) are therefore verified against a full synthetic topology in
# backend/tests/rules_engine/test_rule_engine.py (real Postgres, real RuleEngine, not
# against this specific demo topology) rather than here — see docs/RULES_ENGINE.md
# "Verification scope" for the full account. This script instead demonstrates
# PRESSURE_ABOVE_CONTEXTUAL_BASELINE, PUMP_CURRENT_ABOVE_BASELINE,
# LUBRICATION_PATH_DEGRADATION_PATTERN (the generic catch-all — exactly the honest
# behavior brief §15 asks for when evidence exists but doesn't cleanly separate into a
# more specific pattern), and RESERVOIR_LEVEL_LOW/RESERVOIR_DEPLETION_ABNORMAL, all against
# the real flagship sensors.
#
# NOTE on the data-quality-worker: it independently re-evaluates every tracked sensor
# every ~60s (Phase 7) and will legitimately flag this script's deliberately dramatic
# hand-seeded jump as SPIKE_DETECTED on its own next cycle — correct Phase 7 behavior,
# and exactly what makes INSUFFICIENT_TRUSTED_DATA/quality-gating suppression real rather
# than simulated when it happens (see docs/RULES_ENGINE.md "Quality gating"). It is
# deliberately paused for this script's duration so the specific findings asserted below
# are deterministic, and always resumed on exit (including on failure) via the trap below.
#
# Requires the full stack running: `docker compose up -d`.
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-lubrisense-postgres}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-lubrisense-backend}"
RULES_WORKER_CONTAINER="${RULES_WORKER_CONTAINER:-lubrisense-rules-worker}"
DATA_QUALITY_WORKER_CONTAINER="${DATA_QUALITY_WORKER_CONTAINER:-lubrisense-data-quality-worker}"
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
    echo "verify_rules FAILED: container '$1' is not running. Run 'docker compose up -d' first." >&2
    exit 1
  fi
}

for c in "$POSTGRES_CONTAINER" "$BACKEND_CONTAINER" "$RULES_WORKER_CONTAINER" "$DATA_QUALITY_WORKER_CONTAINER"; do
  require_running "$c"
done

psql_query() {
  docker exec "$POSTGRES_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -t -A -c "$1"
}

docker stop "$DATA_QUALITY_WORKER_CONTAINER" >/dev/null
resume_quality_worker() {
  docker start "$DATA_QUALITY_WORKER_CONTAINER" >/dev/null
}
trap resume_quality_worker EXIT

echo "== 0. rules-worker health =="
WORKER_HEALTH="$(docker inspect -f '{{.State.Health.Status}}' "$RULES_WORKER_CONTAINER" 2>/dev/null || echo "unknown")"
if [ "$WORKER_HEALTH" = "healthy" ]; then
  pass "rules-worker container reports healthy"
else
  fail "rules-worker container health is '$WORKER_HEALTH' (expected healthy)"
fi

echo "== 1. find the real flagship PRESSURE + PUMP_CURRENT sensors and seed synthetic telemetry =="
# Resolve tenant/machine via the PRESSURE sensor's own circuit -> lubrication_system chain
# (matching how Phase 6's ContextEnrichmentService itself resolves machine_id — never
# Sensor.machine_id directly, since a circuit-attached sensor never sets that column).
PRESSURE_ROW="$(psql_query "
SELECT s.tenant_id, s.id, s.circuit_id, ls.machine_id
FROM sensor s
JOIN circuit c ON c.id = s.circuit_id AND c.tenant_id = s.tenant_id
JOIN lubrication_system ls ON ls.id = c.lubrication_system_id AND ls.tenant_id = c.tenant_id
JOIN tenant t ON t.id = s.tenant_id
WHERE t.slug='lubrisense-demo' AND s.sensor_type='PRESSURE'
ORDER BY s.id LIMIT 1;")"
TENANT_ID="$(echo "$PRESSURE_ROW" | cut -d'|' -f1)"
PRESSURE_SENSOR_ID="$(echo "$PRESSURE_ROW" | cut -d'|' -f2)"
CIRCUIT_ID="$(echo "$PRESSURE_ROW" | cut -d'|' -f3)"
MACHINE_ID="$(echo "$PRESSURE_ROW" | cut -d'|' -f4)"

PUMP_CURRENT_SENSOR_ID="$(psql_query "
SELECT s.id FROM sensor s
JOIN pump p ON p.id = s.pump_id AND p.tenant_id = s.tenant_id
JOIN lubrication_system ls ON ls.id = p.lubrication_system_id AND ls.tenant_id = p.tenant_id
WHERE ls.machine_id = '$MACHINE_ID' AND s.sensor_type = 'PUMP_CURRENT'
ORDER BY s.id LIMIT 1;")"

RESERVOIR_SENSOR_ID="$(psql_query "
SELECT s.id FROM sensor s
JOIN reservoir r ON r.id = s.reservoir_id AND r.tenant_id = s.tenant_id
JOIN lubrication_system ls ON ls.id = r.lubrication_system_id AND ls.tenant_id = r.tenant_id
WHERE ls.machine_id = '$MACHINE_ID' AND s.sensor_type = 'RESERVOIR_LEVEL'
ORDER BY s.id LIMIT 1;")"

if [ -z "$TENANT_ID" ] || [ -z "$PRESSURE_SENSOR_ID" ] || [ -z "$PUMP_CURRENT_SENSOR_ID" ] || [ -z "$RESERVOIR_SENSOR_ID" ]; then
  echo "verify_rules FAILED: could not find the expected flagship sensor set — run 'make seed' first." >&2
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
MACHINE_ID = uuid.UUID('$MACHINE_ID')
PRESSURE_SENSOR_ID = uuid.UUID('$PRESSURE_SENSOR_ID')
PUMP_CURRENT_SENSOR_ID = uuid.UUID('$PUMP_CURRENT_SENSOR_ID')
RESERVOIR_SENSOR_ID = uuid.UUID('$RESERVOIR_SENSOR_ID')
CIRCUIT_ID = uuid.UUID('$CIRCUIT_ID')

async def main():
    settings = get_settings()
    db = Database(settings)
    async with db.session() as session:
        now = datetime.now(UTC)
        healthy_start = now - timedelta(hours=3)
        anomaly_start = now - timedelta(minutes=15)

        def row(sensor_id, mtype, unit, t, value, operating_state='RUNNING_NORMAL_LOAD', **extra):
            base = {
                'event_id': uuid.uuid4(), 'schema_version': '1', 'correlation_id': str(uuid.uuid4()),
                'tenant_id': TENANT_ID, 'site_id': None, 'plant_id': None, 'production_line_id': None,
                'machine_id': MACHINE_ID, 'bearing_id': None, 'lubrication_system_id': None,
                'circuit_id': None, 'lubrication_point_id': None, 'sensor_id': sensor_id,
                'measurement_type': mtype, 'value': value, 'unit': unit,
                'quality': TelemetryQuality.GOOD, 'operating_state': operating_state,
                'source_timestamp': t, 'edge_received_timestamp': t, 'edge_emitted_timestamp': None,
                'mqtt_received_timestamp': now, 'kafka_published_timestamp': now,
                'consumer_received_timestamp': now, 'sequence_number': 1, 'gateway_id': 'GW-VERIFY',
                'device_id': 'sim-device', 'firmware_version': None, 'controller_version': None,
                'source': 'synthetic', 'metadata': {}, 'kafka_partition': 0, 'kafka_offset': 0,
            }
            base.update(extra)
            return base

        rows = []
        # Healthy baseline history (3h -> 15min ago) for both sensors.
        for i in range(120):
            t = healthy_start + timedelta(minutes=1.4 * i)
            rows.append(row(PRESSURE_SENSOR_ID, SensorType.PRESSURE, 'bar', t, 9.0, circuit_id=CIRCUIT_ID))
            rows.append(row(PUMP_CURRENT_SENSOR_ID, SensorType.PUMP_CURRENT, 'A', t, 3.0))
            rows.append(row(RESERVOIR_SENSOR_ID, SensorType.RESERVOIR_LEVEL, 'percent', t, 60.0 - 0.05 * i))

        # Anomalous recent window: pressure + pump current both elevated (evidence for
        # LUBRICATION_PATH_DEGRADATION_PATTERN — no FLOW sensor exists on this topology to
        # support the more specific FLOW_PRESSURE_RESTRICTION_PATTERN, see script header),
        # reservoir critically low.
        for i in range(30):
            t = anomaly_start + timedelta(seconds=15 * i)
            rows.append(row(PRESSURE_SENSOR_ID, SensorType.PRESSURE, 'bar', t, 22.0, circuit_id=CIRCUIT_ID))
            rows.append(row(PUMP_CURRENT_SENSOR_ID, SensorType.PUMP_CURRENT, 'A', t, 9.0))
            rows.append(row(RESERVOIR_SENSOR_ID, SensorType.RESERVOIR_LEVEL, 'percent', t, 5.0))

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f'{healthy_start.isoformat()}|{anomaly_start.isoformat()}|{now.isoformat()}')
    await db.dispose()

asyncio.run(main())
" 2>&1)"

if ! echo "$SEED_OUTPUT" | tail -1 | grep -q '|'; then
  echo "seeding failed:" >&2
  echo "$SEED_OUTPUT" >&2
  exit 1
fi
IFS='|' read -r HEALTHY_START ANOMALY_START END <<<"$(echo "$SEED_OUTPUT" | tail -1)"
pass "seeded healthy history + anomalous window for tenant=$TENANT_ID machine=$MACHINE_ID"

mark_eligible() {
  docker exec "$BACKEND_CONTAINER" python -c "
import asyncio, uuid
from app.core.config import get_settings
from app.infrastructure.database import Database
from app.data_quality.repositories.sensor_quality_state_repository import SensorQualityStateRepository
from app.domain.enums import Eligibility, QualityState

TENANT_ID = uuid.UUID('$TENANT_ID')
MACHINE_ID = uuid.UUID('$MACHINE_ID')
SENSOR_IDS = [uuid.UUID('$PRESSURE_SENSOR_ID'), uuid.UUID('$PUMP_CURRENT_SENSOR_ID'), uuid.UUID('$RESERVOIR_SENSOR_ID')]

async def main():
    db = Database(get_settings())
    async with db.session() as session:
        repo = SensorQualityStateRepository(session)
        for sid in SENSOR_IDS:
            await repo.upsert(TENANT_ID, sid, machine_id=MACHINE_ID, quality_state=QualityState.TRUSTED, eligibility=Eligibility.ELIGIBLE, policy_version='1')
        await session.commit()
    await db.dispose()

asyncio.run(main())
" >/tmp/rules_eligibility.log 2>&1 || { fail "eligibility upsert failed"; cat /tmp/rules_eligibility.log >&2; }
}

echo "== 2. mark sensors ELIGIBLE (bypassing the Phase 7 worker's own asynchronous judgment for this direct-seed case) =="
# NOTE: the real, independently-running data-quality-worker (Phase 7) also continuously
# re-evaluates every tracked sensor every ~60s — including these — and can legitimately
# flag a hand-seeded, deliberately dramatic synthetic jump as SPIKE_DETECTED on its own
# next cycle, independent of this script. This is Phase 7 correctly doing its job, not a
# bug; re-asserting ELIGIBLE immediately before both the baseline backfill and the rules
# reprocess (step 5 below) keeps this script deterministic despite that race.
mark_eligible
pass "sensors marked ELIGIBLE"

echo "== 3. build real ACTIVE baselines from the healthy window =="
for SENSOR_ID in "$PRESSURE_SENSOR_ID" "$PUMP_CURRENT_SENSOR_ID" "$RESERVOIR_SENSOR_ID"; do
  for i in 1 2; do
    docker exec "$BACKEND_CONTAINER" python -m app.baselines.workers.backfill \
      --tenant-id "$TENANT_ID" --sensor-id "$SENSOR_ID" --start "$HEALTHY_START" --end "$ANOMALY_START" \
      >/tmp/rules_baseline_backfill.log 2>&1 \
      || { fail "baseline backfill failed for sensor $SENSOR_ID"; cat /tmp/rules_baseline_backfill.log >&2; }
  done
done
ACTIVE_BASELINE_COUNT="$(psql_query "select count(*) from baseline_profile where sensor_id in ('$PRESSURE_SENSOR_ID','$PUMP_CURRENT_SENSOR_ID','$RESERVOIR_SENSOR_ID') and strategy='ROLLING_ASSET_BASELINE' and state='ACTIVE';")"
[ "$ACTIVE_BASELINE_COUNT" -ge 3 ] && pass "built $ACTIVE_BASELINE_COUNT ACTIVE rolling baselines" \
  || fail "expected >= 3 ACTIVE rolling baselines, found $ACTIVE_BASELINE_COUNT"

echo "== 4. re-assert ELIGIBLE immediately before reprocessing (see step 2's race note) =="
mark_eligible
pass "sensors re-marked ELIGIBLE"

echo "== 5. run rules reprocess three times (stability-gate confirmation) =="
for i in 1 2 3; do
  docker exec "$BACKEND_CONTAINER" python -m app.rules_engine.workers.reprocess \
    --tenant-id "$TENANT_ID" --machine-id "$MACHINE_ID" --start "$ANOMALY_START" --end "$END" \
    >/tmp/rules_reprocess_$i.log 2>&1 \
    || { fail "reprocess run $i failed"; cat /tmp/rules_reprocess_$i.log >&2; }
done
pass "reprocess ran three times without error"

echo "== 6. PRESSURE_ABOVE_CONTEXTUAL_BASELINE and PUMP_CURRENT_ABOVE_BASELINE are ACTIVE =="
PRESSURE_FINDING_STATE="$(psql_query "select state from rule_finding where machine_id='$MACHINE_ID' and finding_type='PRESSURE_ABOVE_CONTEXTUAL_BASELINE' order by first_detected_at desc limit 1;")"
[ "$PRESSURE_FINDING_STATE" = "ACTIVE" ] && pass "PRESSURE_ABOVE_CONTEXTUAL_BASELINE is ACTIVE" \
  || fail "PRESSURE_ABOVE_CONTEXTUAL_BASELINE state='$PRESSURE_FINDING_STATE' (expected ACTIVE)"

PUMP_FINDING_STATE="$(psql_query "select state from rule_finding where machine_id='$MACHINE_ID' and finding_type='PUMP_CURRENT_ABOVE_BASELINE' order by first_detected_at desc limit 1;")"
[ "$PUMP_FINDING_STATE" = "ACTIVE" ] && pass "PUMP_CURRENT_ABOVE_BASELINE is ACTIVE" \
  || fail "PUMP_CURRENT_ABOVE_BASELINE state='$PUMP_FINDING_STATE' (expected ACTIVE)"

echo "== 7. generic LUBRICATION_PATH_DEGRADATION_PATTERN fires (no FLOW sensor -> the specific restriction pattern cannot) =="
LPD_STATE="$(psql_query "select state from rule_finding where machine_id='$MACHINE_ID' and finding_type='LUBRICATION_PATH_DEGRADATION_PATTERN' order by first_detected_at desc limit 1;")"
[ "$LPD_STATE" = "ACTIVE" ] && pass "LUBRICATION_PATH_DEGRADATION_PATTERN is ACTIVE" \
  || fail "LUBRICATION_PATH_DEGRADATION_PATTERN state='$LPD_STATE' (expected ACTIVE)"

RESTRICTION_COUNT="$(psql_query "select count(*) from rule_finding where machine_id='$MACHINE_ID' and finding_type='FLOW_PRESSURE_RESTRICTION_PATTERN';")"
[ "$RESTRICTION_COUNT" = "0" ] && pass "FLOW_PRESSURE_RESTRICTION_PATTERN correctly never fires (no FLOW evidence exists)" \
  || fail "FLOW_PRESSURE_RESTRICTION_PATTERN unexpectedly present ($RESTRICTION_COUNT rows) with no FLOW sensor"

echo "== 8. RESERVOIR_LEVEL_LOW fires on the critically-low synthetic reading =="
RESERVOIR_STATE="$(psql_query "select state from rule_finding where machine_id='$MACHINE_ID' and finding_type='RESERVOIR_LEVEL_LOW' order by first_detected_at desc limit 1;")"
[ "$RESERVOIR_STATE" = "ACTIVE" ] && pass "RESERVOIR_LEVEL_LOW is ACTIVE" \
  || fail "RESERVOIR_LEVEL_LOW state='$RESERVOIR_STATE' (expected ACTIVE)"

echo "== 9. explainability: evidence/limitations/rule-version are populated, not opaque =="
EVIDENCE_JSON="$(psql_query "select evidence::text from rule_finding where machine_id='$MACHINE_ID' and finding_type='PRESSURE_ABOVE_CONTEXTUAL_BASELINE' order by first_detected_at desc limit 1;")"
LIMITATIONS_JSON="$(psql_query "select limitations::text from rule_finding where machine_id='$MACHINE_ID' and finding_type='PRESSURE_ABOVE_CONTEXTUAL_BASELINE' order by first_detected_at desc limit 1;")"
if echo "$EVIDENCE_JSON" | grep -q "baseline_median" && [ "$LIMITATIONS_JSON" != "[]" ]; then
  pass "PRESSURE_ABOVE_CONTEXTUAL_BASELINE has structured evidence and non-empty limitations"
else
  fail "finding is missing structured evidence or limitations (evidence=$EVIDENCE_JSON limitations=$LIMITATIONS_JSON)"
fi

echo "== 10. idempotency: a fourth identical reprocess does not create a new row =="
docker exec "$BACKEND_CONTAINER" python -m app.rules_engine.workers.reprocess \
  --tenant-id "$TENANT_ID" --machine-id "$MACHINE_ID" --start "$ANOMALY_START" --end "$END" \
  >/tmp/rules_reprocess_4.log 2>&1 \
  || { fail "reprocess run 4 failed"; cat /tmp/rules_reprocess_4.log >&2; }
VERSION_COUNT="$(psql_query "select count(*) from rule_finding where machine_id='$MACHINE_ID' and finding_type='PRESSURE_ABOVE_CONTEXTUAL_BASELINE' and state in ('CANDIDATE','ACTIVE','RECOVERING');")"
[ "$VERSION_COUNT" = "1" ] && pass "still exactly one non-terminal PRESSURE_ABOVE_CONTEXTUAL_BASELINE row" \
  || fail "expected exactly 1 non-terminal row, found $VERSION_COUNT"

echo "== 11. live API returns the same result =="
API_RESPONSE="$(curl -s -H "X-Tenant-ID: $TENANT_ID" "$API_BASE/api/v1/rules/machines/$MACHINE_ID")"
if echo "$API_RESPONSE" | grep -q '"PRESSURE_ABOVE_CONTEXTUAL_BASELINE"'; then
  pass "GET /api/v1/rules/machines/{id} reports the PRESSURE_ABOVE_CONTEXTUAL_BASELINE finding"
else
  fail "API response missing expected finding: $API_RESPONSE"
fi

SUMMARY_RESPONSE="$(curl -s -H "X-Tenant-ID: $TENANT_ID" "$API_BASE/api/v1/rules/summary")"
if echo "$SUMMARY_RESPONSE" | grep -q '"ACTIVE"'; then
  pass "GET /api/v1/rules/summary reports ACTIVE findings"
else
  fail "summary response missing ACTIVE findings: $SUMMARY_RESPONSE"
fi

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "verify_rules: ALL CHECKS PASSED"
  exit 0
else
  echo "verify_rules: $FAILURES CHECK(S) FAILED"
  exit 1
fi
