"""Admin label/catalog autocomplete endpoints.

Backs the two-step label → catalog# picker in the admin cube editor
(RecordPickerSheet) and the client-side phantom near-miss / USE-ANYWAY path.
The query helpers (``get_distinct_labels`` / ``get_catalogs_for_label``) already
existed in ``gruvax.db.queries``; these are the thin read-only HTTP routes that
expose them. Source is exclusively ``gruvax.v_collection`` (Pitfall 5).

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
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path

from gruvax.api.deps import get_pool, require_admin
from gruvax.db.queries import get_catalogs_for_label, get_distinct_labels


router = APIRouter(tags=["admin-labels"])


@router.get("/labels")
async def list_labels(
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> list[dict[str, str]]:
    """Return all distinct labels for the label autocomplete.

    Response shape matches the frontend ``LabelOption[]``: ``[{"label": str}]``.
    """
    labels = await get_distinct_labels(pool)
    return [{"label": label} for label in labels]


@router.get("/labels/{label}/catalogs")
async def list_catalogs_for_label(
    label: str = Path(min_length=1),
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Return release_id + catalog_number for a label (catalog autocomplete).

    The label path segment is URL-decoded by Starlette. Response shape matches
    the frontend ``CatalogOption[]``: ``[{"release_id": int, "catalog_number": str}]``.
    """
    return await get_catalogs_for_label(pool, label)
