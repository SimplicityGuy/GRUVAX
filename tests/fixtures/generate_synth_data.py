"""Deterministic synthetic-data generator for fake-discogsography seed + SQL fixture.

ONE generator emits BOTH artifacts so the two consumers
(Plan 05's ``services/fake-discogsography/seed.yaml`` AND Plan 06's
``tests/fixtures/synth_profile_collection.sql``) can never drift.

Usage::

    python tests/fixtures/generate_synth_data.py \\
        --yaml services/fake-discogsography/seed.yaml \\
        --sql  tests/fixtures/synth_profile_collection.sql

Determinism: ``random.Random(seed)`` at the top of ``generate_releases``; both
emitters consume the same in-memory list so byte-for-byte reproducibility holds.

Shape-variety contract (preserved from ``tests/fixtures/legacy/synth_collection.sql``
header):
  - alpha+digit prefixes: BLP, BST, ECM, KC
  - multi-prefix labels (Blue Note has both BLP and BST)
  - mixed separators (KC 32731 + KC-32732 in same label)
  - pure-numeric catalogs
  - multi-value comma-separated catalog rows
  - ~50 singleton labels
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random
from typing import Any

import yaml


DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# Shape-variety label catalog — driven by the v1.0 contract preserved in
# tests/fixtures/legacy/synth_collection.sql's header comment.
_LABEL_SPECS: list[dict[str, Any]] = [
    {"label": "Blue Note", "prefixes": ["BLP", "BST"], "separator_mix": True, "rows": 400},
    {"label": "ECM", "prefixes": ["ECM"], "separator_mix": False, "rows": 300},
    {"label": "Columbia", "prefixes": ["KC"], "separator_mix": True, "rows": 250},
    {"label": "Atlantic", "prefixes": ["SD"], "separator_mix": False, "rows": 200},
    {"label": "Verve", "prefixes": ["MGV", "V6"], "separator_mix": True, "rows": 200},
    {"label": "Impulse!", "prefixes": ["AS"], "separator_mix": False, "rows": 200},
    {"label": "Riverside", "prefixes": ["RLP"], "separator_mix": False, "rows": 150},
    {"label": "Prestige", "prefixes": ["PRLP"], "separator_mix": False, "rows": 150},
]


def generate_releases(*, count: int = 3000, seed: int = 42) -> list[dict]:
    """Deterministic synthetic release generator. Returns ~``count`` rows.

    Each release dict matches the discogsography v1 contract envelope item shape::

        {id, title, year, catalog_number, artist, label, genres, styles,
         rating, date_added, folder_id}

    Determinism: ``random.Random(seed)`` is constructed fresh each call, so
    two invocations with the same ``seed`` return byte-identical lists.
    """
    rng = random.Random(seed)  # noqa: S311 — deterministic test fixture, not cryptographic
    releases: list[dict] = []
    rid = 1

    # Multi-row labels (multi-prefix + separator-mix + pure-numeric variants)
    for spec in _LABEL_SPECS:
        for i in range(spec["rows"]):
            prefix = rng.choice(spec["prefixes"])
            number = 1000 + i
            sep = rng.choice([" ", "-", ""]) if spec["separator_mix"] else " "
            catalog = f"{prefix}{sep}{number}"
            releases.append(
                {
                    "id": str(rid),
                    "title": f"{spec['label']} Title {i + 1}",
                    "year": 1960 + (i % 40),
                    "catalog_number": catalog,
                    "artist": f"Artist {rid}",
                    "label": spec["label"],
                    "genres": ["jazz"],
                    "styles": [],
                    "rating": 0,
                    "date_added": "2026-01-01",
                    "folder_id": 1,
                }
            )
            rid += 1

    # Pure-numeric catalog rows (single label)
    for i in range(40):
        releases.append(
            {
                "id": str(rid),
                "title": f"Pure Numeric {i}",
                "year": 1970 + i,
                "catalog_number": str(32731 + i),
                "artist": f"Pure Artist {i}",
                "label": "Pure Label",
                "genres": [],
                "styles": [],
                "rating": 0,
                "date_added": "2026-01-01",
                "folder_id": 1,
            }
        )
        rid += 1

    # Multi-value comma catalog row
    releases.append(
        {
            "id": str(rid),
            "title": "Multi-value Catalog Release",
            "year": 1975,
            "catalog_number": "BLP-100, BST-200",
            "artist": "Multi Artist",
            "label": "Blue Note",
            "genres": ["jazz"],
            "styles": [],
            "rating": 0,
            "date_added": "2026-01-01",
            "folder_id": 1,
        }
    )
    rid += 1

    # ~50 singleton labels — one release each
    for i in range(50):
        releases.append(
            {
                "id": str(rid),
                "title": f"Singleton {i}",
                "year": 1980 + (i % 30),
                "catalog_number": f"S{i:03d}-{i * 7:04d}",
                "artist": f"Singleton Artist {i}",
                "label": f"Singleton Label {i}",
                "genres": [],
                "styles": [],
                "rating": 0,
                "date_added": "2026-01-01",
                "folder_id": 1,
            }
        )
        rid += 1

    # Pad to ~count
    while len(releases) < count:
        releases.append(
            {
                "id": str(rid),
                "title": f"Padding {rid}",
                "year": 1990 + (rid % 30),
                "catalog_number": f"PAD-{rid:05d}",
                "artist": f"Padding Artist {rid}",
                "label": "Padding Label",
                "genres": [],
                "styles": [],
                "rating": 0,
                "date_added": "2026-01-01",
                "folder_id": 1,
            }
        )
        rid += 1

    return releases


def emit_yaml(releases: list[dict], path: Path) -> None:
    """Writes ``{"releases": releases}`` as YAML for the fake-discogsography seed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"releases": releases}, sort_keys=False))


