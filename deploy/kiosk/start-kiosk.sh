#!/usr/bin/env bash
# start-kiosk.sh — GRUVAX kiosk launcher for Raspberry Pi OS Trixie (Wayland/labwc)
#
# Invoked by systemd --user unit gruvax-kiosk.service via ExecStart.
# Copy this file to ~/.config/gruvax/start-kiosk.sh on the Pi and make it
# executable (chmod +x).
#
# Critical: --user-data-dir MUST be on the SD card (persistent storage), NOT on
# tmpfs or /tmp. The fingerprint cookie has max_age=30 days, but Chromium only
# writes cookies to disk if the user-data-dir is on a persistent filesystem.
# See: deploy/kiosk/README.md — "Persistent storage requirement (Pitfall 2)".
#
# Sources:
#   CLAUDE.md §Recommended Stack — Raspberry Pi Kiosk
#   .planning/phases/03-devices-pairing/03-RESEARCH.md Pattern 6

set -euo pipefail

GRUVAX_URL="${GRUVAX_URL:-http://gruvax.lan/pair}"
USER_DATA_DIR="${USER_DATA_DIR:-${HOME}/.local/share/gruvax-kiosk}"

mkdir -p "$USER_DATA_DIR"

# Remove crash flag so Chromium does not show "Restore tabs?" on restart.
# Chromium sets exit_type=Crashed in Preferences when killed ungracefully
# (e.g. systemd stopping the unit). Patching it to Normal before each launch
# suppresses the restore-tabs dialog in kiosk mode.
PREFS="${USER_DATA_DIR}/Default/Preferences"
if [ -f "$PREFS" ]; then
    sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PREFS" 2>/dev/null || true
fi

exec chromium-browser \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --password-store=basic \
    --ozone-platform=wayland \
    --user-data-dir="$USER_DATA_DIR" \
    --app="$GRUVAX_URL"
