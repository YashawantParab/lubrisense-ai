"""`LocalBuffer` — persistent, crash-safe SQLite store-and-forward buffer (Phase 5 brief
§7-§11; ADR-043 persistence choice, ADR-044 sequence strategy, ADR-047 retention policy).

Design notes:
  - SQLite in WAL mode, one file per gateway. Never deleted on startup — the whole point is
    surviving a process restart with events still `PENDING` (§27).
  - `events.event_id` is the primary key: inserting the same `event_id` twice is a no-op,
    not an error and not a duplicate row (§25 deduplication).
  - Sequence numbers are persisted per (gateway_id, sensor_id) in `sequence_state` and
    incremented+committed atomically with the reading they're assigned to, so a restart
    resumes exactly where it left off (§5).
  - Retention breach never deletes: the oldest `PENDING` rows are moved to `DEAD_LETTER`
    (§9 — "no silent discard"), which the buffer must still return via `list_events`.
  - One coarse-grained lock (owned by the caller, `edge.runtime`) protects concurrent
    acquisition-thread/sender-thread access — this module itself is not thread-safe on its
    own connection object, by design (§32): a single `sqlite3.Connection` is not meant to be
    shared across threads without external serialization, and adding per-call locking here
    would just hide that responsibility instead of making it visible at the call site.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from edge.domain.enums import BufferStatus
from edge.domain.envelope import ReadingEnvelope

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    sequence_number INTEGER NOT NULL,
    sensor_id TEXT NOT NULL,
    gateway_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING','SENT','ACKNOWLEDGED','FAILED','DEAD_LETTER')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_attempt_at TEXT,
    acknowledged_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_sensor_seq ON events(sensor_id, sequence_number);

CREATE TABLE IF NOT EXISTS sequence_state (
    gateway_id TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    last_sequence INTEGER NOT NULL,
    PRIMARY KEY (gateway_id, sensor_id)
);

CREATE TABLE IF NOT EXISTS config_state (
    gateway_id TEXT PRIMARY KEY,
    config_version TEXT NOT NULL
);
"""


