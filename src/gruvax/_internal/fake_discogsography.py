"""Fake discogsography FastAPI fixture — single source of truth (D-15, D-16).

This is the canonical module imported by BOTH:
  - test code via ``from gruvax._internal.fake_discogsography import create_fake_app``
    (and via the thin re-export at ``tests/fixtures/fake_discogsography.py``).
  - the Compose ``fake-discogsography`` sibling service at
    ``services/fake-discogsography/server.py`` (Plan 05).

Implements the discogsography v2 integration contract v1 (see
``/Users/Robert/Code/public/discogsography/docs/specs/v2-gruvax-integration.md``).

Routes mounted by ``create_fake_app``:
  - GET /api/user/collection — paged (limit ≤ 200), token routing (Bearer
    dscg_*), magic-token error injection (``dscg_force_429`` and
    ``dscg_force_500``).

Envelope shape returned on 200:
  ``{user_id, releases, total, offset, limit, has_more}`` where
  ``has_more = offset + len(page) < len(seed)``.

Keeping this in ONE module satisfies D-15's "one fake-discogsography FastAPI
fixture" mandate — no ``just sync-fake`` drift guard is needed because both
consumers import from this file directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel


__all__ = ["create_fake_app"]


class _Release(BaseModel):
    """Per-item shape from the discogsography v1 contract (D-04).

    Defined for documentation + optional validation. The route itself
    returns the raw seed dicts so test authors can introduce contract
    drift without re-shaping the seed through this model.
    """

    id: str
    title: str
    year: int | None = None
    catalog_number: str | None = None
    artist: str | None = None
    label: str | None = None
    genres: list[str] = []
    styles: list[str] = []
    rating: int = 0
    date_added: str | None = None
    folder_id: int | None = None


def create_fake_app(
    *,
    seed: list[dict[str, Any]],
    user_id: str = "99999999-9999-9999-9999-999999999999",
) -> FastAPI:
    """Build a fresh FastAPI app serving the contract endpoints from ``seed``.

    Args:
        seed: a list of release dicts (shape per ``_Release``). Each entry
            becomes a row in the in-memory collection. May be empty.
        user_id: the UUID string returned in every response envelope's
            ``user_id`` field. Tests for the strict-rotation invariant
            (D-09) configure this to a known value.

    Returns:
        A FastAPI instance with ``GET /api/user/collection`` mounted.

    Magic tokens (test-only — Plan 02 + Plan 03 retry tests rely on these):
      - ``Bearer dscg_force_429`` → 429 with ``Retry-After: 1`` header
      - ``Bearer dscg_force_500`` → 500 (no retry-after; tests exp backoff)
    """
    app = FastAPI(title="fake-discogsography", version="0.1.0")
    # Stash seed + user_id on app.state for parity with the Wave-0 SHELL —
    # downstream consumers (sibling services) may want to mutate the seed
    # at runtime; keeping it on app.state preserves that future-proofing.
    app.state._seed = seed
    app.state._user_id = user_id

    @app.get("/api/user/collection")
    async def get_collection(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        # Token routing — contract §3.2: any missing/wrong-prefix token is 401.
        # The contract returns identical body shape for "missing", "invalid",
        # "revoked", "wrong-prefix" (no oracle on the failure mode).
        if not authorization or not authorization.startswith("Bearer dscg_"):
            raise HTTPException(status_code=401, detail="Missing or invalid token")

        # Magic-token error injection (test-only).
        if authorization == "Bearer dscg_force_429":
            raise HTTPException(
                status_code=429,
                detail="Rate limited (test injection)",
                headers={"Retry-After": "1"},
            )
        if authorization == "Bearer dscg_force_500":
            raise HTTPException(status_code=500, detail="Server error (test injection)")

        page = seed[offset : offset + limit]
        return {
            "user_id": user_id,
            "releases": page,
            "total": len(seed),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(page) < len(seed),
        }

    return app
