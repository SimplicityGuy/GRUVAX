"""In-memory derived segment structure for the GRUVAX position estimator.

Derived from BoundaryCache (cut points) + CollectionSnapshot (per-label records).
Never stored in DB. Populated at startup and on every boundary_cache.invalidate().

Phase 5: SegmentCache is the seam where two-level interpolation reads segment
fractions. It is fully CPU-only — no DB access during derive() or lookup.

Each SegmentBin holds an ordered tuple of LabelSegment objects describing which
labels occupy that physical Kallax cube and in what proportions. The derive()
algorithm works in six steps:

  1. Sort cut points by (unit_id, row, col).
  2. For each label, sort its records by parse_key(catalog_number) to get a
     globally ordered list. Labels are ORDERED by label_sort_key (pyuca / UCA,
     ADR-0001) so the cut-key order matches the admin picker; label IDENTITY
     (grouping, override matching) is still .casefold().
  3. Assign each label's records to bins by comparing the record's row-rank
     against each bin's cut-point rank within that label's sorted run.
  4. Per bin, sum segment_counts → bin_total; auto_fraction = count / total.
  5. Apply overrides keyed (unit, row, col, label.casefold()-matched) then
     renormalize non-overridden by raw count; assert sum == 1.0 within 1e-6.
  6. Compute offset_in_bin as cumulative sum of preceding applied_fractions;
     set continues=True when a label's records extend past this bin's run.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
import logging
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow

from gruvax.estimator.normalize import label_sort_key, parse_key


logger = logging.getLogger(__name__)

# The pyuca (UCA) sort key type produced by ``label_sort_key`` for a label — the
# label component of every CutKey. See ``normalize.label_sort_key``.
LabelKey = tuple[tuple[int, ...], str]

# Global sort key for a cut point: (label_sort_key(label), parse_key(catalog)).
# This alias names the ONE cut-key comparison contract the record→bin scan relies
# on. The record-side key is built identically (via ``_label_key`` below).
#
# gruvax-icc5 / ADR-0001: the label component is now the pyuca ``label_sort_key``,
# NOT a bare ``.casefold()`` codepoint string. This is the load-bearing swap that
# makes the estimator's record→bin ordering agree with the admin label picker
# (``get_distinct_labels``, which sorts by the same authority). Under the old
# casefold-codepoint order the two disagreed for real labels (A&M/Ace,
# Blue Note/Bluebird, Éditions EG), silently mis-lighting cubes. Keeping the shape
# localized behind this alias + ``_label_key`` confines the contract to one place.
CutKey = tuple[LabelKey, tuple[tuple[int, int | str], ...]]


def _label_key(label: str | None) -> LabelKey:
    """The label component of a CutKey — the single ADR-0001 ordering authority.

    Routes every "order labels" site in the estimator through
    ``label_sort_key`` (pyuca UCA), so a cut point's label key and a record's
    label key are built identically and order the same way the admin picker does.
    """
    return label_sort_key(label)


@dataclass(frozen=True)
class LabelSegment:
    """One label's presence within a single bin.

    All fraction fields are in [0.0, 1.0]. The applied_fractions of all
    LabelSegments within the same SegmentBin always sum to 1.0 (within 1e-6).
    """

    label: str  # casefolded identity key — internal matching ONLY (gruvax-rn7l.3)
    label_display: str  # original-case label as it appears in the collection — UI-facing
    first_rank_in_label: int  # 0-indexed rank of first record in this bin
    last_rank_in_label: int  # 0-indexed rank of last record in this bin (inclusive)
    segment_count: int  # = last_rank - first_rank + 1; row-count, never arithmetic
    auto_fraction: float  # count-derived: segment_count / total_bin_count
    applied_fraction: float  # override ?? auto_fraction; see Pitfall 2 normalization
    offset_in_bin: float  # cumulative sum of applied_fractions of preceding segments
    is_override: bool  # True iff an admin width override is active for this segment
    continues: bool  # True if this label continues into the next bin


@dataclass(frozen=True)
class SegmentBin:
    """One Kallax cube with its ordered list of label segments.

    Segments are ordered by global label order (label_sort_key / pyuca, ADR-0001).
    The applied_fractions of all segments always sum to 1.0 (within 1e-6). An empty
    cube (is_empty=True from BoundaryRow) will have an empty segments tuple.
    """

    unit_id: int
    row: int
    col: int
    cut_label: str | None  # = BoundaryRow.first_label (the cut point)
    cut_catalog: str | None  # = BoundaryRow.first_catalog (the cut point)
    segments: tuple[LabelSegment, ...]  # ordered by label_sort_key (pyuca)


class SegmentCache:
    """In-memory derived structure mapping each Kallax cube to its per-label segments.

    Loaded via derive() after BoundaryCache.load() at startup and after every
    boundary_cache.invalidate() + reload() cycle (Phase 4 SSE seam).

    CPU-only: no DB access during derive() or any lookup method.

    Usage::

        seg_cache = SegmentCache()
        seg_cache.derive(boundary_cache, snapshot, boundary_cache.overrides)
        bin_ = seg_cache.get_bin(unit_id=1, row=0, col=0)
        result = seg_cache.get_segment_for_rank("Blue Note", rank=5)
    """

    def __init__(self) -> None:
        self._bins: list[SegmentBin] = []
        self._by_coord: dict[tuple[int, int, int], SegmentBin] = {}

    # ── Core derivation ───────────────────────────────────────────────────────

    def derive(
        self,
        cache: BoundaryCache,
        snapshot: CollectionSnapshot,
        overrides: dict[tuple[int, int, int, str], float],
    ) -> None:
        """Populate from cut points + collection snapshot.

        Called after BoundaryCache.load() at startup and after every
        invalidate() + reload(). Never called on the hot request path.

        Algorithm:
          Step 1: Sort boundary rows by (unit_id, row, col) — the global bin order.
          Step 2: For each label in the snapshot, sort its records by
                  parse_key(catalog_number) to assign stable row-ranks.
          Step 3: For each label, determine which bins it occupies by comparing
                  parse_key of each bin's cut_catalog against the label's sorted
                  record list. A record belongs to bin B if its rank >= B's
                  first-rank-for-label and < the next bin's first-rank-for-label.
          Step 4: Compute auto_fraction = segment_count / bin_total for each segment.
          Step 5: Apply overrides and renormalize non-overridden segments so that
                  sum(applied_fractions) == 1.0 (within 1e-6) for each bin.
          Step 6: Compute offset_in_bin (cumulative applied_fractions of preceding
                  segments); set continues=True for segments where the label's
                  records extend past this bin.

        Args:
            cache:     The loaded BoundaryCache (provides get_boundaries()).
            snapshot:  The loaded CollectionSnapshot (provides get_label_records()).
            overrides: The current overrides dict from BoundaryCache.overrides.
                       Keyed by (unit_id, row, col, label_str) → fraction float.
                       Note: the label_str keys are compared case-insensitively.
        """
        boundary_rows = sorted(
            cache.get_boundaries(),
            key=lambda r: (r.unit_id, r.row, r.col),
        )

        if not boundary_rows:
            self._bins = []
            self._by_coord = {}
            return

        # Step 2: Build sorted record lists for every label in the snapshot.
        # Keys are label.casefold(); values are sorted by parse_key(catalog).
        all_labels: set[str] = set()
        for row in boundary_rows:
            if row.first_label is not None:
                all_labels.add(row.first_label.casefold())

        # Also collect labels from snapshot that appear in any boundary's cut label.
        # This ensures multi-label bins are properly handled.
        # Gather all unique casefolded labels from the snapshot that we need to process.
        snapshot_labels: set[str] = set()
        for row in boundary_rows:
            if row.first_label is not None:
                snapshot_labels.add(row.first_label.casefold())

        # For multi-label bins: we need to consider all labels in the snapshot
        # that fall within each bin's range. We derive this by checking where
        # each label's records fall relative to the cut points.
        #
        # Algorithm for assigning labels to bins:
        #   - Globally sort all records across all labels by (label.casefold(), parse_key(cat))
        #   - Each bin's cut point (first_label, first_catalog) defines the start of that bin.
        #   - All records from the cut point up to (but not including) the next bin's cut point
        #     belong to this bin.
        #   - Within each bin, group records by label to form LabelSegments.

        # Build the global sorted ordering of all records across all labels.
        # Sort key: (label.casefold(), parse_key(catalog_number))
        # We need all labels from the snapshot (not just those at cut points).

        # Collect all records from the snapshot into a globally sorted list.
        # Access the private _by_label attribute directly: SegmentCache is a
        # trusted internal service (same package, no DB boundary). This avoids
        # adding a public API to CollectionSnapshot just for this use case.
        all_records: list[RecordRow] = []
        by_label: dict[str, list[RecordRow]] = snapshot._by_label

        for records in by_label.values():
            all_records.extend(records)

        # Sort all records globally by (label_sort_key(label), parse_key(catalog))
        # This gives us the global ordering needed to assign records to bins.
        all_records.sort(key=lambda r: (_label_key(r.label), parse_key(r.catalog_number)))

        # Build per-label sorted record lists (for rank assignment within each label)
        label_sorted_records: dict[str, list[RecordRow]] = {}
        for label_key, records in by_label.items():
            label_sorted_records[label_key] = sorted(
                records, key=lambda r: parse_key(r.catalog_number)
            )

        # Step 3: Determine the cut-point index in each label's sorted record list.
        # For each bin, the cut point is (first_label, first_catalog).
        # The cut-point rank for a given label L in bin B is the index of the first
        # record in L's sorted list that is >= parse_key(B.first_catalog), but only
        # when B.first_label.casefold() == L.casefold().
        #
        # For labels that don't match the bin's first_label, they may still appear
        # in the bin if they start alphabetically after the previous cut's label.

        # Build the per-bin record assignment:
        # For each bin, we determine which records (from all labels) belong to it.
        # A record belongs to bin B if it falls in the global ordering between
        # bin B's cut point and bin B+1's cut point.

        # Convert boundary rows to a list for indexed access
        n_bins = len(boundary_rows)

        # For each bin, build the list of (label_casefold, rank_in_label) -> record mappings
        # A record belongs to bin B if:
        #   global_key(record) >= global_key(cut_B) AND
        #   (B is the last bin OR global_key(record) < global_key(cut_{B+1}))
        # where global_key = (label.casefold(), parse_key(catalog_number))

        def _cut_key(row: BoundaryRow) -> CutKey | None:
            """Global sort key for a bin's cut point, or None if the bin has none.

            An empty bin (``is_empty``) or one with a null cut label/catalog does
            not define a cut point — it never starts a record run. Returning None,
            rather than a global-minimum sentinel, keeps such bins OUT of the
            record→bin assignment entirely. Previously a mid-shelf empty bin's
            minimum key satisfied ``cut_key <= rec_key`` for every record and
            (being later in the physical walk) won assignment, then the build loop
            dropped those records as empty — silently swallowing the preceding
            cube's collection (manifestation 1).
            """
            if row.is_empty or row.first_label is None or row.first_catalog is None:
                return None
            return (_label_key(row.first_label), parse_key(row.first_catalog))

        cut_keys = [_cut_key(row) for row in boundary_rows]

        # Only cut-bearing bins receive records, paired with their physical index.
        # Empty / null-cut bins are absent here, so they cannot capture records.
        cut_bins: list[tuple[int, CutKey]] = [
            (i, key) for i, key in enumerate(cut_keys) if key is not None
        ]

        # A record belongs to the cube whose cut point most-immediately precedes it
        # in GLOBAL cut-key order — NOT in physical (unit, row, col) walk order.
        # The two coincide only when the shelf is physically arranged in alphabetical
        # order. The old scan walked bins physically and stopped at the first cut
        # greater than the record; when a later physical cube carried an
        # alphabetically-earlier cut (e.g. a second Kallax unit holding
        # earlier-label records), that early stop misfiled records into an earlier
        # unit's cube at high confidence (manifestation 2). Scanning in cut-key order
        # instead assigns every record to the correct cube regardless of walk order.
        cut_bins_by_key = sorted(cut_bins, key=lambda pair: pair[1])

        # Loudly surface a physically-disordered shelf instead of misfiling silently:
        # if the physical walk does not present cut points in non-decreasing order,
        # the collection is not shelved in the alphabetical order the position
        # estimate assumes. Assignment below stays correct (it uses cut-key order),
        # but the divergence is real boundary-data / fixture rot worth flagging.
        #
        # gruvax-icc5: because the cut key now orders labels by pyuca (label_sort_key,
        # ADR-0001), a shelf that was physically laid out under Postgres's OLD glibc
        # collation — which disagrees with pyuca for real labels (e.g. glibc's
        # punctuation-ignoring order puts ABC, Ace before A&M, whereas pyuca sorts
        # A&M first) — presents cut points that are non-monotonic in pyuca order and
        # trips this guard. That is exactly the intent: the owner sees a loud,
        # admin-visible warning that the boundaries need re-deriving under the new
        # authority, instead of a cube silently lighting for the wrong label.
        for (pa_idx, ka), (pb_idx, kb) in pairwise(cut_bins):
            if kb < ka:
                ra = boundary_rows[pa_idx]
                rb = boundary_rows[pb_idx]
                logger.warning(
                    "SegmentCache.derive: cut points are not monotonically "
                    "non-decreasing along the physical shelf walk — bin "
                    "(%d,%d,%d) cut %r sorts before the preceding bin (%d,%d,%d) "
                    "cut %r. The collection is expected to be shelved in global "
                    "label/catalog order; records are still assigned by cut-key "
                    "order, but this layout indicates boundary data that no longer "
                    "matches the physical shelf.",
                    rb.unit_id,
                    rb.row,
                    rb.col,
                    kb,
                    ra.unit_id,
                    ra.row,
                    ra.col,
                    ka,
                )
                break

        # Build a list of (record, global_sort_key) pairs, sorted globally
        record_global_pairs: list[tuple[RecordRow, CutKey]] = [
            (r, (_label_key(r.label), parse_key(r.catalog_number))) for r in all_records
        ]
        record_global_pairs.sort(key=lambda x: x[1])

        # For each record, determine which bin it belongs to using bisect-style logic
        bin_records: list[list[RecordRow]] = [[] for _ in range(n_bins)]

        for record, rec_key in record_global_pairs:
            # Last cut-bearing bin (in cut-key order) whose cut_key <= rec_key wins.
            assigned_bin = -1
            for phys_idx, key in cut_bins_by_key:
                if key <= rec_key:
                    assigned_bin = phys_idx
                else:
                    break
            if assigned_bin >= 0:
                bin_records[assigned_bin].append(record)

        # Step 4 + 5 + 6: Build SegmentBins from bin_records
        result_bins: list[SegmentBin] = []

        for _bin_idx, (brow, records_in_bin) in enumerate(
            zip(boundary_rows, bin_records, strict=True)
        ):
            if brow.is_empty or not records_in_bin:
                # Empty bin: no segments
                seg_bin = SegmentBin(
                    unit_id=brow.unit_id,
                    row=brow.row,
                    col=brow.col,
                    cut_label=brow.first_label,
                    cut_catalog=brow.first_catalog,
                    segments=(),
                )
                result_bins.append(seg_bin)
                continue

            # Group records in this bin by label (casefold), preserving insertion order
            # by iterating records_in_bin which is already globally sorted
            label_groups: dict[str, list[tuple[int, RecordRow]]] = {}
            # gruvax-rn7l.3: original-case display string per casefold group, taken
            # from the FIRST collection record seen for that label — this is the
            # single original-case source of truth (never an override's stored
            # value, which is itself a casefolded storage key post-fix).
            label_display: dict[str, str] = {}
            for record in records_in_bin:
                lk = record.label.casefold()
                if lk not in label_groups:
                    label_groups[lk] = []
                    label_display[lk] = record.label
                label_groups[lk].append((0, record))  # placeholder rank

            # Compute actual ranks within each label (across ALL bins, not just this bin)
            # first_rank_in_label = index of first record in this bin within the label's
            # globally sorted record list
            bin_total = len(records_in_bin)

            # Build ordered label list. Order segments within a bin by the same
            # pyuca authority (_label_key) used for the global cut-key order, so a
            # multi-label cube's segment order matches the shelf's global label
            # order (gruvax-icc5) rather than bare codepoint order.
            ordered_labels = sorted(label_groups.keys(), key=_label_key)

            # Step 4: compute raw counts (= row-count, never arithmetic)
            label_counts: dict[str, int] = {}
            label_first_ranks: dict[str, int] = {}
            label_last_ranks: dict[str, int] = {}
            label_continues: dict[str, bool] = {}

            for lk in ordered_labels:
                lk_records_in_bin = [r for _, r in label_groups[lk]]
                count = len(lk_records_in_bin)
                label_counts[lk] = count

                # Compute first_rank_in_label: index of first record in this bin
                # within the label's globally sorted record list
                sorted_for_label = label_sorted_records.get(lk, [])
                if not sorted_for_label:
                    label_first_ranks[lk] = 0
                    label_last_ranks[lk] = count - 1
                    label_continues[lk] = False
                    continue

                # The first record in bin (by parse_key) for this label
                lk_in_bin_sorted = sorted(
                    lk_records_in_bin, key=lambda r: parse_key(r.catalog_number)
                )
                first_in_bin_key = parse_key(lk_in_bin_sorted[0].catalog_number)

                # Find first_rank: the index in sorted_for_label where first_in_bin_key appears
                first_rank = 0
                for idx, rec in enumerate(sorted_for_label):
                    if parse_key(rec.catalog_number) >= first_in_bin_key:
                        first_rank = idx
                        break

                last_rank = first_rank + count - 1
                label_first_ranks[lk] = first_rank
                label_last_ranks[lk] = last_rank

                # continues: True if there are more records in this label beyond last_rank
                label_continues[lk] = last_rank < len(sorted_for_label) - 1

            # Step 4: auto_fractions = count / total
            auto_fractions: dict[str, float] = {
                lk: label_counts[lk] / bin_total for lk in ordered_labels
            }

            # Step 5: Apply overrides and renormalize
            # Build a normalized override lookup: (unit, row, col, label_casefold) -> fraction
            # The override keys may use original-case label strings; we casefold for matching.
            applied_fractions: dict[str, float] = {}
            is_override_flags: dict[str, bool] = {}

            # Find overrides that apply to this bin (casefold match on label)
            active_overrides: dict[str, float] = {}
            for lk in ordered_labels:
                # Check overrides dict using all possible original-case labels
                # We match by casefolding the override key's label component
                for (ov_unit, ov_row, ov_col, ov_label), ov_frac in overrides.items():
                    if (
                        ov_unit == brow.unit_id
                        and ov_row == brow.row
                        and ov_col == brow.col
                        and ov_label.casefold() == lk
                    ):
                        active_overrides[lk] = ov_frac
                        break

            if active_overrides:
                # Renormalization (Pitfall 2 / override normalization):
                # Step 5a: sum of overridden fractions
                overridden_sum = sum(active_overrides.values())
                remaining = 1.0 - overridden_sum

                # Step 5b: distribute remaining proportionally among non-overridden by raw count
                non_overridden_labels = [lk for lk in ordered_labels if lk not in active_overrides]
                non_overridden_total = sum(label_counts[lk] for lk in non_overridden_labels)

                # gruvax-cxy: a bin with NO ABSORBER cannot be renormalized by
                # spreading `remaining` — there is nothing to spread it over.
                # That is the case when every label in the bin carries an override
                # (non_overridden_total == 0), or when the overrides already sum
                # past 1.0 so `remaining` is negative and the split would hand the
                # non-overridden labels NEGATIVE widths.
                #
                # Both are reachable from a single LEGAL admin action: the only
                # bounds anywhere are per-ROW (Pydantic `gt=0.0, le=1.0` and the
                # migration-0005 CHECK) — no per-BIN sum constraint exists. A
                # one-label bin plus fraction=0.5 passes every gate, and the old
                # code then produced applied fractions summing to 0.5 and raised
                # the invariant error below. Because callers invalidate BEFORE
                # deriving, that raise left the SegmentCache EMPTY and killed
                # every locate app-wide until the row was deleted by hand — the
                # blast radius of a width tweak was the whole product.
                #
                # Degrade instead of exploding: rescale the overrides to sum 1.0,
                # preserving their RELATIVE widths (for a bin the admin fully
                # specified, the relative split IS the intent), and log loudly so
                # the bad row is discoverable. The endpoint-side guard in
                # api/admin/segments.py rejects this input before it is ever
                # committed; this leg is the second line of defence for rows that
                # predate the guard or arrive by import.
                no_absorber = non_overridden_total == 0 or remaining < 0.0
                if no_absorber and overridden_sum > 0:
                    logger.warning(
                        "SegmentCache.derive: bin (%d,%d,%d) has no absorber for "
                        "its width overrides (%d of %d labels overridden, summing "
                        "to %.6f); rescaling them to sum 1.0 so the derive still "
                        "completes. The applied widths are NOT the values that "
                        "were set — review the overrides for this bin. "
                        "Overrides: %s",
                        brow.unit_id,
                        brow.row,
                        brow.col,
                        len(active_overrides),
                        len(ordered_labels),
                        overridden_sum,
                        active_overrides,
                    )
                    scale = 1.0 / overridden_sum
                    for lk in ordered_labels:
                        # Non-overridden labels (reachable only on the
                        # `remaining < 0` leg) are squeezed to zero width rather
                        # than given a negative one.
                        applied_fractions[lk] = active_overrides.get(lk, 0.0) * scale
                        is_override_flags[lk] = lk in active_overrides
                else:
                    for lk in ordered_labels:
                        if lk in active_overrides:
                            applied_fractions[lk] = active_overrides[lk]
                            is_override_flags[lk] = True
                        else:
                            if non_overridden_total > 0:
                                applied_fractions[lk] = remaining * (
                                    label_counts[lk] / non_overridden_total
                                )
                            else:
                                applied_fractions[lk] = 0.0
                            is_override_flags[lk] = False

                # Step 5c: assert sum == 1.0 within 1e-6.
                # gruvax-cxy: still an invariant — but now an UNREACHABLE one for
                # the fully-overridden shape, which the branch above absorbs. A
                # raise here means the derive found something genuinely unmodelled,
                # and the caller's fresh-derive-then-swap keeps the last good cache
                # serving while it is investigated.
                total_applied = sum(applied_fractions[lk] for lk in ordered_labels)
                if abs(total_applied - 1.0) >= 1e-6:
                    raise ValueError(
                        f"Per-bin applied_fractions sum to {total_applied:.8f} "
                        f"(expected 1.0 within 1e-6) for bin "
                        f"({brow.unit_id},{brow.row},{brow.col}). "
                        f"Overrides: {active_overrides}, auto: {auto_fractions}"
                    )
            else:
                # No overrides: applied_fractions == auto_fractions
                for lk in ordered_labels:
                    applied_fractions[lk] = auto_fractions[lk]
                    is_override_flags[lk] = False

                # Verify sum (should always be 1.0 for well-formed data)
                total_applied = sum(applied_fractions[lk] for lk in ordered_labels)
                if abs(total_applied - 1.0) >= 1e-6:
                    raise ValueError(
                        f"Per-bin auto_fractions sum to {total_applied:.8f} "
                        f"(expected 1.0 within 1e-6) for bin "
                        f"({brow.unit_id},{brow.row},{brow.col}). "
                        f"auto: {auto_fractions}"
                    )

            # Step 6: compute offset_in_bin (cumulative applied_fractions)
            offset = 0.0
            segments: list[LabelSegment] = []
            for lk in ordered_labels:
                seg = LabelSegment(
                    label=lk,  # stored as casefold for consistency
                    label_display=label_display[lk],  # original case (gruvax-rn7l.3)
                    first_rank_in_label=label_first_ranks[lk],
                    last_rank_in_label=label_last_ranks[lk],
                    segment_count=label_counts[lk],
                    auto_fraction=auto_fractions[lk],
                    applied_fraction=applied_fractions[lk],
                    offset_in_bin=offset,
                    is_override=is_override_flags[lk],
                    continues=label_continues[lk],
                )
                segments.append(seg)
                offset += applied_fractions[lk]

            seg_bin = SegmentBin(
                unit_id=brow.unit_id,
                row=brow.row,
                col=brow.col,
                cut_label=brow.first_label,
                cut_catalog=brow.first_catalog,
                segments=tuple(segments),
            )
            result_bins.append(seg_bin)

        self._bins = result_bins
        self._by_coord = {(b.unit_id, b.row, b.col): b for b in result_bins}

    # ── Test seam ─────────────────────────────────────────────────────────────

    def _load_bins(self, bins: list[SegmentBin]) -> None:
        """Test seam: bypass derive() — mirrors BoundaryCache._load_rows().

        Used by tests that want to inject pre-built SegmentBin objects directly
        without going through derive(). This avoids needing a full BoundaryCache
        and CollectionSnapshot in unit tests that focus on lookup behavior.
        """
        self._bins = list(bins)
        self._by_coord = {(b.unit_id, b.row, b.col): b for b in bins}

    # ── Lookup methods ────────────────────────────────────────────────────────

    def get_bin(self, unit_id: int, row: int, col: int) -> SegmentBin | None:
        """Return the SegmentBin at the given coordinates, or None if not found."""
        return self._by_coord.get((unit_id, row, col))

    def get_bins_for_label(self, label: str) -> list[SegmentBin]:
        """Return all bins that contain a segment for the given label.

        Uses casefold comparison per Pitfall C — labels are never compared
        via parse_key().
        """
        key = label.casefold()
        return [b for b in self._bins if any(s.label.casefold() == key for s in b.segments)]

    def get_segment_for_rank(self, label: str, rank: int) -> tuple[SegmentBin, LabelSegment] | None:
        """Find the bin + segment where this label's record at ``rank`` lives.

        Args:
            label: Label string (any case — compared via casefold).
            rank:  0-indexed row-rank within the label's globally sorted record list.

        Returns:
            (SegmentBin, LabelSegment) if found, or None if no segment contains
            the given rank for the given label.
        """
        key = label.casefold()
        for bin_ in self._bins:
            for seg in bin_.segments:
                if (
                    seg.label.casefold() == key
                    and seg.first_rank_in_label <= rank <= seg.last_rank_in_label
                ):
                    return bin_, seg
        return None

    def invalidate(self) -> None:
        """Mirror BoundaryCache.invalidate() — called alongside it.

        Called by the SSE event handler when a ``boundary_changed`` event fires.
        The caller must call derive() again after invalidating to repopulate.

        Example (Phase 4 usage)::

            cache.invalidate()
            segment_cache.invalidate()
            await cache.load(pool)
            segment_cache.derive(cache, snapshot, cache.overrides)
        """
        self._bins = []
        self._by_coord = {}
