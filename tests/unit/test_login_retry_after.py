"""Login's actual fixed window reports remaining time, not a fresh five-minute wait."""

from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from limits.storage import memory
import pytest

from gruvax.api.admin import login
from gruvax.api.admin.limiter import limiter


@pytest.mark.asyncio
@pytest.mark.parametrize("elapsed,remainder", [(0, 300), (290, 10), (299.9, 1)])
async def test_real_fixed_window_retry_after_and_reset(
    monkeypatch: pytest.MonkeyPatch, elapsed: float, remainder: int
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(memory, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(login, "time", lambda: clock[0], raising=False)
    limiter.reset()
    app = FastAPI()
    # Invalid PIN shape returns before DB/hash work; the real login guard still runs.
    app.state.db_pool = object()
    app.include_router(login.router, prefix="/api/admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/admin/login", json={"pin": "x"})).status_code == 401
        clock[0] += elapsed
        for _ in range(4):
            assert (await client.post("/api/admin/login", json={"pin": "x"})).status_code == 401
        limited = await client.post("/api/admin/login", json={"pin": "x"})
        assert limited.status_code == 429
        assert limited.headers["Retry-After"] == str(remainder)
        # Exhaustion does not restart the original window, even on subsequent attempts.
        clock[0] = 1299.9
        limited = await client.post("/api/admin/login", json={"pin": "x"})
        assert limited.status_code == 429 and limited.headers["Retry-After"] == "1"
        clock[0] = 1300.1
        retried = await client.post("/api/admin/login", json={"pin": "x"})
        assert retried.status_code == 401  # accepted by limiter; still an invalid PIN
        assert "Retry-After" not in retried.headers
    limiter.reset()
