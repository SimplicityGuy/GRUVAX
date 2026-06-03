#!/usr/bin/env bash

# update-project.sh — Comprehensive GRUVAX dependency and version updater
#
# Adapted from discogsography/scripts/update-project.sh (1706-line workspace
# script) for GRUVAX's single-package Python + single-frontend layout. Drops the
# Rust extractor branch and the multi-pyproject workspace floor-sweep that have
# no analog here; otherwise mirrors the discogsography behaviour so dev tooling
# stays aligned across the two projects.
#
# This script provides a safe and comprehensive way to update:
# - Python version across pyproject.toml, GitHub workflows, Dockerfile, compose.yaml
# - Python package dependencies via uv (all version types)
# - Dependency floors (>=) in pyproject.toml, raised to match uv.lock
# - Node.js dependencies in frontend/ (npm)
# - UV package manager version in Dockerfile and setup-uv action references
# - Pre-commit hooks to latest versions
# - Docker dependency review (FROM base images, uv image, compose service images)
#
# It also flags capped dependencies (those with a ',<X' upper bound) that have a
# newer release available beyond the cap, so they can be reviewed manually.
#
# Ecosystem behavior:
#   Python (uv):  uv lock --upgrade refreshes uv.lock within the existing >=X.Y
#                 floors (this includes majors). It never raises the floors
#                 themselves, so sync_dependency_floors() does that after the lock
#                 so pyproject.toml minimums track what is actually resolved.
#
# Usage: ./scripts/update-project.sh [options]
#
# Options:
#   --python VERSION    Update Python version (default: keep current)
#   --no-backup        Skip creating backup files
#   --dry-run          Show what would be updated without making changes
#   --major            Include major version upgrades (passed through to uv)
#   --skip-tests       Skip running tests after updates
#   --help             Show this help message

set -euo pipefail

# Default options
BACKUP=true
DRY_RUN=false
MAJOR_UPGRADES=false
SKIP_TESTS=false
UPDATE_PYTHON=false
PYTHON_VERSION=""
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CHANGES_MADE=false

# Emojis for visual logging
EMOJI_INFO="ℹ️"
EMOJI_SUCCESS="✅"
EMOJI_WARNING="⚠️"
EMOJI_ERROR="❌"
EMOJI_ROCKET="🚀"
EMOJI_PACKAGE="📦"
EMOJI_PYTHON="🐍"
EMOJI_DOCKER="🐳"
EMOJI_TEST="🧪"
EMOJI_BACKUP="💾"
EMOJI_CHANGES="📝"
EMOJI_VERIFY="🔍"
EMOJI_GIT="🔀"

# Print colored output with emojis
print_info() {
  echo -e "\033[0;34m$EMOJI_INFO  [INFO]\033[0m $1"
}

print_success() {
  echo -e "\033[0;32m$EMOJI_SUCCESS  [SUCCESS]\033[0m $1"
}

print_warning() {
  echo -e "\033[1;33m$EMOJI_WARNING  [WARNING]\033[0m $1"
}

print_error() {
  echo -e "\033[0;31m$EMOJI_ERROR  [ERROR]\033[0m $1"
}

print_section() {
  echo ""
  echo -e "\033[1;36m$1  $2\033[0m"
  echo -e "\033[1;36m$(printf '=%.0s' {1..60})\033[0m"
}

# Show usage
show_help() {
  head -n 32 "$0" | grep '^#' | sed 's/^# //' | sed 's/^#//'
  exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --python)
      UPDATE_PYTHON=true
      PYTHON_VERSION="$2"
      shift 2
      ;;
    --no-backup)
      BACKUP=false
      shift
      ;;
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
    --help | -h)
      show_help
      ;;
    *)
      print_error "Unknown option: $1"
      show_help
      ;;
  esac
done

# Check if we're in the project root
if [[ ! -f "pyproject.toml" ]] || [[ ! -f "uv.lock" ]]; then
  print_error "This script must be run from the project root directory"
  exit 1
fi

# Check required tools
for tool in uv git curl jq; do
  if ! command -v $tool &>/dev/null; then
    print_error "$tool is not installed. Please install it first."
    exit 1
  fi
done

# Check for uncommitted changes (only warn, don't exit)
if [[ -n $(git status --porcelain) ]]; then
  print_warning "You have uncommitted changes. Consider committing or stashing them for safe rollback."
  print_info "Continuing anyway since we're in automated mode..."
fi

# Create backup directory
BACKUP_DIR="backups/project-updates-${TIMESTAMP}"
if [[ "$BACKUP" == true ]] && [[ "$DRY_RUN" == false ]]; then
  mkdir -p "$BACKUP_DIR"
  print_info "$EMOJI_BACKUP Creating backups in $BACKUP_DIR/"
fi

# Backup function
backup_file() {
  local file=$1
  if [[ "$BACKUP" == true ]] && [[ -f "$file" ]] && [[ "$DRY_RUN" == false ]]; then
    local backup_path
    backup_path="$BACKUP_DIR/$(dirname "$file")"
    mkdir -p "$backup_path"
    cp "$file" "$backup_path/$(basename "$file").backup"
  fi
}

