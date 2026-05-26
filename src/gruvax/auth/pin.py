"""PIN hashing and verification for GRUVAX admin authentication.

Uses passlib CryptContext with Argon2id — a memory-hard algorithm that resists
brute-force and GPU attacks (T-03-04, D-01).

Security rules (non-negotiable):
  - NEVER compare hash strings with ``==``.  Use ``_ctx.verify()`` only.
  - NEVER log the raw PIN.  Log ``pin_attempt=redacted`` instead (Pitfall 12).
  - NEVER store the PIN in plaintext or in environment variables.
    The hash lives in ``gruvax.settings`` key ``auth.pin_hash`` (D-02).
"""

from __future__ import annotations

from passlib.context import CryptContext


# Argon2id context — memory-hard, GPU-resistant (T-03-04).
# ``deprecated="auto"`` ensures older hash schemes are upgraded on next verify.
_ctx = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_pin(pin: str) -> str:
    """Hash a 4-digit PIN using Argon2id.

    Each call produces a unique hash (random salt) even for the same PIN.
    Store the result in ``gruvax.settings`` key ``auth.pin_hash`` — never in
    an environment variable, config file, or source code.

    Args:
        pin: The raw 4-digit numeric PIN string to hash.

    Returns:
        An Argon2id hash string (opaque; not suitable for ``==`` comparison).
    """
    return _ctx.hash(pin)


def verify_pin(pin: str, hashed: str) -> bool:
    """Constant-time verify a PIN against its Argon2id hash.

    Returns ``False`` (not raises) on mismatch, empty input, or any error.
    NEVER compare ``hash_pin(pin) == hashed`` — use this function exclusively
    (Pitfall G).

    Args:
        pin:    The raw PIN string to check.
        hashed: The stored Argon2id hash from ``gruvax.settings auth.pin_hash``.

    Returns:
        ``True`` iff the PIN matches the hash; ``False`` otherwise.
    """
    try:
        return bool(_ctx.verify(pin, hashed))
    except Exception:
        # Invalid hash format or other error — treat as mismatch, not exception.
        return False
