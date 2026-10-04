"""Strict collection paging pins one immutable upstream generation."""

import datetime as dt
from typing import Any

import httpx
import pytest

from gruvax.discogsography.client import DiscogsographyClient


USER = "99999999-9999-9999-9999-999999999999"
GENERATION = "11111111-1111-1111-1111-111111111111"
EXPIRES = (
    (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10))
    .isoformat(timespec="microseconds")
    .replace("+00:00", "Z")
)


def page(start: int = 0, **changes: Any) -> dict[str, Any]:
    result = {
        "user_id": USER,
        "releases": [{"id": str(start + 1)}],
        "total": 2,
        "offset": start,
        "limit": 1,
        "has_more": start == 0,
        "snapshot_token": "opaque-synthetic-token",
        "snapshot_generation": GENERATION,
        "snapshot_expires_at": EXPIRES,
        "snapshot_source": "completed_collection_sync",
    }
    return {**result, **changes}


@pytest.mark.asyncio
async def test_iterator_requests_and_pins_snapshot_on_every_page() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=page(int(request.url.params["offset"])))

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://synthetic"
    )
    try:
        assert [row["id"] async for row in client.iter_collection(page_size=1)] == ["1", "2"]
        assert requests[0].url.params["snapshot"] == "new"
        assert requests[1].url.params["snapshot"] == "opaque-synthetic-token"
        assert requests[1].url.params["snapshot_generation"] == GENERATION
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_token", "changed"),
        ("snapshot_generation", "22222222-2222-2222-2222-222222222222"),
        ("user_id", "22222222-2222-2222-2222-222222222222"),
        ("total", 3),
        ("offset", 0),
        ("limit", True),
        ("has_more", True),
        ("releases", []),
        ("snapshot_source", "live"),
        ("snapshot_expires_at", "2099-01-01T00:00:00.000000Z"),
    ],
)
async def test_continuation_drift_is_rejected_before_invalid_rows_are_yielded(
    field: str, value: Any
) -> None:
    from gruvax.discogsography.errors import SnapshotMismatch

    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=page() if len(calls) == 1 else page(1, **{field: value}))

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://synthetic"
    )
    seen: list[str] = []
    try:
        with pytest.raises(SnapshotMismatch):
            async for row in client.iter_collection(page_size=1):
                seen.append(row["id"])
        assert seen == ["1"]
        assert len(calls) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (409, "snapshot_mismatch"),
        (409, "snapshot_scope_mismatch"),
        (409, "snapshot_unavailable"),
        (410, "snapshot_expired"),
    ],
)
async def test_snapshot_errors_are_safe_and_never_retried(status: int, code: str) -> None:
    from gruvax.discogsography.errors import SnapshotMismatch

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status, json={"detail": {"code": code, "message": "SECRET-snapshot-body"}}
        )

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://synthetic"
    )
    try:
        with pytest.raises(SnapshotMismatch) as error:
            assert [row async for row in client.iter_collection(page_size=1)]
        assert "SECRET" not in str(error.value)
        assert len(requests) == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_fake_snapshot_survives_same_total_mutation_and_preserves_instances() -> None:
    from gruvax._internal.fake_discogsography import create_fake_app

    seed = [
        {"id": "42", "instance_id": 1},
        {"id": "42", "instance_id": 2},
        {"id": "43", "instance_id": None},
    ]
    app = create_fake_app(seed=seed)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://fake",
        headers={"Authorization": "Bearer dscg_synthetic"},
    ) as client:
        first = await client.get(
            "/api/user/collection", params={"snapshot": "new", "limit": 1, "offset": 0}
        )
        assert first.status_code == 200
        pin = first.json()
        seed[:] = [{"id": "99"}, {"id": "98"}, {"id": "97"}]
        second = await client.get(
            "/api/user/collection",
            params={
                "snapshot": pin["snapshot_token"],
                "snapshot_generation": pin["snapshot_generation"],
                "limit": 2,
                "offset": 1,
            },
        )
        assert second.status_code == 200
        assert first.json()["releases"] + second.json()["releases"] == [
            {"id": "42", "instance_id": 1},
            {"id": "42", "instance_id": 2},
            {"id": "43", "instance_id": None},
        ]
        assert second.json()["snapshot_expires_at"] == pin["snapshot_expires_at"]
        probe = await client.get("/api/user/collection", params={"limit": 1})
        assert probe.status_code == 200
        assert "snapshot_token" not in probe.json()


