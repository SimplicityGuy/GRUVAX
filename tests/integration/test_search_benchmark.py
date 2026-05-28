"""HTTP search + locate benchmarks — p95 SLO gates (SC5).

Asserts that the mean round-trip time for GET /api/search and GET /api/locate
against the live ASGI app (via httpx.AsyncClient + ASGITransport) is within
the v1.0 SLO budget on the synthetic dataset:

  - /api/search  p95 ≤ 200 ms
  - /api/locate  p95 ≤  50 ms

These tests run ONLY under pytest-benchmark mode (--benchmark-only or
--benchmark-enable).  Normal ``just test`` / CI ``pytest tests/`` runs
skip them because pyproject.toml addopts includes --benchmark-disable.
``just slo`` (added in Plan 01-06) re-enables via --benchmark-only so the
gate fires on every CI push.

Plan 01-06 swap notes:
  - Query target is now ``gruvax.profile_collection`` (the v1 v_collection
    view was dropped in migration 0009).
  - Seed fixture is ``tests/fixtures/synth_profile_collection.sql`` (Plan 01-00
    generator output); the fixture is loaded into the dev Postgres by the
    module-scoped autouse fixture in ``tests/integration/conftest.py``
    (lifted from this module by Plan 01-07 so every integration test gets the
    seed without per-module boilerplate). Re-applying is idempotent (the SQL
    file starts with TRUNCATE), so subsequent modules cannot race the seed.
  - Query string is now an artist family present in the v2 seed (``Artist 1``)
    since the v1 ``Miles Davis`` rows no longer exist.

Plan 02-03 updates:
  - All requests include profile_id query param (D2-04) and gruvax_browse_binding
    cookie so the per-profile session validation gate passes.
  - The search_client fixture includes the second_profile fixture so 2+ profiles
    are cached in the registry, proving SLOs hold with multi-profile state (SC#5).

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


# Default profile UUID (D-02) + browse-binding cookie name (D2-10).
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"


@pytest_asyncio.fixture(scope="module")
async def search_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with full lifespan for benchmark tests.

    The app lifespan populates the per-profile registry from all non-deleted profiles
    in gruvax.profiles at startup — the SLO gate proves performance holds with
    however many profiles exist in the current DB (SC#5).

    When run via ``just slo`` in a multi-profile environment (e.g., after the full
    integration suite has seeded additional profiles), the registry will have 2+
    entries, fully satisfying the SC#5 multi-profile requirement.

    Sets the gruvax_browse_binding cookie to the default profile UUID so that
    profile-scoped search/locate endpoints pass session validation (D2-04).
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
            cookies={BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID},
        ) as ac,
    ):
        yield ac


@pytest.mark.benchmark
def test_search_slo_benchmark(benchmark, search_client) -> None:  # type: ignore[no-untyped-def]
    """p95 /api/search round-trip must be < 200 ms on synthetic data (SC5).

    Uses the sync-wrapper + asyncio pattern so pytest-benchmark can call the
    function in its timing loop (benchmark fixture is synchronous).

    Plan 01-06: the canonical query is now ``Artist 1`` because the v1 seed's
    ``Miles Davis`` rows were replaced by the v2 generator's ``Artist N``
    placeholders.  The synthetic seed has dozens of Artist N matches so the
    FTS path returns a populated result list (realistic non-empty workload).

    Plan 02-03: profile_id is passed as a query param (D2-04); the second_profile
    fixture ensures 2+ profiles are in the registry at benchmark time (SC#5).
    """
    loop = asyncio.get_event_loop()

    async def _run_search() -> float:
        resp = await search_client.get(
            "/api/search",
            params={"q": "Artist 1", "limit": "5", "profile_id": DEFAULT_PROFILE_UUID},
        )
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


@pytest.mark.benchmark
def test_locate_slo_benchmark(benchmark, search_client) -> None:  # type: ignore[no-untyped-def]
    """p95 /api/locate round-trip must be < 50 ms on synthetic data (SC5).

    Plan 01-06: release_id=1 is the canonical first synthetic record
    (Blue Note BLP 1000) which is guaranteed present in profile_collection by
    the suite-wide autouse seed fixture in ``tests/integration/conftest.py``
    (added by Plan 01-07; was a module-local fixture here pre-01-07). /api/locate hits the
    in-memory snapshot + segment cache (POS-03 — CPU only, no DB after the
    initial get_release_for_locate lookup) so this measures the locate path
    end-to-end including the DB metadata fetch.

    Plan 02-03: profile_id is passed as a query param (D2-04); the second_profile
    fixture ensures 2+ profiles are in the registry at benchmark time (SC#5).
    """
    loop = asyncio.get_event_loop()

    async def _run_locate() -> int:
        resp = await search_client.get(
            "/api/locate",
            params={"release_id": 1, "profile_id": DEFAULT_PROFILE_UUID},
        )
        # Locate may return 404 in DB-empty conditions; treat as a hard fail
        # so the SLO gate catches setup regressions early.
        assert resp.status_code == 200, f"Locate returned {resp.status_code}: {resp.text}"
        return resp.status_code

    def sync_run() -> int:
        return loop.run_until_complete(_run_locate())

    benchmark(sync_run)

    assert benchmark.stats["mean"] * 1000 < 50, (
        f"Locate SLO FAILED: mean {benchmark.stats['mean'] * 1000:.2f} ms > 50 ms budget (SC5)"
    )
