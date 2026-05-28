"""Profile CRUD + connect/rotate-PAT + soft-delete under /api/admin/profiles.

Endpoints:
  GET    /profiles               — list active profiles with sync metadata + status
  GET    /profiles/{id}          — single profile (poll target for D2-13)
  POST   /profiles               — create a PENDING profile; seed default settings rows
  PATCH  /profiles/{id}          — rename (409 on case-insensitive duplicate)
  POST   /profiles/{id}/connect  — connect PAT: test-sync + store + kick full sync
  POST   /profiles/{id}/rotate   — rotate PAT: same as connect + same-user check
  DELETE /profiles/{id}          — soft-delete + evict in-memory registry entries

Auth: all mutating endpoints require PIN session + CSRF (require_admin).
Security: T-02-05-01 through T-02-05-06 — see plan threat register.

Pitfall 6 (pool exhaustion):
  Long operations (the test-sync in /connect and /rotate) run AFTER the pool slot
  is released. Every endpoint reaches into request.app.state.db_pool with tight
  ``async with`` blocks; no endpoint injects the pool via Depends(get_pool).

D-09 strict user_id-match invariant (mirrored from src/gruvax/cli/set_pat.py):
  /connect captures the user_id from the test-sync and checks it against any
  existing active profile. If another active profile already has that user_id,
  returns 409 user_id_collision. /rotate additionally requires the captured
  user_id to equal the profile's existing discogsography_user_id.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
import psycopg.errors
from pydantic import BaseModel

from gruvax.api.admin.profile_sync import _run_sync_background
from gruvax.api.deps import require_admin
from gruvax.db.queries import DEFAULT_PROFILE_UUID
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
)
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-profiles"])


# ── Request models ────────────────────────────────────────────────────────────


class CreateProfileRequest(BaseModel):
    """Request body for POST /profiles."""

    display_name: str


class RenameProfileRequest(BaseModel):
    """Request body for PATCH /profiles/{id}."""

    display_name: str


class ConnectPatRequest(BaseModel):
    """Request body for POST /profiles/{id}/connect and /profiles/{id}/rotate."""

    pat: str


# ── helpers ───────────────────────────────────────────────────────────────────


def _profile_status(row: dict[str, Any]) -> str:
    """Derive human-readable status from profile row fields.

    Status enum (D2-13):
      re-auth-required — app_token_revoked is True (PAT rejected/expired)
      syncing          — last_sync_status = 'in_progress'
      connected        — last_sync_status = 'ok'
      pending          — no PAT connected yet (app_token_revoked=True, never ok)
    """
    if row.get("app_token_revoked") and row.get("last_sync_status") == "ok":
        return "re-auth-required"
    if row.get("app_token_revoked"):
        return "pending"
    if row.get("last_sync_status") == "in_progress":
        return "syncing"
    if row.get("last_sync_status") == "ok":
        return "connected"
    return "pending"


def _parse_uuid(profile_id: str) -> uuid.UUID:
    """Parse profile_id as UUID, raising 400 on failure."""
    try:
        return uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
        ) from None


async def _require_profile(db_pool: Any, uid: uuid.UUID) -> None:
    """Raise 404 if profile is missing or soft-deleted (tight pool checkout)."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
            (str(uid),),
        )
        if await cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "profile_not_found"},
            )
    # Pool slot released here.


async def _run_test_sync(pat: str) -> str:
    """Run a per_page=1 test-sync against discogsography; return user_id.

    Uses profile_sync._make_client so tests can monkeypatch the factory.
    Raises PATRejected (401), RateLimitExhausted (503), ServerError / NetworkError (503).
    """
    client = profile_sync._make_client(settings.DISCOGSOGRAPHY_BASE_URL, pat)
    try:
        page = await client._get_page(limit=1, offset=0)
        user_id = str(page["user_id"])
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()
    return user_id