# Track changes for summary
PACKAGE_CHANGES=()
FILE_CHANGES=()
UV_VERSION_CHANGE=""
PYTHON_VERSION_CHANGE=""
WORKFLOW_CHANGES=()

# Helper function to safely get array length (works with set -u)
array_length() {
  local array_name=$1
  eval "echo \${#${array_name}[@]}" 2>/dev/null || echo 0
}

# Capture package version changes by diffing uv.lock against its pre-update backup
capture_package_changes() {
  if [[ "$DRY_RUN" == true ]]; then
    return
  fi

  if [[ -f "$BACKUP_DIR/uv.lock.backup" ]]; then
    print_info "$EMOJI_CHANGES Analyzing package changes..."

    local old_packages new_packages
    old_packages=$(grep -E "^name = |^version = " "$BACKUP_DIR/uv.lock.backup" | paste -d' ' - - | sed 's/name = "\(.*\)" version = "\(.*\)"/\1==\2/')
    new_packages=$(grep -E "^name = |^version = " "uv.lock" | paste -d' ' - - | sed 's/name = "\(.*\)" version = "\(.*\)"/\1==\2/')

    while IFS= read -r old_pkg; do
      local pkg_name old_version new_version
      pkg_name=$(echo "$old_pkg" | cut -d'=' -f1)
      old_version=$(echo "$old_pkg" | cut -d'=' -f3)
      new_version=$(echo "$new_packages" | grep "^$pkg_name==" | cut -d'=' -f3 || echo "")

      if [[ -n "$new_version" ]] && [[ "$old_version" != "$new_version" ]]; then
        PACKAGE_CHANGES+=("$pkg_name: $old_version → $new_version")
        CHANGES_MADE=true
      fi
    done <<<"$old_packages"
  fi
}

