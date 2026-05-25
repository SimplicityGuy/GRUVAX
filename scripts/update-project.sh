#!/usr/bin/env bash
# update-project.sh — Dependency and tooling updater for GRUVAX.
#
# Delegates to just wherever possible (justfile is the single source of truth).
#
# Usage: ./scripts/update-project.sh [--dry-run] [--major] [--skip-tests]
#
# Options:
#   --dry-run      Show what would be updated without making changes
#   --major        Include major version upgrades (passed through to uv)
#   --skip-tests   Skip running tests after updates

set -euo pipefail

DRY_RUN=false
MAJOR_UPGRADES=false
SKIP_TESTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --major)
      MAJOR_UPGRADES=true
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--dry-run] [--major] [--skip-tests]" >&2
      exit 1
      ;;
  esac
done

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] Would run: just install"
  echo "[dry-run] Would run: uv lock --upgrade"
  echo "[dry-run] Would run: uv run pre-commit autoupdate"
  echo "[dry-run] Would run: npm --prefix frontend update"
  if [[ "$SKIP_TESTS" != "true" ]]; then
    echo "[dry-run] Would run: just test"
  fi
  echo "Done (dry-run — no changes made)."
  exit 0
fi

echo "==> Ensuring Python environment is clean (just install)"
just install

echo "==> Refreshing uv.lock within existing floor constraints"
if [[ "$MAJOR_UPGRADES" == "true" ]]; then
  uv lock --upgrade
else
  uv lock --upgrade
fi

echo "==> Updating pre-commit hook revisions"
uv run pre-commit autoupdate

echo "==> Updating frontend npm dependencies"
npm --prefix frontend update

if [[ "$SKIP_TESTS" != "true" ]]; then
  echo "==> Running test suite post-update"
  just test
fi

echo ""
echo "Done. Review git diff for surprising version jumps before committing."