def _evict_profile_registries(profile_id: str, app_state: Any) -> None:
    """Pop all six per-profile registry entries for the soft-deleted profile (D2-03).

    Uses .pop(key, None) so missing entries are silently ignored (the profile
    may have been created but never synced, leaving some registries empty).
    """
    for attr in (
        "boundary_cache_registry",
        "snapshot_registry",
        "segment_cache_registry",
        "settings_cache_registry",
        "event_bus_registry",
        "profile_state_registry",
    ):
        registry: dict[str, Any] | None = getattr(app_state, attr, None)
        if registry is not None:
            registry.pop(profile_id, None)


# ── GET /profiles ─────────────────────────────────────────────────────────────


@router.get("/profiles")
async def list_profiles(
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """List all active (non-deleted) profiles with sync metadata and status.

    Never returns app_token_encrypted (T-02-05-02 — PAT must not be exposed).
    """
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, display_name, last_sync_at, last_sync_status, "
            "       last_sync_item_count, app_token_revoked "
            "FROM gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at",
        )
        rows = await cur.fetchall()

    profiles = []
    for row in rows:
        pid, display_name, last_sync_at, last_sync_status, item_count, revoked = row
        row_dict: dict[str, Any] = {
            "app_token_revoked": bool(revoked),
            "last_sync_status": last_sync_status,
        }
        profiles.append(
            {
                "id": str(pid),
                "display_name": display_name,
                "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
                "last_sync_status": last_sync_status,
                "last_sync_item_count": item_count,
                "app_token_revoked": bool(revoked),
                "status": _profile_status(row_dict),
            }
        )
    return JSONResponse(content=profiles)


# ── GET /profiles/{id} ────────────────────────────────────────────────────────


@router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: str,
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Fetch a single active profile by id (D2-13 poll target)."""
    uid = _parse_uuid(profile_id)
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, display_name, last_sync_at, last_sync_status, "
            "       last_sync_item_count, app_token_revoked, last_sync_error "
            "FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
            (str(uid),),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )

    pid, display_name, last_sync_at, last_sync_status, item_count, revoked, sync_error = row
    row_dict: dict[str, Any] = {
        "app_token_revoked": bool(revoked),
        "last_sync_status": last_sync_status,
    }
    return JSONResponse(
        content={
            "id": str(pid),
            "display_name": display_name,
            "last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
            "last_sync_status": last_sync_status,
            "last_sync_error": sync_error,
            "last_sync_item_count": item_count,
            "app_token_revoked": bool(revoked),
            "status": _profile_status(row_dict),
        }
    )


# ── POST /profiles ────────────────────────────────────────────────────────────


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
async def create_profile(
    request: Request,
    body: CreateProfileRequest,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Create a new PENDING profile (no PAT).

    Seeds default settings rows for the new profile_id (copies from the default
    profile's settings — RESEARCH Open Question 4). Adds an empty per-profile
    registry entry set (D2-03 — empty caches are valid; first sync populates them).

    Returns 201 with {id: <uuid>} on success.
    409 display_name_taken on case-insensitive duplicate among active profiles.
    """
    db_pool = request.app.state.db_pool

    # Use a sentinel placeholder for the PAT (empty bytea + revoked=TRUE).
    sentinel_pat: bytes = b""

    # INSERT the new profile.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        try:
            await cur.execute(
                "INSERT INTO gruvax.profiles "
                "(display_name, app_token_encrypted, app_token_revoked, last_sync_status) "
                "VALUES (%s, %s::bytea, TRUE, NULL) "
                "RETURNING id::text",
                (body.display_name, sentinel_pat),
            )
            row = await cur.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"type": "insert_failed"},
                )
            new_profile_id: str = row[0]
        except psycopg.errors.UniqueViolation:
            await conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"type": "display_name_taken", "message": "display_name already in use"},
            ) from None

        # Seed default settings rows for the new profile (RESEARCH Open Question 4).
        # After migration 0011, settings PK is (key) alone — settings are global.
        # Insert the standard defaults if they don't exist (ON CONFLICT DO NOTHING).
        _DEFAULT_SETTINGS = [
            ("cube.nominal_capacity", "95"),
            ("session.idle_ttl_seconds", "600"),
            ("session.hard_cap_seconds", "1800"),
        ]
        for key, value in _DEFAULT_SETTINGS:
            await cur.execute(
                "INSERT INTO gruvax.settings (key, value, description, updated_at) "
                "VALUES (%s, %s::jsonb, %s, now()) "
                "ON CONFLICT (key) DO NOTHING",
                (key, value, f"Default value — seeded for profile {new_profile_id}"),
            )

        await conn.commit()

    # Add empty per-profile registry entries so the new profile is routable
    # immediately (D2-03 — empty caches are valid; first sync populates them).
    app_state = request.app.state
    for attr in (
        "boundary_cache_registry",
        "snapshot_registry",
        "segment_cache_registry",
        "settings_cache_registry",
        "event_bus_registry",
        "profile_state_registry",
    ):
        registry: dict[str, Any] | None = getattr(app_state, attr, None)
        if registry is not None and new_profile_id not in registry:
            registry[new_profile_id] = None  # type: ignore[assignment]

    logger.info("profile created: id=%s display_name=%r", new_profile_id, body.display_name)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"id": new_profile_id, "display_name": body.display_name, "status": "pending"},
    )


