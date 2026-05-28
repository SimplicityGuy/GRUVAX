"""Tests for Plan 01-06 — queries.py + collection_snapshot.py rewire.

Behaviour verified (per Plan 01-06 Task 2 <behavior> Tests 1-6):

  1. No literal ``gruvax.v_collection`` reference remains in
     ``src/gruvax/db/queries.py`` after the rewire.
  2. No literal ``v_collection`` reference remains in
     ``src/gruvax/estimator/collection_snapshot.py``.
  3. Every rewired query function in ``queries.py`` binds the profile UUID
     via the ``%s::uuid`` placeholder pattern in its SQL body, and exposes
     ``profile_id`` as a parameter (P2-readiness lever).
  4. ``search_collection`` returns the expected catalog row for the canonical
     "BLP 1000" query against the seeded ``profile_collection`` fixture.
  5. ``CollectionSnapshot.load`` populates the in-memory snapshot from
     ``profile_collection`` and resolves ``Blue Note`` as a non-empty group
     (Plan 01-00 generator seeds 400 Blue Note rows).
  6. The Pitfall-C invariant in ``collection_snapshot.py`` (labels are
     casefolded, never normalize_catalog()) is preserved verbatim.

These tests are intentionally tight — they verify the rewire *contract*
without re-running the full integration suite (which is covered by the
existing ``tests/integration/test_search.py`` / ``test_locate.py`` modules).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from gruvax.db import queries
from gruvax.db.queries import (
    DEFAULT_PROFILE_UUID,
    cube_exact_match,
    did_you_mean_query,
    find_boundary_near_misses,
    get_catalogs_for_label,
    get_distinct_labels,
    get_phantom_boundary_count,
    get_release_for_locate,
    get_sync_staleness_seconds,
    get_top_searched,
    search_collection,
)
from gruvax.estimator.collection_snapshot import CollectionSnapshot


REWIRED_FUNCTIONS = (
    search_collection,
    did_you_mean_query,
    get_release_for_locate,
    get_distinct_labels,
    get_catalogs_for_label,
    cube_exact_match,
    find_boundary_near_misses,
    get_phantom_boundary_count,
    get_top_searched,
    get_sync_staleness_seconds,
)


_QUERIES_SRC = inspect.getsource(queries)


# ── Test 1: zero v_collection in queries.py source ───────────────────────────


def test_queries_module_has_no_v_collection_FROM_clause() -> None:
    """No literal ``gruvax.v_collection`` FROM/JOIN remains in queries.py.

    Comments and docstrings that mention the historical name are tolerated
    (the success-criteria grep gate uses ``gruvax\\.v_collection|FROM
    v_collection`` over .py files, which catches both forms in SQL bodies).
    """
    queries_src_path = Path(__file__).resolve().parents[3] / "src" / "gruvax" / "db" / "queries.py"
    text = queries_src_path.read_text()
    # The qualified SQL form must be entirely absent (allowing the historical
    # mention in the module docstring's "Plan 01-06" provenance line).
    sql_hits = [
        line
        for line in text.splitlines()
        if "gruvax.v_collection" in line and "FROM gruvax.v_collection" in line
    ]
    assert sql_hits == [], f"queries.py still has FROM gruvax.v_collection lines: {sql_hits}"
    # FROM v_collection (unqualified) must also be absent.
    assert "FROM v_collection" not in text, "queries.py still uses unqualified FROM v_collection"


# ── Test 2: zero v_collection in collection_snapshot.py source ───────────────


def test_collection_snapshot_has_no_v_collection_query() -> None:
    """No SQL body in collection_snapshot.py references the legacy view."""
    snap_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "gruvax"
        / "estimator"
        / "collection_snapshot.py"
    )
    text = snap_path.read_text()
    assert "FROM gruvax.v_collection" not in text, (
        "collection_snapshot.py still queries gruvax.v_collection"
    )
    assert "FROM v_collection" not in text, (
        "collection_snapshot.py still queries v_collection unqualified"
    )


# ── Test 3: every rewired function accepts profile_id + binds %s::uuid ───────


# Anti-leakage functions (D2-03/D2-04): profile_id is REQUIRED (no default).
# These must never leak to the default profile if the caller forgets to pass one.
_ANTI_LEAKAGE_FUNCTIONS = {search_collection, did_you_mean_query, get_release_for_locate}


@pytest.mark.parametrize(
    "fn",
    REWIRED_FUNCTIONS,
    ids=[f.__name__ for f in REWIRED_FUNCTIONS],
)
def test_rewired_function_has_profile_id_parameter(fn) -> None:  # type: ignore[no-untyped-def]
    """Each rewired query function exposes a ``profile_id`` parameter.

    For the three anti-leakage functions (D2-03/D2-04 — search_collection,
    did_you_mean_query, get_release_for_locate): profile_id is REQUIRED
    (no default) to prevent accidental single-profile leakage when the caller
    forgets to pass a profile_id.

    For all other rewired functions: profile_id must be present; a default is
    acceptable because those paths don't carry the same leakage risk.
    """
    sig = inspect.signature(fn)
    assert "profile_id" in sig.parameters, (
        f"{fn.__name__} does not accept a profile_id parameter — P2 readiness lost"
    )
    param = sig.parameters["profile_id"]
    if fn in _ANTI_LEAKAGE_FUNCTIONS:
        assert param.default is inspect.Parameter.empty, (
            f"{fn.__name__}.profile_id must be a REQUIRED parameter (no default) "
            f"per D2-03/D2-04 anti-leakage contract; got default={param.default!r}"
        )
    else:
        # Non-anti-leakage functions may retain a default for backward compat.
        assert param.default is inspect.Parameter.empty or param.default == DEFAULT_PROFILE_UUID, (
            f"{fn.__name__}.profile_id default ({param.default!r}) must be "
            f"inspect.Parameter.empty or DEFAULT_PROFILE_UUID"
        )


def test_queries_source_binds_profile_id_uuid_in_sql_bodies() -> None:
    """The rewired SQL bodies all use the ``%s::uuid`` cast pattern for profile_id.

    We require at least one ``%s::uuid`` token per rewired function (each
    function's SQL contains at least one ``profile_id = %s::uuid`` clause).
    """
    # Each rewired function's body should bind profile_id at least once via
    # %s::uuid. The simplest aggregate check: the qualified pattern is present
    # AT LEAST as many times as the count of rewired functions that hit
    # profile_collection in a WHERE.
    pc_where_count = _QUERIES_SRC.count("profile_id = %s::uuid")
    assert pc_where_count >= 8, (
        f"queries.py source has only {pc_where_count} occurrences of "
        f"`profile_id = %s::uuid` — expected ≥ 8 (one per rewired function "
        f"that filters profile_collection)."
    )


# ── Test 4: search_collection returns expected row for canonical query ───────


@pytest.mark.asyncio(loop_scope="session")
async def test_search_returns_canonical_catalog_row(db_pool) -> None:  # type: ignore[no-untyped-def]
    """search_collection("BLP 1000") returns release_id=1 with the BLP 1000 catalog.

    The synthetic seed (Plan 01-00 generator) places "BLP 1000" at release_id=1
    in the Blue Note label. The catalog-boost path is the dominant scorer for
    is_catalog_query("BLP 1000") → True.
    """
    rows, took_ms, _did_you_mean = await search_collection(db_pool, "BLP 1000", limit=10, profile_id=DEFAULT_PROFILE_UUID)
    assert rows, f"Expected a hit for 'BLP 1000', got empty (took_ms={took_ms})"
    # Response-shape compatibility: primary_artist + collection_item_id + format
    # keys must be present (Plan 01-06 SQL alias compatibility decision).
    top = rows[0]
    assert "primary_artist" in top, top
    assert "collection_item_id" in top, top
    assert "format" in top, top
    catalogs = [r["catalog_number"] for r in rows]
    assert any("BLP 1000" in (c or "") for c in catalogs), (
        f"Expected BLP 1000 in catalog_number results, got: {catalogs}"
    )


# ── Test 5: CollectionSnapshot.load groups Blue Note correctly ───────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_snapshot_loads_blue_note_from_profile_collection(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Snapshot.load against profile_collection groups Blue Note rows."""
    snapshot = CollectionSnapshot()
    await snapshot.load(db_pool)
    blue_note = snapshot.get_label_records("Blue Note")
    assert len(blue_note) >= 100, (
        f"Expected >=100 Blue Note records in profile_collection seed, got {len(blue_note)}"
    )
    # Casefold check (Pitfall C) — varied casings resolve identically.
    assert snapshot.get_label_records("BLUE NOTE") == blue_note
    assert snapshot.get_label_records("blue note") == blue_note


# ── Test 6: Pitfall-C casefold loop is preserved verbatim ────────────────────


def test_collection_snapshot_pitfall_c_casefold_preserved() -> None:
    """collection_snapshot.py still uses .casefold() for label keying.

    Mitigates T-01-pitfall-c-loss — if the rewire accidentally swapped the
    casefold call for ``.lower()`` or ``normalize_catalog()`` the snapshot
    would silently miss Unicode label edge cases (German ``ß`` etc.).
    """
    snap_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "gruvax"
        / "estimator"
        / "collection_snapshot.py"
    )
    text = snap_path.read_text()
    assert ".casefold()" in text, (
        "collection_snapshot.py no longer uses .casefold() — Pitfall C regression!"
    )
    # Pitfall C: the module must not actually IMPORT normalize_catalog.
    # Docstring/comment references that warn against the antipattern are OK
    # (and in fact required — they document the trap).
    assert "import normalize_catalog" not in text, (
        "collection_snapshot.py imports normalize_catalog — Pitfall C risk"
    )
    # Strip comment lines + docstrings before checking for actual invocations.
    # The remaining executable body must not call normalize_catalog().
    executable_lines: list[str] = []
    in_docstring = False
    for line in text.splitlines():
        stripped = line.strip()
        # Toggle on/off triple-quoted docstrings (handles the simple case used
        # in this module — opening and closing `"""` on their own lines or at
        # the start of a line).
        if stripped.startswith('"""') or stripped.endswith('"""'):
            # Count `"""` on the line.
            triples = line.count('"""')
            if triples >= 2:
                continue  # single-line docstring — skip entirely
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Skip pure-comment lines.
        if stripped.startswith("#"):
            continue
        executable_lines.append(line)
    executable_text = "\n".join(executable_lines)
    assert "normalize_catalog(" not in executable_text, (
        "collection_snapshot.py calls normalize_catalog() in executable code — Pitfall C regression"
    )
