"""Unit tests for PIN hashing and verification (ADMN-01).

These tests target ``gruvax.auth.pin`` (implemented in Plan 02).
They are authored RED in Plan 01 (Wave-0 scaffold) and go GREEN when
Plan 02 implements ``hash_pin`` and ``verify_pin``.

Analog: tests/unit/test_normalize.py (pure-function pattern).
"""

from __future__ import annotations

import pytest


def test_verify_correct_pin() -> None:
    """hash_pin then verify_pin with the same PIN returns True (ADMN-01)."""
    from gruvax.auth.pin import hash_pin, verify_pin

    hashed = hash_pin("1234")
    assert verify_pin("1234", hashed), "verify_pin must return True for a matching PIN"


def test_verify_wrong_pin() -> None:
    """verify_pin with a different PIN returns False — no exception (ADMN-01).

    Also guards Pitfall G: never compare hash strings with ==; use ctx.verify().
    """
    from gruvax.auth.pin import hash_pin, verify_pin

    hashed = hash_pin("1234")
    assert not verify_pin("5678", hashed), "verify_pin must return False for a wrong PIN"


def test_hash_pin_different_calls_produce_different_hashes() -> None:
    """Two calls to hash_pin on the same PIN produce different hashes (salt).

    Argon2id generates a random salt per hash; two hashes of the same PIN must
    differ (but both verify correctly).
    """
    from gruvax.auth.pin import hash_pin, verify_pin

    h1 = hash_pin("0000")
    h2 = hash_pin("0000")
    # Hashes should differ (random salt)
    assert h1 != h2, "Two hashes of the same PIN should differ (random salt)"
    # But both should verify correctly
    assert verify_pin("0000", h1)
    assert verify_pin("0000", h2)


def test_verify_non_pin_input() -> None:
    """verify_pin('', hashed) returns False — no exception for non-4-digit input."""
    from gruvax.auth.pin import hash_pin, verify_pin

    hashed = hash_pin("1234")
    assert not verify_pin("", hashed)
    assert not verify_pin("abcd", hashed)
