---
phase: 07-wizards-import-export
reviewed: 2026-05-24T22:25:00Z
status: advisory
scope: backend import/export/migration (highest-risk surface)
blockers: 0
---

# Phase 7 Code Review — Backend Import/Export

Focused, advisory review of the new file-upload + atomic-write + secret-exclusion surface.
Non-blocking. Each finding was independently verified against the live interpreter/code
(the reviewer's first CRITICAL was a false positive, so all findings were re-checked).

## Verified clean
- `yaml.safe_load` only (boundary_yaml.py + import_settings); no `yaml.load` anywhere.
- Auth + CSRF on `POST /import/boundaries` and `POST /import/settings`; session on export GETs.
- Settings export uses an **allowlist** (`_ALLOWED_SETTINGS_KEYS`); `auth.pin_hash` is structurally
  excluded (verified `WHERE key = ANY(%s)`); a new key must be opted in explicitly. Unit test
  `test_no_pin_in_export` asserts absence. (D-14 / Pitfall 12 upheld.)
- `import_settings` rejects `auth.*` and unknown keys with 422 **before** any write.
- Boundaries import is atomic: single `async with conn.transaction():` wraps write_boundary +
  history row + segment_overrides upserts + idempotency store (D-09 upheld).
- Reuses `validate_contiguity` + `cube_exact_match` + `find_boundary_near_misses` (no divergent reimpl).
- `psycopg %s` parameterized SQL throughout; no f-string SQL.
- Migration 0007 round-trips (two-step DROP+ADD); downgrade T-07-02 risk documented + unavoidable.

## Findings

### DISMISSED (false positive) — `cubes.py:139` "Python 2 except syntax / service won't start"
The reviewer flagged `except TypeError, ValueError:` as a Py2 SyntaxError that prevents boot.
**Verified false on Python 3.14.5:** `py_compile` succeeds, `import gruvax.api.admin.cubes`
succeeds, `create_app()` builds, 32 backend tests pass, and a semantic test confirms it catches
ValueError correctly (bad value → 95 fallback; "120" → 120). Python 3.14 parses the bare
`TypeError, ValueError` as the tuple `(TypeError, ValueError)`. **Not a bug.**
- *Optional style nit:* add explicit parens `except (TypeError, ValueError):` for clarity.

### LOW/HARDENING — `import_.py:535–563` settings-import not in explicit transaction
Settings writes loop with individual `UPDATE`s then a trailing `conn.commit()`, without the
explicit `async with conn.transaction():` that the boundaries path uses. With psycopg3's default
`autocommit=False` + pool rollback-on-exception, and validation running fully before any write,
this is **not a live partial-write bug** — but wrapping the loop in `conn.transaction()` (and
dropping the redundant `commit()`) would make the "no partial settings write" guarantee explicit
and consistent with the boundaries path. **Recommended, low-risk, ~2 lines.**

### MINOR — `import_.py:542–548` `_INT_KEYS` range gap + silent skip
`cube.nominal_capacity` / `session.idle_ttl_seconds` are range-unchecked on import, and the write
loop `continue`s on an unparseable int instead of raising 422. Consistent with the existing
`update_settings` PUT (which also lacks these range checks), so not a regression. Tighten only if
settings validation is hardened project-wide.

### ACCEPTED — `import_.py:133–138` size cap after full-body buffer
`request.body()` buffers the whole upload before the 100 KB cap is checked. Accepted for a
single-authenticated-admin LAN kiosk; docstring could say "enforced before parse (after read)".

## Recommendation
No blockers. Optionally apply the LOW/HARDENING settings-transaction change before/with the human
UAT pass. Everything else is verified correct.
