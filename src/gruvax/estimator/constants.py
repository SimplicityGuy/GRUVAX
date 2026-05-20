"""Phase 2 estimator constants for the GRUVAX position estimator.

Threshold and band-width constants used by the §4.1 index-based estimator and
the UI layer (02-UI-SPEC.md §Threshold constants).

Exported symbols:
  TEXT_CUE_THRESHOLD     — confidence below which the UI shows '~' low-confidence cue
  POSITION_HALF_WIDTH    — half-width of the rendered sub-cube band for non-singletons
  compute_confidence     — returns calibrated confidence from label record count k

D-01 / Pitfall 21: Sub-cube bars are NEVER zero-width. Non-singletons use
±POSITION_HALF_WIDTH; singletons return start=0.0, end=1.0 (full-cube band, D-02).
"""

from __future__ import annotations

from gruvax.estimator.contract import CUBE_ONLY_CONFIDENCE

# ── Threshold constants ────────────────────────────────────────────────────────

TEXT_CUE_THRESHOLD: float = 0.50
"""Confidence threshold below which the UI renders a '~' low-confidence cue (D-03).

Confidence at or above 0.50 suppresses the cue; below 0.50 the UI adds a tilde
to the position indicator to signal visual uncertainty.
"""

POSITION_HALF_WIDTH: float = 0.05
"""Half-width of the rendered sub-cube band for non-singleton records.

A non-singleton record at fractional position f within its cube is rendered as a
band from max(0.0, f - POSITION_HALF_WIDTH) to min(1.0, f + POSITION_HALF_WIDTH).
This gives a 0.10-wide band centered on f (D-01/Pitfall 21 — never a zero-width bar).

Singletons (k=1) always receive start=0.0, end=1.0 regardless of this constant (D-02).
"""


# ── Confidence calibration ─────────────────────────────────────────────────────


def compute_confidence(k: int) -> float:
    """Return calibrated confidence for a label with k records.

    Confidence increases monotonically with k. Calibration from 02-RESEARCH.md:

      k <= 1  → CUBE_ONLY_CONFIDENCE (0.30) — singleton full-cube band (D-02)
      k == 2  → 0.35
      k == 3  → 0.40
      k <= 10 → min(0.70, 0.50 + 0.05 * (k - 3))
      k <= 30 → min(0.82, 0.70 + 0.012 * (k - 10))
      k > 30  → 0.85 (saturation)

    The k <= 1 case returns CUBE_ONLY_CONFIDENCE (imported from contract.py)
    rather than the literal 0.30 (single source of truth).

    Args:
        k: Number of records in the label's sorted snapshot. Must be >= 0.

    Returns:
        Float confidence value in [CUBE_ONLY_CONFIDENCE, 0.85].
    """
    if k <= 1:
        return CUBE_ONLY_CONFIDENCE  # 0.30 — singleton (D-02)
    if k <= 3:
        # k=2 → 0.35; k=3 → 0.40
        return 0.35 + 0.05 * (k - 2)
    if k <= 10:
        return min(0.70, 0.50 + 0.05 * (k - 3))
    if k <= 30:
        return min(0.82, 0.70 + 0.012 * (k - 10))
    return 0.85