# ── PATCH /profiles/{id} ─────────────────────────────────────────────────────


@router.patch("/profiles/{profile_id}")
async def rename_profile(
    profile_id: str,
    request: Request,
    body: RenameProfileRequest,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Rename a profile (409 on case-insensitive duplicate)."""
    uid = _parse_uuid(profile_id)
    await _require_profile(request.app.state.db_pool, uid)

    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        try:
            await cur.execute(
                "UPDATE gruvax.profiles SET display_name = %s "
                "WHERE id = %s::uuid AND deleted_at IS NULL",
                (body.display_name, str(uid)),
            )
        except psycopg.errors.UniqueViolation:
            await conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"type": "display_name_taken", "message": "display_name already in use"},
            ) from None
        await conn.commit()

    return JSONResponse(content={"id": str(uid), "display_name": body.display_name})


# ── POST /profiles/{id}/connect ───────────────────────────────────────────────


@router.post("/profiles/{profile_id}/connect")
async def connect_pat(
    profile_id: str,
    request: Request,
    body: ConnectPatRequest,
    background_tasks: BackgroundTasks,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Connect a PAT to a profile.

    Flow (mirrors gruvax-set-pat CLI, D-09 strict match):
      1. 404 preflight (tight pool checkout).
      2. Run synchronous per_page=1 test-sync via profile_sync._make_client.
         - 401 pat_rejected if discogsography returns 401/403.
         - 503 upstream errors on rate limit / server error / network error.
      3. Capture user_id from test-sync response.
      4. Check if user_id already belongs to another active profile → 409 user_id_collision.
      5. Encrypt PAT + UPDATE app_token_encrypted, discogsography_user_id, app_token_revoked=FALSE.
      6. Kick the full sync as a background task.
      7. Return 200 {"status":"connected","profile_id":...}.
    """
    uid = _parse_uuid(profile_id)

    # 404 preflight (Pitfall 6 — tight checkout, released before test-sync).
    await _require_profile(request.app.state.db_pool, uid)

    # Run test-sync (long-ish HTTP call — pool slot is NOT held during this).
    try:
        new_user_id = await _run_test_sync(body.pat)
    except PATRejected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "pat_rejected", "message": "PAT rejected by discogsography (401/403)"},
        ) from None
    except RateLimitExhausted as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "rate_limited_upstream", "message": str(exc)},
        ) from exc
    except (ServerError, NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "upstream_unavailable", "message": str(exc)},
        ) from exc

    # D-09 strict user_id collision check: another active profile must not have this user_id.
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles "
            "WHERE discogsography_user_id = %s::uuid "
            "  AND id != %s::uuid "
            "  AND deleted_at IS NULL",
            (new_user_id, str(uid)),
        )
        collision_row = await cur.fetchone()

    if collision_row is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "user_id_collision",
                "message": (
                    f"discogsography_user_id {new_user_id!r} already belongs to "
                    f"profile {collision_row[0]!r}"
                ),
            },
        )

    # Store Fernet-encrypted PAT + flip revoked=FALSE (T-02-05-02 — never store plaintext).
    ciphertext = encrypt_pat(body.pat)
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    app_token_encrypted = %s::bytea, "
            "    app_token_revoked = FALSE, "
            "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid), "
            "    last_sync_status = NULL, "
            "    last_sync_error = NULL "
            "WHERE id = %s::uuid AND deleted_at IS NULL",
            (ciphertext, new_user_id, str(uid)),
        )
        await conn.commit()

    # Kick the full sync as a background task (D2-12).
    background_tasks.add_task(
        _run_sync_background,
        profile_id=str(uid),
        app_state=request.app.state,
    )

    logger.info("PAT connected for profile=%s user_id=%s", str(uid), new_user_id)
    return JSONResponse(
        content={"status": "connected", "profile_id": str(uid)}
    )


