"""Build a one-shot ``Cookie`` request header from an httpx ``Cookies`` jar or dict.

Replaces the deprecated per-request ``cookies=`` keyword (httpx 0.28+) while
preserving its observable behaviour. Background:

* An ``httpx.AsyncClient`` auto-persists ``Set-Cookie`` from login responses
  into its own jar. Passing ``cookies=<jar>`` per request then sends *both* the
  client-jar cookie and the per-request cookie, so the server receives a
  duplicate (e.g. ``gruvax_session=A; gruvax_session=A``) and Starlette resolves
  it to the last value.
* Sending an explicit ``Cookie`` header instead overrides the client jar
  entirely, so the server receives exactly the intended cookies — single, not
  duplicated — without mutating the (often module-scoped, shared) client jar.

Use it in place of ``cookies=``::

    await client.get(url, headers=cookie_header(auth["cookies"]))
    await client.post(url, headers={"X-CSRF-Token": tok, **cookie_header(jar)})

When a request needs cookies that live *only* on the client jar (a different
name than what is passed per-request), include them explicitly here too — a
``Cookie`` header replaces the jar rather than merging with it.
"""

from __future__ import annotations

from typing import Any


def cookie_header(*sources: Any) -> dict[str, str]:
    """Return ``{"Cookie": "<k>=<v>; ..."}`` from one or more httpx Cookies jars/dicts.

    Multiple sources are merged left-to-right (later sources win on a name clash),
    which is how you preserve a request that previously relied on *both* the
    client's persisted jar *and* a per-request ``cookies=`` override::

        # was: client.get(url, cookies=fp_cookies)  # jar + fp_cookies (union)
        client.get(url, headers=cookie_header(client.cookies, fp_cookies))
    """
    merged: dict[str, str] = {}
    for source in sources:
        items = source.items() if hasattr(source, "items") else source
        merged.update(items)
    return {"Cookie": "; ".join(f"{name}={value}" for name, value in merged.items())}
