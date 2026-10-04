"""Real request tasks must drain on the same loop as their owning lifespan."""

import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio

from gruvax.api import locate
from tests.integration.test_locate import client as client


@pytest_asyncio.fixture(scope="module", loop_scope="session", autouse=True)
async def held_selection_task():  # type: ignore[no-untyped-def]
    """Keep an actual locate task pending until the client lifespan cancels it."""
    patch = pytest.MonkeyPatch()
    state = SimpleNamespace(started=asyncio.Event(), cancelled=asyncio.Event(), tasks=[])

    async def held_counter(pool, release_id):  # type: ignore[no-untyped-def]
        task = asyncio.current_task()
        assert task is not None
        state.tasks.append(task)
        state.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            state.cancelled.set()

    patch.setattr(locate, "increment_selection_count", held_counter)
    try:
        yield state
        # Module autouse ownership places this finalizer after the imported
        # client fixture, so this witnesses actual lifespan cancellation/drain.
        await asyncio.wait_for(state.cancelled.wait(), 1)
        assert len(state.tasks) == 1
        assert state.tasks[0].done() and state.tasks[0].cancelled()
    finally:
        patch.undo()


@pytest.mark.asyncio(loop_scope="session")
async def test_locate_request_task_drains_during_client_lifespan(held_selection_task, client):  # type: ignore[no-untyped-def]
    response = await client.get(
        "/api/locate",
        params={"release_id": 1, "profile_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["release_id"] == 1
    await asyncio.wait_for(held_selection_task.started.wait(), 1)
    assert len(held_selection_task.tasks) == 1
    assert held_selection_task.tasks[0].get_loop() is asyncio.get_running_loop()
    assert not held_selection_task.tasks[0].done()
