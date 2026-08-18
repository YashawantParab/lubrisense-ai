from __future__ import annotations

from fastapi.testclient import TestClient

CORRELATION_HEADER = "X-Correlation-ID"


def test_generates_correlation_id_when_absent(client: TestClient) -> None:
    response = client.get("/health")

    assert CORRELATION_HEADER in response.headers
    assert len(response.headers[CORRELATION_HEADER]) > 0


def test_echoes_valid_incoming_correlation_id(client: TestClient) -> None:
    incoming = "test-correlation-id-12345"

    response = client.get("/health", headers={CORRELATION_HEADER: incoming})

    assert response.headers[CORRELATION_HEADER] == incoming


def test_replaces_invalid_incoming_correlation_id(client: TestClient) -> None:
    invalid = "not a valid header value !!"

    response = client.get("/health", headers={CORRELATION_HEADER: invalid})

    assert response.headers[CORRELATION_HEADER] != invalid
