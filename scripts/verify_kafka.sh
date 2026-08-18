#!/usr/bin/env bash
# Proves the local Kafka (KRaft, single-node) broker can create a topic and complete a
# produce/consume round trip.
#
# Uses the kafka-topics.sh / kafka-console-producer.sh / kafka-console-consumer.sh CLI
# tools bundled in the official apache/kafka image (via `docker exec`) rather than adding
# a Kafka client dependency anywhere — this is a platform-foundation smoke test, not the
# real event catalog pipeline (see docs/ARCHITECTURE.md §10, later phase).
set -euo pipefail

CONTAINER="${KAFKA_CONTAINER:-lubrisense-kafka}"
BOOTSTRAP="${KAFKA_BOOTSTRAP:-localhost:9092}"
TOPIC="lubrisense.platform.test"
MESSAGE="lubrisense-kafka-verification-$(date +%s)"
KAFKA_BIN="/opt/kafka/bin"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" >/dev/null 2>&1; then
  echo "Kafka verification FAILED: container '$CONTAINER' is not running." >&2
  exit 1
fi

# Recreate the topic so each run is a clean, deterministic round trip.
docker exec "$CONTAINER" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" \
  --delete --topic "$TOPIC" >/dev/null 2>&1 || true
sleep 2
docker exec "$CONTAINER" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$BOOTSTRAP" \
  --create --topic "$TOPIC" --partitions 1 --replication-factor 1

echo "$MESSAGE" | docker exec -i "$CONTAINER" "$KAFKA_BIN/kafka-console-producer.sh" \
  --bootstrap-server "$BOOTSTRAP" --topic "$TOPIC"

RECEIVED="$(docker exec "$CONTAINER" "$KAFKA_BIN/kafka-console-consumer.sh" \
  --bootstrap-server "$BOOTSTRAP" --topic "$TOPIC" --from-beginning \
  --max-messages 1 --timeout-ms 15000 2>/dev/null | tr -d '\r')"

if [ "$RECEIVED" = "$MESSAGE" ]; then
  echo "Kafka verification PASSED: produced and consumed '$RECEIVED' on topic '$TOPIC'"
  exit 0
fi

echo "Kafka verification FAILED: expected '$MESSAGE', received '$RECEIVED'" >&2
exit 1
