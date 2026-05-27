"""Integration tests for `gruvax-set-pat` CLI — Plan 01-04 Task 2.

Tests (10 — mirrors PLAN.md):
  1. Stdin-pipe happy path → exit 0; profiles row updated (encrypted PAT,
     revoked=FALSE, discogsography_user_id captured).
  2. Argparse rejects `--pat` flag → exit non-zero (D-07 strict).
  3. Env-var fallback is ignored — GRUVAX_PAT set + no stdin → exit non-zero
     "No PAT provided on stdin".
  4. Prefix validation: PAT not starting with `dscg_` → exit non-zero.
  5. 401 (PATRejected) leaves the row UNTOUCHED — Pitfall 2 mitigation.
  6. D-09 strict rotation: PAT for a different user_id → exit non-zero with
     verbatim error string; DB row unchanged.
  7. D-09 strict rotation: same user_id (rotation) → exit 0; PAT updated.
  8. Sample release missing `catalog_number` → exit non-zero "missing
     catalog_number" / "refusing".
  9. TTY interactive flow: in-process invocation with isatty=True forces
     getpass.getpass to fire.
 10. Success-message format includes "PAT stored for profile" + next-step
     hint pointing at `gruvax-sync --profile <name>`.

Harness:
  - A session-scoped uvicorn fixture launches the in-memory fake-discogsography
    app on an ephemeral port; the CLI subprocess gets DISCOGSOGRAPHY_BASE_URL=
    http://127.0.0.1:{port} via env. The fake's seed is rebuilt per test (the
    create_fake_app factory is called with a fresh `seed=[...]` list).
  - For the 401/missing-catalog/rotation tests, the test uses a custom FastAPI
    app launched on the same uvicorn fixture by swapping app.state via a small
    "mux" router.
  - DB state is inspected via the shared `db_pool` fixture.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from typing import TYPE_CHECKING

from fastapi import FastAPI, Header, HTTPException, Query
import pytest
import pytest_asyncio
import uvicorn


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


DEFAULT_PROFILE_NAME = "Default"
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
VALID_PAT = "dscg_test_pat_set_pat_LEAK_DETECTOR_secret_aaaa_50chars_ok"  # ≥ 50 chars
USER_AAA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_BBB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ── helpers ──────────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    """Bind 0 to get an ephemeral port, then close so uvicorn can rebind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _conninfo_from_settings() -> str:
    """Read DATABASE_URL from the live settings instance and return psycopg conninfo."""
    from gruvax.settings import settings

    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _make_release(release_id: int, *, catalog_number: str | None = None) -> dict:
    base = {
        "id": str(release_id),
        "title": f"Title {release_id}",
        "year": 1980,
        "artist": f"Artist {release_id}",
        "label": "Blue Note",
        "folder_id": 1,
    }
    if catalog_number is not None:
        base["catalog_number"] = catalog_number
    else:
        base["catalog_number"] = f"BLP-{release_id:04d}"
    return base


# ── reconfigurable fake app — shared across all tests via a "current app" pointer ──


class _AppMux:
    """A pin-board for the currently-active fake-discogsography app.

    Tests assign `mux.app = create_fake_app(seed=[...])` (or a custom FastAPI
    app) BEFORE invoking the CLI subprocess. The uvicorn fixture wraps an
    outer FastAPI that delegates every request to `mux.app`. This avoids
    starting/stopping a uvicorn server per test (slow + brittle on macOS).
    """

    def __init__(self) -> None:
        self.app: FastAPI | None = None


_MUX = _AppMux()