def emit_sql(
    releases: list[dict],
    path: Path,
    profile_uuid: str = DEFAULT_PROFILE_UUID,
) -> None:
    """Writes the idempotent SQL fixture targeting ``gruvax.profile_collection``.

    Output structure:
      1. Header comment block (cites D-17 + shape-variety contract).
      2. ``INSERT INTO gruvax.profiles ... ON CONFLICT DO NOTHING`` — idempotent profile seed.
      3. ``TRUNCATE gruvax.profile_collection RESTART IDENTITY CASCADE`` — clean slate.
      4. Block of ``INSERT INTO gruvax.profile_collection ...`` rows, one per release.
    """
    header_lines = [
        "-- Synthetic profile_collection seed (committed; PII-free).",
        "--",
        "-- Targets gruvax.profile_collection for the default profile UUID",
        f"-- ({profile_uuid}). Replaces the v1.0 fixtures/synth_collection.sql",
        "-- (now at tests/fixtures/legacy/) per D-17.",
        "--",
        "-- GENERATED by tests/fixtures/generate_synth_data.py.",
        "-- Regenerate via: just regen-synth-data",
        "--",
        "-- Shape-variety contract preserved: alpha+digit prefixes (BLP/BST/ECM/KC),",
        "-- multi-prefix labels, mixed separators, pure-numeric, multi-value comma catalogs,",
        "-- ~50 singleton labels.",
        "--",
        f"-- Row count: {len(releases)}",
        "",
        "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked)",
        f"VALUES ('{profile_uuid}'::uuid, 'Default', '\\x'::bytea, TRUE)",
        "ON CONFLICT (id) DO NOTHING;",
        "",
        "TRUNCATE gruvax.profile_collection RESTART IDENTITY CASCADE;",
        "",
        "-- BEGIN GENERATED INSERTS",
    ]

    def q(v: Any) -> str:
        """SQL-quote a value (None → NULL; doubled single-quotes in strings)."""
        if v is None:
            return "NULL"
        s = str(v).replace("'", "''")
        return f"'{s}'"

    rows: list[str] = []
    for r in releases:
        folder_id_sql = str(r["folder_id"]) if r["folder_id"] is not None else "NULL"
        year_sql = str(r["year"]) if r["year"] is not None else "NULL"

        # S608 noqa rationale: this is a fixture generator. Values come from
        # generate_releases (deterministic, synthesized, no untrusted input) and string
        # values are quoted via q() which doubles embedded single quotes. The output is
        # a committed test fixture, never executed against a live DB with
        # attacker-controllable input.
        rows.append(
            "INSERT INTO gruvax.profile_collection "  # noqa: S608
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            f"VALUES ('{profile_uuid}'::uuid, {int(r['id'])}, "
            f"{folder_id_sql}, "
            f"{q(r['artist'])}, {q(r['title'])}, {q(r['label'])}, "
            f"{q(r['catalog_number'])}, "
            f"{year_sql});"
        )

    footer = ["-- END GENERATED INSERTS", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header_lines) + "\n" + "\n".join(rows) + "\n" + "\n".join(footer))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--yaml", type=Path, required=True)
    parser.add_argument("--sql", type=Path, required=True)
    parser.add_argument("--count", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--profile-uuid", default=DEFAULT_PROFILE_UUID)
    args = parser.parse_args()
    releases = generate_releases(count=args.count, seed=args.seed)
    emit_yaml(releases, args.yaml)
    emit_sql(releases, args.sql, profile_uuid=args.profile_uuid)
    print(f"Generated {len(releases)} releases -> {args.yaml} + {args.sql}")


if __name__ == "__main__":
    main()
