#!/usr/bin/env bash
# Proves the Phase 6 central telemetry pipeline (MQTT -> Kafka bridge -> Kafka -> consumer
# -> TimescaleDB) is idempotent, replay-safe, and resilient to Kafka/DB outages — the
# acceptance scenarios from the Phase 6 brief (duplicate delivery, Kafka outage buffering,
# DB outage recovery, unsupported schema version, unknown-sensor quarantine).
#
# Uses mosquitto_pub (via docker exec, matching verify_mqtt.sh's convention) to publish
# real envelopes and psql to inspect the resulting `telemetry`/`telemetry_quarantine` rows
# — not a Python Kafka client, since Kafka's advertised listener only resolves inside the
# compose network (ADR-020), matching why verify_kafka.sh also runs entirely via
# `docker exec` rather than a host-side client.
#
# Requires the full stack running: `docker compose up -d`.
set -euo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-lubrisense-postgres}"
MOSQUITTO_CONTAINER="${MOSQUITTO_CONTAINER:-lubrisense-mosquitto}"
KAFKA_CONTAINER="${KAFKA_CONTAINER:-lubrisense-kafka}"
BRIDGE_CONTAINER="${BRIDGE_CONTAINER:-lubrisense-mqtt-bridge}"
CONSUMER_CONTAINER="${CONSUMER_CONTAINER:-lubrisense-telemetry-consumer}"
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
    echo "verify_pipeline FAILED: container '$1' is not running. Run 'docker compose up -d' first." >&2
    exit 1
  fi
}

for c in "$POSTGRES_CONTAINER" "$MOSQUITTO_CONTAINER" "$KAFKA_CONTAINER" "$BRIDGE_CONTAINER" "$CONSUMER_CONTAINER"; do
  require_running "$c"
done

psql_query() {
  docker exec "$POSTGRES_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -t -A -c "$1"
}

wait_for_healthy() {
  local container="$1" timeout="${2:-60}" waited=0
  while [ "$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null)" != "healthy" ]; do
    sleep 2
    waited=$((waited + 2))
    if [ "$waited" -ge "$timeout" ]; then
      echo "verify_pipeline FAILED: '$container' did not become healthy within ${timeout}s" >&2
      exit 1
    fi
  done
}

# Polls a query (expected to return a single value) until it matches, or times out.
# Recovery timing after an outage depends on jittered backoff (app.pipeline.backoff), so a
# fixed sleep is inherently a little flaky — this polls instead of guessing one wait time.
wait_for_query() {
  local query="$1" expected="$2" timeout="${3:-45}" waited=0 got=""
  while [ "$waited" -lt "$timeout" ]; do
    got="$(psql_query "$query")"
    if [ "$got" = "$expected" ]; then
      echo "$got"
      return 0
    fi
    sleep 3
    waited=$((waited + 3))
  done
  echo "$got"
  return 1
}

# A real machine-attached sensor + its tenant + a real gateway id, from the seeded demo
# hierarchy (backend/scripts/seed_demo_data.py) — scoped to the deterministic demo tenant
# (slug `lubrisense-demo`, ADR-028) explicitly, not just "any tenant with a sensor": the
# backend test suite commits its own throwaway `test-tenant-*` rows (see
# `tests/conftest.py::api_tenant`), which would otherwise be picked up by an unscoped query.
# Fetched as ONE row from ONE query — three independent `LIMIT 1` queries with no ORDER BY
# are not guaranteed to agree on which row "1" is, and can silently pair a sensor with an
# unrelated machine.
SENSOR_ROW="$(psql_query "SELECT s.tenant_id, s.id, s.machine_id FROM sensor s JOIN tenant t ON t.id = s.tenant_id WHERE s.machine_id IS NOT NULL AND t.slug = 'lubrisense-demo' ORDER BY s.id LIMIT 1;")"
TENANT_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f1)"
SENSOR_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f2)"
MACHINE_ID="$(echo "$SENSOR_ROW" | cut -d'|' -f3)"
GATEWAY_ID="$(psql_query "SELECT id FROM gateway WHERE tenant_id = '$TENANT_ID' ORDER BY id LIMIT 1;")"

if [ -z "$TENANT_ID" ] || [ -z "$SENSOR_ID" ] || [ -z "$GATEWAY_ID" ]; then
  echo "verify_pipeline FAILED: no seeded tenant/sensor/gateway found — run 'make seed' first." >&2
  exit 1