@pytest.mark.asyncio
async def test_fake_bounded_admission_never_evicts_an_active_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gruvax._internal import fake_discogsography as fake

    monkeypatch.setattr(fake, "_MAX_SNAPSHOTS", 1)
    app = fake.create_fake_app(seed=[{"id": "1"}, {"id": "2"}])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://fake",
        headers={"Authorization": "Bearer dscg_synthetic"},
    ) as client:
        first = await client.get("/api/user/collection", params={"snapshot": "new", "limit": 1})
        assert first.status_code == 200
        rejected = await client.get("/api/user/collection", params={"snapshot": "new", "limit": 1})
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "snapshot_unavailable"
        pin = first.json()
        continued = await client.get(
            "/api/user/collection",
            params={
                "snapshot": pin["snapshot_token"],
                "snapshot_generation": pin["snapshot_generation"],
                "limit": 1,
                "offset": 1,
            },
        )
        assert continued.status_code == 200
        assert continued.json()["releases"] == [{"id": "2"}]
        assert continued.json()["snapshot_token"] == pin["snapshot_token"]


@pytest.mark.parametrize(
    "changes",
    [
        {"snapshot_token": None},
        {"snapshot_token": " "},
        {"snapshot_token": "not/url-safe"},
        {"snapshot_generation": "not-a-uuid"},
        {"user_id": "99999999999999999999999999999999"},
        {"total": True},
        {"offset": False},
        {"limit": True},
        {"has_more": 1},
        {"releases": {}},
        {"releases": [1]},
        {"snapshot_expires_at": "2020-01-01T00:00:00.000000Z"},
        {"snapshot_expires_at": "2099-01-01T00:00:00+01:00"},
        {"snapshot_source": None},
        {"total": 0},
    ],
)
def test_invalid_initial_envelopes_are_not_coerced(changes: dict[str, Any]) -> None:
    from gruvax.discogsography.errors import SnapshotMismatch
    from gruvax.discogsography.snapshot_pages import validate_page

    with pytest.raises(SnapshotMismatch):
        validate_page(page(**changes), offset=0, limit=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["network", "server"])
async def test_continuation_retries_preserve_exact_pin(error: str) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        offset = int(request.url.params["offset"])
        if offset and len(calls) == 2:
            if error == "network":
                raise httpx.ReadTimeout("synthetic", request=request)
            return httpx.Response(503)
        return httpx.Response(200, json=page(offset))

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://synthetic"
    )
    try:
        assert [row["id"] async for row in client.iter_collection(page_size=1)] == ["1", "2"]
        assert len(calls) == 3
        assert calls[1].url == calls[2].url
        assert calls[2].url.params["snapshot"] == "opaque-synthetic-token"
        assert calls[2].url.params["snapshot_generation"] == GENERATION
    finally:
        await client.aclose()


@pytest.mark.parametrize("field", list(page()))
def test_missing_envelope_fields_are_rejected(field: str) -> None:
    from gruvax.discogsography.errors import SnapshotMismatch
    from gruvax.discogsography.snapshot_pages import validate_page

    incomplete = page()
    del incomplete[field]
    with pytest.raises(SnapshotMismatch):
        validate_page(incomplete, offset=0, limit=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null"])
async def test_success_status_with_invalid_json_envelope_does_not_fall_back(body: bytes) -> None:
    from gruvax.discogsography.errors import SnapshotMismatch

    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=body)

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://synthetic"
    )
    try:
        with pytest.raises(SnapshotMismatch):
            await anext(client.iter_pages())
        assert len(calls) == 1
        assert calls[0].url.params["snapshot"] == "new"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unrecognized_malformed_error_code_preserves_http_error_without_typeerror() -> None:
    client = DiscogsographyClient("http://synthetic", "dscg_synthetic")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(409, json={"detail": {"code": []}})),
        base_url="http://synthetic",
    )
    try:
        with pytest.raises(httpx.HTTPStatusError) as error:
            await anext(client.iter_pages())
        assert error.value.response.status_code == 409
    finally:
        await client.aclose()
