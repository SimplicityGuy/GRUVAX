"""Global admin-session policy; profile selection does not change PIN authority."""

from typing import Any

from gruvax.auth.sessions import HARD_CAP_SECONDS


def _positive_seconds(value: Any, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def admin_session_policy(cache: dict[str, Any], idle_default: int) -> tuple[int, int]:
    """Use default-profile global settings, falling back for absent/legacy-invalid rows."""
    return (
        _positive_seconds(cache.get("session.idle_ttl_seconds"), idle_default),
        _positive_seconds(cache.get("session.hard_cap_seconds"), HARD_CAP_SECONDS),
    )
