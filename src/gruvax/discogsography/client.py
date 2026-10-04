"""Async HTTP client for the discogsography v2 integration contract v1.

Public surface (Plan 02 Task 3):
  - ``DiscogsographyClient``     — async wrapper around ``httpx.AsyncClient``.
  - ``DiscogsographyClient._get_page``      — paged collection fetch with retry.
  - ``DiscogsographyClient.first_page``     — envelope-returning convenience.
  - ``DiscogsographyClient.fetch_user_id``  — limit=1 test-sync helper.
  - ``DiscogsographyClient.iter_collection``— async iterator over all releases.
  - ``DiscogsographyClient.aclose``         — release the underlying transport.

Retry semantics (CONTEXT.md §specifics — LOCKED):
  - 401/403: ``PATRejected`` immediately (no retry).
  - 429: honor ``Retry-After`` header (seconds; HTTP-date defended), then
    exponential backoff. Max 3 retries (4 total attempts). Exhaustion →
    ``RateLimitExhausted``.
  - 5xx: exponential backoff. Max 3 retries (4 total attempts). Exhaustion
    → ``ServerError``.
  - ``httpx.ConnectError`` / ``ReadTimeout`` / ``WriteTimeout``: 1 retry
    (2 total attempts). Exhaustion → ``NetworkError``.

Security invariants (T-01-PAT-leak + T-01-error-shape-leak):
  - The ``Authorization`` header is set on the underlying ``AsyncClient``
    once at construction time. Per-request headers are NEVER logged.
  - Typed-error messages NEVER include the PAT plaintext. The structlog
    redactor at ``gruvax.discogsography.log_redactor`` defends if a future
    refactor accidentally interpolates the PAT into a log call.

Construct-per-sync lifetime (Open Q3 RESOLVED, RESEARCH.md):
  Each ``sync_profile`` invocation constructs a fresh client, calls
  ``aclose`` at the end. The long-lived ``app.state.discogsography_client``
  model is deferred to P2 (when per-profile clients become useful).
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import httpx
import stamina

from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
    SnapshotMismatch,
)
from gruvax.discogsography.snapshot_pages import SnapshotPin, validate_page


if TYPE_CHECKING:  # pragma: no cover — type-only imports
    from collections.abc import AsyncIterator


__all__ = ["DiscogsographyClient"]


# Retry tuning — kept short for tests; the actual backoff curve is set by
# stamina internally (exponential + jitter). wait_initial small enough that
# Test 4 / Test 6 don't wall-clock blow up; large enough that retries are
# observable in time-sensitive tests (Test 3, Test 10).
_HTTP_MAX_ATTEMPTS = 4  # 1 initial + 3 retries (per CONTEXT.md spec)
_MAX_RETRY_AFTER_SECONDS = 300
_NETWORK_MAX_ATTEMPTS = 2  # 1 initial + 1 retry (per CONTEXT.md spec)


def _parse_retry_after(value: str | None) -> dt.timedelta:
    """Parse a ``Retry-After`` header value, defending against HTTP-date drift.

    The discogsography v1 contract guarantees seconds. RESEARCH §Pitfall 4
    notes that if a future upstream library bump ever sends a date, an
    unguarded ``int()`` parse would crash. Default to 1s on any parse
    failure; valid numeric waits are capped at five minutes so a hostile or
    mistaken header cannot park a sync indefinitely. The cost of an aggressive retry is far smaller than the cost
    of a sync that silently dies on a contract drift.
    """
    if not value:
        return dt.timedelta(seconds=1)
    try:
        return dt.timedelta(seconds=min(_MAX_RETRY_AFTER_SECONDS, max(1, int(float(value)))))
    except TypeError, ValueError, OverflowError:
        return dt.timedelta(seconds=1)


class DiscogsographyClient:
    """Async client for discogsography v2 integration contract v1.

    Construct-per-sync — one instance per ``sync_profile`` call. The caller
    is responsible for ``await client.aclose()`` at the end of the operation
    (typically via ``async with`` or a ``try/finally``).
    """

    def __init__(self, base_url: str, pat: str, *, timeout: float = 10.0) -> None:
        # The Authorization header is set ONCE here. Per-request kwargs never
        # touch it, so the PAT cannot leak via per-request headers={}.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {pat}"},
            timeout=httpx.Timeout(timeout),
        )

    async def aclose(self) -> None:
        """Close the underlying transport. Idempotent."""
        await self._client.aclose()

    # ── retry predicates (per-error-class) ──────────────────────────────────

    @staticmethod
    def _should_retry_http(exc: BaseException) -> bool | dt.timedelta:
        """Stamina retry predicate for HTTP responses (429 + 5xx).

        Returns:
          False     — do NOT retry (raise out of the stamina loop).
          True      — retry with exp backoff.
          timedelta — retry after exactly this wait (used for 429 Retry-After).
        """
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            if code in (401, 403):
                # PATRejected — surface immediately, no retry.
                return False
            if code == 429:
                return _parse_retry_after(exc.response.headers.get("Retry-After"))
            if 500 <= code < 600:
                return True
        return False

    @staticmethod
    def _should_retry_network(exc: BaseException) -> bool:
        """Stamina retry predicate for network errors only."""
        return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout))

    # ── core paged fetch ────────────────────────────────────────────────────

    async def _get_page(
        self,
        *,
        limit: int,
        offset: int,
        snapshot: str | None = None,
        snapshot_generation: str | None = None,
    ) -> dict[str, Any]:
        """Fetch one page; apply locked retry semantics; raise typed errors.

        Architecture: two nested retry loops via ``stamina.retry_context``.
        The OUTER loop handles network errors (max 1 retry = 2 attempts).
        The INNER loop handles HTTP-response errors (max 3 retries = 4
        attempts). Network errors never get HTTP-retried (they happen
        before the response exists); HTTP errors never get network-retried.

        This separation is what lets Test 4 (429 → 4 calls) and Test 7
        (network → 2 calls) both pass under one ``_get_page`` implementation.
        """
        try:
            async for outer_attempt in stamina.retry_context(
                on=self._should_retry_network,
                attempts=_NETWORK_MAX_ATTEMPTS,
                timeout=None,  # Bound attempts, not elapsed Retry-After/request time.
                wait_initial=0.05,
                wait_max=0.1,
                wait_jitter=0.01,
            ):
                with outer_attempt:
                    return await self._do_inner_retry(
                        limit=limit,
                        offset=offset,
                        snapshot=snapshot,
                        snapshot_generation=snapshot_generation,
                    )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            # Stamina exhausted network retries — translate to typed error.
            raise NetworkError("network error reaching discogsography") from e

        # Defensive fallback — unreachable: the inner _do_inner_retry either
        # returns a value or raises a typed/HTTP error.
        raise NetworkError("network retry loop exhausted without an exception")

    async def _do_inner_retry(
        self,
        *,
        limit: int,
        offset: int,
        snapshot: str | None = None,
        snapshot_generation: str | None = None,
    ) -> dict[str, Any]:
        """Inner retry loop — HTTP-status errors (429/5xx) only.

        Stamina's exhaustion behavior re-raises the *last* exception out of
        the ``async for`` loop (the ``with attempt`` block does not swallow
        it). We catch the propagated ``HTTPStatusError`` here and translate
        it to the typed error before returning to the outer (network) loop.
        """
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if snapshot is not None:
            params["snapshot"] = snapshot
        if snapshot_generation is not None:
            params["snapshot_generation"] = snapshot_generation
        try:
            async for inner_attempt in stamina.retry_context(
                on=self._should_retry_http,
                attempts=_HTTP_MAX_ATTEMPTS,
                timeout=None,
                wait_initial=0.05,
                wait_max=2.0,  # cap so 429 Retry-After:1 still dominates wait
                wait_jitter=0.01,
            ):
                with inner_attempt:
                    resp = await self._client.get(
                        "/api/user/collection",
                        params=params,
                    )
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        code = e.response.status_code
                        if code in (401, 403):
                            # PATRejected: NEVER include the PAT in the
                            # message (Test 11 in PLAN.md). Fixed operator-
                            # safe string; the response body is not echoed
                            # either, since httpx error reprs can quote
                            # bodies that could in turn quote headers.
                            raise PATRejected("PAT rejected by discogsography (401/403)") from None
                        if snapshot is not None and code in (409, 410):
                            try:
                                detail = e.response.json().get("detail", {})
                                error_code = (
                                    detail.get("code") if isinstance(detail, dict) else None
                                )
                            except ValueError, AttributeError:
                                error_code = None
                            if isinstance(error_code, str) and (code, error_code) in {
                                (409, "snapshot_mismatch"),
                                (409, "snapshot_scope_mismatch"),
                                (409, "snapshot_unavailable"),
                                (410, "snapshot_expired"),
                            }:
                                raise SnapshotMismatch(
                                    "Collection snapshot unavailable or invalid"
                                ) from None
                        raise  # 429 / 5xx — let stamina decide to retry
                    # 2xx — return the envelope.
                    try:
                        data: dict[str, Any] = resp.json()
                    except ValueError:
                        if snapshot is not None:
                            raise SnapshotMismatch("Invalid collection snapshot envelope") from None
                        raise
                    return data
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                raise RateLimitExhausted("discogsography rate-limit retries exhausted") from e
            if 500 <= code < 600:
                raise ServerError(f"discogsography server error {code} after retries") from e
            # 4xx other than 401/403/429 — let it propagate untranslated.
            raise

        # Defensive fallback — unreachable: the loop either returns or raises.
        raise ServerError("discogsography retry loop exhausted without an exception")

    # ── consumer-facing helpers ────────────────────────────────────────────

    async def first_page(self) -> dict[str, Any]:
        """Return the first page envelope (limit=200, offset=0).

        Used by ``sync_profile`` to extract ``user_id`` from the response
        envelope before iterating the rest of the collection via the
        staging-swap path.
        """
        page = await self._get_page(limit=200, offset=0, snapshot="new")
        validate_page(page, offset=0, limit=200)
        return page

    async def fetch_user_id(self) -> str:
        """Test-sync helper: GET ``/api/user/collection?limit=1``, return ``user_id``.

        Used by ``gruvax-set-pat`` (Plan 04) to validate a freshly pasted
        PAT and capture the discogsography user UUID for the strict-rotation
        check (D-09).
        """
        page = await self._get_page(limit=1, offset=0)
        return str(page["user_id"])

    async def iter_pages(self, *, page_size: int = 200) -> AsyncIterator[dict[str, Any]]:
        """Yield validated pages from one immutable generation; never use live fallback."""
        if type(page_size) is not int or not 1 <= page_size <= 200:
            raise ValueError("page_size must be between 1 and 200")
        offset = 0
        pin: SnapshotPin | None = None
        while True:
            page = await self._get_page(
                limit=page_size,
                offset=offset,
                snapshot=pin.token if pin else "new",
                snapshot_generation=pin.generation if pin else None,
            )
            pin = validate_page(page, offset=offset, limit=page_size, pin=pin)
            yield page
            if not page["has_more"]:
                return
            offset += len(page["releases"])

    async def iter_collection(self, *, page_size: int = 200) -> AsyncIterator[dict[str, Any]]:
        """Yield releases only after their immutable snapshot page is validated."""
        async for page in self.iter_pages(page_size=page_size):
            for release in page["releases"]:
                yield release
