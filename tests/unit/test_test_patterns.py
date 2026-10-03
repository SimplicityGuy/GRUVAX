"""The policy must reject missing behavior while allowing deliberate benchmark/platform skips."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_test_patterns import analyze


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        (
            "def test_route(response):\n    if response.status_code == 404:\n        return\n    assert response.status_code == 200\n",
            "status-early-return",
        ),
        ("def test_empty():\n    pass\n", "no-behavior-assertion"),
        (
            "def test_result(result):\n    if result is not None:\n        assert result.value > 0\n",
            "nullable-invariant-without-census",
        ),
    ],
)
def test_structural_policy_rejects_vacuous_paths(source: str, kind: str) -> None:
    findings = analyze(source, "tests/property/test_probe.py")
    assert kind in {finding.kind for finding in findings}


def test_non_null_assertion_is_a_census_floor() -> None:
    source = "def test_result(result):\n    assert result is not None\n    if result is not None:\n        assert result.value > 0\n"
    assert not analyze(source, "tests/property/test_probe.py")


@pytest.mark.parametrize(
    "floor", ["results == []", "len(results) == 0", "count == 0", "len(results) >= 0"]
)
def test_empty_collector_is_not_a_census_floor(floor: str) -> None:
    source = f"def test_result(result):\n    results = []\n    count = 0\n    if result is not None:\n        results.append(result)\n        count += 1\n        assert result.value > 0\n    assert {floor}\n"
    assert "nullable-invariant-without-census" in {
        f.kind for f in analyze(source, "tests/property/test_probe.py")
    }


@pytest.mark.parametrize(
    "floor", ["results", "len(results) > 0", "count >= 1", "len(results) == 2"]
)
def test_positive_collector_is_a_census_floor(floor: str) -> None:
    source = f"def test_result(result):\n    results = []\n    count = 0\n    if result is not None:\n        results.append(result)\n        count += 1\n        assert result.value > 0\n    assert {floor}\n"
    assert not analyze(source, "tests/property/test_probe.py")


@pytest.mark.parametrize(
    ("source", "code", "message"),
    [
        (
            "import pytest\ndef test_feature():\n    pytest.skip('route not implemented')\n",
            1,
            "Unexpected runtime skip",
        ),
        (
            "import pytest\n@pytest.mark.skip(reason='route not implemented')\ndef test_feature():\n    pass\n",
            1,
            "Unexpected runtime skip",
        ),
        (
            "import pytest\n@pytest.mark.skip(reason='requires another platform')\ndef test_platform():\n    pass\n",
            0,
            "skipped",
        ),
        ("def test_feature():\n    assert 1 == 1\n", 0, "passed"),
    ],
)
def test_runtime_skip_policy(tmp_path: Path, source: str, code: int, message: str) -> None:
    (tmp_path / "test_probe.py").write_text(source)
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\naddopts =\n")
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(root), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(  # noqa: S603 — trusted test fixture, fixed interpreter/arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests.pattern_policy",
            "-c",
            str(config),
            str(tmp_path),
            "-q",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == code, result.stdout + result.stderr
    assert message in result.stdout + result.stderr