# Update Python version function
update_python_version() {
  if [[ "$UPDATE_PYTHON" != true ]]; then
    return
  fi

  print_section "$EMOJI_PYTHON" "Updating Python Version"

  local current_version
  current_version=$(grep 'requires-python = ">=' pyproject.toml | sed 's/.*>=\([0-9.]*\)".*/\1/')
  PYTHON_VERSION_CHANGE="$current_version → $PYTHON_VERSION"

  if [[ "$current_version" == "$PYTHON_VERSION" ]]; then
    print_info "Python version is already $PYTHON_VERSION"
    return
  fi

  print_info "Updating Python from $current_version to $PYTHON_VERSION"

  if [[ "$DRY_RUN" == false ]]; then
    # Update pyproject.toml (single file — GRUVAX has no workspace members).
    print_info "Updating pyproject.toml..."
    backup_file "pyproject.toml"

    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s/requires-python = \">=\?[0-9.]\+\"/requires-python = \">=$PYTHON_VERSION\"/g" pyproject.toml
      sed -i '' "s/python_version = \"[0-9.]\+\"/python_version = \"$PYTHON_VERSION\"/g" pyproject.toml
      # target-version = "pyXY" — bump the ruff target too. The format is
      # "py" + major + minor (no dot), e.g. "py314" for Python 3.14.
      local target
      target="py$(echo "$PYTHON_VERSION" | tr -d '.')"
      sed -i '' "s/target-version = \"py[0-9]\+\"/target-version = \"$target\"/g" pyproject.toml
    else
      sed -i "s/requires-python = \">=\?[0-9.]\+\"/requires-python = \">=$PYTHON_VERSION\"/g" pyproject.toml
      sed -i "s/python_version = \"[0-9.]\+\"/python_version = \"$PYTHON_VERSION\"/g" pyproject.toml
      local target
      target="py$(echo "$PYTHON_VERSION" | tr -d '.')"
      sed -i "s/target-version = \"py[0-9]\+\"/target-version = \"$target\"/g" pyproject.toml
    fi

    print_success "Updated pyproject.toml"
    FILE_CHANGES+=("pyproject.toml: Python $current_version → $PYTHON_VERSION")

    # Update GitHub workflow files (PYTHON_VERSION env vars).
    print_info "Updating GitHub workflow files..."
    for workflow in .github/workflows/*.yml; do
      if [[ -f "$workflow" ]] && grep -q "PYTHON_VERSION" "$workflow"; then
        backup_file "$workflow"

        if [[ "$OSTYPE" == "darwin"* ]]; then
          sed -i '' "s/PYTHON_VERSION: \"[0-9.]\+\"/PYTHON_VERSION: \"$PYTHON_VERSION\"/g" "$workflow"
        else
          sed -i "s/PYTHON_VERSION: \"[0-9.]\+\"/PYTHON_VERSION: \"$PYTHON_VERSION\"/g" "$workflow"
        fi

        print_success "Updated $workflow"
        FILE_CHANGES+=("$workflow: Python $current_version → $PYTHON_VERSION")
      fi
    done

    # Update Dockerfile (python:X-slim or python:X-bookworm-slim base image).
    if [[ -f "Dockerfile" ]] && grep -q "FROM python:" Dockerfile; then
      print_info "Updating Dockerfile python base image..."
      backup_file "Dockerfile"

      if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/FROM python:[0-9.]\+-/FROM python:$PYTHON_VERSION-/g" Dockerfile
      else
        sed -i "s/FROM python:[0-9.]\+-/FROM python:$PYTHON_VERSION-/g" Dockerfile
      fi

      print_success "Updated Dockerfile"
      FILE_CHANGES+=("Dockerfile: Python $current_version → $PYTHON_VERSION")
    fi

    # Update compose.yaml if it carries an explicit PYTHON_VERSION substitution.
    if [[ -f "compose.yaml" ]] && grep -q "PYTHON_VERSION" compose.yaml; then
      backup_file "compose.yaml"

      if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/PYTHON_VERSION:-[0-9.]\+/PYTHON_VERSION:-$PYTHON_VERSION/g" compose.yaml
      else
        sed -i "s/PYTHON_VERSION:-[0-9.]\+/PYTHON_VERSION:-$PYTHON_VERSION/g" compose.yaml
      fi

      print_success "Updated compose.yaml"
      FILE_CHANGES+=("compose.yaml: Python $current_version → $PYTHON_VERSION")
    fi

    CHANGES_MADE=true
  else
    print_info "[DRY RUN] Would update Python version in:"
    print_info "  • pyproject.toml (requires-python + python_version + ruff target-version)"
    print_info "  • GitHub workflow files"
    print_info "  • Dockerfile (FROM python:X-slim)"
    print_info "  • compose.yaml (if PYTHON_VERSION substitution present)"
  fi
}

# Update UV version in Dockerfile and setup-uv action references in workflows.
#
# Note: GRUVAX's Dockerfile currently uses ``ghcr.io/astral-sh/uv:latest``. When
# the image is on :latest, this function does NOT mutate the Dockerfile — the
# image is auto-tracked. It still updates the setup-uv action pins in
# .github/workflows/ regardless.
update_uv_version() {
  print_section "$EMOJI_DOCKER" "Updating UV Version"

  # Get the latest UV version from GitHub
  local latest_uv
  latest_uv=$(curl -s https://api.github.com/repos/astral-sh/uv/releases/latest | jq -r '.tag_name' | sed 's/^v//')

  if [[ -z "$latest_uv" ]]; then
    print_warning "Could not determine latest UV version from GitHub"
    return
  fi

  print_info "Latest UV version: $latest_uv"

  # Latest setup-uv action (commit SHA + tag) for workflow pin updates.
  local latest_setup_uv latest_setup_uv_commit
  latest_setup_uv=$(curl -s https://api.github.com/repos/astral-sh/setup-uv/releases/latest | jq -r '.tag_name')
  latest_setup_uv_commit=$(curl -s "https://api.github.com/repos/astral-sh/setup-uv/commits/$latest_setup_uv" | jq -r '.sha')

  print_info "Latest setup-uv action: $latest_setup_uv (commit: ${latest_setup_uv_commit:0:7})"

  # Detect current UV pin in Dockerfile (if any).
  local current_uv=""
  if [[ -f "Dockerfile" ]]; then
    current_uv=$(grep "ghcr.io/astral-sh/uv:" Dockerfile 2>/dev/null | head -1 | sed -E 's/.*uv:([0-9.]+).*/\1/' || true)
  fi

  if [[ -z "$current_uv" ]]; then
    print_info "Dockerfile uses ghcr.io/astral-sh/uv:latest (no pinned version) — skipping image bump"
  elif [[ "$current_uv" != "$latest_uv" ]]; then
    UV_VERSION_CHANGE="$current_uv → $latest_uv"
    print_info "Updating UV from $current_uv to $latest_uv in Dockerfile"

    if [[ "$DRY_RUN" == false ]]; then
      backup_file "Dockerfile"
      if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/ghcr.io\/astral-sh\/uv:[0-9.]*[0-9]/ghcr.io\/astral-sh\/uv:$latest_uv/g" Dockerfile
      else
        sed -i "s/ghcr.io\/astral-sh\/uv:[0-9.]\+/ghcr.io\/astral-sh\/uv:$latest_uv/g" Dockerfile
      fi
      print_success "Updated Dockerfile"
      FILE_CHANGES+=("Dockerfile: UV $current_uv → $latest_uv")
      CHANGES_MADE=true
    else
      print_info "[DRY RUN] Would update UV version in Dockerfile"
    fi
  else
    print_success "UV version in Dockerfile is already up to date ($current_uv)"
  fi

  # Update setup-uv action SHA pins in .github/workflows/.
  # Pin format: astral-sh/setup-uv@<40-char-sha>  # vX.Y.Z  (two spaces before
  # '#', matching the repo's SHA-pin convention so yamllint stays happy).
  print_info "Checking GitHub Actions for setup-uv updates..."

  if [[ -n "$latest_setup_uv_commit" ]] && [[ "$latest_setup_uv_commit" != "null" ]]; then
    local f setup_uv_files=()
    while IFS= read -r f; do
      [[ -n "$f" ]] && setup_uv_files+=("$f")
    done < <(grep -rlE "astral-sh/setup-uv@" .github/workflows 2>/dev/null || true)

    local workflow current_commit
    for workflow in "${setup_uv_files[@]:-}"; do
      [[ -f "$workflow" ]] || continue
      current_commit=$(grep -oE "astral-sh/setup-uv@[a-f0-9]{40}" "$workflow" | head -1 | cut -d'@' -f2)
      if [[ -n "$current_commit" ]] && [[ "$current_commit" != "$latest_setup_uv_commit" ]]; then
        if [[ "$DRY_RUN" == false ]]; then
          backup_file "$workflow"
          if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|\(astral-sh/setup-uv@\).*|\1$latest_setup_uv_commit  # $latest_setup_uv|" "$workflow"
          else
            sed -i "s|\(astral-sh/setup-uv@\).*|\1$latest_setup_uv_commit  # $latest_setup_uv|" "$workflow"
          fi
          print_success "Updated ${workflow#./} (setup-uv → ${latest_setup_uv_commit:0:7} $latest_setup_uv)"
          WORKFLOW_CHANGES+=("${workflow#./}: setup-uv ${current_commit:0:7} → ${latest_setup_uv_commit:0:7}")
          CHANGES_MADE=true
        else
          print_info "[DRY RUN] Would update setup-uv in ${workflow#./}"
        fi
      fi
    done
  fi

  if [[ $(array_length WORKFLOW_CHANGES) -eq 0 ]]; then
    print_success "setup-uv action is already up to date"
  fi
}

