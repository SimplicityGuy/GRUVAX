"""Integration tests for PRIV-02 + PRIV-03 privacy guarantees.

CI-locks two privacy invariants that are already de-facto true (per L-04):
  - PRIV-02: raw query text never appears in app.state.log_ring_buffer
  - PRIV-02: uvicorn.access logger is suppressed to WARNING or higher
  - PRIV-03: no gruvax.search_log table exists (stats are aggregate-only)

Tests:
  - test_query_never_in_logs:          After a search request, the probe term is
                                        absent from every ring-buffer entry.
  - test_uvicorn_access_log_suppressed: uvicorn.access level >= WARNING (regression
                                        guard for logging_config.py:188).
  - test_no_search_log_table:           Active schema has no search_log table
                                        (PRIV-03 — aggregate-only stats).

No production code is modified by this plan (test-only, behaviour-locking).
Analog: tests/integration/test_diagnostics.py — LifespanManager fixture shape,
ring-buffer assertion pattern.
"""

from __future__ import annotations

import logging

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


# Unique probe term — chosen to be absent from any legitimate log message so the
# assertion is unambiguous.  If this term ever appears in a ring entry after a
# search request, PRIV-02 is violated.
PROBE_TERM = "probe_priv02_xyz"


# ── Module-scoped client (no admin override — /api/search is public) ──────────


@pytest_asyncio.fixture(scope="module")
async def privacy_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client for privacy assertion tests.

    Mirrors the ``diag_client`` fixture in ``test_diagnostics.py`` but omits
    the ``require_admin`` dependency override because ``/api/search`` is a
    public endpoint — no authentication required.

    Uses ``LifespanManager`` so the app's lifespan startup runs and populates
    ``app.state.log_ring_buffer`` before any test fires.

    Yields ``(ac, manager.app)`` — tests destructure as ``ac, app = privacy_client``.
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        # Yield the original ``app`` (not manager.app) so tests can access
        # ``app.state.log_ring_buffer`` directly.  manager.app is the ASGI
        # callable wrapper; app is the FastAPI instance that owns ``state``.
        yield ac, app


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_query_never_in_logs(privacy_client) -> None:  # type: ignore[no-untyped-def]
    """PRIV-02: raw query text must never appear in the in-process log ring buffer.

    Drives a real search request through the ASGI client (the app is live under
    LifespanManager) and then inspects every entry in ``app.state.log_ring_buffer``.
    The probe term must be absent from every ``msg`` field.

    Fails loudly with the offending entry if the probe term is found, so the
    log statement responsible is immediately identifiable.
    """
    ac, app = privacy_client

    # Drive a real search request containing the probe term in the query string.
    # The endpoint may return 200 (zero results is fine — SRCH-04) or a non-200
    # status (e.g. 400 session_unbound if no bound profile is set in the test
    # environment).  Either way, the ring-buffer assertion is what matters here:
    # the query text must never reach the buffer regardless of the response code.
    await ac.get(f"/api/search?q={PROBE_TERM}&limit=5")

    ring = list(app.state.log_ring_buffer)
    offenders = [entry for entry in ring if PROBE_TERM in entry.get("msg", "")]
    assert not offenders, (
        f"PRIV-02 VIOLATION: query term {PROBE_TERM!r} found in {len(offenders)} "
        f"log ring entry/entries:\n" + "\n".join(f"  {e!r}" for e in offenders)
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_uvicorn_access_log_suppressed(privacy_client) -> None:  # type: ignore[no-untyped-def]
    """PRIV-02 regression guard: uvicorn.access must be suppressed to WARNING or higher.

    ``logging_config.py:188`` pins ``uvicorn.access`` to ``WARNING`` so that
    access-log lines (which include the full request URI with query string) never
    reach stdout or journald.  This test is a pure regression guard: if
    ``configure_logging()`` ever removes or lowers that suppression, this test
    turns red immediately.

    The ``privacy_client`` fixture causes ``LifespanManager`` to run the app
    lifespan, which calls ``configure_logging()`` — so the suppression is active
    before this assertion fires.
    """
    # Consume the fixture to ensure lifespan (and configure_logging) ran.
    _ac, _app = privacy_client

    uvicorn_access_level = logging.getLogger("uvicorn.access").level
    assert uvicorn_access_level >= logging.WARNING, (
        f"uvicorn.access level must be WARNING ({logging.WARNING}) or higher to "
        f"suppress query-string URLs from reaching stdout, but got "
        f"{uvicorn_access_level} ({logging.getLevelName(uvicorn_access_level)}). "
        f"Check logging_config.py — the suppression at line ~188 may have been removed."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_no_search_log_table(privacy_client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """PRIV-03: no per-query search_log table exists in the active gruvax schema.

    Record statistics must remain aggregate-only (``gruvax.record_stats`` stores
    per-release counts, not per-query text).  A ``search_log`` table would
    constitute a per-query log and is explicitly forbidden by PRIV-03.

    Resolves the active schema at runtime via ``SELECT current_schema()`` — the
    schema name is NEVER hardcoded.  The dev DB uses ``gruvax_dev``; production
    uses ``gruvax``; the test must work correctly in both environments.

    Uses ``to_regclass('{schema}.search_log')`` which returns NULL when the
    relation does not exist — no information-schema scan required.
    """
    # Consume the fixture (fixture is module-scoped; this ensures lifespan ran).
    _ac, _app = privacy_client

    async with db_pool.connection() as conn, conn.cursor() as cur:
        # Resolve the active schema at runtime — never hardcode 'gruvax' or 'gruvax_dev'.
        await cur.execute("SELECT current_schema()")
        schema_row = await cur.fetchone()
        assert schema_row is not None, "current_schema() returned no row"
        schema: str = schema_row[0]

        # Assert the search_log relation does not exist in the active schema.
        await cur.execute("SELECT to_regclass(%s)", (f"{schema}.search_log",))
        regclass_row = await cur.fetchone()

    assert regclass_row is not None, "to_regclass() query returned no row"
    assert regclass_row[0] is None, (
        f"PRIV-03 VIOLATION: {schema}.search_log table exists but must not — "
        f"per-query history tables are forbidden; stats must stay aggregate-only. "
        f"to_regclass returned: {regclass_row[0]!r}"
    )
