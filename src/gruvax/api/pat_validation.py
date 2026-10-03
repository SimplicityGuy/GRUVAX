"""Cheap, secret-safe PAT input validation shared by web entry points."""

from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import BeforeValidator


def _validate_pat_shape(value: Any) -> str:
    """Match CLI prefix/length authority without echoing a rejected secret."""
    if not isinstance(value, str) or not value.startswith("dscg_") or len(value) < 50:
        # A normal Pydantic error includes its raw input in FastAPI's 422 response.
        raise HTTPException(
            status_code=422,
            detail={
                "type": "invalid_pat",
                "message": "PAT must start with 'dscg_' and be at least 50 characters long.",
            },
        )
    return value


WebPAT = Annotated[str, BeforeValidator(_validate_pat_shape)]
