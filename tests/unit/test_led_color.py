"""Unit tests for LED color math — Phase 6 Plan 03.

Tests:
  - test_colorblind_preview: gold #FFD700 and purple #7C3AED stay distinguishable
    under deuteranopia (Pitfall 18 safety guarantee) — LED-05
  - test_hex_to_rgb: import hex_to_rgb from gruvax.mqtt.publishers; basic conversion
"""

from __future__ import annotations

# ── hex_to_rgb ────────────────────────────────────────────────────────────────


def test_hex_to_rgb() -> None:
    """hex_to_rgb("#FFD700") == (255, 215, 0); tolerates missing '#'."""
    from gruvax.mqtt.publishers import hex_to_rgb

    # Standard #RRGGBB
    assert hex_to_rgb("#FFD700") == (255, 215, 0), "Gold hex failed"
    assert hex_to_rgb("#7C3AED") == (124, 58, 237), "Purple hex failed"
    assert hex_to_rgb("#000000") == (0, 0, 0), "Black hex failed"
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255), "White hex failed"

    # Without leading '#'
    assert hex_to_rgb("FFD700") == (255, 215, 0), "Gold without # failed"
    assert hex_to_rgb("0051A2") == (0, 81, 162), "Blue without # failed"


# ── color-blind simulation ────────────────────────────────────────────────────

# Mirror the TypeScript matrices verbatim from RESEARCH.md §Code Examples
# (colorjack.com matrices via gist.github.com/Lokno/df7c3bfdc9ad32558bb7)
_MATRICES: dict[str, list[list[float]]] = {
    "deuteranopia": [
        [0.625, 0.375, 0.000],
        [0.700, 0.300, 0.000],
        [0.000, 0.300, 0.700],
    ],
    "protanopia": [
        [0.567, 0.433, 0.000],
        [0.558, 0.442, 0.000],
        [0.000, 0.242, 0.758],
    ],
    "tritanopia": [
        [0.950, 0.050, 0.000],
        [0.000, 0.433, 0.567],
        [0.000, 0.475, 0.525],
    ],
}


def _simulate_color_blindness(hex_color: str, cb_type: str) -> tuple[int, int, int]:
    """Python mirror of the TypeScript simulateColorBlindness function.

    Used in tests to verify that the ColorBlindPreview component will produce
    the expected outputs for the seed gold/purple pair.
    """
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    m = _MATRICES[cb_type]
    nr = round((m[0][0] * r + m[0][1] * g + m[0][2] * b) * 255)
    ng = round((m[1][0] * r + m[1][1] * g + m[1][2] * b) * 255)
    nb = round((m[2][0] * r + m[2][1] * g + m[2][2] * b) * 255)
    return (nr, ng, nb)


def test_colorblind_preview() -> None:
    """Gold #FFD700 and purple #7C3AED produce DISTINCT results under deuteranopia.

    This is the Pitfall 18 guarantee: the accessibility-default color pair
    stays distinguishable even for people with deuteranopia (the most common
    form of red-green color blindness). The simulated outputs must differ in
    at least one channel — the pair is not collapsed to the same color.

    LED-05 / D-18 / D-05
    """
    gold = "#FFD700"
    purple = "#7C3AED"

    gold_deuteranopia = _simulate_color_blindness(gold, "deuteranopia")
    purple_deuteranopia = _simulate_color_blindness(purple, "deuteranopia")

    assert gold_deuteranopia != purple_deuteranopia, (
        f"Gold and purple collapsed to the same color under deuteranopia: "
        f"gold={gold_deuteranopia} purple={purple_deuteranopia}. "
        "The accessibility default pair must stay distinguishable (Pitfall 18)."
    )

    # Additionally verify protanopia and tritanopia also keep them distinct
    gold_protanopia = _simulate_color_blindness(gold, "protanopia")
    purple_protanopia = _simulate_color_blindness(purple, "protanopia")
    assert gold_protanopia != purple_protanopia, (
        f"Gold and purple collapsed under protanopia: "
        f"gold={gold_protanopia} purple={purple_protanopia}"
    )

    gold_tritanopia = _simulate_color_blindness(gold, "tritanopia")
    purple_tritanopia = _simulate_color_blindness(purple, "tritanopia")
    assert gold_tritanopia != purple_tritanopia, (
        f"Gold and purple collapsed under tritanopia: "
        f"gold={gold_tritanopia} purple={purple_tritanopia}"
    )