fi

echo "Using tenant=$TENANT_ID sensor=$SENSOR_ID machine=$MACHINE_ID gateway=$GATEWAY_ID"

build_payload() {
  # build_payload <event_id> <sequence_number> <value> -- echoes the JSON envelope.
  # A real duplicate delivery redelivers the exact same bytes (the edge never regenerates
  # an envelope on retry — ADR-045) — callers that need to publish the *same* event twice
  # must reuse the string this returns, not call this twice (which would compute a fresh
  # `now` each time and violate the event_id -> source_timestamp determinism the
  # `(event_id, source_timestamp)` idempotency key relies on).
  local event_id="$1" seq="$2" value="$3" now
  now="$(date -u +%Y-%m-%dT%H:%M:%S.000000+00:00)"
  cat <<JSON
{"event_id":"$event_id","schema_version":"1","correlation_id":"$event_id","tenant_id":"$TENANT_ID","machine_id":"$MACHINE_ID","sensor_id":"$SENSOR_ID","measurement_type":"PRESSURE","value":$value,"unit":"bar","quality":"GOOD","operating_state":"RUNNING_NORMAL_LOAD","source_timestamp":"$now","edge_received_timestamp":"$now","sequence_number":$seq,"gateway_id":"$GATEWAY_ID","device_id":"verify-pipeline","source":"synthetic"}
JSON
}

publish_payload() {
  docker exec "$MOSQUITTO_CONTAINER" mosquitto_pub -h localhost -t "lubrisense/v1/$TENANT_ID/$GATEWAY_ID/telemetry" -q 1 -m "$1"
}

publish_event() {
  # publish_event <event_id> <sequence_number> <value>
  publish_payload "$(build_payload "$1" "$2" "$3")"
}

new_uuid() { psql_query "SELECT gen_random_uuid();"; }

echo ""
echo "=== 1. Full round trip + event-id/source-timestamp preservation ==="
EVENT_1="$(new_uuid)"
publish_event "$EVENT_1" 1001 5.5
sleep 6
ROW="$(psql_query "SELECT event_id || '|' || value FROM telemetry WHERE event_id = '$EVENT_1';")"
if [ "$ROW" = "$EVENT_1|5.5" ]; then
  pass "event persisted with original event_id and value"
else
  fail "expected row for $EVENT_1 with value 5.5, got '$ROW'"
fi

echo ""
echo "=== 2. Duplicate delivery -> exactly one row ==="
EVENT_2="$(new_uuid)"
PAYLOAD_2="$(build_payload "$EVENT_2" 1002 6.1)"
publish_payload "$PAYLOAD_2"
publish_payload "$PAYLOAD_2"
sleep 6
COUNT="$(psql_query "SELECT count(*) FROM telemetry WHERE event_id = '$EVENT_2';")"
if [ "$COUNT" = "1" ]; then
  pass "duplicate delivery produced exactly one row"
else
  fail "expected 1 row for duplicated event $EVENT_2, got $COUNT"
fi

echo ""
echo "=== 3. Unsupported schema version -> quarantined ==="
EVENT_3="$(new_uuid)"
now="$(date -u +%Y-%m-%dT%H:%M:%S.000000+00:00)"
BAD_SCHEMA_PAYLOAD="{\"event_id\":\"$EVENT_3\",\"schema_version\":\"99\",\"correlation_id\":\"$EVENT_3\",\"tenant_id\":\"$TENANT_ID\",\"machine_id\":\"$MACHINE_ID\",\"sensor_id\":\"$SENSOR_ID\",\"measurement_type\":\"PRESSURE\",\"value\":1.0,\"unit\":\"bar\",\"quality\":\"GOOD\",\"operating_state\":\"RUNNING_NORMAL_LOAD\",\"source_timestamp\":\"$now\",\"edge_received_timestamp\":\"$now\",\"sequence_number\":1,\"gateway_id\":\"$GATEWAY_ID\",\"device_id\":\"verify-pipeline\",\"source\":\"synthetic\"}"
docker exec "$MOSQUITTO_CONTAINER" mosquitto_pub -h localhost -t "lubrisense/v1/$TENANT_ID/$GATEWAY_ID/telemetry" -q 1 -m "$BAD_SCHEMA_PAYLOAD"
sleep 6
REASON="$(psql_query "SELECT reason FROM telemetry_quarantine WHERE event_id = '$EVENT_3';")"
if [ "$REASON" = "UNSUPPORTED_SCHEMA_VERSION" ]; then
  pass "unsupported schema_version quarantined with the correct reason"
