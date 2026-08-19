"""Lightweight, reproducible load test (Phase 33 brief §33.6) — no external load-testing
infrastructure, just concurrent real HTTP requests against a running backend, reporting
real p50/p95/max latency and achieved throughput per endpoint. This is a reference-scale
sanity check, not a claim of validated production capacity at any specific RPS.

    uv run python scripts/load_test.py --base-url http://localhost:8000 \
        --tenant-id <uuid> --concurrency 10 --requests 100
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from dataclasses import dataclass, field

import httpx


@dataclass
class EndpointResult:
    path: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0

    def summary(self) -> dict[str, object]:
        if not self.latencies_ms:
            return {"path": self.path, "requests": 0, "errors": self.errors}
        sorted_latencies = sorted(self.latencies_ms)
        n = len(sorted_latencies)
        return {
            "path": self.path,
            "requests": n,
            "errors": self.errors,
            "p50_ms": round(sorted_latencies[n // 2], 2),
            "p95_ms": round(sorted_latencies[min(int(n * 0.95), n - 1)], 2),
            "max_ms": round(sorted_latencies[-1], 2),
            "min_ms": round(sorted_latencies[0], 2),
        }


async def _hit(
    client: httpx.AsyncClient, path: str, headers: dict[str, str], result: EndpointResult
) -> None:
    start = time.perf_counter()
    try:
        response = await client.get(path, headers=headers)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status_code >= 400:
            result.errors += 1
        else:
            result.latencies_ms.append(elapsed_ms)
    except httpx.HTTPError:
        result.errors += 1


async def _run_endpoint(
    base_url: str, path: str, headers: dict[str, str], concurrency: int, total_requests: int
) -> EndpointResult:
    result = EndpointResult(path=path)
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded() -> None:
            async with semaphore:
                await _hit(client, path, headers, result)

        start = time.perf_counter()
        await asyncio.gather(*(bounded() for _ in range(total_requests)))
        elapsed = time.perf_counter() - start
    throughput = total_requests / elapsed if elapsed > 0 else 0.0
    print(f"{path}: {total_requests} requests, concurrency={concurrency}, "
          f"{elapsed:.2f}s, {throughput:.1f} req/s")
    return result


async def _demo_login(base_url: str, tenant_id: uuid.UUID) -> str:
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        response = await client.post(
            "/api/v1/auth/demo-login",
            headers={"X-Tenant-ID": str(tenant_id)},
            json={"role": "ADMIN"},
        )
        response.raise_for_status()
        return str(response.json()["access_token"])


_DEFAULT_ENDPOINTS = [
    "/api/v1/fleet/overview",
    "/api/v1/hierarchy",
    "/api/v1/incidents",
    "/api/v1/maintenance/cases",
    "/api/v1/product-metrics",
]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--endpoints", nargs="*", default=_DEFAULT_ENDPOINTS)
    args = parser.parse_args()

    token = await _demo_login(args.base_url, args.tenant_id)
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(args.tenant_id)}

    print(f"Load test against {args.base_url} (tenant={args.tenant_id}, "
          f"concurrency={args.concurrency}, requests/endpoint={args.requests})\n")

    summaries = []
    for path in args.endpoints:
        result = await _run_endpoint(
            args.base_url, path, headers, args.concurrency, args.requests
        )
        summaries.append(result.summary())

    print("\nSummary:")
    for summary in summaries:
        print(f"  {summary}")


if __name__ == "__main__":
    asyncio.run(main())