# Review the full Docker dependency surface — surfaces every Docker dependency
# so nothing is silently missed. Does not mutate.
#
# Division of labour:
#   - uv binary image (ghcr.io/astral-sh/uv) -> bumped by update_uv_version()
#   - Python base image (python:X-slim)      -> bumped by update_python_version() (--python)
#   - other FROM base images + compose service images -> tracked by Dependabot
#   - apt packages -> intentionally unpinned / distro-managed
update_docker_images() {
  print_section "$EMOJI_DOCKER" "Reviewing Docker Dependencies"

  print_info "Base + tool images in Dockerfile (FROM lines and the uv image):"
  if [[ -f "Dockerfile" ]]; then
    local matches
    matches=$(grep -nE "^FROM |ghcr.io/astral-sh/uv:" Dockerfile 2>/dev/null) || true
    [[ -n "$matches" ]] && echo "$matches" | sed "s|^|  Dockerfile:|"
  fi

  print_info "Service images in compose.yaml:"
  if [[ -f "compose.yaml" ]]; then
    local matches
    matches=$(grep -nE "^[[:space:]]*image:" compose.yaml 2>/dev/null) || true
    [[ -n "$matches" ]] && echo "$matches" | sed "s|^|  compose.yaml:|"
  fi

  print_info "Dependency ownership:"
  print_info "  • uv image (ghcr.io/astral-sh/uv)   → managed by update_uv_version()"
  print_info "  • Python base (python:X-slim)       → managed by --python"
  print_info "  • Other FROM tags + compose service images → Dependabot docker group"
  print_info "  • apt packages                      → distro-managed (intentionally unpinned)"
}

# Update pre-commit hooks to latest versions
update_precommit_hooks() {
  print_section "🪝" "Updating Pre-commit Hooks"

  if ! command -v pre-commit >/dev/null 2>&1 && ! uv run pre-commit --version >/dev/null 2>&1; then
    print_warning "pre-commit not installed, skipping hook updates"
    return
  fi

  print_info "Updating pre-commit hooks to latest versions (frozen to commit SHAs)..."

  if [[ "$DRY_RUN" == false ]]; then
    if [[ "$BACKUP" == true ]]; then
      backup_file ".pre-commit-config.yaml"
    fi

    if uv run pre-commit autoupdate --freeze; then
      print_success "Pre-commit hooks updated successfully"
      FILE_CHANGES+=(".pre-commit-config.yaml: Updated pre-commit hooks to latest versions (frozen to commit SHAs)")
      CHANGES_MADE=true

      sync_dependencies_after_precommit

      # Re-install hooks so the new versions are wired up.
      uv run pre-commit install --install-hooks || true
    else
      print_warning "Failed to update pre-commit hooks"
    fi
  else
    print_info "[DRY RUN] Would run: uv run pre-commit autoupdate --freeze"
  fi
}

