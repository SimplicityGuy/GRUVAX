"""Integration tests for `gruvax-sync` CLI — Plan 01-04 Task 3.

Tests (7 — mirrors PLAN.md):
  1. Happy path TTY-piped: subprocess invocation with PIN piped on stdin → exit 0;
     captured stdout contains '"status":"ok"' or equivalent.
  2. Bad PIN → exit non-zero with "Admin login failed: HTTP 401" or 403.
  3. Sync 503 (upstream 500): login succeeds, sync returns 503 → exit non-zero.
  4. Profile resolution: --profile default → POST hits /api/admin/profiles/
     <DEFAULT_UUID>/sync (verified by route hit).
  5. Static source-read: httpx.Timeout(read=120.0) or similar generous read
     timeout present in src/gruvax/cli/sync_cli.py.
  6. Stdin-pipe PIN (non-TTY) — `echo $PIN | gruvax-sync` form for Plan 05
     init-sync container support.
  7. PIN validation: non-numeric / wrong length → exit non-zero with "PIN must
     be 4 numeric digits".

Harness:
  - A session-scoped uvicorn fixture launches the REAL GRUVAX FastAPI on an
    ephemeral port (so the CLI subprocess can talk to it over HTTP).
  - A second uvicorn fixture launches the fake-discogsography on a second
    ephemeral port; GRUVAX_BASE_URL + DISCOGSOGRAPHY_BASE_URL are passed to
    the subprocess via env.
  - For static-content checks (Test 5) we just read the CLI source file.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
import uvicorn


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


DEFAULT_PROFILE_NAME = "Default"
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
TEST_PIN = "0000"
TEST_PAT = "dscg_test_sync_cli_LEAK_DETECTOR_secret_aaaaaaaaaa"  # ≥ 50 chars


# ── helpers ──────────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _make_release(release_id: int) -> dict:
    return {
        "id": str(release_id),
        "title": f"Title {release_id}",
        "year": 1980,
        "artist": f"Artist {release_id}",
        "label": "Blue Note",
        "catalog_number": f"BLP-{release_id:04d}",
        "folder_id": 1,
    }


# ── fake-discogsography mux (reused across all tests via a pin board) ────────


class _FakeMux:
    """Holds the currently-active fake-discogsography FastAPI app."""

    def __init__(self) -> None:
        self.app = None  # type: ignore[var-annotated]


_FAKE_MUX = _FakeMux()


def _build_fake_outer():  # type: ignore[no-untyped-def]
    from fastapi import FastAPI, Header, HTTPException, Query

    outer = FastAPI()

    @outer.get("/api/user/collection")
    async def _proxy(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        if _FAKE_MUX.app is None:
            raise HTTPException(503, "no fake app configured")
        inner = _FAKE_MUX.app
        for route in inner.routes:
            if getattr(route, "path", None) == "/api/user/collection":
                handler = route.endpoint  # type: ignore[attr-defined]
                return await handler(authorization=authorization, limit=limit, offset=offset)
        raise HTTPException(500, "inner has no /api/user/collection route")

    return outer


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key() -> None:
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        os.environ["GRUVAX_SECRET_KEY"] = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _ensure_session_secret() -> None:
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"


@pytest.fixture(scope="module")
def fake_disco_port() -> int:
    return _find_free_port()


@pytest.fixture(scope="module")
def gruvax_api_port() -> int:
    return _find_free_port()


@pytest.fixture(scope="module", autouse=False)
def fake_disco_server(fake_disco_port) -> Iterator[None]:  # type: ignore[no-untyped-def]
    """Run the fake-discogsography uvicorn for the whole test session."""
    outer = _build_fake_outer()
    config = uvicorn.Config(
        outer, host="127.0.0.1", port=fake_disco_port, log_level="warning", loop="asyncio"
    )
    server = uvicorn.Server(config)

    def _run() -> None:
        server.run()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", fake_disco_port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError(f"fake-discogsography did not start on {fake_disco_port}")

    yield
    server.should_exit = True
    thread.join(timeout=5.0)


@pytest.fixture(scope="module", autouse=False)
def gruvax_api_server(gruvax_api_port, fake_disco_port, fake_disco_server) -> Iterator[None]:  # type: ignore[no-untyped-def]
    """Run the real GRUVAX FastAPI on an ephemeral port for the session.

    The subprocess CLI POSTs to this server (login + sync). The
    DISCOGSOGRAPHY_BASE_URL env is set BEFORE the app is imported so the
    Settings singleton picks up the fake-disco port.
    """
    os.environ["DISCOGSOGRAPHY_BASE_URL"] = f"http://127.0.0.1:{fake_disco_port}"
    # Force settings to reflect the new base URL even though other modules have
    # already done `from gruvax.settings import settings` (singleton-by-import
    # pattern). Re-instantiate AND mutate the live singleton's attribute so
    # cached references in sync_profile / set_pat see the test fake-disco port.
    import gruvax.settings as _settings_mod

    _settings_mod.settings.DISCOGSOGRAPHY_BASE_URL = (  # type: ignore[misc]
        f"http://127.0.0.1:{fake_disco_port}"
    )

    from gruvax.app import create_app

    # Patch sync_profile._refresh_app_caches to a no-op while THIS server is
    # running — the in-process sync triggered by the CLI subprocess would
    # otherwise hit the live collection_snapshot read path
    # (gruvax.profile_collection). We restore the original at fixture teardown so
    # we don't leak into other test modules' cache-refresh assertions.
    from gruvax.sync import profile_sync as _profile_sync_mod

    _original_refresh = _profile_sync_mod._refresh_app_caches

    async def _noop_refresh(_app_state) -> None:  # type: ignore[no-untyped-def]
        return None

    _profile_sync_mod._refresh_app_caches = _noop_refresh  # type: ignore[assignment]

    app = create_app()

    config = uvicorn.Config(
        app, host="127.0.0.1", port=gruvax_api_port, log_level="warning", loop="asyncio"
    )
    server = uvicorn.Server(config)

    def _run() -> None:
        server.run()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", gruvax_api_port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"gruvax-api did not start on {gruvax_api_port}")

    # Wait for /api/health to actually respond (lifespan startup may still be running).
    # Use httpx (already a project dep) instead of urllib to avoid the urllib
    # file:// scheme attack surface flagged by semgrep — even though the URL
    # here is a test-controlled localhost literal, httpx is strictly HTTP/HTTPS.
    import httpx

    health_deadline = time.time() + 10.0
    while time.time() < health_deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{gruvax_api_port}/api/health", timeout=1.0)
            r.raise_for_status()
            break
        except Exception:
            time.sleep(0.1)

    yield
    server.should_exit = True
    thread.join(timeout=5.0)
    # Restore the original cache-refresh so cross-module tests are unaffected.
    _profile_sync_mod._refresh_app_caches = _original_refresh  # type: ignore[assignment]


@pytest_asyncio.fixture(loop_scope="session")
async def reset_profile_and_pin(db_pool) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    """Seed test PIN '0000' and reset the default profile to a sync-runnable state."""
    from gruvax.auth.pin import hash_pin
    from gruvax.sync.pat_crypto import encrypt_pat

    cipher = encrypt_pat(TEST_PAT)
    pin_hash = hash_pin(TEST_PIN)
    async with db_pool.connection() as conn:
        _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
        await conn.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb, 'Test PIN for sync_cli', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (_DEFAULT_PROFILE_UUID, f'"{pin_hash}"'),
        )
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    app_token_encrypted = %s, app_token_revoked = FALSE, "
            "    last_sync_status = NULL, last_sync_error = NULL, "
            "    display_name = %s "
            "WHERE id = %s::uuid",
            (cipher, DEFAULT_PROFILE_NAME, DEFAULT_PROFILE_UUID),
        )
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_PROFILE_UUID,),
        )
        await conn.commit()
    yield


def _run_sync_cli(
    *,
    stdin: str,
    gruvax_api_port: int,
    profile: str = DEFAULT_PROFILE_NAME,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GRUVAX_BASE_URL"] = f"http://127.0.0.1:{gruvax_api_port}"
    if extra_env:
        env.update(extra_env)
    args = ["uv", "run", "gruvax-sync", "--profile", profile]
    return subprocess.run(  # noqa: S603
        args,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_happy_path_piped_pin(  # type: ignore[no-untyped-def]
    db_pool, reset_profile_and_pin, fake_disco_server, gruvax_api_server, gruvax_api_port
) -> None:
    """Test 1: stdin-piped PIN → 200 from sync → exit 0; stdout contains "status":"ok"."""
    from gruvax._internal.fake_discogsography import create_fake_app

    _FAKE_MUX.app = create_fake_app(seed=[_make_release(i) for i in range(1, 6)])

    result = _run_sync_cli(stdin=f"{TEST_PIN}\n", gruvax_api_port=gruvax_api_port)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert '"status"' in result.stdout and "ok" in result.stdout, result.stdout


@pytest.mark.asyncio(loop_scope="session")
async def test_bad_pin_exits_nonzero(  # type: ignore[no-untyped-def]
    reset_profile_and_pin, fake_disco_server, gruvax_api_server, gruvax_api_port
) -> None:
    """Test 2: wrong PIN → exit non-zero with Admin login failed."""
    result = _run_sync_cli(stdin="9999\n", gruvax_api_port=gruvax_api_port)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Admin login failed" in combined and "401" in combined, combined


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_503_exits_nonzero(  # type: ignore[no-untyped-def]
    db_pool, reset_profile_and_pin, fake_disco_server, gruvax_api_server, gruvax_api_port
) -> None:
    """Test 3: fake returns 500 → sync endpoint 503 → CLI exit non-zero."""
    from fastapi import FastAPI, HTTPException

    fake = FastAPI()

    @fake.get("/api/user/collection")
    async def _always_500() -> dict:
        raise HTTPException(500, "boom")

    _FAKE_MUX.app = fake

    result = _run_sync_cli(stdin=f"{TEST_PIN}\n", gruvax_api_port=gruvax_api_port)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ("503" in combined) or ("upstream_unavailable" in combined), combined


@pytest.mark.asyncio(loop_scope="session")
async def test_profile_resolves_to_default_uuid(  # type: ignore[no-untyped-def]
    db_pool, reset_profile_and_pin, fake_disco_server, gruvax_api_server, gruvax_api_port
) -> None:
    """Test 4: --profile Default → POST hits /api/admin/profiles/<DEFAULT_UUID>/sync.

    Verified by inspecting profiles.last_sync_at AFTER the call — only the
    Default profile (UUID 00000000-…0001) gets a last_sync_at update.
    """
    from gruvax._internal.fake_discogsography import create_fake_app

    _FAKE_MUX.app = create_fake_app(seed=[_make_release(i) for i in range(1, 4)])

    result = _run_sync_cli(stdin=f"{TEST_PIN}\n", gruvax_api_port=gruvax_api_port)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT last_sync_status, last_sync_at IS NOT NULL "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_PROFILE_UUID,),
        )
        row = await cur.fetchone()
        assert row == ("ok", True), row


def test_static_read_timeout_120s() -> None:
    """Test 5: source contains a generous read timeout for the sync POST."""
    from pathlib import Path

    src = Path("src/gruvax/cli/sync_cli.py").read_text()
    # Either form is accepted: httpx.Timeout(read=120.0) or read=120 literal.
    assert "read=120" in src or "Timeout(connect=10.0, read=120" in src, (
        "sync_cli.py must use httpx.Timeout with read>=120s for the sync POST "
        "(PATTERNS §2 line 163)."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_pin_via_stdin_pipe_non_tty(  # type: ignore[no-untyped-def]
    db_pool, reset_profile_and_pin, fake_disco_server, gruvax_api_server, gruvax_api_port
) -> None:
    """Test 6: `echo $PIN | gruvax-sync` form (stdin is a pipe, not a TTY).

    This is the exact form Plan 05's init-sync compose container uses:
      command: ["sh", "-c", "echo $GRUVAX_ADMIN_PIN | gruvax-sync --profile default"]
    The subprocess form here guarantees stdin is a pipe; the CLI must use
    sys.stdin.readline().rstrip() rather than getpass when stdin is non-TTY.
    """
    from gruvax._internal.fake_discogsography import create_fake_app

    _FAKE_MUX.app = create_fake_app(seed=[_make_release(i) for i in range(1, 4)])

    # Use shell pipeline to exactly mirror the Plan 05 compose form.
    env = os.environ.copy()
    env["GRUVAX_BASE_URL"] = f"http://127.0.0.1:{gruvax_api_port}"
    env["GRUVAX_ADMIN_PIN"] = TEST_PIN
    result = subprocess.run(
        [  # noqa: S607
            "sh",
            "-c",
            "echo $GRUVAX_ADMIN_PIN | uv run gruvax-sync --profile Default",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert '"status"' in result.stdout and "ok" in result.stdout, result.stdout


@pytest.mark.asyncio(loop_scope="session")
async def test_pin_validation(  # type: ignore[no-untyped-def]
    reset_profile_and_pin, fake_disco_server, gruvax_api_server, gruvax_api_port
) -> None:
    """Test 7: non-numeric or wrong-length PIN → exit non-zero with the canonical message."""
    # 7a — non-numeric
    result = _run_sync_cli(stdin="abcd\n", gruvax_api_port=gruvax_api_port)
    assert result.returncode != 0
    assert "PIN must be 4 numeric digits" in (result.stderr + result.stdout)

    # 7b — too long
    result = _run_sync_cli(stdin="12345\n", gruvax_api_port=gruvax_api_port)
    assert result.returncode != 0
    assert "PIN must be 4 numeric digits" in (result.stderr + result.stdout)
