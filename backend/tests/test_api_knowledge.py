"""Phase 18 knowledge/RAG API: contract shape, lifecycle via HTTP, not-found handling,
search/answer, and metrics."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.models import Tenant
from app.infrastructure.database import Database
from tests.factories import make_tenant

_MARKER = "zqapitest"

_CONTENT = f"""# API Test Doc {_MARKER}

## Steps

Real content for the {_MARKER} API test document, long enough to be chunked and kept.
"""


async def _committed_tenant() -> Tenant:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            await session.commit()
            return tenant
    finally:
        await database.dispose()


def test_get_unknown_document_404(client: TestClient, api_tenant: Tenant) -> None:
    import uuid

    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.get(f"/api/v1/knowledge/documents/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


def test_ingest_and_full_lifecycle_via_api(client: TestClient) -> None:
    tenant = asyncio.run(_committed_tenant())
    headers = {"X-Tenant-ID": str(tenant.id)}

    created = client.post(
        "/api/v1/knowledge/documents",
        headers=headers,
        json={
            "document_key": f"api-test-doc-{_MARKER}",
            "title": f"API Test Doc {_MARKER}",
            "document_type": "TROUBLESHOOTING_GUIDE",
            "version": "1.0.0",
            "source_name": "Test",
            "content": _CONTENT,
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "DRAFT"
    document_id = created.json()["id"]

    reviewed = client.post(
        f"/api/v1/knowledge/documents/{document_id}/submit-for-review", headers=headers
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "REVIEW"

    approved = client.post(
        f"/api/v1/knowledge/documents/{document_id}/approve",
        headers=headers,
        json={"approved_by": "api-tester"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by"] == "api-tester"

    search = client.post(
        "/api/v1/knowledge/search", headers=headers, json={"query": f"{_MARKER} steps"}
    )
    assert search.status_code == 200
    assert any(r["citation"]["document_title"] == f"API Test Doc {_MARKER}" for r in search.json())

    answer = client.post(
        "/api/v1/knowledge/answer", headers=headers, json={"query": f"{_MARKER} steps"}
    )
    assert answer.status_code == 200
    assert answer.json()["status"] in ("SUFFICIENT", "PARTIAL")
    assert len(answer.json()["citations"]) > 0

    retired = client.post(f"/api/v1/knowledge/documents/{document_id}/retire", headers=headers)
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"


def test_ingest_conflict_returns_409(client: TestClient) -> None:
    tenant = asyncio.run(_committed_tenant())
    headers = {"X-Tenant-ID": str(tenant.id)}
    body = {
        "document_key": f"conflict-doc-{_MARKER}",
        "title": "Conflict Doc",
        "document_type": "TROUBLESHOOTING_GUIDE",
        "version": "1.0.0",
        "source_name": "Test",
        "content": _CONTENT,
    }
    first = client.post("/api/v1/knowledge/documents", headers=headers, json=body)
    assert first.status_code == 201
    second = client.post(
        "/api/v1/knowledge/documents",
        headers=headers,
        json={**body, "content": _CONTENT + "\n## Extra\n\nDifferent real content here.\n"},
    )
    assert second.status_code == 409


def test_insufficient_documentation_via_api(client: TestClient, api_tenant: Tenant) -> None:
    headers = {"X-Tenant-ID": str(api_tenant.id)}
    response = client.post(
        "/api/v1/knowledge/answer",
        headers=headers,
        json={"query": "quantum entanglement stock market forecast xyzzy"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT"
    assert response.json()["text"] == "Insufficient approved documentation to answer reliably."


def test_knowledge_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/knowledge/metrics")
    assert response.status_code == 200
