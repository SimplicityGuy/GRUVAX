"""Regression: YAML and SQL emitted by generate_synth_data.py have identical row counts.

Also covers determinism, shape-variety contract, and the
tests.fixtures.fake_discogsography shim identity check.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import yaml

from tests.fixtures.generate_synth_data import (
    DEFAULT_PROFILE_UUID,
    emit_sql,
    emit_yaml,
    generate_releases,
)


if TYPE_CHECKING:
    from pathlib import Path


def test_yaml_and_sql_row_count_agree(tmp_path: Path) -> None:
    """T-00-fixture-drift mitigation: ONE generator, two outputs, row counts equal."""
    releases = generate_releases(count=3000, seed=42)
    yaml_path = tmp_path / "seed.yaml"
    sql_path = tmp_path / "seed.sql"
    emit_yaml(releases, yaml_path)
    emit_sql(releases, sql_path, profile_uuid=DEFAULT_PROFILE_UUID)
    yaml_rows = yaml.safe_load(yaml_path.read_text())["releases"]
    sql_text = sql_path.read_text()
    sql_insert_count = sql_text.count("INSERT INTO gruvax.profile_collection")
    assert len(yaml_rows) == sql_insert_count, (
        f"YAML row count ({len(yaml_rows)}) != SQL INSERT count ({sql_insert_count})"
    )
    assert len(yaml_rows) >= 2900


def test_generator_is_deterministic() -> None:
    """random.Random(42) → byte-identical lists across two calls."""
    a = generate_releases(count=3000, seed=42)
    b = generate_releases(count=3000, seed=42)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_shape_variety_contract_preserved() -> None:
    """Every shape from the v1.0 fixture header is represented in the generator output."""
    releases = generate_releases(count=3000, seed=42)
    catalogs = [r["catalog_number"] for r in releases if r["catalog_number"]]
    # Required shapes per the v1.0 fixture header contract:
    assert any("BLP" in c for c in catalogs), "missing BLP prefix"
    assert any("BST" in c for c in catalogs), "missing BST prefix"
    assert any("ECM" in c for c in catalogs), "missing ECM prefix"
    assert any("KC" in c for c in catalogs), "missing KC prefix"
    assert any("," in c for c in catalogs), "missing multi-value comma catalog"
    assert any(c.isdigit() for c in catalogs), "missing pure-numeric catalog"


def test_fake_discogsography_shim_re_exports_canonical() -> None:
    """tests.fixtures.fake_discogsography must re-export the canonical module's function."""
    from gruvax._internal.fake_discogsography import create_fake_app as canonical
    from tests.fixtures.fake_discogsography import create_fake_app as shim

    assert canonical is shim
