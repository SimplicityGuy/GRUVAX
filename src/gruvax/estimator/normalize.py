"""POS-01 catalog-number normalization and comparison module.

This is the single **normalization & ordering authority** for GRUVAX (ADR-0001):
it owns both catalog-number identity (``normalize_catalog`` / ``parse_key``) and
label ordering (``label_sort_key``). Postgres stores and retrieves but no longer
defines string identity or sort order — the authoritative transforms live here so
the estimator, the admin label picker, sync ingest, and the FTS index all agree by
construction.

Implements Strategy C (token-stream split) per RESEARCH.md §Pattern 2 and
INTERPOLATION.md §3.1. Raw string comparison of catalog numbers is **forbidden**;
all comparisons must go through ``parse_key``.

Decision D-13: parser strategy C delegated to researcher and confirmed here.
Decision T-01-04: all comparisons route through parse_key (tampering mitigation).
Decision T-01-05: digit-run capped at _DIGIT_CAP to prevent DoS on adversarial input.
ADR-0001: pyuca is the label-ordering authority. This module is the ONLY import
site for ``pyuca`` — every "sort labels" call site must route through
``label_sort_key`` so the picker and the estimator's cut-key order agree.

Exported symbols:
  label_sort_key           — casefold + pyuca (UCA) sort key; total order over labels
  normalize_catalog        — NFKC + casefold + first-of-comma + separator-collapse
  normalize_catalog_storage — NFKC-fold only; preserves case/separators (gruvax-rn7l.6)
  parse_key                — alternating (type_tag, value) tokens; empties sort first
  compare_catalogs         — -1/0/1 total order over parse_key
  catalog_in_range         — True iff parse_key(first) <= parse_key(catalog) <= parse_key(last)
"""

from __future__ import annotations

import re
import unicodedata

from pyuca import Collator


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Separators stripped from catalog numbers before tokenizing.
# This means "BLP 4195" and "BLP-4195" produce identical keys (documented choice).
_SEP_COLLAPSE: re.Pattern[str] = re.compile(r"[\s\-_./]+")

# Tokenizer: alternating runs of letters or digits.
_TOKEN: re.Pattern[str] = re.compile(r"([A-Za-z]+|\d+)")

# Cap digit runs longer than this many digits to avoid barcode-style outliers
# blowing up the integer (T-01-05 DoS mitigation). 12 digits covers all real
# catalog numbers; barcodes/ISRCs are 12-13+ digits and are placeholders in Discogs.
_DIGIT_CAP: int = 12

# Saturation ceiling for over-long digit runs (ADR-0001 / gruvax-raz). Any run
# with MORE than _DIGIT_CAP digits saturates to this single value, which is
# strictly greater than every representable <=_DIGIT_CAP-digit number
# (max is 10**_DIGIT_CAP - 1). This is a *saturating clamp*, not a prefix slice:
# it preserves numeric monotonicity — a 13+-digit catalog sorts AFTER all
# 12-digit catalogs instead of being truncated back below them — while still
# bounding int() cost on adversarial input (the DoS guard). Runs above the cap
# collapse together at the top; runs at/below it keep true numeric order, so e.g.
# 999999999999 < 1000000000000.
_DIGIT_SATURATION: int = 10**_DIGIT_CAP

# Values that represent "no catalog number" — sort before all real catalogs.
# Includes both raw forms and their normalized equivalents (after separator collapse):
#   "n/a" → "na", "n.a." → "na" (same result after separator collapse)
_NONE_SENTINELS: frozenset[str] = frozenset({"none", "n/a", "n.a.", "?", "", "na"})

# Sentinel tuple — sorts before any (0, ...) or (1, ...) element.
# type-tag -1 ensures sentinel tokens sort before alpha (0) and numeric (1) tokens.
_SENTINEL: tuple[tuple[int, int], ...] = ((-1, 0),)

