"""POS-01 catalog-number normalization and comparison module.

Implements Strategy C (token-stream split) per RESEARCH.md §Pattern 2 and
INTERPOLATION.md §3.1. Raw string comparison of catalog numbers is **forbidden**;
all comparisons must go through ``parse_key``.

Decision D-13: parser strategy C delegated to researcher and confirmed here.
Decision T-01-04: all comparisons route through parse_key (tampering mitigation).
Decision T-01-05: digit-run capped at _DIGIT_CAP to prevent DoS on adversarial input.

Exported symbols:
  normalize_catalog  — NFKC + casefold + first-of-comma + separator-collapse
  parse_key          — alternating (type_tag, value) tokens; empties sort first
  compare_catalogs   — -1/0/1 total order over parse_key
  catalog_in_range   — True iff parse_key(first) <= parse_key(catalog) <= parse_key(last)
"""

from __future__ import annotations

import re
import unicodedata

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

# Values that represent "no catalog number" — sort before all real catalogs.
# Includes both raw forms and their normalized equivalents (after separator collapse):
#   "n/a" → "na", "n.a." → "na" (same result after separator collapse)
_NONE_SENTINELS: frozenset[str] = frozenset({"none", "n/a", "n.a.", "?", "", "na"})

# Sentinel tuple — sorts before any (0, ...) or (1, ...) element.
# type-tag -1 ensures sentinel tokens sort before alpha (0) and numeric (1) tokens.
_SENTINEL: tuple[tuple[int, int], ...] = ((-1, 0),)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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


def parse_key(catalog: str | None) -> tuple[tuple[int, int | str], ...]:
    """Return a total-order comparison key for a catalog number.

    Normalizes via ``normalize_catalog`` then splits into alternating
    alpha/numeric tokens:
      - Alpha tokens: (0, <casefolded string>)  — lexicographic
      - Numeric tokens: (1, <int>)               — numeric (capped at _DIGIT_CAP)

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
            # Cap long digit runs before converting to int (T-01-05 DoS guard).
            capped: str = tok if len(tok) <= _DIGIT_CAP else tok[:_DIGIT_CAP]
            out.append((1, int(capped)))
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
