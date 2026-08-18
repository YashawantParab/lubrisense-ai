#!/usr/bin/env bash
# Proves the Phase 7 data-quality engine detects real, hand-crafted quality issues end to
# end: MQTT publish -> Kafka (independent `lubrisense-data-quality` consumer group) ->
# QualityEngine/WindowEvaluator -> quality_issue/sensor_quality_state rows, inspected
# directly via psql — mirroring verify_pipeline.sh's proven convention (plan decision #10:
# these are synthetic, hand-built cases that only need crafted timestamps/sequence
# numbers/values, not real scenario physics; see run_scenario_validation.py for the
# SENSOR_DRIFT/SENSOR_DROPOUT/NETWORK_FAILURE cases that DO need real scenario physics).
#
# Requires the full stack running: `docker compose up -d`.
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-lubrisense-postgres}"
MOSQUITTO_CONTAINER="${MOSQUITTO_CONTAINER:-lubrisense-mosquitto}"
KAFKA_CONTAINER="${KAFKA_CONTAINER:-lubrisense-kafka}"
WORKER_CONTAINER="${WORKER_CONTAINER:-lubrisense-data-quality-worker}"
PG_USER="${POSTGRES_USER:-lubrisense}"
PG_DB="${POSTGRES_DB:-lubrisense}"

FAILURES=0
pass() { echo "  PASS: $1"; }
fail() {
  echo "  FAIL: $1" >&2
  FAILURES=$((FAILURES + 1))
}

require_running() {
  if ! docker inspect -f '{{.State.Running}}' "$1" >/dev/null 2>&1; then
    echo "verify_data_quality FAILED: container '$1' is not running. Run 'docker compose up -d' first." >&2
    exit 1
  fi
}

for c in "$POSTGRES_CONTAINER" "$MOSQUITTO_CONTAINER" "$KAFKA_CONTAINER" "$WORKER_CONTAINER"; do
  require_running "$c"
done

psql_query() {
  docker exec "$POSTGRES_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -t -A -c "$1"
}

# Polls a query (expected to return a single value) until it matches, or times out — quality
# processing is asynchronous (independent consumer group + periodic window task), so a fixed
# sleep would be flaky.
wait_for_query() {
  local query="$1" expected="$2" timeout="${3:-30}" waited=0 got=""
  while [ "$waited" -lt "$timeout" ]; do
    got="$(psql_query "$query")"
    if [ "$got" = "$expected" ]; then
      echo "$got"
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done
  echo "$got"
  return 1
}

# A different seeded sensor than verify_pipeline.sh's (which deliberately targets a mismatched
# measurement_type/sensor to prove Phase 6 doesn't care) — this one's own sensor_type/unit are
# read from the DB and used to build clean payloads, so most cases below isolate exactly one
# issue at a time rather than incidentally tripping CONTEXT_INCONSISTENCY on every payload.
SENSOR_ROW="$(psql_query "SELECT s.tenant_id, s.id, s.machine_id, s.sensor_type, s.unit FROM sensor s JOIN tenant t ON t.id = s.tenant_id WHERE s.machine_id IS NOT NULL AND t.slug = 'lubrisense-demo' ORDER BY s.id LIMIT 1;")"
TENANT_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f1)"
SENSOR_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f2)"
MACHINE_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f3)"
MEASUREMENT_TYPE="$(echo "$SENSOR_ROW" | cut -d'|' -f4)"
UNIT="$(echo "$SENSOR_ROW" | cut -d'|' -f5)"
GATEWAY_ID="$(psql_query "SELECT id FROM gateway WHERE tenant_id = '$TENANT_ID' ORDER BY id LIMIT 1;")"

if [ -z "$TENANT_ID" ] || [ -z "$SENSOR_ID" ] || [ -z "$GATEWAY_ID" ]; then
  echo "verify_data_quality FAILED: no seeded tenant/sensor/gateway found — run 'make seed' first." >&2
  exit 1
fi

