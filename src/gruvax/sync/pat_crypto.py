"""Fernet helpers for PAT-at-rest encryption (P1 D-01, T-01-PAT-rest mitigation).

Security rules (non-negotiable):
  - NEVER store the PAT in plaintext at rest. The database column
    ``gruvax.profiles.app_token_encrypted`` is the ONLY persisted form.
  - NEVER catch ``InvalidToken`` silently. The caller (sync_profile) treats
    a decrypt failure as an operator-actionable signal: ``last_sync_status
    = 'failed'`` and ``last_sync_error = 'pat_rejected'``. Swallowing the
    error would orphan the row in a confusing "PAT present but unusable"
    state with no log trail.
  - NEVER include the PAT plaintext in any log line. The structlog
    redactor at ``gruvax.discogsography.log_redactor.redact_dscg_tokens``
    masks the substring at the processor level, but the callsite is
    responsible for not constructing log dicts that depend on the PAT.

Public API:
  - ``encrypt_pat(plaintext: str) -> bytes`` — produces a Fernet ciphertext
    suitable for direct INSERT into ``BYTEA``.
  - ``decrypt_pat(ciphertext: bytes) -> str`` — returns the plaintext PAT.
    Raises ``cryptography.fernet.InvalidToken`` if the ciphertext was
    produced under a different ``GRUVAX_SECRET_KEY`` (operator-actionable —
    re-issue the PAT via ``gruvax-set-pat``).

Lazy Fernet construction (PATTERNS §5 — differs from auth/pin's eager
``_ctx`` singleton): the Fernet instance is built on each call rather than
at module import. This avoids ordering dependencies on settings load AND
lets the migration import ``pat_crypto`` (for the seed-row placeholder
write) before ``GRUVAX_SECRET_KEY`` is provided. The env-var read happens
at call time, so tests can ``monkeypatch.setenv("GRUVAX_SECRET_KEY", ...)``
between operations.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


__all__ = ["decrypt_pat", "encrypt_pat"]


_ENV_VAR = "GRUVAX_SECRET_KEY"


def _fernet() -> Fernet:
    """Build a Fernet instance from the live ``GRUVAX_SECRET_KEY`` env var.

    Reads the env var (not ``settings.GRUVAX_SECRET_KEY``) so this module
    can import cleanly even when Plan 01-01's Settings extension has not
    landed yet — sibling plan timing. Once the Settings field exists, both
    approaches resolve to the same value (pydantic-settings reads env).

    Raises:
        RuntimeError: if ``GRUVAX_SECRET_KEY`` is not set in the
            environment when ``encrypt_pat`` / ``decrypt_pat`` is invoked.
        ValueError: if the key is malformed (not URL-safe base64-encoded
            32 random bytes). Propagated from ``Fernet()``'s constructor.
    """
    key = os.environ.get(_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{_ENV_VAR} is not set — cannot encrypt/decrypt PATs. "
            f"Generate a key with: "
            f'python -c "from cryptography.fernet import Fernet; '
            f'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def encrypt_pat(plaintext: str) -> bytes:
    """Encrypt a plaintext PAT for at-rest storage.

    Args:
        plaintext: the PAT string (e.g. ``dscg_…``) to encrypt.

    Returns:
        Fernet ciphertext bytes (URL-safe base64 inside) suitable for
        ``INSERT INTO gruvax.profiles (app_token_encrypted) VALUES (%s)``.
    """
    return _fernet().encrypt(plaintext.encode())


def decrypt_pat(ciphertext: bytes) -> str:
    """Decrypt a previously-encrypted PAT.

    Args:
        ciphertext: the bytes loaded from
            ``gruvax.profiles.app_token_encrypted``.

    Returns:
        The plaintext PAT string.

    Raises:
        cryptography.fernet.InvalidToken: if the ciphertext was produced
            with a different ``GRUVAX_SECRET_KEY`` (key rotation orphan)
            or has been tampered with. The caller (``sync_profile``)
            translates this to ``last_sync_status='failed'`` +
            ``last_sync_error='pat_rejected'``.
    """
    return _fernet().decrypt(ciphertext).decode()
