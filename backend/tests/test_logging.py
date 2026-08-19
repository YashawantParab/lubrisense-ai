"""Real bug found during Phase 35 comprehensive testing: `logger.warning(msg,
extra={...})` calls across the pipeline/worker modules were silently losing their
`extra` diagnostic fields — `JSONLogFormatter.format()` never read them off the
`LogRecord`, so every structured-log consumer of these fields (dashboards, `grep`,
`jq`) saw only the bare message, with the actual error/sensor_id/etc. discarded."""

from __future__ import annotations

import json
import logging

from app.core.logging import ConsoleLogFormatter, JSONLogFormatter


def _make_record(extra: dict[str, object] | None = None) -> logging.LogRecord:
    logger = logging.getLogger("test.logging")
    record = logger.makeRecord(
        "test.logging", logging.WARNING, __file__, 1, "something failed", (), None, extra=extra
    )
    return record


def test_json_formatter_includes_extra_fields() -> None:
    record = _make_record({"sensor_id": "abc-123", "error": "boom"})
    payload = json.loads(JSONLogFormatter().format(record))
    assert payload["message"] == "something failed"
    assert payload["extra"] == {"sensor_id": "abc-123", "error": "boom"}


def test_json_formatter_omits_extra_key_when_no_extra_passed() -> None:
    record = _make_record()
    payload = json.loads(JSONLogFormatter().format(record))
    assert "extra" not in payload


def test_json_formatter_never_lets_extra_overwrite_reserved_keys() -> None:
    # A caller passing extra={"level": "..."} (accidentally reusing a reserved top-level
    # payload name — not one of Python's own reserved LogRecord attributes, so stdlib
    # logging itself does not block it) must not corrupt the top-level payload field.
    record = _make_record({"level": "spoofed", "service": "spoofed-service"})
    payload = json.loads(JSONLogFormatter().format(record))
    assert payload["level"] == "WARNING"
    assert payload["service"] != "spoofed-service"


def test_json_formatter_stringifies_non_json_safe_extra_values() -> None:
    class Unserializable:
        def __str__(self) -> str:
            return "<Unserializable>"

    record = _make_record({"weird": Unserializable()})
    payload = json.loads(JSONLogFormatter().format(record))
    assert payload["extra"]["weird"] == "<Unserializable>"


def test_console_formatter_includes_extra_fields() -> None:
    record = _make_record({"sensor_id": "abc-123"})
    text = ConsoleLogFormatter().format(record)
    assert "something failed" in text
    assert "sensor_id" in text
    assert "abc-123" in text
