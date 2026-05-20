"""Position estimator package for GRUVAX.

Provides the POS-01 catalog-number parser/comparator, the locked LocateResult
contract, the startup-loaded BoundaryCache, and the cube-only-v1 estimator.

Design decisions implemented here:
- D-10: Phase 1 ships the cube-only fallback (INTERPOLATION §4.8).
- D-11: confidence is a float (0..1), not a string enum; cube-only uses 0.30.
- D-12: real label_span computed via POS-01 comparator.
- D-13: POS-01 uses token-stream split (Strategy C), zero dependency.
"""
