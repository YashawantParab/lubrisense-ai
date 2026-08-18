"""Metrics and tracing instrumentation.

Structured logging and correlation IDs (see `app.core.logging`, `app.core.middleware`)
are the Phase 1 observability foundation. `metrics.py`/`worker_health.py` (Phase 6/7) add
a shared counters object and a `/health`/`/ready`/`/metrics` HTTP server for background
worker processes (MQTT bridge, telemetry consumer, data-quality worker) that don't sit
behind FastAPI. Full Prometheus scraping/OpenTelemetry tracing remain a later,
observability-focused phase.
"""