# A SECOND, distinct sensor exclusively for case 11 (stuck-sensor): `check_stuck_sensor`
# evaluates the sensor's *whole* recent telemetry history, not just the points this script
# just published — sharing SENSOR_ID with cases 1-10's deliberately varied values (999999,
# null, etc.) would make that history non-constant and the stuck check would never fire.
STUCK_SENSOR_ROW="$(psql_query "SELECT s.id, s.machine_id, s.sensor_type, s.unit FROM sensor s JOIN tenant t ON t.id = s.tenant_id WHERE s.machine_id IS NOT NULL AND s.id != '$SENSOR_ID' AND s.sensor_type NOT IN ('CYCLE_COMPLETION','PISTON_MOVEMENT','PUMP_RUNTIME') AND t.slug = 'lubrisense-demo' ORDER BY s.id LIMIT 1;")"
STUCK_SENSOR_ID="$(echo "$STUCK_SENSOR_ROW" | cut -d'|' -f1)"
STUCK_MACHINE_ID="$(echo "$STUCK_SENSOR_ROW" | cut -d'|' -f2)"
STUCK_MEASUREMENT_TYPE="$(echo "$STUCK_SENSOR_ROW" | cut -d'|' -f3)"
STUCK_UNIT="$(echo "$STUCK_SENSOR_ROW" | cut -d'|' -f4)"

echo "Using tenant=$TENANT_ID sensor=$SENSOR_ID ($MEASUREMENT_TYPE, $UNIT) machine=$MACHINE_ID gateway=$GATEWAY_ID"
echo "Stuck-sensor case uses a separate sensor=$STUCK_SENSOR_ID ($STUCK_MEASUREMENT_TYPE, $STUCK_UNIT)"

build_payload() {
  # build_payload <event_id> <seq> <value> <source_timestamp> [extra_json_fields]
  local event_id="$1" seq="$2" value="$3" ts="$4" extra="${5:-}"
  local now
  now="$(date -u +%Y-%m-%dT%H:%M:%S.000000+00:00)"
  cat <<JSON
{"event_id":"$event_id","schema_version":"1","correlation_id":"$event_id","tenant_id":"$TENANT_ID","machine_id":"$MACHINE_ID","sensor_id":"$SENSOR_ID","measurement_type":"$MEASUREMENT_TYPE","value":$value,"unit":"$UNIT","quality":"GOOD","operating_state":"RUNNING_NORMAL_LOAD","source_timestamp":"$ts","edge_received_timestamp":"$now","sequence_number":$seq,"gateway_id":"$GATEWAY_ID","device_id":"verify-data-quality","source":"synthetic"$extra}
JSON
}

publish_payload() {
  docker exec "$MOSQUITTO_CONTAINER" mosquitto_pub -h localhost -t "lubrisense/v1/$TENANT_ID/$GATEWAY_ID/telemetry" -q 1 -m "$1"
}

now_ts() { date -u +%Y-%m-%dT%H:%M:%S.000000+00:00; }
new_uuid() { psql_query "SELECT gen_random_uuid();"; }

echo ""
echo "=== 1. Sequence gap ==="
# A unix-epoch-seconds base, not a small random offset: `sensor_quality_state.
# expected_next_sequence` is a monotonically-advancing, persistent counter that only ever
# grows across every run against this shared demo sensor (this script, verify_pipeline.sh,
# manual testing, ...) — a small random offset can fall *behind* an already-high counter
# from a prior run, silently breaking the sequence-gap assertion below.
BASE_SEQ=$(date +%s)
E1A="$(new_uuid)"
publish_payload "$(build_payload "$E1A" "$BASE_SEQ" 5.0 "$(now_ts)")"
sleep 4
E1B="$(new_uuid)"
publish_payload "$(build_payload "$E1B" "$((BASE_SEQ + 10))" 5.1 "$(now_ts)")"
sleep 4
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E1B' AND issue_type = 'SEQUENCE_GAP';" "SEQUENCE_GAP" 20)"
[ "$ISSUE" = "SEQUENCE_GAP" ] && pass "sequence gap detected" || fail "expected SEQUENCE_GAP for $E1B, got '$ISSUE'"

echo ""
echo "=== 2. Late arrival ==="
E2="$(new_uuid)"
PAST_TS="$(date -u -v-60S +%Y-%m-%dT%H:%M:%S.000000+00:00 2>/dev/null || date -u -d '60 seconds ago' +%Y-%m-%dT%H:%M:%S.000000+00:00)"
publish_payload "$(build_payload "$E2" $((BASE_SEQ + 20)) 5.2 "$PAST_TS")"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E2' AND issue_type IN ('LATE_ARRIVAL','VERY_LATE_ARRIVAL');" "LATE_ARRIVAL" 20)"
[ "$ISSUE" = "LATE_ARRIVAL" ] && pass "late arrival detected" || fail "expected LATE_ARRIVAL for $E2, got '$ISSUE'"