# Module-level Collator: constructing it loads the bundled DUCET table once
# (ADR-0001 chose pyuca's bundled tables for determinism across environments and
# upgrades). Reused for every label_sort_key call — do not construct per call.
_COLLATOR: Collator = Collator()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def label_sort_key(label: str | None) -> tuple[tuple[int, ...], str]:
    """Return a total-order sort key for a record label (ADR-0001 authority).

    The key is ``(UCA_sort_key, casefolded_label)``:
      1. **casefold** the label so ``blue note`` and ``Blue Note`` collate equal.
      2. The pyuca (Unicode Collation Algorithm) sort key gives linguistically
         correct primary/secondary/tertiary ordering — punctuation and spaces are
         significant and sort before letters (non-ignorable DUCET weighting), so
         ``A&M`` < ``ABC`` and ``Blue Note`` < ``Bluebird``; accented letters fold
         to their base primary weight (``Éditions EG`` sorts under ``E``).
      3. The casefolded string is appended as a deterministic tie-breaker so the
         key is a strict **total** order even when two distinct strings share a UCA
         key (canonical/compatibility equivalents) — guaranteeing antisymmetry.

    Used by BOTH the admin label picker and the estimator's cut-key comparison so
    the two orders agree by construction (ADR-0001). ``None``/empty sort first.

    The returned key is a plain tuple — safe to compare directly and to embed as
    the label component of a ``CutKey``.

    Example (ADR witness list, deterministically ordered)::

        >>> labels = ["ZZ Top Records", "Éditions EG", "Bluebird", "Blue Note",
        ...           "Ace", "ABC", "A&M", "4AD"]
        >>> sorted(labels, key=label_sort_key)
        ['4AD', 'A&M', 'ABC', 'Ace', 'Blue Note', 'Bluebird', 'Éditions EG', 'ZZ Top Records']
    """
    folded: str = (label or "").casefold()
    return (tuple(_COLLATOR.sort_key(folded)), folded)


def normalize_catalog(raw: str | None) -> str:
    """Normalize a catalog number for sorting and comparison.

    Pipeline (order matters for idempotency):
      1. Handle None and whitespace-only values → return ``""``
      2. Unicode NFKC normalization + casefold (+ NFKC again — casefold can
         denormalize). Done FIRST so compatibility characters that decompose
         into separators or commas (e.g. U+1F101 "DIGIT ZERO COMMA" → "0,")
         are resolved in the SAME pass as the comma-split / separator-collapse.
      3. Take first part only for multi-value (comma-separated) catalogs
      4. Collapse separator runs (spaces, dashes, underscores, dots, slashes) → ``""``

    The result is stable: ``normalize_catalog(normalize_catalog(s)) == normalize_catalog(s)``.
    Idempotency requires NFKC to precede the comma-split and separator-collapse;
    otherwise a compatibility char that NFKC-expands into a comma/separator would
    only be split on the second pass, breaking the fixed-point property.
    """
    if raw is None:
        return ""
    s: str = raw.strip()
    if not s:
        return ""
    # NFKC (full-width digits, ligatures, compat decompositions) then casefold,
    # then NFKC again because casefolding can itself denormalize. NFKC and
    # casefold are each idempotent; NFKC→casefold→NFKC reaches a fixed point.
    s = unicodedata.normalize("NFKC", s).casefold()
    s = unicodedata.normalize("NFKC", s)
    # Multi-value: Discogs sometimes stores "BLP-100, BST-200"; take the first part only.
    # (Any compat-comma from NFKC above is now a literal comma, handled here in-pass.)
    if "," in s:
        s = s.split(",", 1)[0].strip()
    # Collapse all separator runs to nothing. The key is separator-invariant by design.
    s = _SEP_COLLAPSE.sub("", s)
    # Final NFKC: collapsing a separator can leave a combining mark (e.g. one that
    # NFKC produced from a spacing accent like U+00B4) adjacent to its base char in
    # DECOMPOSED form. Re-compose so the output is a fixed point — without this the
    # next pass would compose it and break idempotency. Collapse only removes chars,
    # so this cannot reintroduce a separator or comma.
    s = unicodedata.normalize("NFKC", s)
    return s


def normalize_catalog_storage(raw: str | None) -> str:
    """Normalize a catalog number for **persistence** (gruvax-rn7l.6 / ADR-0001).

    ``normalize_catalog`` above produces the estimator's fully-collapsed
    comparison *key* (casefolded, separators stripped entirely) — the right
    shape for ``parse_key``/sorting, but the WRONG shape to persist verbatim:

      - It would defeat FTS tokenization. The ``fts_vector`` generated column
        (migrations 0013/0014) rewrites ``catalog_number`` separators to a
        single space (``regexp_replace(catalog_number, '[\\s\\-_./]+', ' ',
        'g')``) *before* ``to_tsvector`` so a hyphenated catalog like
        ``BLP-1016`` tokenizes into TWO lexemes (``blp`` + ``1016``) and a
        bare-number query (``1016``) matches. If the stored value already had
        every separator removed (``blp1016``), that regexp_replace has
        nothing left to split on and Postgres's parser tokenizes the whole
        alphanumeric run as ONE ``numword`` lexeme — silently breaking
        bare-number search for every full-width-sourced catalog.
      - It would casefold the display value. Every read site (search
        results, the admin cubes picker, ``get_catalogs_for_label``) returns
        ``catalog_number`` verbatim to the UI; downstream comparisons
        already wrap in SQL ``lower()`` (the LIKE path, the trigram
        near-miss path) or fold case internally (``to_tsvector`` lexemes are
        lowercased by the text-search dictionary), so nothing downstream
        *needs* the stored value pre-casefolded.

    So this function applies **only** the character-identity fold — NFKC —
    the piece that actually caused the bug (a full-width catalog, e.g. the
    fullwidth-Latin/fullwidth-digit spelling of "BLP-4195", stores
    compatibility characters that no SQL-side ``lower()``/
    ``regexp_replace()`` call folds to ASCII). NFKC alone maps fullwidth
    Latin letters/digits/punctuation to their canonical ASCII forms while
    preserving case and existing separator characters (the fullwidth
    hyphen U+FF0D decomposes to ASCII ``-``), so that fullwidth spelling
    normalizes to the human-readable ``"BLP-4195"`` — findable by both
    search paths and identical, once re-normalized by ``parse_key``, to
    what the estimator already computes for it.

    A single NFKC pass is idempotent and sufficient here: unlike
    ``normalize_catalog``, no casefold step follows that could reintroduce a
    compatibility character needing a second pass.

    Args:
        raw: Raw catalog-number string from the sync source (may be None).

    Returns:
        The NFKC-normalized string (``""`` for ``None``/blank input),
        case and separators preserved.
    """
    if raw is None:
        return ""
    s: str = raw.strip()
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s)


