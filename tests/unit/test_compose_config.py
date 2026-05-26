"""Automated assertions for DEP-04 and DEP-05 against compose.yaml.

DEP-04: each production service must declare a json-file logging driver
        with max-size 10m and max-file 3.
DEP-05: each production service must declare a healthcheck and
        restart: unless-stopped.

Production services under test: api, gruvax-dev-pg, mosquitto.
The mqtt-explorer service (debug profile) is explicitly excluded — it is
intentionally not hardened and must NOT appear in the parametrized set.

This is a pure file-parsing test: no docker, no network, no DB required.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

# ── Locate compose.yaml relative to this test file ───────────────────────────

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_COMPOSE_PATH = _REPO_ROOT / "compose.yaml"

# ── Load once at module level ─────────────────────────────────────────────────


def _load_compose() -> dict:
    with _COMPOSE_PATH.open() as fh:
        return yaml.safe_load(fh)


_COMPOSE = _load_compose()
_SERVICES: dict = _COMPOSE.get("services", {})

# Production services to assert against (mqtt-explorer deliberately excluded).
PRODUCTION_SERVICES = ["api", "gruvax-dev-pg", "mosquitto"]


# ── DEP-05: healthcheck ────────────────────────────────────────────────────────


@pytest.mark.parametrize("service_name", PRODUCTION_SERVICES)
def test_production_service_has_healthcheck(service_name: str) -> None:
    """DEP-05: every production service must declare a healthcheck block."""
    svc = _SERVICES.get(service_name)
    assert svc is not None, (
        f"Service '{service_name}' not found in compose.yaml. "
        f"Known services: {list(_SERVICES.keys())}"
    )
    assert "healthcheck" in svc, (
        f"DEP-05 violation: service '{service_name}' is missing a healthcheck declaration."
    )
    hc = svc["healthcheck"]
    assert isinstance(hc, dict), (
        f"DEP-05 violation: service '{service_name}' healthcheck must be a mapping, got {type(hc)}"
    )
    assert "test" in hc, (
        f"DEP-05 violation: service '{service_name}' healthcheck has no 'test' key."
    )


# ── DEP-05: restart: unless-stopped ──────────────────────────────────────────


@pytest.mark.parametrize("service_name", PRODUCTION_SERVICES)
def test_production_service_has_restart_unless_stopped(service_name: str) -> None:
    """DEP-05: every production service must declare restart: unless-stopped."""
    svc = _SERVICES.get(service_name)
    assert svc is not None, f"Service '{service_name}' not found in compose.yaml."
    restart = svc.get("restart")
    assert restart == "unless-stopped", (
        f"DEP-05 violation: service '{service_name}' restart policy is {restart!r}, "
        "expected 'unless-stopped'."
    )


# ── DEP-04: json-file logging driver ──────────────────────────────────────────


@pytest.mark.parametrize("service_name", PRODUCTION_SERVICES)
def test_production_service_logging_driver_is_json_file(service_name: str) -> None:
    """DEP-04: every production service must declare logging driver json-file."""
    svc = _SERVICES.get(service_name)
    assert svc is not None, f"Service '{service_name}' not found in compose.yaml."
    assert "logging" in svc, (
        f"DEP-04 violation: service '{service_name}' has no logging declaration."
    )
    logging_cfg = svc["logging"]
    assert isinstance(logging_cfg, dict), (
        f"DEP-04 violation: service '{service_name}' logging must be a mapping."
    )
    driver = logging_cfg.get("driver")
    assert driver == "json-file", (
        f"DEP-04 violation: service '{service_name}' logging driver is {driver!r}, "
        "expected 'json-file'."
    )


@pytest.mark.parametrize("service_name", PRODUCTION_SERVICES)
def test_production_service_logging_max_size_is_10m(service_name: str) -> None:
    """DEP-04: every production service logging options must set max-size to '10m'."""
    svc = _SERVICES.get(service_name)
    assert svc is not None
    logging_cfg = svc.get("logging", {})
    options = logging_cfg.get("options", {})
    raw = options.get("max-size")
    assert raw is not None, (
        f"DEP-04 violation: service '{service_name}' logging options missing max-size."
    )
    # Normalize to str in case YAML parsed it as a non-string (e.g. future int).
    assert str(raw) == "10m", (
        f"DEP-04 violation: service '{service_name}' max-size is {raw!r}, expected '10m'."
    )


@pytest.mark.parametrize("service_name", PRODUCTION_SERVICES)
def test_production_service_logging_max_file_is_3(service_name: str) -> None:
    """DEP-04: every production service logging options must set max-file to 3 (or '3')."""
    svc = _SERVICES.get(service_name)
    assert svc is not None
    logging_cfg = svc.get("logging", {})
    options = logging_cfg.get("options", {})
    raw = options.get("max-file")
    assert raw is not None, (
        f"DEP-04 violation: service '{service_name}' logging options missing max-file."
    )
    # Normalize to str — Docker accepts both "3" and 3; YAML may parse either.
    assert str(raw) == "3", (
        f"DEP-04 violation: service '{service_name}' max-file is {raw!r}, expected '3' or 3."
    )


# ── Exclusion guard: mqtt-explorer must NOT be in PRODUCTION_SERVICES ─────────


def test_mqtt_explorer_excluded_from_production_hardening_assertions() -> None:
    """mqtt-explorer (debug profile) must not be subject to DEP-04/DEP-05 assertions.

    This test confirms our parametrize list explicitly excludes it, and that
    mqtt-explorer exists in compose.yaml but lacks a logging block — consistent
    with it being intentionally unhardened.
    """
    assert "mqtt-explorer" not in PRODUCTION_SERVICES, (
        "mqtt-explorer must be excluded from production hardening assertions."
    )
    # Confirm the service actually exists in compose.yaml (guards against a rename).
    assert "mqtt-explorer" in _SERVICES, (
        "mqtt-explorer service not found in compose.yaml — verify service name."
    )
    # Confirm it is gated by the debug profile (not a plain production service).
    profiles = _SERVICES["mqtt-explorer"].get("profiles", [])
    assert "debug" in profiles, (
        f"mqtt-explorer is expected to be gated by profiles: [debug], got {profiles!r}."
    )
    # Confirm it deliberately has no logging block (intentionally unhardened).
    assert "logging" not in _SERVICES["mqtt-explorer"], (
        "mqtt-explorer unexpectedly has a logging block — update this test if intentional."
    )