echo ""
echo "=== 3. Out of order ==="
NOW_TS="$(now_ts)"
EARLIER_TS="$(date -u -v-10S +%Y-%m-%dT%H:%M:%S.000000+00:00 2>/dev/null || date -u -d '10 seconds ago' +%Y-%m-%dT%H:%M:%S.000000+00:00)"
E3A="$(new_uuid)"
publish_payload "$(build_payload "$E3A" $((BASE_SEQ + 30)) 5.3 "$NOW_TS")"
sleep 4
E3B="$(new_uuid)"
publish_payload "$(build_payload "$E3B" $((BASE_SEQ + 31)) 5.35 "$EARLIER_TS")"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E3B' AND issue_type = 'OUT_OF_ORDER';" "OUT_OF_ORDER" 20)"
[ "$ISSUE" = "OUT_OF_ORDER" ] && pass "out-of-order arrival detected" || fail "expected OUT_OF_ORDER for $E3B, got '$ISSUE'"

echo ""
echo "=== 4. Duplicate pattern (same sensor/source_timestamp/value, different event_id) ==="
SHARED_TS="$(now_ts)"
E4A="$(new_uuid)"
publish_payload "$(build_payload "$E4A" $((BASE_SEQ + 40)) 5.4 "$SHARED_TS")"
sleep 4
E4B="$(new_uuid)"
publish_payload "$(build_payload "$E4B" $((BASE_SEQ + 41)) 5.4 "$SHARED_TS")"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E4B' AND issue_type = 'DUPLICATE_PATTERN';" "DUPLICATE_PATTERN" 20)"
[ "$ISSUE" = "DUPLICATE_PATTERN" ] && pass "duplicate pattern detected" || fail "expected DUPLICATE_PATTERN for $E4B, got '$ISSUE'"

echo ""
echo "=== 5. Out of range ==="
E5="$(new_uuid)"
publish_payload "$(build_payload "$E5" $((BASE_SEQ + 50)) 999999999.0 "$(now_ts)")"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E5' AND issue_type = 'OUT_OF_RANGE';" "OUT_OF_RANGE" 20)"
[ "$ISSUE" = "OUT_OF_RANGE" ] && pass "out-of-range value detected" || fail "expected OUT_OF_RANGE for $E5, got '$ISSUE'"

echo ""
echo "=== 6. Unit mismatch ==="
E6="$(new_uuid)"
PAYLOAD_6="$(build_payload "$E6" $((BASE_SEQ + 60)) 5.6 "$(now_ts)")"
PAYLOAD_6="$(echo "$PAYLOAD_6" | sed "s/\"unit\":\"$UNIT\"/\"unit\":\"xyz\"/")"
publish_payload "$PAYLOAD_6"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E6' AND issue_type = 'UNIT_MISMATCH';" "UNIT_MISMATCH" 20)"
[ "$ISSUE" = "UNIT_MISMATCH" ] && pass "unit mismatch detected" || fail "expected UNIT_MISMATCH for $E6, got '$ISSUE'"

echo ""
echo "=== 7. Context inconsistency (measurement_type != sensor's configured sensor_type) ==="
E7="$(new_uuid)"
MISMATCHED_TYPE="PRESSURE"
[ "$MEASUREMENT_TYPE" = "PRESSURE" ] && MISMATCHED_TYPE="RPM"
PAYLOAD_7="$(build_payload "$E7" $((BASE_SEQ + 70)) 5.7 "$(now_ts)")"
PAYLOAD_7="$(echo "$PAYLOAD_7" | sed "s/\"measurement_type\":\"$MEASUREMENT_TYPE\"/\"measurement_type\":\"$MISMATCHED_TYPE\"/")"
publish_payload "$PAYLOAD_7"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E7' AND issue_type = 'CONTEXT_INCONSISTENCY';" "CONTEXT_INCONSISTENCY" 20)"
[ "$ISSUE" = "CONTEXT_INCONSISTENCY" ] && pass "context inconsistency detected" || fail "expected CONTEXT_INCONSISTENCY for $E7, got '$ISSUE'"

