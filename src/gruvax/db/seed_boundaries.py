"""CLI helper: load fixtures/boundaries.yaml into gruvax.cube_boundaries.

Usage (via justfile ``seed-dev`` recipe):
    python -m gruvax.db.seed_boundaries fixtures/boundaries.yaml

The script is idempotent: it upserts based on the (profile_id, unit_id, row, col)
primary key.  Running it twice is safe.

It also upserts the unit rows (units must exist before cube_boundaries can
reference them, per the FK constraint).

Phase 5 changes:
  - INSERT column list no longer includes last_label / last_catalog (dropped in
    SEG-01 migration 0005). The YAML fixture already omits these keys (05-01).
  - ON CONFLICT SET no longer updates last_label / last_catalog.
  - VALUES placeholder count reduced to match the cut-point-only column set.

Phase 2 (migration 0010): cube_boundaries PK is now (profile_id, unit_id, row, col).
Seed always uses the default profile UUID — dev boundaries belong to the default profile.

gruvax-nrx2: the ON CONFLICT DO UPDATE above makes ``load_boundaries`` silently
revert any admin cut-point edits the default profile already has, whenever it
runs. ``load_boundaries`` itself stays an unconditional upsert — integration
tests call it directly to deliberately restore canonical fixture state after a
mutating test. The boot path (docker-entrypoint.sh → ``main`` →
``seed_boundaries_guarded``) is what needs gating: it skips the seed entirely
if the default profile already has ANY cube_boundaries rows, mirroring the
``GRUVAX_ENV=development`` + ``COUNT==0`` double guard the profile_collection
seed uses in docker-entrypoint.sh.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import sys
from typing import Any

import yaml

from gruvax.db.pool import get_pool_context


logger = logging.getLogger(__name__)

# Dev boundaries always belong to the default profile (migration 0009 default UUID).
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"


async def _is_already_populated(conn: Any) -> bool:
    """Return True if the default profile already has cube_boundaries rows.

    gruvax-nrx2: this is the "already-populated" half of the double guard
    (mirrors the ``GRUVAX_ENV=development`` + ``COUNT==0`` pattern used by the
    profile_collection seed in docker-entrypoint.sh). Without it, the seed's
    ON CONFLICT DO UPDATE silently reverts admin cut-point edits back to the
    synthetic fixture on every container restart.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid",
            (_DEFAULT_PROFILE_UUID,),
        )
        row = await cur.fetchone()
    count: int = row[0] if row is not None else 0
    return count > 0


async def _upsert_units(
    conn: Any,
    units: list[dict[str, Any]],
) -> None:
    """Upsert unit rows into gruvax.units."""
    for unit in units:
        await conn.execute(
            """
            INSERT INTO gruvax.units
                (id, display_name, rows, cols, ordering)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    rows         = EXCLUDED.rows,
                    cols         = EXCLUDED.cols,
                    ordering     = EXCLUDED.ordering,
                    updated_at   = now()
            """,
            (
                unit["unit_id"],
                unit["display_name"],
                unit["rows"],
                unit["cols"],
                unit["ordering"],
            ),
        )


async def _upsert_cubes(
    conn: Any,
    unit_id: int,
    cubes: list[dict[str, Any]],
) -> int:
    """Upsert cube boundary rows; return count of rows inserted/updated.

    Phase 5: Only writes cut-point columns (first_label, first_catalog).
    last_label and last_catalog are dropped from the DB schema in SEG-01
    migration 0005 — they are now derived by SegmentCache, not stored.
    """
    count = 0
    for cube in cubes:
        await conn.execute(
            """
            INSERT INTO gruvax.cube_boundaries
                (profile_id, unit_id, row, col,
                 first_label, first_catalog,
                 is_empty)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (profile_id, unit_id, row, col) DO UPDATE
                SET first_label   = EXCLUDED.first_label,
                    first_catalog = EXCLUDED.first_catalog,
                    is_empty      = EXCLUDED.is_empty,
                    updated_at    = now()
            """,
            (
                _DEFAULT_PROFILE_UUID,
                unit_id,
                cube["row"],
                cube["col"],
                cube.get("first_label"),
                cube.get("first_catalog"),
                cube.get("is_empty", False),
            ),
        )
        count += 1
    return count


async def load_boundaries(yaml_path: Path) -> None:
    """Load boundary YAML fixture into the database.

    Unconditional upsert — callers (e.g. integration tests restoring canonical
    fixture state after a mutating test) rely on this always writing. The
    already-populated guard for the *boot* path lives in
    ``seed_boundaries_guarded``, not here.
    """
    data: dict[str, Any] = yaml.safe_load(yaml_path.read_text())
    units: list[dict[str, Any]] = data["units"]

    async with (
        get_pool_context(min_size=1, max_size=2) as pool,
        pool.connection() as conn,
        conn.transaction(),
    ):
        await _upsert_units(conn, units)

        total = 0
        for unit in units:
            n = await _upsert_cubes(conn, unit["unit_id"], unit["cubes"])
            total += n


async def seed_boundaries_guarded(yaml_path: Path) -> None:
    """Boot-time entry point: seed only if the default profile is empty.

    gruvax-nrx2: this is the already-populated half of the seed's double guard
    (the other half, ``GRUVAX_ENV=development``, lives in
    docker-entrypoint.sh). Without it, a container restart's ON CONFLICT DO
    UPDATE in ``load_boundaries`` would silently overwrite admin cut-point
    edits on the default profile with the synthetic fixture, every time.
    """
    async with get_pool_context(min_size=1, max_size=2) as pool, pool.connection() as conn:
        if await _is_already_populated(conn):
            logger.info(
                "cube_boundaries already populated for the default profile; "
                "skipping boundary seed (gruvax-nrx2 guard)."
            )
            return

    await load_boundaries(yaml_path)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    if not yaml_path.exists():
        sys.exit(1)

    asyncio.run(seed_boundaries_guarded(yaml_path))


if __name__ == "__main__":
    main()
