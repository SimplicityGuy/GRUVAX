"""HTTP search benchmark — p95 /api/search SLO gate (SC5).

Asserts that the mean round-trip time for GET /api/search against the live
ASGI app (via httpx.AsyncClient + ASGITransport) is under 200 ms on the
synthetic dataset.

This test runs ONLY under pytest-benchmark mode (--benchmark-only or
--benchmark-enable).  Normal ``just test`` / CI ``pytest tests/`` runs
skip it because pyproject.toml addopts includes --benchmark-disable.

The CI "Benchmark SLO gate" step re-enables via --benchmark-only so the
gate fires on every push.

NOTE: this test requires a live DATABASE_URL (Postgres with the synthetic
collection seeded) — the ``db_pool`` session fixture in conftest.py ensures
the pool is open before the ASGI app boots.
"""

from __future__ import annotations

import asyncio

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


@pytest_asyncio.fixture(scope="module")
async def search_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with full lifespan for benchmark tests."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac


@pytest.mark.benchmark
def test_search_slo_benchmark(benchmark, search_client) -> None:  # type: ignore[no-untyped-def]
    """p95 /api/search round-trip must be < 200 ms on synthetic data (SC5).

    Uses the sync-wrapper + asyncio pattern so pytest-benchmark can call the
    function in its timing loop (benchmark fixture is synchronous).

    The query ``Miles Davis`` is used because the synthetic dataset in
    ``fixtures/synth_collection.sql`` includes Miles Davis records, making
    this a realistic non-zero-result search.
    """
    loop = asyncio.get_event_loop()

    async def _run_search() -> float:
        resp = await search_client.get("/api/search", params={"q": "Miles Davis", "limit": "5"})
        assert resp.status_code == 200, f"Search returned {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "took_ms" in body, f"Response missing took_ms: {body}"
        return float(body["took_ms"])

    def sync_run() -> float:
        return loop.run_until_complete(_run_search())

    benchmark(sync_run)

    assert benchmark.stats["mean"] * 1000 < 200, (
        f"Search SLO FAILED: mean {benchmark.stats['mean'] * 1000:.2f} ms > 200 ms budget (SC5)"
    )
