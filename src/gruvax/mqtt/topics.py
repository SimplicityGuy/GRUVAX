"""MQTT topic builder functions for GRUVAX LED control.

Phase 6: LED Contract over MQTT (Hardware Stubbed)

All topics are prefixed with ``settings.MQTT_TOPIC_PREFIX`` so dev and prod
retained messages live in separate namespaces and never pollute each other
(D-14, Pitfall 3 from PITFALLS.md §3).

Topic structure (locked contract — ARCHITECTURE.md §"MQTT Topic Design"):

  illuminate/{unit_id}/{row}/{col}  — QoS 0, non-retained command: light this cube
  span/{change_id}                  — QoS 0, non-retained command: light the label span
  sub/{unit_id}/{row}/{col}         — QoS 0, non-retained command: sub-cube interval
  state/{unit_id}/{row}/{col}       — QoS 1, RETAINED: current LED state for this cube
  all/off                           — QoS 1, non-retained command: turn all LEDs off
  status/#                          — subscribe wildcard for firmware status responses

NEVER retain command topics (illuminate/span/sub) — stale-command-replay footgun
(see ARCHITECTURE.md §"Retained Hygiene").

Dead-code scan note (gruvax-e4k7, Repowise index @ 3f72378): this module and
``publishers.py::publish_all_off``/``run_diagnostic`` were flagged unreferenced.
Verified false positive — ``publishers.py`` imports this module and calls
``illuminate_topic``, ``span_topic``, ``sub_topic``, ``state_topic``,
``all_off_topic`` and ``status_wildcard`` from live, tested code wired to
``POST /api/admin/leds/off`` and ``POST /api/admin/leds/diagnostic``
(``src/gruvax/api/admin/leds.py``, registered in ``app.py`` via
``create_admin_router()``). Diagnostics are server-driven ``state/*`` sweeps;
there is no firmware-side diagnostic command topic or payload schema.
"""

from __future__ import annotations


def illuminate_topic(prefix: str, unit_id: int, row: int, col: int) -> str:
    """Build the illuminate command topic for a single cube.

    QoS 0, non-retained.  ``{prefix}/illuminate/{unit_id}/{row}/{col}``
    """
    return f"{prefix}/illuminate/{unit_id}/{row}/{col}"


def span_topic(prefix: str, change_id: str) -> str:
    """Build the label-span command topic for a highlight change.

    QoS 0, non-retained.  ``{prefix}/span/{change_id}``

    Each call gets a fresh UUID ``change_id`` so firmware can detect
    repeated span publishes that differ only in the cubeset.
    """
    return f"{prefix}/span/{change_id}"


def sub_topic(prefix: str, unit_id: int, row: int, col: int) -> str:
    """Build the sub-cube interval command topic.

    QoS 0, non-retained.  ``{prefix}/sub/{unit_id}/{row}/{col}``
    """
    return f"{prefix}/sub/{unit_id}/{row}/{col}"


def state_topic(prefix: str, unit_id: int, row: int, col: int) -> str:
    """Build the retained state topic for a single cube.

    QoS 1, RETAINED.  ``{prefix}/state/{unit_id}/{row}/{col}``

    Firmware subscribes on boot to know the current state of each cube
    without waiting for a command.  Must carry message_expiry_interval
    (D-12) to avoid permanent stale state on broker restart.
    """
    return f"{prefix}/state/{unit_id}/{row}/{col}"


def all_off_topic(prefix: str) -> str:
    """Build the all-LEDs-off command topic.

    QoS 1, non-retained.  ``{prefix}/all/off``
    """
    return f"{prefix}/all/off"


def status_wildcard(prefix: str) -> str:
    """Build the status subscription wildcard for firmware heartbeat/response topics.

    ``{prefix}/status/#``

    Subscribed transiently during a diagnostic run; unsubscribed when done.
    """
    return f"{prefix}/status/#"
