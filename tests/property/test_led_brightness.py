"""Hypothesis property tests for LED brightness clamping and payload validation.

Nyquist Wave-0 scaffold — Phase 6: LED Contract over MQTT (Hardware Stubbed)

Covers:
  - clamp_brightness invariant: output always in [0, ceiling] (span/active/ambient clamping)
  - IlluminatePayload model validates for any valid LocateResult-shaped dict (LED-08)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import assume, given
from hypothesis import strategies as st

from gruvax.mqtt.publishers import clamp_brightness
from gruvax.mqtt.schemas import IlluminatePayload, RGBColor, TransitionSpec


# ── Property 1: clamp_brightness invariant ────────────────────────────────────


@given(
    val=st.integers(min_value=-1000, max_value=1000),
    ceiling=st.integers(min_value=0, max_value=255),
)
def test_clamp_brightness_within_bounds(val: int, ceiling: int) -> None:
    """For any brightness integer and any ceiling 0..255, clamp_brightness(val, ceiling)
    is within [0, ceiling].

    This invariant covers the span tier (ceiling=led_brightness.span),
    the active/position tier (ceiling=led_brightness.active), and the
    ambient/idle tier (ceiling=led_brightness.ambient).
    """
    result = clamp_brightness(val, ceiling)
    assert 0 <= result <= ceiling, (
        f"clamp_brightness({val}, {ceiling}) = {result}, expected in [0, {ceiling}]"
    )


# ── Property 2: IlluminatePayload validates for any valid LocateResult dict ────


@given(
    unit_id=st.integers(min_value=0, max_value=9),
    row=st.integers(min_value=0, max_value=3),
    col=st.integers(min_value=0, max_value=3),
    r=st.integers(min_value=0, max_value=255),
    g=st.integers(min_value=0, max_value=255),
    b=st.integers(min_value=0, max_value=255),
    brightness=st.integers(min_value=0, max_value=255),
    duration_ms=st.integers(min_value=0, max_value=10000),
    transition_style=st.sampled_from(["pulse", "fade", "instant"]),
)
def test_illuminate_payload_validates(
    unit_id: int,
    row: int,
    col: int,
    r: int,
    g: int,
    b: int,
    brightness: int,
    duration_ms: int,
    transition_style: str,
) -> None:
    """For any valid LocateResult-shaped dict with non-null primary_cube,
    the IlluminatePayload model validates without error (LED-08).

    SC4: Payload schemas live in gruvax.mqtt.schemas and validate at publish time.
    """
    payload = IlluminatePayload(
        issued_at=datetime.now(UTC).isoformat(),
        unit_id=unit_id,
        row=row,
        col=col,
        color=RGBColor(r=r, g=g, b=b),
        brightness=brightness,
        transition=TransitionSpec(style=transition_style, duration_ms=duration_ms),
    )
    # schema_ field must default to the contract name
    assert payload.schema_ == "gruvax.illuminate.v1"
    # Serialization must use the `schema` alias (by_alias=True)
    dumped = payload.model_dump(by_alias=True)
    assert "schema" in dumped, f"Expected 'schema' key (alias); got keys: {list(dumped.keys())}"
    assert dumped["schema"] == "gruvax.illuminate.v1"