else
  fail "expected UNSUPPORTED_SCHEMA_VERSION quarantine row, got '$REASON'"
fi

echo ""
echo "=== 4. Unknown sensor -> quarantined ==="
EVENT_4="$(new_uuid)"
UNKNOWN_SENSOR="$(new_uuid)"
now="$(date -u +%Y-%m-%dT%H:%M:%S.000000+00:00)"
UNKNOWN_SENSOR_PAYLOAD="{\"event_id\":\"$EVENT_4\",\"schema_version\":\"1\",\"correlation_id\":\"$EVENT_4\",\"tenant_id\":\"$TENANT_ID\",\"machine_id\":\"$MACHINE_ID\",\"sensor_id\":\"$UNKNOWN_SENSOR\",\"measurement_type\":\"PRESSURE\",\"value\":1.0,\"unit\":\"bar\",\"quality\":\"GOOD\",\"operating_state\":\"RUNNING_NORMAL_LOAD\",\"source_timestamp\":\"$now\",\"edge_received_timestamp\":\"$now\",\"sequence_number\":1,\"gateway_id\":\"$GATEWAY_ID\",\"device_id\":\"verify-pipeline\",\"source\":\"synthetic\"}"
docker exec "$MOSQUITTO_CONTAINER" mosquitto_pub -h localhost -t "lubrisense/v1/$TENANT_ID/$GATEWAY_ID/telemetry" -q 1 -m "$UNKNOWN_SENSOR_PAYLOAD"
sleep 6
REASON="$(psql_query "SELECT reason FROM telemetry_quarantine WHERE event_id = '$EVENT_4';")"
if [ "$REASON" = "UNKNOWN_SENSOR" ]; then
  pass "unknown sensor quarantined with the correct reason"
else
  fail "expected UNKNOWN_SENSOR quarantine row, got '$REASON'"
fi

echo ""
echo "=== 5. Kafka outage: bridge buffers durably, drains on recovery ==="
docker stop "$KAFKA_CONTAINER" >/dev/null
sleep 3
EVENT_5="$(new_uuid)"
publish_event "$EVENT_5" 1005 7.7
sleep 25
DEPTH="$(docker exec "$BRIDGE_CONTAINER" python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8081/ready').read().decode())" | grep bridge_buffer_depth | grep -o '[0-9]*')"
if [ "${DEPTH:-0}" -ge 1 ]; then
  pass "bridge durably spooled the event during the Kafka outage (depth=$DEPTH)"
else
  fail "expected bridge_buffer_depth >= 1 during Kafka outage, got '$DEPTH'"
fi
docker start "$KAFKA_CONTAINER" >/dev/null
wait_for_healthy "$KAFKA_CONTAINER" 90
ROW="$(wait_for_query "SELECT event_id FROM telemetry WHERE event_id = '$EVENT_5';" "$EVENT_5" 45)"
if [ "$ROW" = "$EVENT_5" ]; then
  pass "spooled event drained into TimescaleDB after Kafka recovered, no data lost"
else
  fail "expected event $EVENT_5 to be persisted after Kafka recovery, found '$ROW'"
fi

echo ""
echo "=== 6. Database outage: consumer retries without losing or duplicating ==="
EVENT_6="$(new_uuid)"  # generated before stopping Postgres — new_uuid() itself needs the DB
docker stop "$POSTGRES_CONTAINER" >/dev/null
sleep 3
publish_event "$EVENT_6" 1006 8.8
sleep 8
docker start "$POSTGRES_CONTAINER" >/dev/null
wait_for_healthy "$POSTGRES_CONTAINER" 60
COUNT="$(wait_for_query "SELECT count(*) FROM telemetry WHERE event_id = '$EVENT_6';" "1" 45)"
if [ "$COUNT" = "1" ]; then
  pass "event published during the DB outage was persisted exactly once after recovery"
else
  fail "expected exactly 1 row for $EVENT_6 after DB recovery, got $COUNT"
fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "verify_pipeline PASSED: all scenarios succeeded, zero data loss, zero duplicate rows."
  exit 0
fi
echo "verify_pipeline FAILED: $FAILURES scenario(s) failed — see above." >&2
exit 1
