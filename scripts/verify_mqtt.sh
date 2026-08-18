#!/usr/bin/env bash
# Proves the local Mosquitto broker can accept a connection, a publish, and a subscribe.
#
# Uses the mosquitto_pub/mosquitto_sub client binaries bundled in the eclipse-mosquitto
# image itself (via `docker exec`) rather than adding an MQTT client dependency to any
# service — this is a platform-foundation smoke test, not application telemetry
# (see docs/ARCHITECTURE.md §10: real telemetry schemas are a later phase).
set -euo pipefail

CONTAINER="${MQTT_CONTAINER:-lubrisense-mosquitto}"
TOPIC="lubrisense/platform/test"
MESSAGE="lubrisense-mqtt-verification-$(date +%s)"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" >/dev/null 2>&1; then
  echo "MQTT verification FAILED: container '$CONTAINER' is not running." >&2
  exit 1
fi

OUTPUT_FILE="$(mktemp)"
trap 'rm -f "$OUTPUT_FILE"' EXIT

docker exec "$CONTAINER" mosquitto_sub -h localhost -p 1883 -t "$TOPIC" -C 1 -W 10 >"$OUTPUT_FILE" &
SUB_PID=$!

sleep 1

docker exec "$CONTAINER" mosquitto_pub -h localhost -p 1883 -t "$TOPIC" -m "$MESSAGE"

wait "$SUB_PID"
RECEIVED="$(tr -d '\r\n' <"$OUTPUT_FILE")"

if [ "$RECEIVED" = "$MESSAGE" ]; then
  echo "MQTT verification PASSED: published and received '$RECEIVED' on topic '$TOPIC'"
  exit 0
fi

echo "MQTT verification FAILED: expected '$MESSAGE', received '$RECEIVED'" >&2
exit 1
