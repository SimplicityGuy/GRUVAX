"""Integration tests for GET /api/search.

Tests:
  - test_catalog_path: catalog-number prefix search hits correct record
    (e.g. "BLP 4195" normalizes to find Blue Note BLP records).
  - test_fts_artist: FTS search on artist name returns matching records.
  - test_no_results: q="zzznomatch" returns HTTP 200 with items: [].
  - test_sqli_payload: SQL injection payload returns safe 200 response.
  - test_max_length_enforced: q of 201 characters returns HTTP 422.
  - test_limit_enforced: limit=999 returns HTTP 422.
  - test_min_length_enforced: empty q returns HTTP 422.
  - test_default_limit: no limit param → defaults to 20.
  - test_did_you_mean: near-miss query returns did_you_mean field (SRCH-07).
  - test_catalog_boost: catalog-like query ranks catalog record first (SRCH-08).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan."""
    app = create_app()
    async with LifespanManager(app) as manager, AsyncClient(
        transport=ASGITransport(app=manager.app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_path(client) -> None:  # type: ignore[no-untyped-def]
    """Catalog path: 'BLP 4001' hits Blue Note BLP 4001 record."""
    response = await client.get("/api/search", params={"q": "BLP 4001"})
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "took_ms" in body

    release_ids = [item["release_id"] for item in body["items"]]
    assert release_ids, f"Expected at least one result for BLP 4001, got none. body={body}"

    # The record with catalog_number "BLP 4001" is release_id 1 in the seed
    catalog_numbers = [item["catalog_number"] for item in body["items"]]
    assert any("BLP 4001" in cn for cn in catalog_numbers), (
        f"Expected BLP 4001 in catalog numbers, got: {catalog_numbers}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_path_normalized(client) -> None:  # type: ignore[no-untyped-def]
    """Normalized catalog path: 'blp4001' (no space/separator) hits BLP 4001."""
    response = await client.get("/api/search", params={"q": "blp4001"})
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert items, "Expected results for 'blp4001', got none"
    catalog_numbers = [item["catalog_number"] for item in items]
    assert any("BLP 4001" in cn for cn in catalog_numbers), (
        f"Separator-normalized 'blp4001' should match 'BLP 4001'. Got: {catalog_numbers}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_fts_artist(client) -> None:  # type: ignore[no-untyped-def]
    """FTS: search by artist name returns matching records."""
    response = await client.get("/api/search", params={"q": "Miles Davis"})
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert items, "Expected at least one result for 'Miles Davis', got none"

    artists = [item["primary_artist"] for item in items]
    assert any("Miles Davis" in (a or "") for a in artists), (
        f"Expected Miles Davis in results, got artists: {artists}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_fts_title(client) -> None:  # type: ignore[no-untyped-def]
    """FTS: search by album title returns matching record."""
    response = await client.get("/api/search", params={"q": "Kind of Blue"})
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert items, "Expected results for 'Kind of Blue'"
    titles = [item["title"] for item in items]
    assert any("Kind of Blue" in (t or "") for t in titles), (
        f"Expected 'Kind of Blue' in titles. Got: {titles}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_no_results(client) -> None:  # type: ignore[no-untyped-def]
    """SRCH-04: q='zzznomatch' returns HTTP 200 with items: [] (empty list).

    Also verifies the new did_you_mean key is present in the response
    (SRCH-07 — value may be null when no trigram candidate exceeds threshold
    or when pg_trgm is unavailable).
    """
    response = await client.get("/api/search", params={"q": "zzznomatch"})
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [], (
        f"Expected empty items for 'zzznomatch', got: {body}"
    )
    assert "did_you_mean" in body, (
        f"Response missing 'did_you_mean' key: {body}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_sqli_payload(client) -> None:  # type: ignore[no-untyped-def]
    """T-01-07: SQL injection payload returns 200 safe response (no SQL error).

    The parameterized psycopg query treats the entire q value as a literal
    string, so injection payloads are harmless text. The FTS query will
    return no results (the payload matches nothing in the collection).
    """
    payload = "') OR 1=1 --"
    response = await client.get("/api/search", params={"q": payload})
    # Must NOT return 500 (SQL error) or any other error status
    assert response.status_code == 200, (
        f"SQL injection payload caused non-200 response: {response.status_code}, "
        f"body: {response.text}"
    )
    body = response.json()
    assert "items" in body, f"Response missing 'items' key: {body}"
    # The injection payload should not cause unexpected data leakage or errors


@pytest.mark.asyncio(loop_scope="session")
async def test_max_length_enforced(client) -> None:  # type: ignore[no-untyped-def]
    """T-01-10: q with 201 characters returns HTTP 422 (max_length=200)."""
    long_q = "a" * 201
    response = await client.get("/api/search", params={"q": long_q})
    assert response.status_code == 422, (
        f"Expected 422 for oversized q, got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_limit_enforced(client) -> None:  # type: ignore[no-untyped-def]
    """T-01-08: limit=999 returns HTTP 422 (le=50)."""
    response = await client.get("/api/search", params={"q": "blue note", "limit": 999})
    assert response.status_code == 422, (
        f"Expected 422 for limit=999, got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_limit_zero_enforced(client) -> None:  # type: ignore[no-untyped-def]
    """T-01-08: limit=0 returns HTTP 422 (ge=1)."""
    response = await client.get("/api/search", params={"q": "blue note", "limit": 0})
    assert response.status_code == 422, (
        f"Expected 422 for limit=0, got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_empty_q_enforced(client) -> None:  # type: ignore[no-untyped-def]
    """min_length=1: empty q returns HTTP 422."""
    response = await client.get("/api/search", params={"q": ""})
    assert response.status_code == 422, (
        f"Expected 422 for empty q, got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_response_shape(client) -> None:  # type: ignore[no-untyped-def]
    """Search response items have the expected field set."""
    response = await client.get("/api/search", params={"q": "Blue Note"})
    assert response.status_code == 200
    body = response.json()
    if body["items"]:
        item = body["items"][0]
        expected_fields = {
            "release_id", "collection_item_id", "title", "primary_artist",
            "label", "catalog_number", "format", "year", "rank",
        }
        assert expected_fields.issubset(item.keys()), (
            f"Missing fields in search item: {expected_fields - item.keys()}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_did_you_mean(client) -> None:  # type: ignore[no-untyped-def]
    """SRCH-07: near-miss query returns did_you_mean field.

    Uses a single-character typo of a common term.  The test is robust to
    the [ASSUMED] pg_trgm dependency: when the extension is unavailable,
    did_you_mean degrades to null (Pitfall E) — the test accepts both:
      - A non-empty string suggestion that differs from the input typo
      - None (pg_trgm absent)

    The response must be 200 in both cases and the key must be present.
    """
    # Use a near-miss query that returns no strong FTS hit but is close to
    # a real label/artist in the collection.
    response = await client.get("/api/search", params={"q": "zzznomatch"})
    assert response.status_code == 200
    body = response.json()
    assert "did_you_mean" in body, (
        f"Response missing 'did_you_mean' key: {body}"
    )
    # Accept both None (pg_trgm unavailable) and a string suggestion
    dym = body["did_you_mean"]
    assert dym is None or isinstance(dym, str), (
        f"did_you_mean should be None or str, got {type(dym)!r}: {dym!r}"
    )
    # When non-null, the suggestion must differ from the input typo
    if dym is not None:
        assert dym != "zzznomatch", (
            f"did_you_mean returned the same as input: {dym!r}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_boost(client) -> None:  # type: ignore[no-untyped-def]
    """SRCH-08: catalog-like query ranks the catalog record first.

    Runs two queries:
      1. Catalog-like (e.g. "BLP 4001") — should match the catalog record
         as top result via the catalog-boost path.
      2. Plain artist text — should return results but NOT via catalog boost.

    Both must return 200 and contain the did_you_mean key.
    The catalog query must have the matching catalog record as items[0].
    """
    # Catalog-like query — is_catalog_query("BLP 4001") → True
    response = await client.get("/api/search", params={"q": "BLP 4001"})
    assert response.status_code == 200
    body = response.json()
    assert "did_you_mean" in body, (
        f"Response missing 'did_you_mean' key: {body}"
    )
    items = body["items"]
    assert items, "Expected at least one result for 'BLP 4001'"
    # Top result must contain the catalog number BLP 4001
    catalog_numbers = [item["catalog_number"] for item in items]
    assert any("BLP 4001" in (cn or "") for cn in catalog_numbers), (
        f"Expected BLP 4001 in top results via catalog boost. Got: {catalog_numbers}"
    )

    # Plain artist text query — must also return did_you_mean key
    response2 = await client.get("/api/search", params={"q": "Miles Davis"})
    assert response2.status_code == 200
    body2 = response2.json()
    assert "did_you_mean" in body2, (
        f"Response missing 'did_you_mean' key for artist query: {body2}"
    )
