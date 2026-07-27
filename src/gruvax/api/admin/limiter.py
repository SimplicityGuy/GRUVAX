"""Login rate-limiter singleton for GRUVAX admin endpoints.

The limiter is built on the public ``limits`` library (slowapi's own dependency)
so it does NOT depend on any slowapi private attributes.  This makes the
brute-force guard stable across slowapi upgrades.

Exposed names
-------------
limiter : MemoryStorage
    The shared in-process storage backend.  Tests call ``limiter.reset()`` to
    clear the counter between runs.

_rate_limiter : FixedWindowRateLimiter
    The strategy object.  ``login.py`` calls
    ``_rate_limiter.hit(_LOGIN_RATE, "login", client_ip)`` to enforce the limit.

_LOGIN_RATE : RateLimitItem
    Parsed rate-limit spec: 5 attempts per 5-minute window.
"""

from __future__ import annotations

from limits import parse as parse_limit
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter


# Shared in-process storage — ``limiter.reset()`` used by tests to clear state.
# Rate-limit key is the direct socket peer IP (``request.client.host``), which
# is correct for GRUVAX's single-host home-LAN deployment with NO reverse proxy.
# If a proxy is introduced, configure trusted X-Forwarded-For / ProxyHeaders
# handling so the limit keys on the real client IP rather than the proxy.
limiter: MemoryStorage = MemoryStorage()

# Fixed-window strategy — 5 login attempts per 5-minute window per IP.
_rate_limiter: FixedWindowRateLimiter = FixedWindowRateLimiter(limiter)

# Parsed once at module load so the limit item is not re-parsed on every request.
_LOGIN_RATE = parse_limit("5/5minutes")

# Device bind rate limit — 10 attempts per 5-minute window per IP.
# Shared storage singleton; namespace key is "device_bind" (vs "login" for login).
# At 10k code keyspace, exhausting this limit eliminates only 10 codes per window
# — brute-force is infeasible even against repeated window resets (RESEARCH.md Pattern 3).
_BIND_RATE = parse_limit("10/5minutes")

# Invite redeem rate limit — 5 attempts per 10-minute window per IP.
# Public endpoint accepting a secret (member PAT) — lower limit than device bind
# to slow brute-force code enumeration (T-07-05). Namespace key "invite_redeem"
# keeps it isolated from the login and device_bind counters.
_REDEEM_RATE = parse_limit("5/10minutes")

# Pairing-code GENERATION rate limit — 30 attempts per 5-minute window per IP
# (gruvax-8fp). POST /api/devices/pairing-codes is intentionally unauthenticated
# (a kiosk hasn't paired yet), so without this, any LAN client could loop the
# endpoint and exhaust the 10,000-code CHAR(4) namespace in seconds. 30/5min
# comfortably covers a legitimate kiosk's steady-state 1-per-5-min auto-reroll
# plus the occasional gruvax-7j5 failure-retry burst, while still bounding
# worst-case abuse. Namespace key "pairing_generate" keeps it isolated from the
# other counters above.
_PAIRING_GENERATE_RATE = parse_limit("30/5minutes")