class LocalBuffer:
    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- sequence numbers ----------------------------------------------------

    def next_sequence(self, gateway_id: str, sensor_id: str) -> int:
        """Atomically increment and persist the per-(gateway, sensor) sequence counter
        (ADR-044). Survives restart because it is read back from disk, not kept in memory."""
        cur = self._conn.execute(
            "SELECT last_sequence FROM sequence_state WHERE gateway_id=? AND sensor_id=?",
            (gateway_id, sensor_id),
        )
        row = cur.fetchone()
        next_value = 1 if row is None else row[0] + 1
        self._conn.execute(
            "INSERT INTO sequence_state (gateway_id, sensor_id, last_sequence) VALUES (?, ?, ?) "
            "ON CONFLICT(gateway_id, sensor_id) DO UPDATE SET last_sequence=excluded.last_sequence",
            (gateway_id, sensor_id, next_value),
        )
        self._conn.commit()
        return next_value

    # -- config version tracking (§21) ---------------------------------------

    def get_config_version(self, gateway_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT config_version FROM config_state WHERE gateway_id=?", (gateway_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_config_version(self, gateway_id: str, version: str) -> None:
        self._conn.execute(
            "INSERT INTO config_state (gateway_id, config_version) VALUES (?, ?) "
            "ON CONFLICT(gateway_id) DO UPDATE SET config_version=excluded.config_version",
            (gateway_id, version),
        )
        self._conn.commit()

    # -- event lifecycle -------------------------------------------------------

    def insert_pending(self, envelope: ReadingEnvelope) -> bool:
        """Insert a newly-acquired event as PENDING. Returns False (no-op) if `event_id`
        already exists — deduplication is enforced by the primary key, not application
        logic that could be bypassed (§25)."""
        try:
            self._conn.execute(
                "INSERT INTO events "
                "(event_id, sequence_number, sensor_id, gateway_id, payload, status, "
                " attempt_count, created_at) VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?)",
                (
                    envelope.event_id,
                    envelope.sequence_number,
                    str(envelope.sensor_id),
                    envelope.gateway_id,
                    envelope.to_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def mark_sent(self, event_id: str, payload: str | None = None) -> None:
        if payload is not None:
            self._conn.execute(
                "UPDATE events SET status='SENT', attempt_count=attempt_count+1, "
                "last_attempt_at=?, payload=? WHERE event_id=?",
                (datetime.now(UTC).isoformat(), payload, event_id),
            )
        else:
            self._conn.execute(
                "UPDATE events SET status='SENT', attempt_count=attempt_count+1, "
                "last_attempt_at=? WHERE event_id=?",
                (datetime.now(UTC).isoformat(), event_id),
            )
        self._conn.commit()

    def mark_acknowledged(self, event_id: str) -> None:
        self._conn.execute(
            "UPDATE events SET status='ACKNOWLEDGED', acknowledged_at=? WHERE event_id=?",
            (datetime.now(UTC).isoformat(), event_id),
        )
        self._conn.commit()

    def mark_failed(self, event_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE events SET status='FAILED', attempt_count=attempt_count+1, "
            "last_attempt_at=?, error=? WHERE event_id=?",
            (datetime.now(UTC).isoformat(), error, event_id),
        )
        self._conn.commit()

    # -- replay / queries ------------------------------------------------------

    def get_replayable(self, limit: int = 500) -> list[ReadingEnvelope]:
        """PENDING and FAILED events, deterministically ordered by sequence number then
        creation time (§10 — replay must preserve original order)."""
        cur = self._conn.execute(
            "SELECT payload FROM events WHERE status IN ('PENDING','FAILED') "
            "ORDER BY sequence_number ASC, created_at ASC LIMIT ?",
            (limit,),
        )
        return [ReadingEnvelope.from_json(row[0]) for row in cur.fetchall()]

    def pending_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM events WHERE status='PENDING'")
        return int(cur.fetchone()[0])

    def oldest_pending_age_seconds(self) -> float | None:
        cur = self._conn.execute(
            "SELECT created_at FROM events WHERE status='PENDING' ORDER BY created_at ASC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return None
        created = datetime.fromisoformat(row[0])
        return (datetime.now(UTC) - created).total_seconds()

    def list_events(
        self, status: BufferStatus | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        if status is not None:
            cur = self._conn.execute(
                "SELECT event_id, sequence_number, sensor_id, status, attempt_count, "
                "created_at, last_attempt_at, acknowledged_at, error FROM events "
                "WHERE status=? ORDER BY sequence_number ASC LIMIT ?",
                (status.value, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT event_id, sequence_number, sensor_id, status, attempt_count, "
                "created_at, last_attempt_at, acknowledged_at, error FROM events "
                "ORDER BY sequence_number ASC LIMIT ?",
                (limit,),
            )
        columns = [
            "event_id",
            "sequence_number",
            "sensor_id",
            "status",
            "attempt_count",
            "created_at",
            "last_attempt_at",
            "acknowledged_at",
            "error",
        ]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]

    def counts_by_status(self) -> dict[str, int]:
        cur = self._conn.execute("SELECT status, COUNT(*) FROM events GROUP BY status")
        return {row[0]: row[1] for row in cur.fetchall()}

    # -- retention (§9 — never silently discard) --------------------------------

    def enforce_retention(self, max_buffered_events: int, max_buffer_age_seconds: float) -> int:
        """Moves the OLDEST `PENDING` rows to `DEAD_LETTER` when the count or age limit is
        breached. Never deletes. Returns the number of rows moved."""
        moved = 0
        cur = self._conn.execute("SELECT COUNT(*) FROM events WHERE status='PENDING'")
        pending_total = int(cur.fetchone()[0])
        if pending_total > max_buffered_events:
            overflow = pending_total - max_buffered_events
            cur = self._conn.execute(
                "SELECT event_id FROM events WHERE status='PENDING' "
                "ORDER BY sequence_number ASC LIMIT ?",
                (overflow,),
            )
            ids = [row[0] for row in cur.fetchall()]
            self._dead_letter(ids, "buffer overflow: exceeded max_buffered_events")
            moved += len(ids)

        cutoff = datetime.now(UTC).timestamp() - max_buffer_age_seconds
        cur = self._conn.execute("SELECT event_id, created_at FROM events WHERE status='PENDING'")
        stale_ids = [
            row[0] for row in cur.fetchall() if datetime.fromisoformat(row[1]).timestamp() < cutoff
        ]
        if stale_ids:
            self._dead_letter(stale_ids, "buffer overflow: exceeded max_buffer_age_seconds")
            moved += len(stale_ids)
        return moved

    def _dead_letter(self, event_ids: Sequence[str], reason: str) -> None:
        for event_id in event_ids:
            self._conn.execute(
                "UPDATE events SET status='DEAD_LETTER', error=? WHERE event_id=?",
                (reason, event_id),
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> LocalBuffer:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def dump_envelope_json(payload: str) -> dict[str, object]:
    return dict(json.loads(payload))
