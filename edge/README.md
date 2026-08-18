# Edge

Reference implementation of the edge-controller responsibilities defined in
`docs/ARCHITECTURE.md` §5: sensor collection, local timestamps, deterministic basic rules,
local alarms, buffering/store-and-forward, offline operation, gateway health, and basic
data-quality checks. Publishes telemetry to the platform via MQTT
(`TECHNICAL_DECISIONS.md` ADR-006).

**Phase 5 status: implemented.** See `docs/EDGE_ARCHITECTURE.md` for the full design
(acquisition, envelope, event-id/sequence/timestamp strategy, local buffer, store-and-
forward, connectivity/backoff, MQTT transport/topic/QoS, local rules, configuration,
concurrency model, cloud-independence boundary). Quick start:

```
make edge-install
make edge-test                          # unit + the 3 mandatory MQTT integration tests
docker compose --profile edge up        # not started by default
docker compose --profile edge run --rm edge python -m edge status
```

Not implemented here (see `IMPLEMENTATION_STATUS.md` Phase 5 for the full boundary): Kafka
central ingestion, TimescaleDB telemetry persistence, the Phase 9 rules engine, ML, RAG,
GenAI agents, or physical control — those are later phases' responsibility.