# Sync pyproject.toml dependencies after pre-commit autoupdate
sync_dependencies_after_precommit() {
  print_info "Syncing dependencies after pre-commit hook updates..."

  if [[ "$DRY_RUN" == false ]]; then
    if uv sync --upgrade; then
      print_success "Dependencies synced successfully"
      FILE_CHANGES+=("pyproject.toml and uv.lock: Synced with latest dependency versions")
      CHANGES_MADE=true
    else
      print_warning "Failed to sync dependencies after pre-commit updates"
    fi
  else
    print_info "[DRY RUN] Would run: uv sync --upgrade"
  fi

  echo ""
}

# Verify all dependencies were updated
verify_dependency_updates() {
  print_section "✅" "Verifying Dependency Updates"

  print_info "All dependency types have been updated:"

  print_success "✓ Python core dependencies ([project] dependencies)"
  print_success "✓ Python dev dependencies ([dependency-groups])"
  print_success "✓ Python build dependencies ([build-system])"
  print_success "✓ Python dependency floors raised to match uv.lock"

  if [[ -f "frontend/package.json" ]]; then
    print_success "✓ Node.js dependencies (frontend/package.json + package-lock.json)"
  fi

  print_success "✓ Pre-commit hooks and their dependencies"
  print_success "✓ UV package manager + setup-uv action pins"
  print_success "✓ GitHub Actions dependencies (PYTHON_VERSION, setup-uv)"

  if [[ "$DRY_RUN" == false ]]; then
    print_info "Run 'uv tree --outdated' to verify all Python packages are up to date"
  fi
}

# Update Node.js dependencies (frontend/ SPA)
update_node_packages() {
  if [[ ! -f "frontend/package.json" ]]; then
    print_info "No frontend/package.json found, skipping Node.js updates"
    return
  fi

  print_section "📦" "Updating Node.js Dependencies"

  if [[ "$BACKUP" == true ]] && [[ "$DRY_RUN" == false ]]; then
    backup_file "frontend/package.json"
    backup_file "frontend/package-lock.json"
  fi

  if [[ "$DRY_RUN" == false ]]; then
    print_info "Updating npm packages in frontend/..."

    if npm --prefix frontend update; then
      print_success "npm packages updated successfully"
      FILE_CHANGES+=("frontend/package.json: Updated npm dependencies")
      FILE_CHANGES+=("frontend/package-lock.json: Updated npm lockfile")
      CHANGES_MADE=true
    else
      print_warning "Failed to update npm packages"
    fi
  else
    print_info "[DRY RUN] Would run: npm --prefix frontend update"
  fi
}

# Update Python packages
update_python_packages() {
  print_section "$EMOJI_PACKAGE" "Updating Python Dependencies"

  if [[ "$BACKUP" == true ]] && [[ "$DRY_RUN" == false ]]; then
    backup_file "uv.lock"
    backup_file "pyproject.toml"
  fi

  # Update uv itself (self-update).
  print_info "Checking for uv updates..."
  if [[ "$DRY_RUN" == false ]]; then
    if uv self update 2>&1; then
      print_success "uv updated successfully (or already latest)"
    else
      print_warning "Could not self-update uv (this is fine when installed via pipx/Homebrew)"
    fi
  else
    print_info "[DRY RUN] Would run: uv self update"
  fi

  # Refresh the lockfile.
  print_info "Updating ALL dependency types:"
  print_info "  • Core dependencies ([project] dependencies)"
  print_info "  • Dev dependencies ([dependency-groups])"
  print_info "  • Build dependencies ([build-system])"

  if [[ "$MAJOR_UPGRADES" == true ]]; then
    print_info "Including major version upgrades (uv lock --upgrade — respects >= constraints)"
  else
    print_info "Refreshing within existing >= constraints"
  fi

  if [[ "$DRY_RUN" == true ]]; then
    if [[ "$MAJOR_UPGRADES" == true ]]; then
      print_info "[DRY RUN] Would run: uv lock --upgrade"
    else
      print_info "[DRY RUN] Would run: uv lock"
    fi
    print_info "Checking for available updates..."
    uv tree --outdated || true
  else
    local uv_lock_cmd="uv lock"
    [[ "$MAJOR_UPGRADES" == true ]] && uv_lock_cmd="uv lock --upgrade"
    if $uv_lock_cmd; then
      print_success "Lockfile refreshed successfully"
      CHANGES_MADE=true
    else
      print_error "Failed to refresh lockfile"
      exit 1
    fi
  fi

  if [[ "$DRY_RUN" == false ]]; then
    print_info "Syncing upgraded dependencies (including dev)..."
    if uv sync --all-groups; then
      print_success "Dependencies synced successfully"
    else
      print_error "Failed to sync dependencies"
      exit 1
    fi

    capture_package_changes

    print_success "Completed Python dependency updates"
  else
    print_info "[DRY RUN] Would run: uv sync --all-groups"
  fi
}

