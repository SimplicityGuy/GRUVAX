"""Development seeding replaces only its target profile, including on repeated runs."""

from pathlib import Path
from typing import Any

import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_synthetic_seed_preserves_other_profiles(db_pool: Any) -> None:
    sql = (Path(__file__).parents[1] / "fixtures/synth_profile_collection.sql").read_text()
    other = "bd5b6052-f037-4d57-936c-d0dc33626c07"
    default = "00000000-0000-0000-0000-000000000001"
    async with db_pool.connection() as conn, conn.transaction(force_rollback=True):
        await conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked) "
            "VALUES (%s, 'Seed isolation sentinel', %s, TRUE)",
            (other, b""),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number) "
            "VALUES (%s, 987654321, 1, 'Other artist', 'Keep this', 'Other label', 'KEEP-1')",
            (other,),
        )
        for _ in range(2):
            await conn.execute(sql, prepare=False)
            cur = await conn.execute(
                "SELECT title, catalog_number FROM gruvax.profile_collection "
                "WHERE profile_id = %s AND release_id = 987654321",
                (other,),
            )
            assert await cur.fetchone() == ("Keep this", "KEEP-1")
            cur = await conn.execute(
                "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s", (default,)
            )
            assert await cur.fetchone() == (3000,)