echo ""
echo "=== 8. Missing value (self-labeled, never zero-substituted) ==="
E8="$(new_uuid)"
PAYLOAD_8="$(build_payload "$E8" $((BASE_SEQ + 80)) null "$(now_ts)")"
PAYLOAD_8="$(echo "$PAYLOAD_8" | sed 's/"quality":"GOOD"/"quality":"MISSING"/')"
publish_payload "$PAYLOAD_8"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E8' AND issue_type = 'MISSING_VALUE';" "MISSING_VALUE" 20)"
[ "$ISSUE" = "MISSING_VALUE" ] && pass "missing value detected (not zero-substituted)" || fail "expected MISSING_VALUE for $E8, got '$ISSUE'"

echo ""
echo "=== 9. Invalid value ==="
E9="$(new_uuid)"
PAYLOAD_9="$(build_payload "$E9" $((BASE_SEQ + 90)) 5.9 "$(now_ts)")"
PAYLOAD_9="$(echo "$PAYLOAD_9" | sed 's/"quality":"GOOD"/"quality":"INVALID"/')"
publish_payload "$PAYLOAD_9"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E9' AND issue_type = 'INVALID_VALUE';" "INVALID_VALUE" 20)"
[ "$ISSUE" = "INVALID_VALUE" ] && pass "invalid value detected" || fail "expected INVALID_VALUE for $E9, got '$ISSUE'"

echo ""
echo "=== 10. Spike (rate-of-change limit, same operating_state) ==="
E10A="$(new_uuid)"
publish_payload "$(build_payload "$E10A" $((BASE_SEQ + 100)) 1.0 "$(now_ts)")"
sleep 4
E10B="$(new_uuid)"
publish_payload "$(build_payload "$E10B" $((BASE_SEQ + 101)) 999999.0 "$(now_ts)")"
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE event_id = '$E10B' AND issue_type = 'SPIKE_DETECTED';" "SPIKE_DETECTED" 20)"
[ "$ISSUE" = "SPIKE_DETECTED" ] && pass "spike detected" || fail "expected SPIKE_DETECTED for $E10B, got '$ISSUE'"

echo ""
echo "=== 11. Stuck sensor (window-level — waits for the periodic evaluation cycle) ==="
STUCK_SEQ=$((BASE_SEQ + 200))
for i in 1 2 3 4 5 6 7 8; do
  E="$(new_uuid)"
  now="$(date -u +%Y-%m-%dT%H:%M:%S.000000+00:00)"
  PAYLOAD="{\"event_id\":\"$E\",\"schema_version\":\"1\",\"correlation_id\":\"$E\",\"tenant_id\":\"$TENANT_ID\",\"machine_id\":\"$STUCK_MACHINE_ID\",\"sensor_id\":\"$STUCK_SENSOR_ID\",\"measurement_type\":\"$STUCK_MEASUREMENT_TYPE\",\"value\":3.14159,\"unit\":\"$STUCK_UNIT\",\"quality\":\"GOOD\",\"operating_state\":\"RUNNING_NORMAL_LOAD\",\"source_timestamp\":\"$now\",\"edge_received_timestamp\":\"$now\",\"sequence_number\":$((STUCK_SEQ + i)),\"gateway_id\":\"$GATEWAY_ID\",\"device_id\":\"verify-data-quality\",\"source\":\"synthetic\"}"
  publish_payload "$PAYLOAD"
  sleep 1
done
ISSUE="$(wait_for_query "SELECT issue_type FROM quality_issue WHERE sensor_id = '$STUCK_SENSOR_ID' AND issue_type = 'STUCK_SENSOR_SUSPECTED' AND status IN ('ACTIVE','RECOVERING') ORDER BY last_seen DESC LIMIT 1;" "STUCK_SENSOR_SUSPECTED" 90)"
[ "$ISSUE" = "STUCK_SENSOR_SUSPECTED" ] && pass "stuck sensor detected by periodic window evaluation" || fail "expected STUCK_SENSOR_SUSPECTED for sensor $STUCK_SENSOR_ID, got '$ISSUE'"

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "verify_data_quality PASSED: all synthetic cases detected correctly."
  exit 0
fi
echo "verify_data_quality FAILED: $FAILURES case(s) failed — see above." >&2
exit 1
