"""Documented Pydantic payload schemas for GRUVAX LED MQTT contract.

Phase 6: LED Contract over MQTT (Hardware Stubbed)

SC4 / LED-08: these models are the single source of truth for the LED contract
surface.  They live in the source repo alongside the topic builders so any
change to the schema is an explicit code review.

Schema names (locked per ARCHITECTURE.md §"Payload Schema Names"):
  gruvax.illuminate.v1   — primary cube highlight
  gruvax.sub_interval.v1 — sub-cube interval (normalized 0..1 within cube width)
  gruvax.span.v1         — label-span multi-cube highlight

All payloads use by_alias=True when serialized so the emitted JSON key is
``schema`` (not the Python attribute name ``schema_`` which avoids shadowing
the Pydantic/SQLAlchemy Schema type).

Color injection mitigation (T-06-02): RGBColor field validators clamp values
to 0..255 at deserialization time.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RGBColor(BaseModel):
    """A clamped 8-bit-per-channel RGB colour.

    T-06-02 mitigation: field validators clamp each channel to [0, 255] so a
    crafted ``{"r": -1}`` payload cannot cause firmware colour underflow.
    """

    r: int
    g: int
    b: int

    @field_validator("r", "g", "b", mode="before")
    @classmethod
    def clamp_channel(cls, v: Any) -> int:
        """Clamp channel to valid 8-bit range."""
        return max(0, min(255, int(v)))


class TransitionSpec(BaseModel):
    """LED transition animation specification.

    Firmware interprets these as: ``pulse`` = spring-on then sustain,
    ``fade`` = linear fade-in, ``instant`` = immediate state change.

    D-16 / D-17: transition defaults shipped as constants (position=pulse,
    span=fade, all-off=instant); no transition editor UI in v1.
    """

    style: Literal["pulse", "fade", "instant"]
    duration_ms: int


class IlluminatePayload(BaseModel):
    """Payload for ``illuminate/{unit_id}/{row}/{col}`` — primary cube highlight.

    Schema name: ``gruvax.illuminate.v1``

    QoS 0, non-retained.  Published by GRUVAX server on kiosk locate;
    consumed by ESP32 firmware to light the target cube.

    LED-01 / SC4.
    """

    model_config = {"populate_by_name": True}

    schema_: str = Field(default="gruvax.illuminate.v1", alias="schema")
    issued_at: str
    unit_id: int
    row: int
    col: int
    color: RGBColor
    brightness: int  # 0..255, server-clamped to active ceiling (D-24)
    duration_ms: int | None = None
    transition: TransitionSpec


class SubIntervalPayload(BaseModel):
    """Payload for ``sub/{unit_id}/{row}/{col}`` — sub-cube interval.

    Schema name: ``gruvax.sub_interval.v1``

    QoS 0, non-retained.  ``interval.start`` and ``interval.end`` are
    normalized 0..1 within the cube's pixel range; firmware translates to
    pixel indices (LED-03 pixel_start/pixel_end semantics).

    LED-03 / SC4.
    """

    model_config = {"populate_by_name": True}

    schema_: str = Field(default="gruvax.sub_interval.v1", alias="schema")
    issued_at: str
    unit_id: int
    row: int
    col: int
    interval: dict[str, float]  # {"start": 0..1, "end": 0..1}
    color: RGBColor
    brightness: int
    duration_ms: int | None = None


class SpanPayload(BaseModel):
    """Payload for ``span/{change_id}`` — label-span multi-cube highlight.

    Schema name: ``gruvax.span.v1``

    QoS 0, non-retained.  ``cubes`` lists every cube in the label span as
    ``[{"unit_id": ..., "row": ..., "col": ...}, ...]``; firmware lights
    each one at the span brightness tier (LED-02, D-24).

    LED-02 / SC4.
    """

    model_config = {"populate_by_name": True}

    schema_: str = Field(default="gruvax.span.v1", alias="schema")
    issued_at: str
    change_id: str
    cubes: list[dict[str, int]]  # [{unit_id, row, col}, ...]
    color: RGBColor
    brightness: int  # clamped to led_brightness.span ceiling (D-24)
    transition: TransitionSpec
