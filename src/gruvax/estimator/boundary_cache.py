"""In-memory cache of cube_boundaries rows for the GRUVAX position estimator.

The cache is loaded once at FastAPI lifespan startup from ``gruvax.cube_boundaries``
(D-03) and provides a fast, CPU-only lookup surface for the estimator — no DB calls
during estimation (INTERPOLATION §1 latency budget).

Phase 4 hook: The ``invalidate()`` method is the seam where the SSE event bus will
call in to flush the cache before reloading on a ``boundary_changed`` event.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True)
class BoundaryRow:
    """Single row from ``gruvax.cube_boundaries``.

    Mirrors the DB column names exactly so the cache can be loaded by index
    from a ``psycopg`` cursor result without name mapping.
    """

    unit_id: int
    row: int
    col: int
    first_label: str | None
    first_catalog: str | None
    last_label: str | None
    last_catalog: str | None
    is_empty: bool


class BoundaryCache:
    """In-memory cache of all cube boundary rows.

    Loaded at startup in FastAPI lifespan; Phase 4 wires the ``boundary_changed``
    SSE event to call ``invalidate()`` then ``load(pool)`` to refresh.

    Usage::

        cache = BoundaryCache()
        await cache.load(pool)          # called once in lifespan
        rows = cache.get_boundaries()   # O(1) for estimator
        cache.invalidate()              # Phase 4 SSE seam
    """

    def __init__(self) -> None:
        self._rows: list[BoundaryRow] = []

    async def load(self, pool: AsyncConnectionPool[AsyncConnection[object]]) -> None:
        """Load all rows from ``gruvax.cube_boundaries``.

        Called once during FastAPI lifespan startup. Uses the async psycopg pool
        to fetch all boundary rows ordered by (unit_id, row, col).

        Args:
            pool: An open ``psycopg_pool.AsyncConnectionPool`` instance.
        """
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT unit_id, row, col, first_label, first_catalog,"
                " last_label, last_catalog, is_empty"
                " FROM gruvax.cube_boundaries ORDER BY unit_id, row, col"
            )
            rows_raw = await cur.fetchall()
            self._rows = [BoundaryRow(*row) for row in rows_raw]  # type: ignore[misc]

    def _load_rows(self, rows: list[BoundaryRow]) -> None:
        """Internal seam for testing: bypass DB and load rows directly.

        Tests use this to populate the cache from the YAML fixture without
        needing a live DB connection.
        """
        self._rows = list(rows)

    def get_boundaries(self) -> Sequence[BoundaryRow]:
        """Return the current set of boundary rows (immutable view)."""
        return self._rows

    def invalidate(self) -> None:
        """Phase 4 SSE seam: empty the cache before a reload.

        Called by the SSE event handler when a ``boundary_changed`` event is
        received (Phase 4). The caller is responsible for immediately calling
        ``load(pool)`` after invalidating to refresh the cache.

        Example (Phase 4 usage)::

            cache.invalidate()
            await cache.load(pool)  # repopulate from DB
        """
        self._rows = []
