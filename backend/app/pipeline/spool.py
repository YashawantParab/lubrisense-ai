"""The MQTT->Kafka bridge's durable local buffer (Phase 6 brief §23/§41, ADR-056).

Used whenever Kafka is unreachable: rather than dropping or holding messages only in
memory (insufficient for a prolonged outage per the brief), the bridge spools them to a
dedicated SQLite file — separate from the edge's own buffer database (a different
responsibility; see edge.buffering.store.LocalBuffer) — and a background task drains it
with bounded backoff once Kafka is reachable again.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SpooledEvent:
    event_id: str
    kafka_topic: str
    partition_key: str
    payload: bytes
    mqtt_received_at: str
    attempts: int


class BridgeSpool:
    def __init__(self, path: str) -> None:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS spooled_events (
                    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    kafka_topic TEXT NOT NULL,
                    partition_key TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    mqtt_received_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    spooled_at TEXT NOT NULL
                )
                """
            )

    def enqueue(
        self,
        *,
        event_id: str,
        kafka_topic: str,
        partition_key: str,
        payload: bytes,
        mqtt_received_at: str,
    ) -> None:
        """Idempotent on `event_id` — re-spooling an already-spooled event is a no-op, so a
        redelivered MQTT message never duplicates a pending spool row."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO spooled_events "
                "(event_id, kafka_topic, partition_key, payload, mqtt_received_at, attempts, "
                "spooled_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (
                    event_id,
                    kafka_topic,
                    partition_key,
                    payload,
                    mqtt_received_at,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def peek_batch(self, limit: int) -> list[SpooledEvent]:
        """Oldest-first — preserves publish order as much as a single-threaded drain can."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT event_id, kafka_topic, partition_key, payload, mqtt_received_at, attempts "
                "FROM spooled_events ORDER BY rowid ASC LIMIT ?",
                (limit,),
            )
            return [SpooledEvent(*row) for row in cursor.fetchall()]

    def remove(self, event_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM spooled_events WHERE event_id = ?", (event_id,))

    def mark_attempt(self, event_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE spooled_events SET attempts = attempts + 1 WHERE event_id = ?", (event_id,)
            )

    def depth(self) -> int:
        with self._lock:
            cursor = self._conn.execute("SELECT COUNT(*) FROM spooled_events")
            row = cursor.fetchone()
            return int(row[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
