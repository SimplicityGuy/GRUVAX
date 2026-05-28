"""In-memory cache of cube_boundaries rows for the GRUVAX position estimator.

The cache is loaded once at FastAPI lifespan startup from ``gruvax.cube_boundaries``
(D-03) and provides a fast, CPU-only lookup surface for the estimator — no DB calls
during estimation (INTERPOLATION §1 latency budget).

Phase 4 hook: The ``invalidate()`` method is the seam where the SSE event bus will
call in to flush the cache before reloading on a ``boundary_changed`` event.

Phase 5 changes:
- ``BoundaryRow`` drops ``last_label`` and ``last_catalog`` (now derived by SegmentCache
  from the next cube's cut point). Only ``first_*`` columns are stored (D-05 / SEG-01).
- ``BoundaryCache`` loads ``gruvax.segment_overrides`` into ``_overrides`` dict in the
  second SELECT of ``load()``. Provides a ``_load_overrides`` test seam and an
  ``overrides`` read accessor.
- ``invalidate()`` clears both ``_rows`` and ``_overrides``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast


if TYPE_CHECKING:
    from collections.abc import Sequence

    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True)
class BoundaryRow:
    """Single row from ``gruvax.cube_boundaries`` (Phase 5 cut-point shape).

    Phase 5: ``last_label`` and ``last_catalog`` are DROPPED. They are now derived
    by SegmentCache from the next cube's cut point + CollectionSnapshot row counts.
    Only the cut-point columns (first_*) are stored (D-05 / SEG-01).

    Mirrors the DB column names exactly so the cache can be loaded by index
    from a ``psycopg`` cursor result without name mapping.
    """

    unit_id: int
    row: int
    col: int
    first_label: str | None  # the cut point — first record in this bin
    first_catalog: str | None  # the cut point — first catalog# in this bin
    is_empty: bool
    # last_label and last_catalog are DERIVED from SegmentCache — not stored here


class BoundaryCache:
    """In-memory cache of all cube boundary rows.

    Loaded at startup in FastAPI lifespan; Phase 4 wires the ``boundary_changed``
    SSE event to call ``invalidate()`` then ``load(pool)`` to refresh.

    Phase 5 addition: Also loads ``gruvax.segment_overrides`` into ``_overrides``
    (keyed by ``(unit_id, row, col, label) -> fraction``).

    Usage::

        cache = BoundaryCache()
        await cache.load(pool)          # called once in lifespan
        rows = cache.get_boundaries()   # O(1) for estimator
        ovr  = cache.overrides          # dict for SegmentCache.derive()
        cache.invalidate()              # Phase 4 SSE seam (clears rows + overrides)
    """

    def __init__(self) -> None:
        self._rows: list[BoundaryRow] = []
        self._overrides: dict[tuple[int, int, int, str], float] = {}

    async def load(
        self,
        pool: AsyncConnectionPool[AsyncConnection[object]],
        profile_id: str = "00000000-0000-0000-0000-000000000001",
    ) -> None:
        """Load all rows from ``gruvax.cube_boundaries`` and ``gruvax.segment_overrides``.

        Called once during FastAPI lifespan startup. Uses the async psycopg pool
        to fetch all boundary rows ordered by (unit_id, row, col), then loads
        all segment overrides into ``_overrides``.

        Args:
            pool: An open ``psycopg_pool.AsyncConnectionPool`` instance.
            profile_id: UUID string of the profile to scope the load to
                (P1: default UUID; P2: per-session profile_id from registry).
        """
        # First SELECT: cut-point columns only (last_* dropped in Phase 5 migration)
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT unit_id, row, col, first_label, first_catalog, is_empty"
                " FROM gruvax.cube_boundaries"
                " WHERE profile_id = %s::uuid"
                " ORDER BY unit_id, row, col",
                (profile_id,),
            )
            rows_raw = await cur.fetchall()
            self._rows = [BoundaryRow(*row) for row in rows_raw]  # type: ignore[misc]

        # Second SELECT: segment overrides (Phase 5 addition — SEG-04)
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT unit_id, row, col, label, fraction"
                " FROM gruvax.segment_overrides"
                " WHERE profile_id = %s::uuid",
                (profile_id,),
            )
            overrides_raw = await cur.fetchall()
            # Cast each row to a typed tuple so mypy --strict can verify index access.
            # psycopg fetchall() returns list[Any] in practice; the explicit cast is
            # safe because the SELECT column order matches the tuple shape exactly:
            # (unit_id:int, row:int, col:int, label:str, fraction:float).
            typed_rows = cast(
                "list[tuple[int, int, int, str, float]]",
                overrides_raw,
            )
            self._overrides = {(r[0], r[1], r[2], r[3]): r[4] for r in typed_rows}

    def _load_rows(self, rows: list[BoundaryRow]) -> None:
        """Internal seam for testing: bypass DB and load rows directly.

        Tests use this to populate the cache from the YAML fixture without
        needing a live DB connection.
        """
        self._rows = list(rows)

    def _load_overrides(self, overrides: dict[tuple[int, int, int, str], float]) -> None:
        """Internal seam for testing: bypass DB and load overrides directly.

        Mirrors ``_load_rows`` for the overrides dict. Used by test factories
        (e.g., make_multi_label_bin) to inject known override values without
        a live DB connection.
        """
        self._overrides = dict(overrides)

    @property
    def overrides(self) -> dict[tuple[int, int, int, str], float]:
        """Read accessor for segment overrides dict.

        Returns a reference to the current overrides dict (not a copy).
        Keyed by ``(unit_id, row, col, label) -> fraction``.
        """
        return self._overrides

    def get_boundaries(self) -> Sequence[BoundaryRow]:
        """Return the current set of boundary rows (immutable view)."""
        return self._rows

    def invalidate(self) -> None:
        """Phase 4 SSE seam: empty the cache before a reload.

        Called by the SSE event handler when a ``boundary_changed`` event is
        received (Phase 4). Also clears ``_overrides`` so both boundary rows
        and segment overrides are refreshed together on the next ``load(pool)``
        call (Phase 5 addition).

        The caller is responsible for immediately calling ``load(pool)`` after
        invalidating to refresh the cache.

        Example (Phase 4 usage)::

            cache.invalidate()
            await cache.load(pool)  # repopulate from DB
        """
        self._rows = []
        self._overrides = {}
