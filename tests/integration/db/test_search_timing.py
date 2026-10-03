"""Handler timing includes real profile resolution, SQL and optional suggestion."""

from __future__ import annotations

import asyncio
import importlib
import time
from typing import TYPE_CHECKING, Any

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from psycopg import AsyncCursor
import pytest
import pytest_asyncio

from gruvax.app import create_app
from gruvax.db import queries
from tests.cookies import cookie_header
from tests.integration.db.test_search_correctness import profile as profile


if TYPE_CHECKING:
    from fastapi import FastAPI

search_router = importlib.import_module("gruvax.api.search")


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def timed_client(profile: str):  # type: ignore[no-untyped-def]
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
            headers=cookie_header({"gruvax_browse_binding": profile}),
        ) as client,
    ):
        yield app, client


def delay_real_search_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject latency while retaining the real resolver, SQL and suggestion."""
    resolve = search_router.resolve_profile_from_request
    suggest = queries.did_you_mean_query
    execute = AsyncCursor.execute

    async def slow_resolve(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.22)
        return await resolve(*args, **kwargs)

    async def slow_suggest(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.08)
        return await suggest(*args, **kwargs)

    async def slow_execute(self: Any, query: Any, *args: Any, **kwargs: Any) -> Any:
        if str(query).lstrip().startswith("WITH fts AS"):
            await asyncio.sleep(0.04)
        return await execute(self, query, *args, **kwargs)

    monkeypatch.setattr(search_router, "resolve_profile_from_request", slow_resolve)
    monkeypatch.setattr(queries, "did_you_mean_query", slow_suggest)
    monkeypatch.setattr(AsyncCursor, "execute", slow_execute)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("q", "expected_id", "suggestion", "minimum_db_ms"),
    [
        ("Tommy", 920001, None, 40),
        ("Destroyr", None, "Destroyer", 120),
        ("-", None, None, 0),
    ],
)
async def test_http_total_and_db_phases_are_separate(
    timed_client: tuple[FastAPI, AsyncClient],
    monkeypatch: pytest.MonkeyPatch,
    q: str,
    expected_id: int | None,
    suggestion: str | None,
    minimum_db_ms: int,
) -> None:
    app, client = timed_client
    app.state.slow_query_ring.clear()
    delay_real_search_phases(monkeypatch)
    observed: list[float] = []
    search = search_router.search_collection

    async def capture_db_phase(*args: Any, **kwargs: Any) -> Any:
        result = await search(*args, **kwargs)
        observed.append(result[1])
        return result

    monkeypatch.setattr(search_router, "search_collection", capture_db_phase)
    start = time.perf_counter()
    response = await client.get("/api/search", params={"q": q})
    external_ms = (time.perf_counter() - start) * 1000
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["release_id"] for row in body["items"]] == (
        [] if expected_id is None else [expected_id]
    )
    assert body["did_you_mean"] == suggestion
    assert len(observed) == 1
    db_ms = observed[0]
    assert db_ms >= minimum_db_ms
    assert body["took_ms"] >= 220 + minimum_db_ms
    assert external_ms >= body["took_ms"] - 1
    assert body["took_ms"] - db_ms >= 215
    entries = [entry for entry in app.state.slow_query_ring if entry["path"] == "/api/search"]
    assert len(entries) == 1
    assert entries[0]["total_ms"] == pytest.approx(body["took_ms"], abs=0.11)
    assert entries[0]["db_ms"] == pytest.approx(db_ms, abs=0.11)
    assert entries[0]["threshold_ms"] == 200
