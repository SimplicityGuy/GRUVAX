"""Sync routine fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def add_page_iterator(client: Any) -> Any:
    """Adapt controlled single-page mocks without changing their await barriers."""

    async def iter_pages() -> AsyncIterator[dict[str, Any]]:
        yield await client.first_page()

    client.iter_pages = iter_pages
    return client
