"""Malformed CSV headers fail as parse errors before any import mutation."""

import pytest

from tests.integration.test_import_integrity import import_api as import_api, import_state


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("dry_run", [False, True])
async def test_unterminated_csv_header_is_atomic_422(import_api, db_pool, dry_run):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    before = await import_state(db_pool, app, profiles)
    response = await client.post(
        f"/api/admin/import/boundaries?dry_run={str(dry_run).lower()}",
        content='"unit_id,row,col,first_label,first_catalog,is_empty',
        headers={**headers, "Content-Type": "text/csv"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "parse_error"
    assert "CSV line 1" in response.json()["detail"]["message"]
    assert await import_state(db_pool, app, profiles) == before
    assert all(queue.empty() for queue in queues)
