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

Environment = Literal["local", "development", "staging", "production"]


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
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
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

    cors_allowed_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")
    trusted_hosts: str = Field(default="*", alias="TRUSTED_HOSTS")

    correlation_id_header: str = Field(default="X-Correlation-ID", alias="CORRELATION_ID_HEADER")

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
