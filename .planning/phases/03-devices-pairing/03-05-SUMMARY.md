---
phase: "03-devices-pairing"
plan: "05"
subsystem: "kiosk-provisioning"
tags: ["kiosk", "systemd", "playwright", "DEV-01", "reboot-persistence", "Pi"]
dependency_graph:
  requires:
    - "03-00 (playwright dev dep + browser test scaffold)"
    - "03-01 (fingerprint cookie + pairing-codes endpoint)"
    - "03-02 (admin bind endpoint)"
    - "03-04 (/pair frontend route)"
  provides:
    - "deploy/kiosk/start-kiosk.sh"
    - "deploy/kiosk/gruvax-kiosk.service"
    - "deploy/kiosk/README.md"
    - "tests/browser/conftest.py (live_server_url fixture)"
    - "tests/browser/test_reboot_persistence.py (GREEN)"
  affects:
    - "DEV-01 reboot-persistence criterion #2 proven in CI"
tech_stack:
  added: []
  patterns:
    - "uvicorn-in-thread live_server_url fixture (mirrors test_sse_per_profile.py + test_devices.py)"
    - "Playwright context.request.post() for API calls in browser context (cookie jar sharing)"
    - "launch_persistent_context with tmp user_data_dir for reboot simulation"
    - "context.close() + relaunch same dir = CI-faithful reboot simulation"
    - "crash-recovery Preferences exit_type patch in start-kiosk.sh"
key_files:
  created:
    - "deploy/kiosk/start-kiosk.sh"
    - "deploy/kiosk/gruvax-kiosk.service"
    - "deploy/kiosk/README.md"
    - "tests/browser/conftest.py"
  modified:
    - "tests/browser/test_reboot_persistence.py"
decisions:
  - "context.request.post() used for API calls in Playwright test — shares browser cookie jar, issues gruvax_device_fp into Chromium context without JS (HttpOnly cookie cannot be set via JavaScript)"
  - "live_server_url fixture uses separate asyncio loop for PIN seed (not the uvicorn loop on daemon thread)"
  - "start-kiosk.sh user-data-dir defaulted to ~/.local/share/gruvax-kiosk (SD card, not tmpfs — Pitfall 2)"
metrics:
  duration: "~6 minutes"
  completed_date: "2026-05-29"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
---

# Phase 3 Plan 05: Pi Provisioning Artifacts + Reboot Persistence Proof Summary

**One-liner:** Committed start-kiosk.sh + systemd --user unit launch Chromium at /pair with persistent SD-card user-data-dir; Playwright persistent-context round-trip proves the fingerprint cookie survives context close + relaunch (CI reboot simulation, 1 passed).

## What Was Built

### Task 1: Kiosk provisioning artifacts

**deploy/kiosk/start-kiosk.sh** — Chromium kiosk launcher:
- `set -euo pipefail`; `GRUVAX_URL="${GRUVAX_URL:-http://gruvax.lan/pair}"` default
- `USER_DATA_DIR="${USER_DATA_DIR:-${HOME}/.local/share/gruvax-kiosk}"` — SD card, NOT tmpfs (Pitfall 2)
- `mkdir -p "$USER_DATA_DIR"` creates the profile dir on first run
- Preferences `exit_type` Crashed→Normal patch to suppress restore-tabs dialog
- Full Wayland/labwc flag set: `--kiosk --noerrdialogs --disable-infobars --no-first-run --password-store=basic --ozone-platform=wayland --user-data-dir --app`
- Executable (`chmod +x`)

**deploy/kiosk/gruvax-kiosk.service** — systemd `--user` unit:
- `After=graphical-session.target`
- `ExecStart=%h/.config/gruvax/start-kiosk.sh`
- `Restart=always`, `RestartSec=3` (T-03-19 mitigation)
- `Environment=GRUVAX_URL=http://gruvax.lan/pair`

**deploy/kiosk/README.md** — provisioning guide:
- Install steps (copy + enable unit)
- Persistent storage requirement (Pitfall 2 warning, tmpfs check command)
- Pairing flow Mermaid sequence diagram
- Manual reboot smoke test (<30s end-to-end stopwatch, expected behavior, troubleshooting table)
- Chromium flags reference table

### Task 2: Playwright reboot-persistence test (TDD GREEN)