def parse_key(catalog: str | None) -> tuple[tuple[int, int | str], ...]:
    """Return a total-order comparison key for a catalog number.

    Normalizes via ``normalize_catalog`` then splits into alternating
    alpha/numeric tokens:
      - Alpha tokens: (0, <casefolded string>)  — lexicographic
      - Numeric tokens: (1, <int>)               — numeric; runs longer than
        _DIGIT_CAP digits saturate to _DIGIT_SATURATION (monotonic, DoS-bounded)

    Empty / sentinel values return ``_SENTINEL`` and sort before all real catalogs.

    Examples::

        parse_key("BLP 9")    -> ((0, 'blp'), (1, 9))
        parse_key("BLP 10")   -> ((0, 'blp'), (1, 10))
        parse_key("BLP 9") < parse_key("BLP 10")  # True — numeric-aware
        parse_key("BLP 4195") == parse_key("blp-4195")  # True — cosmetic stability
    """
    normed: str = normalize_catalog(catalog)
    if not normed or normed in _NONE_SENTINELS:
        return _SENTINEL
    tokens: list[str] = _TOKEN.findall(normed)
    if not tokens:
        return _SENTINEL
    out: list[tuple[int, int | str]] = []
    for tok in tokens:
        if tok.isdigit():
            # Saturating clamp (gruvax-raz): runs longer than the cap saturate to
            # _DIGIT_SATURATION, which is strictly greater than any <=_DIGIT_CAP
            # digit value — so 13+-digit barcodes sort AFTER every 12-digit
            # catalog (monotonic) rather than being sliced back below them. The
            # length check also keeps int() off adversarial mega-runs (T-01-05).
            value: int = _DIGIT_SATURATION if len(tok) > _DIGIT_CAP else int(tok)
            out.append((1, value))
        else:
            # Already casefolded by normalize_catalog.
            out.append((0, tok))
    return tuple(out)


def compare_catalogs(a: str | None, b: str | None) -> int:
    """Return -1, 0, or 1 as a total-order comparator over ``parse_key``.

    Satisfies:
      - compare_catalogs(a, b) ∈ {-1, 0, 1}
      - compare_catalogs(a, b) == -compare_catalogs(b, a)  (antisymmetric)
      - compare_catalogs(a, b) <= 0 and compare_catalogs(b, c) <= 0
        implies compare_catalogs(a, c) <= 0  (transitive)

    Usage::

        compare_catalogs("BLP 9", "BLP 10")   # -1
        compare_catalogs("BLP 4001", "BLP 4001")  # 0
    """
    ka: tuple[tuple[int, int | str], ...] = parse_key(a)
    kb: tuple[tuple[int, int | str], ...] = parse_key(b)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


def catalog_in_range(
    catalog: str | None,
    first_catalog: str | None,
    last_catalog: str | None,
) -> bool:
    """Return True iff ``parse_key(first_catalog) <= parse_key(catalog) <= parse_key(last_catalog)``.

    Uses ``parse_key`` for all comparisons — raw string comparison is forbidden
    (POS-01 / T-01-04).

    Example::

        catalog_in_range("BLP 4010", "BLP 4001", "BLP 4020")  # True
        catalog_in_range("BLP 9", "BLP 10", "BLP 20")          # False — numeric-aware
    """
    k: tuple[tuple[int, int | str], ...] = parse_key(catalog)
    return parse_key(first_catalog) <= k <= parse_key(last_catalog)
