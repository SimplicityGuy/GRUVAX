"""Admin label/catalog autocomplete endpoints.

Backs the two-step label → catalog# picker in the admin cube editor
(RecordPickerSheet) and the client-side phantom near-miss / USE-ANYWAY path.
The query helpers (``get_distinct_labels`` / ``get_catalogs_for_label``) already
existed in ``gruvax.db.queries``; these are the thin read-only HTTP routes that
expose them. Source is exclusively ``gruvax.profile_collection`` (Pitfall 5).

Endpoints:
  - ``GET /admin/labels``:
      Returns all distinct labels (sorted) for the label autocomplete.
  - ``GET /admin/labels/{label}/catalogs``:
      Returns release_id + catalog_number for a label (catalog autocomplete,
      and the source list the client uses to detect phantom catalog values).

Security:
  - Both handlers depend on require_admin (session cookie, ASVS V4 — T-03-13).
  - Read-only (GET): no CSRF, no INSERT/UPDATE/DELETE.
  - All SQL lives in db.queries and uses %s placeholders (T-03-16).
  - Both handlers are scoped to the caller's resolved profile (gruvax-7ad) — see
    below.

Profile scoping (gruvax-7ad):
  Both queries used to run with the ``profile_id`` default, i.e. the DEFAULT
  profile, regardless of which profile the admin was bound to. That is a
  cross-profile collection disclosure (an admin bound to B was shown A's label
  list) AND it put the picker at odds with the validator: the write-side phantom
  check IS profile-scoped (cubes.py -> cube_exact_match(..., profile_id)), so
  selecting one of A's labels while bound to B produced 400 phantom_boundary. The
  picker offered exactly what the validator rejected, by construction.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path

from gruvax.api.deps import get_pool, get_read_profile_id, require_admin
from gruvax.db.queries import get_catalogs_for_label, get_distinct_labels


router = APIRouter(tags=["admin-labels"])


@router.get("/labels")
async def list_labels(
    pool: Any = Depends(get_pool),
    profile_id: str = Depends(get_read_profile_id),
    _admin: dict[str, Any] = Depends(require_admin),
) -> list[dict[str, str]]:
    """Return the bound profile's distinct labels for the label autocomplete.

    Response shape matches the frontend ``LabelOption[]``: ``[{"label": str}]``.

    gruvax-7ad: scoped to the resolved profile — the same resolution the write
    path uses, so the picker can only offer values the phantom check will accept.
    """
    labels = await get_distinct_labels(pool, profile_id=profile_id)
    return [{"label": label} for label in labels]


@router.get("/labels/{label}/catalogs")
async def list_catalogs_for_label(
    label: str = Path(min_length=1),
    pool: Any = Depends(get_pool),
    profile_id: str = Depends(get_read_profile_id),
    _admin: dict[str, Any] = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Return the bound profile's release_id + catalog_number for a label.

    The label path segment is URL-decoded by Starlette. Response shape matches
    the frontend ``CatalogOption[]``: ``[{"release_id": int, "catalog_number": str}]``.

    gruvax-7ad: scoped to the resolved profile (see module docstring).
    """
    return await get_catalogs_for_label(pool, label, profile_id=profile_id)
