"""In-memory snapshot of gruvax.profile_collection records grouped by label.

The snapshot is loaded once at FastAPI lifespan startup from
``gruvax.profile_collection`` (the v2 local cache that replaced the v1
cross-schema view dropped in migration 0009) and provides a CPU-only,
zero-DB lookup surface for the §4.1 index-based estimator.

Plan 01-06 rewire: the SELECT now binds ``WHERE profile_id = %s::uuid`` so the
snapshot is scoped to a single profile (P1 uses the default profile UUID; P2
will flip the call site to a per-session value). The casefold-by-label grouping
logic (Pitfall C) is unchanged — only the source query changes.

Phase 4 hook: The ``invalidate()`` method is the seam where the SSE event bus will
call in to flush the snapshot before reloading on a ``boundary_changed`` event.

Pitfall C (D-13): label keys are stored and looked up via ``.casefold()`` — labels
are NOT catalog numbers and must NEVER be compared via ``normalize_catalog()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from gruvax.db.queries import DEFAULT_PROFILE_UUID


if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True)
class RecordRow:
    """Single record row fetched from ``gruvax.profile_collection``.

    Contains only the fields needed for the §4.1 index-based estimator.
    Frozen so it can be used safely in sorted lists and sets.
    """

    release_id: int
    label: str
    catalog_number: str


class CollectionSnapshot:
    """In-memory snapshot of all collection records grouped by label (casefolded).

    Loaded at startup in FastAPI lifespan; Phase 4 wires the ``boundary_changed``
    SSE event to call ``invalidate()`` then ``load(pool)`` to refresh.

    Usage::

        snapshot = CollectionSnapshot()
        await snapshot.load(pool)                           # called once in lifespan
        records = snapshot.get_label_records("Blue Note")   # O(1) dict lookup
        snapshot.invalidate()                               # Phase 4 SSE seam
    """

    def __init__(self) -> None:
        # Keyed by label.casefold() — Pitfall C: never normalize_catalog() on labels.
        self._by_label: dict[str, list[RecordRow]] = {}

    async def load(
        self,
        pool: AsyncConnectionPool[AsyncConnection[object]],
        profile_id: str = DEFAULT_PROFILE_UUID,
    ) -> None:
        """Load all records from ``gruvax.profile_collection`` and group by label.

        Called once during FastAPI lifespan startup. Reads from the local cache
        populated by ``sync_profile`` against the discogsography v2 HTTP API
        (DEP-02 — the contact surface with discogsography is the API, not a
        cross-schema view).

        Plan 01-06: source rewired from the v1 cross-schema view (dropped in
        migration 0009) to ``gruvax.profile_collection WHERE profile_id =
        %s::uuid``. The label-casefold grouping (Pitfall C, T-01-pitfall-c-loss
        mitigation) is preserved verbatim — only the FROM clause changed.

        Args:
            pool:       An open ``psycopg_pool.AsyncConnectionPool`` instance.
            profile_id: UUID of the profile to load (P1: default; P2: per-session).
        """
        sql = (
            "SELECT release_id, label, catalog_number FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid"
        )
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (profile_id,))
            rows_raw = await cur.fetchall()

        by_label: dict[str, list[RecordRow]] = {}
        for row in rows_raw:
            release_id, label, catalog_number = cast("tuple[int, str | None, str | None]", row)
            # Pitfall C: casefold label for grouping — never normalize_catalog() on labels
            key = (label or "").casefold()
            record = RecordRow(
                release_id=int(release_id),
                label=label or "",
                catalog_number=catalog_number or "",
            )
            if key not in by_label:
                by_label[key] = []
            by_label[key].append(record)

        self._by_label = by_label

    def _load_snapshot(self, by_label: dict[str, list[RecordRow]]) -> None:
        """Internal seam for testing: bypass DB and load groups directly.

        Tests use this to populate the snapshot from a synthetic fixture without
        needing a live DB connection. The caller is responsible for casefolding
        the dict keys before passing in (or using the factory helpers in
        ``fixtures/synth_collection.py``).
        """
        self._by_label = dict(by_label)

    def get_label_records(self, label: str) -> list[RecordRow]:
        """Return all records for the given label (case-insensitive).

        Args:
            label: Label string in any case (e.g. ``"Blue Note"``, ``"BLUE NOTE"``).

        Returns:
            List of RecordRow for that label, or ``[]`` if label not in snapshot.
            Order is insertion order (as loaded from DB); callers that need a
            sorted view (§4.1) must sort by ``parse_key(r.catalog_number)``.
        """
        return self._by_label.get((label or "").casefold(), [])

    def invalidate(self) -> None:
        """Phase 4 SSE seam: empty the snapshot before a reload.

        Called by the SSE event handler when a ``boundary_changed`` event is
        received (Phase 4). The caller is responsible for immediately calling
        ``load(pool)`` after invalidating to refresh the snapshot.

        Example (Phase 4 usage)::

            snapshot.invalidate()
            await snapshot.load(pool)  # repopulate from DB
        """
        self._by_label = {}
