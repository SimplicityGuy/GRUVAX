"""The one way an admin write rebuilds its profile's derived caches.

Every admin endpoint that mutates ``gruvax.cube_boundaries`` or
``gruvax.segment_overrides`` has to refresh the in-memory structures the kiosk
reads from.  That was open-coded at seven call sites, and each copy drifted:

  - gruvax-591 — four of them re-derived from a hand-built override dict
    covering only the edited bin, silently clearing every other cube's width
    override in the live cache.
  - gruvax-cxy — all seven invalidated the caches BEFORE rebuilding, so a
    failure anywhere in the rebuild left them empty and killed every locate in
    the app.
  - gruvax-xkc — all seven called ``load(pool)`` with no ``profile_id``, so a
    write scoped to profile B refreshed profile A's cache.

One function now owns the sequence, so those three fixes cannot drift apart
again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from gruvax.api.deps import WriteContext


async def rebuild_derived_caches(pool: Any, ctx: WriteContext) -> None:
    """Reload the BoundaryCache and re-derive the SegmentCache for one profile.

    MUST be called AFTER the write transaction has committed (Pitfall A) — never
    inside it, or a rollback leaves the caches describing rows that do not exist.

    Ordering contract (all three are load-bearing):

    1. Scope by ``ctx.profile_id``.  ``ctx`` carries the profile's OWN cache
       objects out of the registries, so the scoped read lands in the scoped
       cache.  Passing a profile_id to the default-profile alias instead would
       overwrite the kiosk's live cache with another profile's rows.
    2. Re-derive from ``boundary_cache.overrides`` — the complete override set
       the ``load()`` on the line above just read.  Anything narrower reverts
       the overrides it omits.
    3. Do NOT invalidate first.  ``load()`` and ``derive()`` each publish their
       result only once fully built, so if either raises, the previous good
       cache keeps serving instead of the request leaving an empty one behind.

    Args:
        pool: The psycopg async connection pool.
        ctx:  The resolved per-profile write context (``get_write_context``).
    """
    # psycopg AsyncConnectionPool is invariant in its connection row type;
    # create_pool yields tuple-rows while load() declares object-rows. Runtime is
    # correct — the generic mismatch is known psycopg typing friction (app.py).
    await ctx.boundary_cache.load(pool, profile_id=ctx.profile_id)
    ctx.segment_cache.derive(ctx.boundary_cache, ctx.snapshot, ctx.boundary_cache.overrides)
