"""Exercise the production static mount through the real application router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
import pytest

import gruvax.app as app_module


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def static_apps(tmp_path: Path, monkeypatch: Any):  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    development = app_module.create_app()
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>Synthetic SPA</title>")
    (static / "assets" / "entry-123.js").write_text("window.synthetic = true;")
    (static / "api").mkdir()
    (static / "api" / "counterfeit").write_text("not an API response")
    production = app_module.create_app()
    return development, production


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api", "/api/nonexistent", "/api/nonexistent/", "/api/counterfeit"]
)
@pytest.mark.parametrize("method", ["GET", "POST", "HEAD"])
async def test_unknown_api_is_json_404_with_and_without_static(
    static_apps: tuple[Any, Any],
    path: str,
    method: str,
) -> None:
    for app in static_apps:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.request(method, path)
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
        if method != "HEAD":
            assert response.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
@pytest.mark.parametrize("root_path", ["", "/gruvax"])
async def test_api_slash_redirect_and_method_errors_preserve_native_parity(
    static_apps: tuple[Any, Any],
    root_path: str,
) -> None:
    results = []
    for app in static_apps:
        async with AsyncClient(
            transport=ASGITransport(app=app, root_path=root_path),
            base_url="http://test",
        ) as client:
            slash = await client.get(f"http://test{root_path}/api/health/?probe=1")
            post = await client.post(f"http://test{root_path}/api/health")
            head = await client.head(f"http://test{root_path}/api/health")
            health = await client.get(f"http://test{root_path}/api/health")
        assert slash.status_code == 307
        assert slash.headers["location"] == f"http://test{root_path}/api/health?probe=1"
        assert post.status_code == head.status_code == 405
        assert post.headers["allow"] == head.headers["allow"] == "GET"
        assert health.status_code == 200
        assert health.headers["content-type"] == "application/json"
        assert health.json()["status"] == "degraded"
        results.append((post.json(), health.json().keys()))
    assert results[0] == results[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/", "/admin", "/admin/cubes/1/0/0", "/redeem/synthetic-code", "/apiary"]
)
async def test_spa_deep_links_keep_html_and_no_store(
    static_apps: tuple[Any, Any], path: str
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=static_apps[1]), base_url="http://test"
    ) as client:
        response = await client.get(path)
    assert response.status_code == 200
    assert "Synthetic SPA" in response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_static_assets_and_missing_assets_keep_their_contract(
    static_apps: tuple[Any, Any],
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=static_apps[1]), base_url="http://test"
    ) as client:
        asset = await client.get("/assets/entry-123.js")
        missing = await client.get("/assets/missing.js")
    assert asset.status_code == 200
    assert asset.text == "window.synthetic = true;"
    assert "no-store" not in asset.headers.get("cache-control", "")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}


@pytest.mark.asyncio
async def test_production_missing_health_router_is_loud(
    static_apps: tuple[Any, Any],
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(app_module, "health_router", APIRouter())
    app = app_module.create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"detail": "Not Found"}
