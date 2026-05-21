"""Shared SlowAPI limiter instance for GRUVAX admin endpoints.

The limiter must be a singleton so that:
  1. ``@limiter.limit()`` decorators in ``login.py`` register limits on
     this instance's ``_route_limits`` dict.
  2. ``app.state.limiter`` (set in ``app.py``) points to this same instance
     so ``SlowAPIMiddleware`` enforces those limits correctly.

Import this module instead of creating a new ``Limiter()`` in each file.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Singleton limiter — used by both @limiter.limit() decorators and
# assigned to app.state.limiter in create_app().
limiter = Limiter(key_func=get_remote_address)
