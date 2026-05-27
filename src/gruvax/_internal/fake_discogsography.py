"""Fake discogsography FastAPI fixture — single source of truth (D-15, D-16).

This is the canonical module imported by BOTH:
  - test code via ``from gruvax._internal.fake_discogsography import create_fake_app``
    (and via the thin re-export at ``tests/fixtures/fake_discogsography.py``).
  - the Compose ``fake-discogsography`` sibling service at
    ``services/fake-discogsography/server.py``.

Wave 0 ships a SHELL with no routes mounted. Plan 02 Task 2 fleshes out:
  - GET /api/user/collection (paged, token routing, magic-token error injection)
  - the _Release pydantic model
  - the contract envelope shape

Keeping this in ONE module satisfies D-15's "one fake-discogsography FastAPI fixture"
mandate — no ``just sync-fake`` drift guard is needed because both consumers import
from this file directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


__all__ = ["create_fake_app"]


def create_fake_app(
    *,
    seed: list[dict[str, Any]],
    user_id: str = "99999999-9999-9999-9999-999999999999",
) -> FastAPI:
    """SHELL — Plan 02 Task 2 adds the contract routes.

    Returns a FastAPI app with no application routes. The ``seed`` and ``user_id``
    parameters are captured into app.state so Plan 02's route bodies can access
    them when added.
    """
    app = FastAPI(title="fake-discogsography (shell)", version="0.0.0-shell")
    # Plan 02 Task 2 attaches state + routes here.
    app.state._seed = seed
    app.state._user_id = user_id
    return app
