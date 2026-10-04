"""Validate a strict snapshot page before either consumer can expose its rows."""

from dataclasses import dataclass
import datetime as dt
import re
from typing import Any
from uuid import UUID

from gruvax.discogsography.errors import SnapshotMismatch


_SOURCE = "completed_collection_sync"
_TOKEN = re.compile(r"[A-Za-z0-9_-]+={0,2}")
_EXPIRY = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")


@dataclass(frozen=True)
class SnapshotPin:
    user_id: str
    token: str
    generation: str
    expires_at: str
    total: int


def _uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _expiry(value: Any) -> bool:
    if not isinstance(value, str) or not _EXPIRY.fullmatch(value):
        return False
    try:
        return dt.datetime.fromisoformat(value) > dt.datetime.now(dt.UTC)
    except ValueError:
        return False


def validate_page(
    page: Any, *, offset: int, limit: int, pin: SnapshotPin | None = None
) -> SnapshotPin:
    """Reject malformed or drifting envelopes without echoing their contents."""
    if not isinstance(page, dict):
        raise SnapshotMismatch("Invalid collection snapshot envelope")
    releases = page.get("releases")
    total = page.get("total")
    token = page.get("snapshot_token")
    if (
        not isinstance(releases, list)
        or any(not isinstance(row, dict) for row in releases)
        or type(total) is not int
        or total < 0
        or type(page.get("offset")) is not int
        or page["offset"] != offset
        or type(page.get("limit")) is not int
        or page["limit"] != limit
        or offset > total
        or len(releases) != min(limit, total - offset)
        or type(page.get("has_more")) is not bool
        or page["has_more"] != (offset + len(releases) < total)
        or not _uuid(page.get("user_id"))
        or not _uuid(page.get("snapshot_generation"))
        or not isinstance(token, str)
        or not _TOKEN.fullmatch(token)
        or not _expiry(page.get("snapshot_expires_at"))
        or page.get("snapshot_source") != _SOURCE
    ):
        raise SnapshotMismatch("Invalid collection snapshot envelope")
    current = SnapshotPin(
        page["user_id"], token, page["snapshot_generation"], page["snapshot_expires_at"], total
    )
    if pin is not None and current != pin:
        raise SnapshotMismatch("Collection snapshot changed during pagination")
    return current