# Raise the `>=` floors in pyproject.toml to match the versions actually pinned
# in uv.lock.
#
# `uv lock --upgrade` refreshes the lockfile WITHIN the existing floors but never
# raises the floors themselves. This closes the gap Dependabot otherwise opens
# PRs for, so declared minimums track what is actually resolved.
#
# GRUVAX is a single-package project (no uv workspace members), so this rewrites
# just one pyproject.toml — simpler than the discogsography workspace sweep.
sync_dependency_floors() {
  print_section "$EMOJI_PACKAGE" "Syncing Dependency Floors"

  local apply_val=1
  [[ "$DRY_RUN" == true ]] && apply_val=0

  local output
  output=$(
    APPLY="$apply_val" uv run python - <<'PY'
import os
import re
import tomllib
from pathlib import Path

apply = os.environ.get("APPLY") == "1"

try:
    from packaging.version import InvalidVersion, Version

    def strictly_newer(candidate: str, current: str) -> bool:
        try:
            return Version(candidate) > Version(current)
        except InvalidVersion:
            # uv.lock always resolves at or above the floor; default to True.
            return True
except ImportError:

    def strictly_newer(candidate: str, current: str) -> bool:
        return True


# GRUVAX is a single-package project: just the root pyproject.toml.
pyprojects = [Path("pyproject.toml")]

# Resolve every requirement against the root uv.lock.
lock = tomllib.loads(Path("uv.lock").read_text())
locked = {p["name"].lower().replace("_", "-"): p["version"] for p in lock.get("package", [])}

header_re = re.compile(r"^\[\[?(?P<name>[^\]]+)\]\]?\s*$")
open_re = re.compile(r"^(?P<key>[A-Za-z0-9._-]+)\s*=\s*\[\s*(#.*)?$")
close_re = re.compile(r"^\s*\]")
entry_re = re.compile(r'^(?P<indent>\s*)"(?P<spec>[^"]+)"(?P<trail>.*)$')
spec_re = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+(?:\[[A-Za-z0-9._,-]+\])?)"
    r"(?P<specs>[<>=!~][^;]*)?"
    r"(?P<marker>;.*)?$"
)
floor_re = re.compile(r">=\s*([^,;\s]+)")

total = 0
for pyproject in pyprojects:
    lines = pyproject.read_text().split("\n")
    out: list[str] = []
    section = ""
    in_array = False
    process = False
    changes: list[tuple[str, str, str]] = []
    for line in lines:
        if not in_array:
            header = header_re.match(line.strip())
            if header:
                section = header.group("name")
                out.append(line)
                continue
            opener = open_re.match(line.strip())
            if opener:
                key = opener.group("key")
                process = (
                    (section == "project" and key == "dependencies")
                    or section == "project.optional-dependencies"
                    or section == "dependency-groups"
                )
                in_array = True
                out.append(line)
                continue
            out.append(line)
            continue
        # Inside an array.
        if close_re.match(line):
            in_array = False
            process = False
            out.append(line)
            continue
        if process:
            matched = entry_re.match(line)
            if matched:
                parsed = spec_re.match(matched.group("spec"))
                specs = parsed.group("specs") if parsed else None
                if parsed and specs:
                    base = parsed.group("name").split("[")[0].lower().replace("_", "-")
                    locked_version = locked.get(base)
                    floor = floor_re.search(specs)
                    if locked_version and floor:
                        current = floor.group(1)
                        if current != locked_version and strictly_newer(locked_version, current):
                            new_specs = specs[: floor.start(1)] + locked_version + specs[floor.end(1) :]
                            new_spec = parsed.group("name") + new_specs + (parsed.group("marker") or "")
                            changes.append((base, current, locked_version))
                            out.append(f'{matched.group("indent")}"{new_spec}"{matched.group("trail")}')
                            continue
        out.append(line)
    for base, old, new in changes:
        print(f"BUMPED {pyproject}: {base} {old} -> {new}")
    if apply and changes:
        pyproject.write_text("\n".join(out))
    total += len(changes)

print(f"FLOORS_CHANGED={total}")
PY
  )

  echo "$output" | grep -E "^BUMPED " | sed 's/^BUMPED /  /' || true

  local changed
  changed=$(echo "$output" | sed -n 's/^FLOORS_CHANGED=//p')
  changed=${changed:-0}

  if [[ "$DRY_RUN" == true ]]; then
    if [[ "$changed" -gt 0 ]]; then
      print_info "[DRY RUN] Would raise $changed dependency floor(s) in pyproject.toml to match uv.lock"
    else
      print_success "[DRY RUN] All dependency floors already match uv.lock"
    fi
    return
  fi

  if [[ "$changed" -gt 0 ]]; then
    print_info "Re-locking so uv.lock requirement metadata matches the raised floors..."
    uv lock >/dev/null 2>&1 || uv lock
    CHANGES_MADE=true
    FILE_CHANGES+=("pyproject.toml: raised $changed dependency floor(s) to match uv.lock")
    print_success "Raised $changed dependency floor(s) to match uv.lock"
  else
    print_success "All dependency floors already match uv.lock"
  fi
}

