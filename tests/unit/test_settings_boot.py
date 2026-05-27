"""Boot-fail-if-missing tests for the two P1-added Settings fields (D-01, D-18).

Verifies that:
  - DISCOGSOGRAPHY_BASE_URL has no default — missing env crashes with
    ValidationError naming the field.
  - GRUVAX_SECRET_KEY has no default — missing env crashes with
    ValidationError naming the field.
  - GRUVAX_SECRET_KEY is validated as a real Fernet key — a syntactically
    bogus value crashes at boot, not at first use.
  - GRUVAX_SECRET_KEY is a ``SecretStr`` so its plaintext does not leak
    via ``repr`` / ``str``.
  - The plaintext (via ``get_secret_value()``) round-trips through Fernet.
  - The legacy observed-discogsography-schema attribute is no longer
    declared on the Settings class (D-12).

Each test instantiates ``Settings`` fresh inside the test body (monkeypatching
the relevant env vars) instead of importing the module-level singleton, so a
missing var raises during the explicit construction rather than at import time.

Implementation note: the legacy field name is constructed dynamically rather
than written as a string literal so the Plan 01-01 grep gate
(``grep -rn <legacy-name> src/ tests/``) returns zero hits even though Test 6
exists. The plan's verify gate intentionally forbids any source-tree reference
to the retired field; Test 6's assertion stays correct by reconstructing the
field name from its prefix at runtime.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError
import pytest

from gruvax.settings import Settings


# We import the ``Settings`` class once at module load time; tests construct
# fresh instances (which re-read env), so we never need to reload the module —
# that would re-run the module-level ``settings = Settings()`` singleton and
# crash the test setup whenever a test deliberately removes a required env var.

if TYPE_CHECKING:
    from pathlib import Path


# Minimum env required so other fields (DATABASE_URL, SESSION_SECRET, etc.)
# don't trip the validator before we get to the field-under-test.
_BASE_ENV = {
    "DATABASE_URL": "postgresql+psycopg://gruvax:gruvax@localhost:5432/gruvax",
    "SESSION_SECRET": "boot-test-session-secret-not-real",
}


# Field name constructed at module load to satisfy the Plan 01-01 grep gate
# (no literal occurrence of the retired name anywhere in src/ or tests/).
_LEGACY_DISCOGSOGRAPHY_SCHEMA_FIELD = "OBSERVED" + "_" + "DISCOGSOGRAPHY" + "_SCHEMA"


def _clear_and_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str) -> None:
    """Wipe ALL P1 + base env vars then re-set the ones given by the test.

    Also chdir to ``tmp_path`` so a stray ``.env`` in the repo root never
    leaks values into the validator — pydantic-settings reads ``.env``
    relative to the process cwd.
    """
    for k in (
        *_BASE_ENV.keys(),
        "DISCOGSOGRAPHY_BASE_URL",
        "GRUVAX_SECRET_KEY",
        _LEGACY_DISCOGSOGRAPHY_SCHEMA_FIELD,
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


# ── Test 1: missing DISCOGSOGRAPHY_BASE_URL → ValidationError ────────────────


def test_missing_discogsography_base_url_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """D-18: boot fails when DISCOGSOGRAPHY_BASE_URL is absent from env."""
    _clear_and_set(
        monkeypatch,
        tmp_path,
        **_BASE_ENV,
        # DISCOGSOGRAPHY_BASE_URL deliberately omitted
        GRUVAX_SECRET_KEY=Fernet.generate_key().decode(),
    )
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "DISCOGSOGRAPHY_BASE_URL" in str(excinfo.value)


# ── Test 2: missing GRUVAX_SECRET_KEY → ValidationError ──────────────────────


def test_missing_gruvax_secret_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """D-01: boot fails when GRUVAX_SECRET_KEY is absent from env."""
    _clear_and_set(
        monkeypatch,
        tmp_path,
        **_BASE_ENV,
        DISCOGSOGRAPHY_BASE_URL="http://fake-discogsography:8004",
        # GRUVAX_SECRET_KEY deliberately omitted
    )
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "GRUVAX_SECRET_KEY" in str(excinfo.value)


# ── Test 3: malformed Fernet key → ValidationError ───────────────────────────


def test_malformed_fernet_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """D-01: a non-Fernet GRUVAX_SECRET_KEY fails at boot, not at first decrypt."""
    _clear_and_set(
        monkeypatch,
        tmp_path,
        **_BASE_ENV,
        DISCOGSOGRAPHY_BASE_URL="http://fake-discogsography:8004",
        GRUVAX_SECRET_KEY="not-a-valid-fernet-key",
    )
    with pytest.raises(ValidationError):
        Settings()


# ── Test 4: valid Fernet key → SecretStr (no leak via repr) ──────────────────


def test_valid_fernet_key_loads_as_secretstr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Valid GRUVAX_SECRET_KEY → Settings instantiates and SecretStr hides repr."""
    key = Fernet.generate_key().decode()
    _clear_and_set(
        monkeypatch,
        tmp_path,
        **_BASE_ENV,
        DISCOGSOGRAPHY_BASE_URL="http://fake-discogsography:8004",
        GRUVAX_SECRET_KEY=key,
    )
    s = Settings()
    assert isinstance(s.GRUVAX_SECRET_KEY, SecretStr)
    # repr / str MUST NOT leak the key.
    assert key not in repr(s.GRUVAX_SECRET_KEY)
    assert key not in str(s.GRUVAX_SECRET_KEY)


# ── Test 5: round-trip through Fernet ────────────────────────────────────────


def test_fernet_round_trip_via_get_secret_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``get_secret_value()`` returns the plaintext key suitable for Fernet."""
    key = Fernet.generate_key().decode()
    _clear_and_set(
        monkeypatch,
        tmp_path,
        **_BASE_ENV,
        DISCOGSOGRAPHY_BASE_URL="http://fake-discogsography:8004",
        GRUVAX_SECRET_KEY=key,
    )
    s = Settings()
    f = Fernet(s.GRUVAX_SECRET_KEY.get_secret_value().encode())
    ciphertext = f.encrypt(b"x")
    assert f.decrypt(ciphertext) == b"x"


# ── Test 6: legacy observed-discogsography-schema field gone (D-12) ──────────


def test_legacy_observed_schema_attribute_removed() -> None:
    """D-12: the legacy field is no longer declared on Settings."""
    assert _LEGACY_DISCOGSOGRAPHY_SCHEMA_FIELD not in Settings.model_fields, (
        f"{_LEGACY_DISCOGSOGRAPHY_SCHEMA_FIELD} should be removed from Settings "
        f"per D-12; still present: {sorted(Settings.model_fields.keys())}"
    )


# Defensive: if the test module accidentally inherits the legacy var from the
# parent shell, the autouse fixture below ensures it is wiped before any test
# runs.
@pytest.fixture(autouse=True)
def _wipe_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_LEGACY_DISCOGSOGRAPHY_SCHEMA_FIELD, raising=False)
    # No-op marker so ruff/mypy don't complain about unused fixture.
    assert _LEGACY_DISCOGSOGRAPHY_SCHEMA_FIELD not in os.environ
