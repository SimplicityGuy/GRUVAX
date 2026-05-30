"""GET /api/locate — position estimate for a collection release (POS-02).

Query parameters:
  - ``release_id``:  Integer Discogs release ID (T-01-09: typed param, 422 on non-int).
  - ``profile_id``:  Profile UUID; optional — defaults to the bound profile from the
                     gruvax_browse_binding cookie (D2-04, B-02).  When supplied,
                     validated against the cookie (403 profile_mismatch on mismatch).

Response (HTTP 200): Locked LocateResult JSON contract (D-10/D-11/D-12):
  ``{release_id, primary_cube, label_span, sub_cube_interval, confidence,
     generated_at, estimator_version}``

The ``sub_cube_interval`` field (Phase 5) shape (UI-SPEC §TypeScript Type Extension):
  ``{start, end, crosses_boundary, next_cube}``
  NOTE: the ``cube`` field of the SubInterval dataclass is NOT emitted — the frontend
  derives the cube from context (primary_cube / label_span).

Error semantics:
  - HTTP 404: release_id not in gruvax.profile_collection (for the active profile)
    → ``{type: "release_not_in_collection", release_id: <id>}``
  - HTTP 200 with confidence 0.0 / primary_cube null / label_span []:
    release IS in collection but no cube boundary covers its label (D-12).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette import status

from gruvax.api.deps import (
    get_pool,
    resolve_profile_from_request,
)
from gruvax.db.queries import get_release_for_locate, increment_selection_count
from gruvax.estimator.algorithm import locate
from gruvax.middleware.timing import record_slow_query


if TYPE_CHECKING:
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.contract import CubeRef, SubInterval
    from gruvax.estimator.segment_cache import SegmentCache


logger = logging.getLogger(__name__)

router = APIRouter(tags=["locate"])


def _cube_ref_to_dict(cube: CubeRef) -> dict[str, int]:
    """Serialize a CubeRef dataclass to a JSON-safe dict."""
    return {"unit_id": cube.unit_id, "row": cube.row, "col": cube.col}


def _sub_interval_to_dict(si: SubInterval) -> dict[str, Any]:
    """Serialize a SubInterval dataclass to a JSON-safe dict.

    Emits ``{start, end, crosses_boundary, next_cube}`` — the ``cube`` field is
    intentionally omitted (UI-SPEC §TypeScript Type Extension; the frontend derives
    the cube from primary_cube / label_span context).
    """
    return {
        "start": si.start,
        "end": si.end,
        "crosses_boundary": si.crosses_boundary,
        "next_cube": _cube_ref_to_dict(si.next_cube) if si.next_cube else None,
    }


@router.get("/locate")
async def locate_endpoint(
    request: Request,
    release_id: int,
    profile_id: str | None = Query(default=None),
    pool: Any = Depends(get_pool),
) -> JSONResponse:
    """Return the locked LocateResult for a release scoped to a profile.

    The profile_id query parameter is optional; defaults to the bound profile from the
    gruvax_browse_binding cookie (D2-04, B-02).  When omitted, the authoritative profile
    is resolved via resolve_profile_from_request (cookie/device authoritative): 400 if
    unbound, 403 if device_unknown/device_revoked.  When supplied, the resolved profile
    must match the supplied value (403 profile_mismatch on mismatch).

    Uses the profile's per-profile segment_cache and snapshot for position estimation
    (CPU-only, POS-03).

    Args:
        release_id: Discogs release ID (integer; 422 on non-integer T-01-09).
        profile_id: Profile UUID (optional; defaults to cookie-bound profile, D2-04/B-02).

    Returns:
        HTTP 200 with the LocateResult JSON on success (including no-boundary case).
        HTTP 404 with ``{type: "release_not_in_collection"}`` if not in collection.

    The JSON shape (Phase 5 extension of the contract):
      ``{release_id, primary_cube, label_span, sub_cube_interval,
         confidence, generated_at, estimator_version}``
    where ``sub_cube_interval`` is ``{start, end, crosses_boundary, next_cube}``
    when the estimator produces a sub-cube estimate, or ``null`` for the cube-only fallback.
    """
    # OBS-05: measure request-total from handler entry (locate is CPU-only, POS-03).
    t0 = time.perf_counter()

    # B-02: resolve the authoritative profile from the request (cookie/device wins).
    # resolve_profile_from_request raises 400 session_unbound or 403 device_unknown/
    # device_revoked automatically — these propagate as HTTP errors.
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)

    if profile_id is None:
        # Omitted-param path (B-02): use the cookie-authoritative resolved profile.
        effective_profile_id = resolved_profile_id
    else:
        # Supplied-param path: normalize both sides to canonical UUID form before
        # comparing (WR-02 — raw string compare spuriously 403s when the client
        # sends the same UUID in a different case/format).
        try:
            supplied_uuid = UUID(profile_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"type": "invalid_profile_id"},
            ) from None
        # resolved_profile_id comes from the DB (canonical lowercase) or from the
        # browse-binding cookie (raw string that may not be a valid UUID — e.g. a
        # legacy value).  Guard the parse so a non-UUID resolved value falls back to
        # the original string compare rather than raising an uncaught 500.
        try:
            resolved_uuid = UUID(resolved_profile_id)
            mismatch = resolved_uuid != supplied_uuid
        except ValueError:
            mismatch = resolved_profile_id != profile_id
        if mismatch:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"type": "profile_mismatch"},
            )
        effective_profile_id = profile_id

    # Resolve the per-profile segment_cache and snapshot for position estimation.
    # Registry-only lookups — resolve_profile_from_request already ran above; calling
    # get_segment_cache_for_profile / get_snapshot_for_profile here would re-resolve
    # (2-3 extra DB round-trips + duplicated throttled last_seen_at writes, WR-01).
    # Reproduce the same 503/404 error taxonomy directly against the already-resolved
    # effective_profile_id, then cast to the concrete type (the registry holds the
    # right objects; TYPE_CHECKING imports keep mypy happy).
    seg_registry: dict[str, SegmentCache] | None = getattr(
        request.app.state, "segment_cache_registry", None
    )
    if seg_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Segment cache registry not ready",
        )
    segment_cache: SegmentCache | None = seg_registry.get(str(effective_profile_id))
    if segment_cache is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )

    snap_registry: dict[str, CollectionSnapshot] | None = getattr(
        request.app.state, "snapshot_registry", None
    )
    if snap_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Snapshot registry not ready",
        )
    snapshot: CollectionSnapshot | None = snap_registry.get(str(effective_profile_id))
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )

    record = await get_release_for_locate(pool, release_id, effective_profile_id)

    if record is None:
        # 404 path — do NOT increment selection_count (D-04: only successful locates count).
        raise HTTPException(
            status_code=404,
            detail={
                "type": "release_not_in_collection",
                "release_id": release_id,
            },
        )

    label: str = record.get("label") or ""
    catalog_number: str = record.get("catalog_number") or ""

    result = locate(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        segment_cache=segment_cache,
        snapshot=snapshot,
    )

    # OBS-07/D-04: fire-and-forget counter increment on SUCCESS path only.
    # PRIVACY: only the int release_id is passed — never label or catalog text.
    # CR-01: strong-reference via app.state.background_tasks so GC cannot cancel mid-flight.
    task = asyncio.create_task(increment_selection_count(pool, release_id))
    # CR-01 fix: never fall back to a throwaway set() — that would drop the only
    # strong reference and let the GC cancel the task. Persist the set on app.state
    # if the lifespan did not seed it (e.g. tests without a full lifespan).
    bg: set[asyncio.Task[None]] | None = getattr(request.app.state, "background_tasks", None)
    if bg is None:
        bg = set()
        request.app.state.background_tasks = bg
    bg.add(task)
    task.add_done_callback(bg.discard)

    # Pitfall 2: log exceptions from fire-and-forget tasks; never crash the response.
    def _log_exc(t: asyncio.Task[None]) -> None:
        if not t.cancelled() and t.exception() is not None:
            logger.warning(
                "increment_selection_count failed for release_id=%s: %s",
                release_id,
                t.exception(),
            )

    task.add_done_callback(_log_exc)

    # OBS-05: record slow request. Locate is CPU-only so db_ms = 0.0 (POS-03).
    total_ms = (time.perf_counter() - t0) * 1000
    record_slow_query(request.app, "/api/locate", total_ms, 0.0)

    # Serialize LocateResult to JSON-compatible dict.
    # Dataclasses are not JSON-serializable by default; JSONResponse handles dicts.
    body: dict[str, Any] = {
        "release_id": result.release_id,
        "primary_cube": _cube_ref_to_dict(result.primary_cube) if result.primary_cube else None,
        "label_span": [_cube_ref_to_dict(c) for c in result.label_span],
        "sub_cube_interval": (
            _sub_interval_to_dict(result.sub_cube_interval)
            if result.sub_cube_interval is not None
            else None
        ),
        "confidence": result.confidence,
        "generated_at": result.generated_at.isoformat(),
        "estimator_version": result.estimator_version,
    }

    return JSONResponse(content=body, status_code=200)
