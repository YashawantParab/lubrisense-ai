from __future__ import annotations

from fastapi.testclient import TestClient


def test_not_found_uses_consistent_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"code", "message", "details", "correlation_id"}
    assert body["code"] == "HTTP_ERROR"
    assert body["correlation_id"] is not None


def test_method_not_allowed_uses_consistent_error_shape(client: TestClient) -> None:
    response = client.post("/health")

    assert response.status_code == 405
    body = response.json()
    assert set(body.keys()) == {"code", "message", "details", "correlation_id"}


def test_error_response_never_contains_stack_trace(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    body_text = response.text.lower()
    assert "traceback" not in body_text
    assert ".py" not in body_text
