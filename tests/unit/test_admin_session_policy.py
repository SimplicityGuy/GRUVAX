"""Global session-policy fallbacks remain compatible with absent/invalid legacy rows."""

import pytest

from gruvax.auth.session_policy import admin_session_policy


@pytest.mark.parametrize(
    "cache",
    [
        {},
        {"session.idle_ttl_seconds": 0, "session.hard_cap_seconds": -1},
        {"session.idle_ttl_seconds": True, "session.hard_cap_seconds": "bad"},
    ],
)
def test_global_policy_falls_back(cache: dict) -> None:
    assert admin_session_policy(cache, 47) == (47, 1800)
