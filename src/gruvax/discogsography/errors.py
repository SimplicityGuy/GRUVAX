"""Typed exceptions for DiscogsographyClient (P1, PATTERNS §4).

Plain Python exceptions — no Pydantic. The class hierarchy lets ``sync_profile``
map terminal client errors to ``last_sync_error`` tag strings without string
parsing:

  - ``PATRejected``        → ``last_sync_error = 'pat_rejected'``  (401/403)
  - ``RateLimitExhausted`` → ``last_sync_error = 'rate_limited'``  (429 after retries)
  - ``ServerError``        → ``last_sync_error = 'server_error'``  (5xx after retries)
  - ``NetworkError``       → ``last_sync_error = 'network'``       (timeouts after retry)
  - ``SyncInProgress``     → 409 surface, not a sync-failure tag

Security invariant (Test 11 in Plan 02 Task 3 + T-01-error-shape-leak in threat model):
The constructor messages MUST be operator-safe — NEVER include the PAT plaintext
or the raw ``Authorization`` header value.
"""

from __future__ import annotations


class DiscogsographyError(Exception):
    """Base for all DiscogsographyClient errors."""


class PATRejected(DiscogsographyError):
    """401/403 from discogsography — terminal, no retry. Caller sets app_token_revoked=TRUE."""


class RateLimitExhausted(DiscogsographyError):
    """429 retried max times — propagates ``last_sync_error = 'rate_limited'``."""


class ServerError(DiscogsographyError):
    """5xx retried max times — propagates ``last_sync_error = 'server_error'``."""


class NetworkError(DiscogsographyError):
    """Connect/Read/WriteTimeout retried once then failed — ``'network'``."""


class SyncInProgress(DiscogsographyError):
    """pg_try_advisory_lock returned FALSE — another sync is already running for this profile."""
