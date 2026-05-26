"""CLI helper: load fixtures/boundaries.yaml into gruvax.cube_boundaries.

Usage (via justfile ``seed-dev`` recipe):
    python -m gruvax.db.seed_boundaries fixtures/boundaries.yaml

The script is idempotent: it upserts based on the (unit_id, row, col) primary
key.  Running it twice is safe.

It also upserts the unit rows (units must exist before cube_boundaries can
reference them, per the FK constraint).

Phase 5 changes:
  - INSERT column list no longer includes last_label / last_catalog (dropped in
    SEG-01 migration 0005). The YAML fixture already omits these keys (05-01).
  - ON CONFLICT SET no longer updates last_label / last_catalog.
  - VALUES placeholder count reduced to match the cut-point-only column set.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any

import yaml

from gruvax.db.pool import get_pool_context


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
                (unit_id, row, col,
                 first_label, first_catalog,
                 is_empty)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id, row, col) DO UPDATE
                SET first_label   = EXCLUDED.first_label,
                    first_catalog = EXCLUDED.first_catalog,
                    is_empty      = EXCLUDED.is_empty,
                    updated_at    = now()
            """,
            (
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
    """Load boundary YAML fixture into the database."""
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



def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    if not yaml_path.exists():
        sys.exit(1)

    asyncio.run(load_boundaries(yaml_path))


if __name__ == "__main__":
    main()
