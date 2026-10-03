"""Flat CSV parser for GRUVAX boundary cut-point data.

This module is import-only (D-12). CSV is a flat format and carries no per-label
segment overrides. Every CutPointEntry produced by this parser has overrides=={}.

Overrides are a YAML-only feature (D-10). If a CSV import contains no overrides,
that is correct by design — existing overrides in the DB are not cleared by a
CSV import (that reconciliation happens in import_.py, Plan 03).

Security: csv.DictReader handles RFC 4180 quoting and BOM (UTF-8 BOM is stripped
when the input string is decoded with utf-8-sig, or when the BOM character appears
as the first character in the header row — DictReader strips it automatically for
StringIO inputs that start with the U+FEFF BOM character, T-07-CSV-INJ).

All SQL interaction is outside this module — pure transform only.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from gruvax.io.boundary_yaml import CutPointEntry


REQUIRED_HEADERS: frozenset[str] = frozenset(
    {"unit_id", "row", "col", "first_label", "first_catalog", "is_empty"}
)

_TRUTHY = frozenset({"true", "1", "yes"})


def parse_csv_boundaries(content: str) -> list[CutPointEntry]:
    """Parse a flat CSV boundary file into a list of CutPointEntry values.

    The CSV must have these headers (order is flexible):
      unit_id, row, col, first_label, first_catalog, is_empty

    is_empty truthy values: "true", "1", "yes" (case-insensitive).
    All other values (including blank/"false"/"0") are treated as False.

    first_label and first_catalog are stripped of whitespace; empty strings
    become None.

    CSV carries no overrides (D-12). Every returned entry has overrides=={}.

    Args:
        content: CSV string (UTF-8, optionally BOM-prefixed).

    Returns:
        List of CutPointEntry instances.

    Raises:
        ValueError: If any required header is missing. The error message names
                    the full set of required headers.
    """
    # csv.DictReader over StringIO — handles quoting, BOM (U+FEFF as first char
    # in the header row is treated as part of the first field name by the stdlib
    # csv module, so we strip it explicitly if present).
    text = content.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text), strict=True)

    try:
        fieldnames = reader.fieldnames or []
        if not REQUIRED_HEADERS.issubset(set(fieldnames)):
            missing = REQUIRED_HEADERS - set(fieldnames)
            raise ValueError(
                f"CSV missing required headers. Expected: {sorted(REQUIRED_HEADERS)}. "
                f"Missing: {sorted(missing)}"
            )
        return [_parse_csv_row(row, reader.line_num) for row in reader]
    except csv.Error as exc:
        raise ValueError(f"CSV line {reader.reader.line_num}: {exc}") from None


def _csv_address(row: dict[str | None, Any], key: str, line: int) -> int:
    try:
        value = int(row[key].strip())
    except ValueError:
        raise ValueError(f"CSV line {line}: {key} must be an integer") from None
    minimum = 1 if key == "unit_id" else 0
    if value < minimum:
        raise ValueError(f"CSV line {line}: {key} must be at least {minimum}")
    return value


def _parse_csv_row(row: dict[str | None, Any], line: int) -> CutPointEntry:
    missing = sorted(key for key in REQUIRED_HEADERS if row.get(key) is None)
    if missing:
        raise ValueError(f"CSV line {line}: missing fields {', '.join(missing)}")
    if None in row:
        raise ValueError(f"CSV line {line}: too many fields")
    return CutPointEntry(
        unit_id=_csv_address(row, "unit_id", line),
        row=_csv_address(row, "row", line),
        col=_csv_address(row, "col", line),
        first_label=row["first_label"].strip() or None,
        first_catalog=row["first_catalog"].strip() or None,
        is_empty=row["is_empty"].strip().lower() in _TRUTHY,
        overrides={},
    )