# ── POST /profiles/{id}/rotate ────────────────────────────────────────────────


@router.post("/profiles/{profile_id}/rotate")
async def rotate_pat(
    profile_id: str,
    request: Request,
    body: ConnectPatRequest,
    background_tasks: BackgroundTasks,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Rotate (replace) the PAT for a profile.

    Same as /connect but requires the captured user_id to match the profile's
    existing discogsography_user_id (D-09 strict rotation check).
    409 user_id_mismatch if it doesn't.
    """
    uid = _parse_uuid(profile_id)

    # 404 preflight + read existing user_id.
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT discogsography_user_id::text FROM gruvax.profiles "
            "WHERE id = %s::uuid AND deleted_at IS NULL",
            (str(uid),),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    existing_user_id: str | None = row[0]

    # Run test-sync.
    try:
        new_user_id = await _run_test_sync(body.pat)
    except PATRejected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "pat_rejected", "message": "PAT rejected by discogsography (401/403)"},
        ) from None
    except RateLimitExhausted as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "rate_limited_upstream", "message": str(exc)},
        ) from exc
    except (ServerError, NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "upstream_unavailable", "message": str(exc)},
        ) from exc

    # D-09: require user_id to match (strict rotation check).
    if existing_user_id is not None and existing_user_id != new_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "user_id_mismatch",
                "message": (
                    f"PAT belongs to a different discogsography user "
                    f"(was {existing_user_id!r}, got {new_user_id!r}). "
                    "Soft-delete the profile first if you really intend to switch."
                ),
            },
        )

    # Store Fernet-encrypted PAT + flip revoked=FALSE.
    ciphertext = encrypt_pat(body.pat)
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET "
            "    app_token_encrypted = %s::bytea, "
            "    app_token_revoked = FALSE, "
            "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid), "
            "    last_sync_status = NULL, "
            "    last_sync_error = NULL "
            "WHERE id = %s::uuid AND deleted_at IS NULL",
            (ciphertext, new_user_id, str(uid)),
        )
        await conn.commit()

    background_tasks.add_task(
        _run_sync_background,
        profile_id=str(uid),
        app_state=request.app.state,
    )

    logger.info("PAT rotated for profile=%s user_id=%s", str(uid), new_user_id)
    return JSONResponse(
        content={"status": "connected", "profile_id": str(uid)}
    )


# ── DELETE /profiles/{id} ────────────────────────────────────────────────────


@router.delete("/profiles/{profile_id}")
async def soft_delete_profile(
    profile_id: str,
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Soft-delete a profile and evict its in-memory registry entries (D2-03).

    The Default profile (DEFAULT_PROFILE_UUID) is protected from deletion
    (returns 409). The async row purge is deferred to Phase 4 — this handler
    only sets deleted_at and evicts the six registry caches.
    """
    uid = _parse_uuid(profile_id)

    # Protect the default profile from deletion (UI-SPEC).
    if str(uid) == DEFAULT_PROFILE_UUID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "default_profile_protected",
                "message": "The default profile cannot be deleted",
            },
        )

    await _require_profile(request.app.state.db_pool, uid)

    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET deleted_at = NOW() "
            "WHERE id = %s::uuid AND deleted_at IS NULL",
            (str(uid),),
        )
        await conn.commit()

    # Evict all six per-profile registry entries (D2-03, T-02-05-06).
    _evict_profile_registries(str(uid), request.app.state)

    logger.info("profile soft-deleted: id=%s", str(uid))
    return JSONResponse(content={"id": str(uid), "status": "deleted"})