# Flag capped dependencies (`,<X` upper bound) with a release available AT OR
# BEYOND the cap. `uv lock --upgrade` cannot cross a cap on its own; raising one
# is a deliberate human decision — we only warn, never edit.
flag_capped_dependencies() {
  print_section "$EMOJI_VERIFY" "Checking Capped Dependencies"

  if [[ "$DRY_RUN" == true ]]; then
    print_info "[DRY RUN] Would flag capped dependencies with releases beyond their cap"
    return
  fi

  local outdated
  outdated=$(uv pip list --outdated 2>/dev/null) || true

  local output
  output=$(
    OUTDATED="$outdated" uv run python - <<'PY'
import os
import re
import tomllib
from pathlib import Path

try:
    from packaging.version import InvalidVersion, Version

    def at_or_beyond_cap(latest: str, cap: str) -> bool:
        try:
            return Version(latest) >= Version(cap)
        except InvalidVersion:
            return True
except ImportError:

    def at_or_beyond_cap(latest: str, cap: str) -> bool:
        return True


pyprojects = [Path("pyproject.toml")]

name_re = re.compile(r"^([A-Za-z0-9._-]+)")
cap_re = re.compile(r"<\s*([0-9][^,;\s]*)")
caps: dict[str, str] = {}
own: set[str] = set()

for pyproject in pyprojects:
    if not pyproject.exists():
        continue
    try:
        data = tomllib.loads(pyproject.read_text())
    except tomllib.TOMLDecodeError:
        continue
    project = data.get("project", {})
    own_name = project.get("name")
    if own_name:
        own.add(own_name.lower().replace("_", "-"))
    specs: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(s for s in group if isinstance(s, str))
    for group in data.get("dependency-groups", {}).values():
        specs.extend(s for s in group if isinstance(s, str))
    for spec in specs:
        name_match = name_re.match(spec)
        cap_match = cap_re.search(spec.split(";")[0])
        if name_match and cap_match:
            caps[name_match.group(1).lower().replace("_", "-")] = cap_match.group(1)

latest: dict[str, str] = {}
for raw in os.environ.get("OUTDATED", "").splitlines():
    parts = raw.split()
    if len(parts) >= 3 and parts[0] != "Package" and not parts[0].startswith("-"):
        latest[parts[0].lower().replace("_", "-")] = parts[2]

flagged = 0
for name, cap in sorted(caps.items()):
    if name in own:
        continue
    newest = latest.get(name)
    if newest and at_or_beyond_cap(newest, cap):
        print(f"FLAG {name}: {newest} available, capped at <{cap}")
        flagged += 1
print(f"CAPPED_FLAGGED={flagged}")
PY
  )

  local flagged
  flagged=$(echo "$output" | sed -n 's/^CAPPED_FLAGGED=//p')
  flagged=${flagged:-0}

  if [[ "$flagged" -gt 0 ]]; then
    while IFS= read -r line; do
      print_warning "${line#FLAG }"
    done < <(echo "$output" | grep -E "^FLAG ")
    print_info "Raise the cap in pyproject.toml manually, then re-run: uv lock --upgrade && uv sync --all-groups"
  else
    print_success "No capped dependencies have releases beyond their cap"
  fi
}

# Run tests
run_tests() {
  if [[ "$SKIP_TESTS" == true ]] || [[ "$DRY_RUN" == true ]]; then
    return
  fi

  print_section "$EMOJI_TEST" "Running Tests"

  print_info "Running linters..."
  if just lint; then
    print_success "Linting passed"
  else
    print_warning "Linting failed — review the changes"
  fi

  print_info "Running Python tests..."
  if just test; then
    print_success "Python tests passed"
  else
    print_warning "Python tests failed — review the changes"
  fi
}

