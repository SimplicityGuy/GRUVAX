"""Admin router factory for GRUVAX.

``create_admin_router()`` returns a combined ``/admin`` APIRouter that
includes all admin sub-routers (login, settings).

History note: this module previously held its sub-router imports inside
``create_admin_router()`` as a defensive guard against the circular-import
pattern documented in ``app.py``.  Audit during the discogsography tooling
alignment showed no sub-router (and no module they transitively import)
imports back from ``gruvax.api.admin.router`` or ``gruvax.app`` — the
guard was overcautious.  Imports are now at module top.
"""

from __future__ import annotations

from fastapi import APIRouter

from gruvax.api.admin.cubes import router as cubes_router
from gruvax.api.admin.devices import router as admin_devices_router
from gruvax.api.admin.diagnostics import router as diagnostics_router
from gruvax.api.admin.editing import router as editing_router
from gruvax.api.admin.export import router as export_router
from gruvax.api.admin.history import router as history_router
from gruvax.api.admin.import_ import router as import_router
from gruvax.api.admin.labels import router as labels_router
from gruvax.api.admin.leds import router as leds_router
from gruvax.api.admin.login import router as login_router
from gruvax.api.admin.profile_sync import router as profile_sync_router
from gruvax.api.admin.profiles import router as profiles_router
from gruvax.api.admin.segments import router as segments_router
from gruvax.api.admin.settings import router as settings_router


def create_admin_router() -> APIRouter:
    """Return the combined ``/admin`` router.

    Returns:
        An ``APIRouter`` with prefix ``/admin`` that includes login,
        cubes, history, and settings sub-routers.
    """
    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(login_router)
    router.include_router(cubes_router)
    router.include_router(history_router)
    router.include_router(settings_router)
    router.include_router(editing_router)
    router.include_router(segments_router)
    router.include_router(labels_router)
    router.include_router(leds_router)
    router.include_router(export_router)
    router.include_router(import_router)
    router.include_router(diagnostics_router)
    router.include_router(profile_sync_router)
    router.include_router(profiles_router)
    router.include_router(admin_devices_router)
    return router
