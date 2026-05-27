"""Plan 02 Task 2 — Fernet PAT-at-rest helpers.

Tests 1-4 (per PLAN.md):
  1. Round-trip: encrypt → decrypt → original plaintext.
  2. InvalidToken raises (not silent) on garbage ciphertext.
  3. Cross-key fails: encrypt with key A, decrypt with key B → InvalidToken.
  4. Lazy fernet: pat_crypto module imports successfully even when
     GRUVAX_SECRET_KEY is unset (the env-var check runs at call time).
"""

from __future__ import annotations

import importlib

from cryptography.fernet import Fernet, InvalidToken
import pytest

from gruvax.sync import pat_crypto


# Two fixed test keys — generated once with Fernet.generate_key().
_TEST_KEY_A = b"BNvJpRRGOIDvBuKbHEU5OWZTrIFRWxbk9_ZkPSCHA8c="
_TEST_KEY_B = b"qhh7H03Q9OQ6yKZHrFhcQO9XKzKM_DXf1zZsT5q1bAo="


@pytest.fixture
def key_a(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set GRUVAX_SECRET_KEY=_TEST_KEY_A for the duration of one test."""
    monkeypatch.setenv("GRUVAX_SECRET_KEY", _TEST_KEY_A.decode())
    return _TEST_KEY_A.decode()


def test_round_trip(key_a: str) -> None:
    """Test 1: encrypt(plaintext) → decrypt(ciphertext) == plaintext.

    Also verify ciphertext is bytes and != plaintext bytes.
    """
    plaintext = "dscg_test_pat_abc123"
    ciphertext = pat_crypto.encrypt_pat(plaintext)
    assert isinstance(ciphertext, bytes), "encrypt_pat must return bytes"
    assert ciphertext != plaintext.encode(), "ciphertext must not equal plaintext bytes"
    recovered = pat_crypto.decrypt_pat(ciphertext)
    assert recovered == plaintext


def test_decrypt_invalid_token_raises(key_a: str) -> None:
    """Test 2: decrypt_pat(garbage) raises InvalidToken — does NOT silently return.

    The caller (sync_profile) treats InvalidToken as an operator-actionable
    signal (last_sync_error='pat_rejected'); silently returning would orphan
    the row in a confusing state.
    """
    with pytest.raises(InvalidToken):
        pat_crypto.decrypt_pat(b"not-a-fernet-token")


def test_cross_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 3: encrypt with key A, attempt decrypt with key B → InvalidToken.

    Models the GRUVAX_SECRET_KEY rotation scenario (D-01 deferred). The
    caller sets last_sync_status='failed' + last_sync_error='pat_rejected'
    so the operator re-issues the PAT via gruvax-set-pat.
    """
    monkeypatch.setenv("GRUVAX_SECRET_KEY", _TEST_KEY_A.decode())
    ciphertext = pat_crypto.encrypt_pat("dscg_cross_key_test")

    # Now rotate the key under the function's feet — mid-test.
    monkeypatch.setenv("GRUVAX_SECRET_KEY", _TEST_KEY_B.decode())
    with pytest.raises(InvalidToken):
        pat_crypto.decrypt_pat(ciphertext)


def test_lazy_fernet_import_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 4: pat_crypto module imports cleanly with GRUVAX_SECRET_KEY unset.

    The validator runs at _fernet() call time (lazy), not at module import.
    This lets:
      - tests import pat_crypto without bootstrapping the full env.
      - the Alembic migration import pat_crypto for the seed-row placeholder
        without bringing GRUVAX_SECRET_KEY into the migration context.

    Reload the module under a delenv to be sure — the import statement
    above this fixture has already run with whatever env was set.
    """
    monkeypatch.delenv("GRUVAX_SECRET_KEY", raising=False)
    # Reload pat_crypto under the cleared env.
    reloaded = importlib.reload(pat_crypto)
    # The module is importable, and the constants/functions are exported.
    assert hasattr(reloaded, "encrypt_pat")
    assert hasattr(reloaded, "decrypt_pat")
    # But calling them raises clearly, not Settings-validation noise.
    with pytest.raises(RuntimeError, match=r"GRUVAX_SECRET_KEY"):
        reloaded.encrypt_pat("dscg_test_pat")


def test_fernet_generate_key_format_sanity() -> None:
    """Sanity: Fernet.generate_key() output is the format our test keys use.

    Bus-factor defence — if the cryptography library's key format ever
    changes, the test keys above will silently rot. This test fails fast.
    """
    generated = Fernet.generate_key()
    assert isinstance(generated, bytes)
    assert len(generated) == 44  # URL-safe base64-encoded 32 bytes
