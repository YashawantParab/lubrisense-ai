"""Typed, environment-driven application settings.

Every setting has a sensible local-development default so the service can start without
a populated `.env` file, while still allowing every value to be overridden via environment
variables in any deployment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: `hosted_demo` is a deployment/configuration distinction, not a parallel product
#: implementation (docs/HOSTED_DEPLOYMENT.md) — it is the public-reviewer-facing hosted
#: deployment of this exact platform, running on persisted pre-seeded demo data instead
#: of the continuous industrial ingestion path (simulator/MQTT/Kafka/workers), which the
#: hosted demo does not run. It shares every one of `production`'s fail-fast safety
#: checks below (`model_post_init`) — a public demo carries the same auth/CORS/secret
#: risk surface as production even though it is explicitly not a claim of real
#: industrial deployment readiness (CLAUDE.md's Industrial Adoption Boundary,
#: docs/INDUSTRIAL_ADOPTION.md).
Environment = Literal["local", "development", "staging", "production", "hosted_demo"]

_INSECURE_DEFAULT_DEMO_AUTH_SECRET = "local-dev-insecure-demo-auth-secret-do-not-use-in-production"
_STRICT_SAFETY_ENVIRONMENTS = ("production", "hosted_demo")


class Settings(BaseSettings):
    """Application settings sourced from environment variables (or a `.env` file locally)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="lubrisense-backend", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    app_env: Environment = Field(default="local", alias="APP_ENV")

    host: str = Field(default="0.0.0.0", alias="APP_HOST")
    port: int = Field(default=8000, alias="APP_PORT")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(default="json", alias="LOG_FORMAT")

    database_url: str = Field(
        default="postgresql+psycopg://lubrisense:lubrisense@localhost:5432/lubrisense",
        alias="DATABASE_URL",
    )
    # Phase 33 perf finding: request queueing under concurrent load turned out to be
    # CPU-bound on a single uvicorn worker process, not DB-connection-starved (see
    # backend/Dockerfile's `UVICORN_WORKERS` and docs/PERFORMANCE.md) — this pool size is
    # deliberately per-worker-process, not per-container: at the default 4 workers, 10
    # connections/worker = 40 total, leaving headroom under Postgres's 100-connection
    # ceiling alongside the other pipeline-worker containers. Raising this further without
    # also lowering `UVICORN_WORKERS` (or raising Postgres `max_connections`) would risk
    # exhausting the database's connection ceiling, not improve throughput.
    database_pool_size: int = Field(default=10, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout_seconds: int = Field(default=5, alias="DATABASE_POOL_TIMEOUT_SECONDS")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    mqtt_host: str = Field(default="localhost", alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, alias="MQTT_PORT")

    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_telemetry_topic: str = Field(
        default="lubrisense.telemetry.v1", alias="KAFKA_TELEMETRY_TOPIC"
    )
    kafka_dlq_topic: str = Field(default="lubrisense.telemetry.dlq.v1", alias="KAFKA_DLQ_TOPIC")
    kafka_consumer_group_id: str = Field(
        default="lubrisense-telemetry-consumer", alias="KAFKA_CONSUMER_GROUP_ID"
    )

    mqtt_topic_pattern: str = Field(
        default="lubrisense/v1/+/+/telemetry", alias="MQTT_TOPIC_PATTERN"
    )

    pipeline_batch_size: int = Field(default=500, alias="PIPELINE_BATCH_SIZE")
    pipeline_batch_timeout_seconds: float = Field(
        default=2.0, alias="PIPELINE_BATCH_TIMEOUT_SECONDS"
    )
    pipeline_retry_max_backoff_seconds: float = Field(
        default=30.0, alias="PIPELINE_RETRY_MAX_BACKOFF_SECONDS"
    )
    pipeline_supported_schema_versions: str = Field(
        default="1", alias="PIPELINE_SUPPORTED_SCHEMA_VERSIONS"
    )
    pipeline_bridge_spool_path: str = Field(
        default="./data/mqtt_bridge_spool.db", alias="PIPELINE_BRIDGE_SPOOL_PATH"
    )
    pipeline_bridge_spool_drain_interval_seconds: float = Field(
        default=5.0, alias="PIPELINE_BRIDGE_SPOOL_DRAIN_INTERVAL_SECONDS"
    )

    mqtt_bridge_health_port: int = Field(default=8081, alias="MQTT_BRIDGE_HEALTH_PORT")
    telemetry_consumer_health_port: int = Field(
        default=8082, alias="TELEMETRY_CONSUMER_HEALTH_PORT"
    )

    # Phase 7: a separate Kafka consumer group reading the same telemetry topic
    # independently of `kafka_consumer_group_id` (plan decision #2 — fan-out, not a
    # post-persistence trigger; quality-worker lag never blocks telemetry ingestion).
    data_quality_consumer_group_id: str = Field(
        default="lubrisense-data-quality", alias="DATA_QUALITY_CONSUMER_GROUP_ID"
    )
    data_quality_worker_health_port: int = Field(
        default=8083, alias="DATA_QUALITY_WORKER_HEALTH_PORT"
    )
    data_quality_window_evaluation_interval_seconds: float = Field(
        default=60.0, alias="DATA_QUALITY_WINDOW_EVALUATION_INTERVAL_SECONDS"
    )

    # Phase 8: periodic refresh worker, not a Kafka consumer (see
    # app/baselines/workers/worker.py module docstring).
    baseline_worker_health_port: int = Field(default=8084, alias="BASELINE_WORKER_HEALTH_PORT")
    baseline_refresh_interval_seconds: float = Field(
        default=300.0, alias="BASELINE_REFRESH_INTERVAL_SECONDS"
    )

    # Phase 9: periodic evaluation worker, not a Kafka consumer (see
    # app/rules_engine/workers/worker.py module docstring) — rules depend on Phase 8
    # baselines, which are themselves only periodically refreshed.
    rules_worker_health_port: int = Field(default=8085, alias="RULES_WORKER_HEALTH_PORT")
    rules_worker_cycle_seconds: float = Field(default=300.0, alias="RULES_WORKER_CYCLE_SECONDS")

    # Phase 10: periodic materialization of selected point-in-time feature vectors.
    feature_worker_health_port: int = Field(default=8086, alias="FEATURE_WORKER_HEALTH_PORT")
    feature_worker_cycle_seconds: float = Field(default=900.0, alias="FEATURE_WORKER_CYCLE_SECONDS")

    # Phase 11: the ml-service model registry's base directory. Training
    # (`ml-service/scripts`/`ml_service.training.*`) runs on the host and writes here;
    # the container mounts the same host directory read-only (docker-compose.yml) so the
    # backend can load whatever the most recently trained/registered models are without
    # baking model artifacts into the image or requiring a rebuild per training run. There
    # is deliberately no automatic promotion/retraining loop here (CLAUDE.md "Maintenance
    # Workflow": no auto-retraining from a single event) — this only controls where the
    # registry already produced by a training run is read from.
    ml_artifacts_dir: str = Field(
        default="../ml-service/artifacts/models", alias="ML_ARTIFACTS_DIR"
    )

    cors_allowed_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")
    trusted_hosts: str = Field(default="*", alias="TRUSTED_HOSTS")

    correlation_id_header: str = Field(default="X-Correlation-ID", alias="CORRELATION_ID_HEADER")

    # Phase 24: demo/reference authorization — see app.auth and docs/SECURITY.md.
    # "permissive" (the local/demo default) lets a request with no Authorization header
    # fall back to a full-access principal, preserving backward compatibility with every
    # pre-Phase-24 API caller (including this repo's own pre-Phase-24 test suite, which
    # never sends a token). "strict" requires a valid bearer token on every request.
    # `is_production` below refuses to start in "permissive" mode, or with the insecure
    # default secret, in production — see the `model_post_init` validation.
    auth_enforcement_mode: Literal["permissive", "strict"] = Field(
        default="permissive", alias="AUTH_ENFORCEMENT_MODE"
    )
    demo_auth_secret: str = Field(
        default=_INSECURE_DEFAULT_DEMO_AUTH_SECRET,
        alias="DEMO_AUTH_SECRET",
    )
    demo_token_ttl_seconds: int = Field(default=3600, alias="DEMO_TOKEN_TTL_SECONDS")

    # Phase 23: request-size guards for the two endpoints most exposed to unbounded
    # client-supplied text (CLAUDE.md "Production Engineering Rules" — bound expensive
    # endpoints explicitly rather than trusting client good behavior).
    agent_message_max_length: int = Field(default=2000, alias="AGENT_MESSAGE_MAX_LENGTH")
    knowledge_document_max_content_length: int = Field(
        default=200_000, alias="KNOWLEDGE_DOCUMENT_MAX_CONTENT_LENGTH"
    )

    def model_post_init(self, __context: object) -> None:
        """Fail fast on invalid production-relevant configuration (Phase 23 brief
        §23.7) rather than silently starting with an unsafe default. Applies identically
        to `hosted_demo` — a publicly reachable deployment carries the same auth/CORS/
        secret risk surface as `production`, even though it is a demo, not a claim of
        real industrial deployment readiness (docs/HOSTED_DEPLOYMENT.md)."""
        if self.app_env in _STRICT_SAFETY_ENVIRONMENTS:
            problems: list[str] = []
            if self.auth_enforcement_mode != "strict":
                problems.append(f"AUTH_ENFORCEMENT_MODE must be 'strict' in {self.app_env}")
            if self.demo_auth_secret == _INSECURE_DEFAULT_DEMO_AUTH_SECRET:
                problems.append(f"DEMO_AUTH_SECRET must be overridden in {self.app_env}")
            if "*" in self.cors_allowed_origins_list:
                problems.append(f"CORS_ALLOWED_ORIGINS must not be '*' in {self.app_env}")
            if "*" in self.trusted_hosts_list:
                problems.append(f"TRUSTED_HOSTS must not be '*' in {self.app_env}")
            if problems:
                raise ValueError(f"Invalid {self.app_env} configuration: " + "; ".join(problems))

    @property
    def pipeline_supported_schema_versions_set(self) -> set[str]:
        return {v.strip() for v in self.pipeline_supported_schema_versions.split(",") if v.strip()}

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached because Settings is re-parsed from the environment on every instantiation;
    the process environment does not change during the lifetime of a running app.
    """
    return Settings()