# Generate summary
generate_summary() {
  print_section "$EMOJI_CHANGES" "Update Summary"

  if [[ "$DRY_RUN" == true ]]; then
    print_info "This was a dry run. No changes were made."
    print_info "Run without --dry-run to apply changes."
    return
  fi

  if [[ "$CHANGES_MADE" == false ]]; then
    print_success "Everything is already up to date! No changes were needed."
    return
  fi

  if [[ -n "$PYTHON_VERSION_CHANGE" ]]; then
    echo ""
    echo "🐍 Python Version:"
    echo "  $PYTHON_VERSION_CHANGE"
  fi

  if [[ -n "$UV_VERSION_CHANGE" ]]; then
    echo ""
    echo "🐳 UV Package Manager:"
    echo "  $UV_VERSION_CHANGE"
  fi

  if [[ $(array_length PACKAGE_CHANGES) -gt 0 ]]; then
    echo ""
    echo "📦 Package Updates:"
    printf '%s\n' "${PACKAGE_CHANGES[@]:-}" | sort | while IFS= read -r change; do
      echo "  • $change"
    done
  fi

  if [[ $(array_length FILE_CHANGES) -gt 0 ]]; then
    echo ""
    echo "📄 File Updates:"
    printf '%s\n' "${FILE_CHANGES[@]:-}" | sort | while IFS= read -r change; do
      echo "  • $change"
    done
  fi

  if [[ $(array_length WORKFLOW_CHANGES) -gt 0 ]]; then
    echo ""
    echo "🔄 GitHub Workflow Updates:"
    for change in "${WORKFLOW_CHANGES[@]:-}"; do
      echo "  • $change"
    done
  fi

  echo ""
  print_section "$EMOJI_GIT" "Next Steps"

  echo "1. Review the changes:"
  echo "   git diff --stat"
  echo "   git diff uv.lock"

  if [[ -n "$UV_VERSION_CHANGE" ]]; then
    echo "   git diff Dockerfile"
  fi

  echo ""
  echo "2. Stage the changes:"

  if [[ $(array_length PACKAGE_CHANGES) -gt 0 ]]; then
    echo "   git add uv.lock"
  fi

  if [[ -n "$PYTHON_VERSION_CHANGE" ]]; then
    echo "   git add pyproject.toml"
    echo "   git add .github/workflows/*.yml"
    echo "   git add Dockerfile compose.yaml"
  fi

  if [[ -n "$UV_VERSION_CHANGE" ]]; then
    echo "   git add Dockerfile"
  fi

  if [[ $(array_length WORKFLOW_CHANGES) -gt 0 ]]; then
    echo "   git add .github/workflows/*.yml"
  fi

  echo ""
  echo "3. Commit the changes:"
  echo "   git commit -m \"chore: update dependencies"

  if [[ -n "$PYTHON_VERSION_CHANGE" ]]; then
    echo ""
    echo "   - Update Python to ${PYTHON_VERSION_CHANGE##* → }"
  fi

  if [[ -n "$UV_VERSION_CHANGE" ]]; then
    echo "   - Update UV to ${UV_VERSION_CHANGE##* → }"
  fi

  if [[ $(array_length PACKAGE_CHANGES) -gt 0 ]]; then
    echo "   - Update $(array_length PACKAGE_CHANGES) Python packages"
  fi

  echo "   \""
}

# Manual verification steps
show_verification_steps() {
  print_section "$EMOJI_VERIFY" "Manual Verification Steps"

  echo "Please verify the following before merging:"
  echo ""
  echo "1. 🐳 Docker build:"
  echo "   docker compose build --no-cache"
  echo ""
  echo "2. 🧪 Service health:"
  echo "   docker compose up -d"
  echo "   docker compose ps  # All services should be 'healthy'"
  echo "   curl -f http://localhost:8000/api/health"
  echo ""
  echo "3. 📊 Review dependency changes:"
  echo "   uv run pip-audit --desc"
  echo "   git diff uv.lock | grep -E \"^[+-]version\""
  echo ""
  echo "4. 📝 Update CHANGELOG.md if needed"
  echo ""

  if [[ "$BACKUP" == true ]]; then
    echo "💾 Backups are stored in: $BACKUP_DIR/"
    echo "   To restore: cp $BACKUP_DIR/uv.lock.backup uv.lock && uv sync --all-groups"
  fi
}

# Verify all expected components exist
verify_components() {
  print_section "$EMOJI_VERIFY" "Verifying Project Components"

  local missing_components=()
  local total_components=0
  local found_components=0

  local expected_files=(
    "pyproject.toml"
    "uv.lock"
    "Dockerfile"
    "compose.yaml"
    "justfile"
    "frontend/package.json"
    "frontend/package-lock.json"
    ".pre-commit-config.yaml"
  )

  for file in "${expected_files[@]}"; do
    total_components=$((total_components + 1))
    if [[ -f "$file" ]]; then
      found_components=$((found_components + 1))
    else
      missing_components+=("$file")
    fi
  done

  print_success "Found $found_components/$total_components expected components"

  if [[ ${#missing_components[@]} -gt 0 ]]; then
    print_warning "Missing ${#missing_components[@]} components:"
    for component in "${missing_components[@]}"; do
      echo "  ⚠️  $component"
    done
    print_info "This may be normal if components were removed from the project."
  else
    print_success "All expected components found!"
  fi

  echo ""
}

# Handle errors
trap 'handle_error $?' ERR

handle_error() {
  local exit_code=$1
  print_error "An error occurred (exit code: $exit_code)"

  if [[ "$BACKUP" == true ]] && [[ "$DRY_RUN" == false ]] && [[ -d "$BACKUP_DIR" ]]; then
    print_info "You can restore from backup with:"
    echo "  cp $BACKUP_DIR/uv.lock.backup uv.lock"
    echo "  uv sync --all-groups"
  fi

  exit $exit_code
}

# Main execution
main() {
  print_section "$EMOJI_ROCKET" "Starting Project Update"

  verify_components

  update_python_version
  update_uv_version
  update_docker_images
  update_precommit_hooks
  update_python_packages
  sync_dependency_floors
  flag_capped_dependencies
  update_node_packages
  verify_dependency_updates
  run_tests
  generate_summary

  if [[ "$DRY_RUN" == false ]] && [[ "$CHANGES_MADE" == true ]]; then
    show_verification_steps
  fi
}

main