**tests/browser/conftest.py** — `live_server_url` fixture:
- `_find_free_port()` (socket bind to 127.0.0.1:0)
- Module-scoped fixture takes `db_pool`, builds `create_app()`, runs `uvicorn.Server` on daemon thread
- `server.install_signal_handlers = lambda: None` (no signal handling in thread)
- Waits up to 10s for `server.started`
- Seeds test PIN "0000" via `_seed_test_pin()` using a separate asyncio loop (not the uvicorn loop)
- Yields `http://127.0.0.1:{port}`

**tests/browser/test_reboot_persistence.py** — full GREEN implementation (replaced 03-00 scaffold):
- First launch: `context.request.post("/api/devices/pairing-codes")` → issues gruvax_device_fp cookie in Chromium cookie jar
- Admin login via `context.request.post("/api/admin/login")` → captures CSRF token
- Admin bind via `context.request.post("/api/admin/devices/bind", {"code": ...})` → device bound to default profile
- Asserts: `httpOnly=True`, `sameSite="Strict"`, `expires > time.time() + 86400` (not a session cookie)
- `context.close()` simulates Pi reboot / browser exit
- Second launch from SAME `user_data_dir`: asserts fingerprint cookie present with identical value
- `context.request.get("/api/session")` asserts `device_id != None` + `bound_profile_id != None`
- `pytest.importorskip("playwright")` guard at module level

## Verification Evidence

```
pytest tests/browser/test_reboot_persistence.py -x -v
============================= test session starts ==============================
...
tests/browser/test_reboot_persistence.py::test_fingerprint_persists_across_reboot PASSED

========================== 1 passed, 4 warnings in 1.25s =======================
```

```
bash -n deploy/kiosk/start-kiosk.sh  → exit 0 (valid shell syntax)
grep -q "gruvax.lan/pair" deploy/kiosk/start-kiosk.sh  → PASS
grep -q "Restart=always" deploy/kiosk/gruvax-kiosk.service  → PASS
grep -q "user-data-dir" deploy/kiosk/start-kiosk.sh  → PASS
[ -x deploy/kiosk/start-kiosk.sh ]  → PASS (chmod +x)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] .env symlink required for worktree test run**
- **Found during:** Task 2 verification — `pydantic_settings` `Settings()` failed (DATABASE_URL / SESSION_SECRET required)
- **Issue:** The worktree has no `.env` file (only `.env.example`). `settings.py` reads `env_file=".env"` relative to cwd. The main GRUVAX repo has `.env` at its root but the worktree doesn't inherit it.
- **Fix:** Created symlink `.env → /Users/Robert/Code/public/GRUVAX/.env` in the worktree root. The symlink is not git-tracked (`.env` is gitignored) and matches the established pattern for worktree test runs.
- **Files modified:** None (symlink only, not committed)

**2. [Rule 2 - Missing] context.request instead of page.goto for fingerprint cookie issuance**
- **Found during:** Task 2 implementation review — the RESEARCH Pattern 5 scaffold navigated to `/pair` and then checked cookies. But in the test environment, the SPA bundle may not be built (no `static/` directory), so `page.goto("/pair")` would not trigger `POST /api/devices/pairing-codes` automatically.
- **Fix:** Used `context.request.post()` (Playwright's API request client, which shares the browser's cookie jar) to call the endpoint directly. This is more reliable in CI and tests the exact contract: the fingerprint cookie is issued by `POST /api/devices/pairing-codes`, not by SPA load. The HttpOnly cookie is correctly set in Chromium's cookie store via the response `Set-Cookie` header.

## Known Stubs

None. All provisioning artifacts are fully implemented. The test is fully implemented and passes.

## Threat Flags

No new threat surface introduced:
- `deploy/kiosk/` files are shell scripts and INI files — no new network endpoints or auth paths
- `tests/browser/conftest.py` and `tests/browser/test_reboot_persistence.py` are test-only files
- The kiosk launcher artifacts address T-03-18 (cookie persistence) and T-03-19 (process supervision) as planned

## Self-Check: PASSED

Files created:
- deploy/kiosk/start-kiosk.sh ✓
- deploy/kiosk/gruvax-kiosk.service ✓
- deploy/kiosk/README.md ✓
- tests/browser/conftest.py ✓

Files modified:
- tests/browser/test_reboot_persistence.py ✓

Commits:
- 04dd2cc: feat(03-05): kiosk provisioning artifacts — start-kiosk.sh + systemd unit + README ✓
- eb7ccd0: feat(03-05): Playwright reboot-persistence test — live_server_url + full bind round-trip ✓
