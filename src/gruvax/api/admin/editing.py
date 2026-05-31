"""POST /api/admin/editing — admin_editing heartbeat (D-01, D-03).

Debounced by the admin client (~300ms). Fans out an admin_editing SSE event
so the kiosk can shimmer the affected cube range while the owner is mid-edit.
Server-side: no DB write, no state stored — pure fan-out via EventBus.

Security:
  - Session + CSRF gated via ``require_admin`` (same as every admin write).
  - Body validated by Pydantic ``EditingPayload`` (typed cube_ids ints + editing bool).
  - ``model_dump()`` emits only validated fields onto the bus — no raw client strings.
  (T-04-08, T-04-11)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gruvax.api.deps import get_write_target, require_admin


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-editing"])


class CubeId(BaseModel):
    """A single cube address. Typed so the heartbeat can't smuggle arbitrary keys
    (CR review WR-03): ``list[dict[str, int]]`` accepted ``{"unit_42": 0}``."""

    model_config = {"extra": "forbid"}

    unit: int
    row: int
    col: int


class EditingPayload(BaseModel):
    """Heartbeat payload from the admin client.

    Mirrors the admin_editing SSE event shape (CONTEXT.md Q5):
      editing=True  — editor opened / value changed (kiosk shimmers)
      editing=False — editor closed / commit completed (kiosk clears shimmer)
    """

    # max_length caps a malformed/abusive heartbeat (CR review WR-03); a real
    # change-set never touches more than a handful of cubes at once.
    cube_ids: list[CubeId] = Field(max_length=64)
    editing: bool  # True = editor open; False = closed / committed


@router.post("/editing")
async def signal_editing(
    body: EditingPayload,
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> JSONResponse:
    """Fan-out admin_editing event — no DB write, no state stored.

    Phase 4 seam (D-01, RTM-04): debounced ~300ms by the admin client;
    server fans out immediately so the kiosk shimmer is low-latency.
    The bus drops on QueueFull (slow clients) — safe for a heartbeat.

    Phase 6 (D-04 / 06-01): retargeted to per-profile bus via get_write_target
    so an admin editing profile A does not shimmer cubes on profile B's kiosks.
    No DB write; no 0-row check needed (bus retarget only).
    """
    _profile_id, bus = _write_target
    await bus.publish("admin_editing", body.model_dump())
    logger.debug(
        "admin_editing published: cube_ids=%s editing=%s",
        body.cube_ids,
        body.editing,
    )
    return JSONResponse(content={"ok": True})
