---
created: 2026-05-25T03:22:58.371Z
title: Reconcile gruvax vs gruvax_app Postgres role naming
area: database
files:
  - migrations/versions/0002_v_collection_view.py:16-21
  - justfile:67-72
  - compose.yaml:58,101,116
  - .env (DATABASE_URL)
  - src/gruvax/settings.py:21
---

## Problem

The runtime config and the operator-facing grant docs disagree on the name of the
Postgres role GRUVAX uses.

- The application **connects** as DB user `gruvax`:
  - `.env` → `DATABASE_URL=postgresql+psycopg://gruvax:...`
  - `compose.yaml:58` → `GRUVAX_DB_USER` default `gruvax` (also feeds the bundled
    dev Postgres `POSTGRES_USER` at line 101 and the healthcheck at line 116)
- The production **grant docs** reference a different role, `gruvax_app`:
  - migration 0002 GRANT NOTE — `migrations/versions/0002_v_collection_view.py:16-21`
    (`GRANT USAGE ON SCHEMA discogsography TO gruvax_app;` + SELECT grants)
  - the `just provision-db` recipe — `justfile:67-72` (same grants, `gruvax_app`)

An operator following `just provision-db` on the shared discogsography Postgres
would grant read access to `gruvax_app`, but the app authenticates as `gruvax` —
so in production the SELECT grants land on the wrong role and `gruvax.v_collection`
reads would fail until the mismatch is noticed.

This is the sole read-contact surface with discogsography (DEP-02), so getting the
role name right matters for the production cutover, even though it's a
doc/config-consistency fix with no code-behavior change in dev (dev uses the
bundled Postgres where `gruvax` owns everything).

## Solution

1. **Decide the canonical role name first** (the real decision in this task):
   - Likely answer: keep a distinct read-grant role `gruvax_app` on the shared
     discogsography instance (least-privilege, SELECT-only, separate from the
     `gruvax` schema owner), and have the app connect as that role in prod.
   - The dev container can stay `gruvax` (it owns the whole throwaway DB), OR be
     renamed to match prod for parity. Pick one and document the rationale.
2. Once decided, make the name consistent across all sites:
   - `.env` `DATABASE_URL` user
   - `compose.yaml` `GRUVAX_DB_USER` (+ note that this also sets dev
     `POSTGRES_USER` / healthcheck — changing it only takes effect on a fresh
     `gruvax-dev-pg-data` volume)
   - migration 0002 GRANT NOTE comment
   - `just provision-db` recipe
3. If prod and dev intentionally differ, add a one-line comment at each site
   explaining the split so a future reader doesn't "fix" it back into a mismatch.

Effort: small. No runtime behavior change for dev; this de-risks the production
cutover onto the shared discogsography Postgres on `lux`.

Route the execution through `/gsd-quick` per project workflow.
