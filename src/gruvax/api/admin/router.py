"""Admin router factory for GRUVAX.

``create_admin_router()`` returns a combined ``/admin`` APIRouter that
includes all admin sub-routers (login, settings).  It is imported inside
``create_app()`` in ``app.py`` — not at module level — to avoid circular
imports (same pattern as the other routers, Phase 1 decision).
"""

from __future__ import annotations

from fastapi import APIRouter


def create_admin_router() -> APIRouter:
    """Return the combined ``/admin`` router.

    Imports sub-routers inside the function body (not at module level) to
    mirror the circular-import guard from ``app.py`` lines 139-148.

    Returns:
        An ``APIRouter`` with prefix ``/admin`` that includes login and
        settings sub-routers.
    """
    from gruvax.api.admin.login import router as login_router
    from gruvax.api.admin.settings import router as settings_router

    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(login_router)
    router.include_router(settings_router)
    return router
