"""CLI helper: load fixtures/boundaries.yaml into gruvax.cube_boundaries.

Usage (via justfile ``seed-dev`` recipe):
    python -m gruvax.db.seed_boundaries fixtures/boundaries.yaml

The script is idempotent: it upserts based on the (unit_id, row, col) primary
key.  Running it twice is safe.

It also upserts the unit rows (units must exist before cube_boundaries can
reference them, per the FK constraint).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
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
    """Upsert cube boundary rows; return count of rows inserted/updated."""
    count = 0
    for cube in cubes:
        await conn.execute(
            """
            INSERT INTO gruvax.cube_boundaries
                (unit_id, row, col,
                 first_label, first_catalog, last_label, last_catalog,
                 is_empty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id, row, col) DO UPDATE
                SET first_label   = EXCLUDED.first_label,
                    first_catalog = EXCLUDED.first_catalog,
                    last_label    = EXCLUDED.last_label,
                    last_catalog  = EXCLUDED.last_catalog,
                    is_empty      = EXCLUDED.is_empty,
                    updated_at    = now()
            """,
            (
                unit_id,
                cube["row"],
                cube["col"],
                cube.get("first_label"),
                cube.get("first_catalog"),
                cube.get("last_label"),
                cube.get("last_catalog"),
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

    print(f"seed_boundaries: loaded {total} cube boundary rows from {yaml_path}")


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m gruvax.db.seed_boundaries <path/to/boundaries.yaml>",
            file=sys.stderr,
        )
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    if not yaml_path.exists():
        print(f"Error: {yaml_path} not found", file=sys.stderr)
        sys.exit(1)

    asyncio.run(load_boundaries(yaml_path))


if __name__ == "__main__":
    main()
