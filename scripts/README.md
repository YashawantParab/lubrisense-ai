# Scripts

Developer and operational tooling.

- `verify_mqtt.sh` — proves the local Mosquitto broker accepts a connect/publish/subscribe
  round trip. Run via `make mqtt-verify` or directly once the stack is up.
- `verify_kafka.sh` — proves the local Kafka (KRaft) broker can create a topic and
  complete a produce/consume round trip. Run via `make kafka-verify`.

Both scripts drive the client tooling bundled inside the respective service's own Docker
image via `docker exec`, so no MQTT/Kafka client dependency is added to any application
service for what is purely a platform smoke test.