def _build_outer_app() -> FastAPI:
    """Build the outer FastAPI that forwards to whichever app `_MUX.app` points at."""
    outer = FastAPI()

    @outer.get("/api/user/collection")
    async def _proxy_collection(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        if _MUX.app is None:
            raise HTTPException(503, "no fake app configured")
        # Invoke the inner route directly via the app's own dependency-resolution.
        # The simplest path is to call the route function via lookup since both
        # outer and inner expose the same signature.
        inner = _MUX.app
        # Find the matching route handler on the inner app
        for route in inner.routes:
            if getattr(route, "path", None) == "/api/user/collection":
                handler = route.endpoint  # type: ignore[attr-defined]
                return await handler(authorization=authorization, limit=limit, offset=offset)
        raise HTTPException(500, "inner app has no /api/user/collection route")

    return outer


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key() -> None:
    """Guarantee GRUVAX_SECRET_KEY is set for the subprocess + in-process tests."""
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        os.environ["GRUVAX_SECRET_KEY"] = Fernet.generate_key().decode()


@pytest.fixture(scope="session")
def fake_port() -> int:
    """Pick an ephemeral port once per session."""
    return _find_free_port()


@pytest.fixture(scope="session", autouse=False)
def fake_uvicorn(fake_port) -> Iterator[None]:  # type: ignore[no-untyped-def]
    """Run the outer fake-discogsography app on a uvicorn thread for the whole session.

    The outer app proxies to `_MUX.app`; tests rebuild `_MUX.app` between
    invocations to swap the response shape without restarting uvicorn.
    """
    outer = _build_outer_app()
    config = uvicorn.Config(
        outer,
        host="127.0.0.1",
        port=fake_port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    def _run() -> None:
        # uvicorn.Server.run() builds its own event loop.
        server.run()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # Wait for the server to be ready by polling the port.
    import time

    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", fake_port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError(f"fake-discogsography uvicorn did not start on {fake_port}")

    yield
    server.should_exit = True
    thread.join(timeout=5.0)


@pytest_asyncio.fixture(loop_scope="session")
async def reset_profile(db_pool) -> AsyncIterator[bytes]:  # type: ignore[no-untyped-def]
    """Reset the default profile to a pristine known-ciphertext state.

    Returns the original ciphertext (a real Fernet-encrypted "PRIOR-PAT") so
    Pitfall 2 tests can assert the row was untouched after a 401 failure path.
    """
    from gruvax.sync.pat_crypto import encrypt_pat

    original = encrypt_pat("dscg_PRIOR_PAT_for_unchanged_assertions_xxx")
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    app_token_encrypted = %s, "
            "    app_token_revoked = TRUE, "
            "    discogsography_user_id = NULL, "
            "    last_sync_status = NULL, "
            "    last_sync_error = NULL "
            "WHERE id = %s::uuid",
            (original, DEFAULT_PROFILE_UUID),
        )
        # Also normalize display_name to 'Default' for the lookup.
        await conn.execute(
            "UPDATE gruvax.profiles SET display_name = %s WHERE id = %s::uuid",
            (DEFAULT_PROFILE_NAME, DEFAULT_PROFILE_UUID),
        )
        await conn.commit()
    yield original


def _run_cli(
    *,
    stdin: str,
    fake_port: int,
    extra_args: list[str] | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `uv run gruvax-set-pat --profile <name>` with the given stdin."""
    env = os.environ.copy()
    env["DISCOGSOGRAPHY_BASE_URL"] = f"http://127.0.0.1:{fake_port}"
    if env_extra:
        env.update(env_extra)
    args = ["uv", "run", "gruvax-set-pat", "--profile", DEFAULT_PROFILE_NAME]
    if extra_args:
        args.extend(extra_args)
    # subprocess: test harness drives the CLI under test; args are all literals.
    return subprocess.run(  # noqa: S603
        args,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


async def _read_profile_row(db_pool) -> tuple:  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT app_token_encrypted, app_token_revoked, "
            "       discogsography_user_id::text "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_PROFILE_UUID,),
        )
        row = await cur.fetchone()
        return (bytes(row[0]), bool(row[1]), row[2])


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_stdin_pipe_success(  # type: ignore[no-untyped-def]
    db_pool, reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 1: stdin-pipe happy path → exit 0, row updated."""
    from gruvax._internal.fake_discogsography import create_fake_app

    seed = [_make_release(1)]
    _MUX.app = create_fake_app(seed=seed, user_id=USER_AAA)

    result = _run_cli(stdin=VALID_PAT + "\n", fake_port=fake_port)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    ciphertext, revoked, user_id = await _read_profile_row(db_pool)
    assert ciphertext != reset_profile, "PAT ciphertext was not rewritten"
    assert ciphertext != b"\\x", "Sentinel ciphertext still present"
    assert revoked is False
    assert user_id == USER_AAA


@pytest.mark.asyncio(loop_scope="session")
async def test_no_pat_flag(  # type: ignore[no-untyped-def]
    reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 2: argparse rejects --pat flag (D-07 strict)."""
    result = _run_cli(stdin="", fake_port=fake_port, extra_args=["--pat", "dscg_x" * 10])
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert "--pat" in combined or "unrecognized" in combined.lower(), combined


@pytest.mark.asyncio(loop_scope="session")
async def test_env_var_fallback_ignored(  # type: ignore[no-untyped-def]
    reset_profile, fake_uvicorn, fake_port, db_pool
) -> None:
    """Test 3: GRUVAX_PAT env var is IGNORED (D-07 strict)."""
    result = _run_cli(
        stdin="",  # empty stdin
        fake_port=fake_port,
        env_extra={"GRUVAX_PAT": "dscg_should_be_ignored_aaaaaaaaaaaaaaaaaaaaaaaaaa"},
    )
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert (
        "No PAT" in combined
        or "must start" in combined
        or "stdin" in combined.lower()
        or "PAT must" in combined
    ), combined

    # Row must be unchanged.
    ciphertext, _, _ = await _read_profile_row(db_pool)
    assert ciphertext == reset_profile, "row was modified despite env-var-only PAT"


@pytest.mark.asyncio(loop_scope="session")
async def test_prefix_validation(  # type: ignore[no-untyped-def]
    reset_profile, fake_uvicorn, fake_port, db_pool
) -> None:
    """Test 4: PAT not starting with dscg_ → exit non-zero."""
    result = _run_cli(stdin="no_prefix_pat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n", fake_port=fake_port)
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert "dscg_" in combined or "PAT must" in combined, combined

    ciphertext, _, _ = await _read_profile_row(db_pool)
    assert ciphertext == reset_profile


@pytest.mark.asyncio(loop_scope="session")
async def test_401_leaves_row_unchanged(  # type: ignore[no-untyped-def]
    db_pool, reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 5: 401 PATRejected → row UNCHANGED (Pitfall 2)."""
    fake = FastAPI()

    @fake.get("/api/user/collection")
    async def _always_401(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        raise HTTPException(401, "Token rejected")

    _MUX.app = fake

    result = _run_cli(stdin=VALID_PAT + "\n", fake_port=fake_port)
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert "rejected" in combined.lower() or "401" in combined, combined

    ciphertext, revoked, user_id = await _read_profile_row(db_pool)
    assert ciphertext == reset_profile, "Pitfall 2 regression: row was modified on 401"
    assert revoked is True  # the reset_profile fixture leaves revoked=TRUE
    assert user_id is None


@pytest.mark.asyncio(loop_scope="session")
async def test_d09_strict_rotation_mismatch(  # type: ignore[no-untyped-def]
    db_pool, reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 6: D-09 strict rotation — different user_id → exit non-zero, row unchanged."""
    # Pre-populate discogsography_user_id = USER_AAA on the profile row.
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET discogsography_user_id = %s::uuid WHERE id = %s::uuid",
            (USER_AAA, DEFAULT_PROFILE_UUID),
        )
        await conn.commit()

    from gruvax._internal.fake_discogsography import create_fake_app

    _MUX.app = create_fake_app(seed=[_make_release(1)], user_id=USER_BBB)

    result = _run_cli(stdin=VALID_PAT + "\n", fake_port=fake_port)
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert "PAT belongs to a different discogsography user" in combined, combined
    assert USER_AAA in combined and USER_BBB in combined, combined

    ciphertext, _, user_id = await _read_profile_row(db_pool)
    assert ciphertext == reset_profile, "D-09 rotation regression: row was rewritten"
    assert user_id == USER_AAA  # unchanged


@pytest.mark.asyncio(loop_scope="session")
async def test_d09_strict_rotation_same_user_passes(  # type: ignore[no-untyped-def]
    db_pool, reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 7: D-09 strict rotation — same user_id → exit 0, PAT updated."""
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET discogsography_user_id = %s::uuid WHERE id = %s::uuid",
            (USER_AAA, DEFAULT_PROFILE_UUID),
        )
        await conn.commit()

    from gruvax._internal.fake_discogsography import create_fake_app

    _MUX.app = create_fake_app(seed=[_make_release(1)], user_id=USER_AAA)

    result = _run_cli(stdin=VALID_PAT + "\n", fake_port=fake_port)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    ciphertext, revoked, user_id = await _read_profile_row(db_pool)
    assert ciphertext != reset_profile
    assert revoked is False
    assert user_id == USER_AAA


@pytest.mark.asyncio(loop_scope="session")
async def test_missing_catalog_number_refused(  # type: ignore[no-untyped-def]
    db_pool, reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 8: sample release missing `catalog_number` → exit non-zero, row unchanged."""
    fake = FastAPI()

    @fake.get("/api/user/collection")
    async def _no_catalog(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        if not authorization or not authorization.startswith("Bearer dscg_"):
            raise HTTPException(401)
        # Release with NO catalog_number key at all.
        return {
            "user_id": USER_AAA,
            "releases": [
                {
                    "id": "1",
                    "title": "T",
                    "artist": "A",
                    "label": "L",
                    "year": 2000,
                    "folder_id": 1,
                }
            ],
            "total": 1,
            "offset": 0,
            "limit": limit,
            "has_more": False,
        }

    _MUX.app = fake

    result = _run_cli(stdin=VALID_PAT + "\n", fake_port=fake_port)
    assert result.returncode != 0
    combined = result.stderr + result.stdout
    assert "catalog_number" in combined or "refusing" in combined, combined

    ciphertext, _, _ = await _read_profile_row(db_pool)
    assert ciphertext == reset_profile


@pytest.mark.asyncio(loop_scope="session")
async def test_tty_flow_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 9: TTY interactive flow — when sys.stdin.isatty() is True, getpass fires.

    Runs the CLI's `_read_pat` helper in-process (subprocess can't reliably simulate
    a TTY on macOS without pty). Asserts that the getpass branch is taken.
    """
    import io

    from gruvax.cli.set_pat import _read_pat

    monkeypatch.setattr("sys.stdin", io.StringIO("ignored-via-stdin"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    called = {"getpass": False}

    def _fake_getpass(prompt: str = "") -> str:
        called["getpass"] = True
        return "dscg_from_getpass_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    monkeypatch.setattr("getpass.getpass", _fake_getpass)
    monkeypatch.setattr("gruvax.cli.set_pat.getpass.getpass", _fake_getpass, raising=False)

    pat = _read_pat()
    assert called["getpass"], "_read_pat did not call getpass.getpass when isatty=True"
    assert pat.startswith("dscg_from_getpass")


@pytest.mark.asyncio(loop_scope="session")
async def test_success_message_format(  # type: ignore[no-untyped-def]
    db_pool, reset_profile, fake_uvicorn, fake_port
) -> None:
    """Test 10: success stdout includes "PAT stored for profile" + next-step hint."""
    from gruvax._internal.fake_discogsography import create_fake_app

    _MUX.app = create_fake_app(seed=[_make_release(1)], user_id=USER_AAA)

    result = _run_cli(stdin=VALID_PAT + "\n", fake_port=fake_port)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "PAT stored for profile" in combined, combined
    assert "gruvax-sync --profile" in combined, combined
