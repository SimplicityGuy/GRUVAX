"""Locked LocateResult contract for the GRUVAX position estimator.

This contract is locked in Phase 1 (D-10) and used by all later phases. Phase 2
will swap in a higher-accuracy estimator behind the same LocateResult shape.

Decision D-11 reconciliation:
  - ROADMAP Phase 1 criterion 5 uses the string tag ``confidence: "cube_only"``.
  - ARCHITECTURE.md specifies ``confidence: float``.
  - Resolution: confidence is a float (0..1). Cube-only results use the constant
    ``CUBE_ONLY_CONFIDENCE = 0.30`` and set ``estimator_version = "cube-only-v1"``.
    The string tag is documented here for traceability but is NOT used in the contract.

Decision D-12:
  - ``label_span`` contains ALL cubes whose [first, last] boundary covers the record's
    label via the POS-01 comparator. The UI in Phase 1 highlights only ``primary_cube``
    (CUBE-02); multi-cube secondary highlight is Phase 2 (CUBE-03).
  - ``primary_cube`` is ``None`` when no boundary covers the label (confidence 0.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# ── Confidence constants (D-11) ──────────────────────────────────────────────

CUBE_ONLY_CONFIDENCE: float = 0.30
"""Confidence value for the Phase 1 cube-only estimator.

Signals "cube identified, please scan visually within it". Below the future 0.5
threshold the Phase 4 UI will use to decide whether to show a sub-cube bar.
Defined here for import by algorithm.py and tests (single source of truth).
"""

NO_BOUNDARY_CONFIDENCE: float = 0.0
"""Confidence when no boundary covers the record's label (D-12 error semantics).

The locate endpoint returns HTTP 200 with this value (not 404) to indicate
"the record is in the collection but no cube has been assigned for its label yet".
"""


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CubeRef:
    """Immutable reference to a single Kallax cube position.

    ``unit_id`` identifies the shelving unit; ``row`` and ``col`` are 0-indexed.
    Frozen so it can be used as a dict key and in sets.
    """

    unit_id: int
    row: int
    col: int


@dataclass(frozen=True)
class SubInterval:
    """Normalized horizontal slice within a cube where a record likely sits.

    ``start`` and ``end`` are in [0, 1] relative to the cube's width. When the
    record straddles a cube boundary, ``crosses_boundary`` is True and ``next_cube``
    is populated.

    Phase 1 never creates a SubInterval (cube-only estimator). It exists here so
    the contract is locked and importable from Phase 1 onward.
    """

    cube: CubeRef
    start: float          # 0..1 within cube width
    end: float            # 0..1 within cube width
    crosses_boundary: bool
    next_cube: CubeRef | None = None


@dataclass
class LocateResult:
    """Result of a position estimate for a single release.

    Attributes:
        release_id: The Discogs release ID being located.
        primary_cube: The best single-cube answer, or None if no boundary covers
            the label (``confidence == 0.0`` in that case).
        label_span: All cubes whose [first, last] boundary covers the label, sorted
            by (unit_id, row, col). Populated even in Phase 1 (D-12).
        sub_cube_interval: Normalized position within the primary cube. Always None
            in Phase 1 (cube-only-v1). Phase 2 populates this.
        confidence: Float in [0, 1]. ``CUBE_ONLY_CONFIDENCE`` (0.30) for covered
            records; ``NO_BOUNDARY_CONFIDENCE`` (0.0) for uncovered.
        generated_at: UTC timestamp of estimate computation.
        estimator_version: Identifies which algorithm produced this result.
            "cube-only-v1" for Phase 1; Phase 2 will use a different tag.
    """

    release_id: int
    primary_cube: CubeRef | None
    label_span: list[CubeRef]
    sub_cube_interval: SubInterval | None
    confidence: float
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    estimator_version: str = "cube-only-v1"
