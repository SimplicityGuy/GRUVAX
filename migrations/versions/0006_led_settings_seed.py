"""Seed LED color/brightness/transition/highlight defaults in gruvax.settings.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-23

Phase 6: LED Contract over MQTT (Hardware Stubbed)

Seeds the full LED presentation vocabulary so every later LED slice
(lifecycle revert/retain in 06-02, admin colors in 06-03, all-off +
diagnostic in 06-04) reads keys that already exist:

  led_color.*             — hex string colors for position, label_span, error, setup,
                            all_off, and the ambient idle-baseline (D-20/D-25)
  led_brightness.span     — label-span tier (~50%) — D-24: renamed from the old incorrect
                            "ambient" key; this is NOT the idle baseline
  led_brightness.active   — position/primary tier (100%)
  led_brightness.ambient  — idle baseline brightness (low, ~16%) — D-20/D-24/D-25
  led_transition.*        — animation style + duration for position and span
  led_highlight.*         — active TTL, retain mode, retain TTL — D-21/D-23/D-25

Naming contract (D-24 — LOCKED):
  led_brightness.span     → label-span cubes during an active highlight (~50%)
  led_brightness.active   → primary/position cube (100%)
  led_brightness.ambient  → idle/resting baseline (NOT the span tier)

Conventions (carried from 0001-0005):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() removes only the rows seeded here (DELETE WHERE key IN ...).
- Colors stored as JSON strings ('"#FFD700"'); numbers and the boolean as bare JSON
  (128, 180, false) — consistent with auth.pin_hash storage pattern in migration 0004.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO gruvax.settings (key, value, description)
        VALUES
            -- ── LED colors ────────────────────────────────────────────────────
            ('led_color.position',        '"#FFD700"',  'LED: primary/position cube color (gold)'),
            ('led_color.label_span',      '"#7C3AED"',  'LED: label-span cube color (purple)'),
            ('led_color.error',           '"#E63946"',  'LED: error state color'),
            ('led_color.setup',           '"#0077B6"',  'LED: setup/diagnostic color'),
            ('led_color.all_off',         '"#000000"',  'LED: all-off color (off)'),
            -- D-20/D-25: idle baseline color; Nordic Grid IKEA blue is a sensible
            -- accessible default for ambient/idle state
            ('led_color.ambient',         '"#0051A2"',  'LED: idle/ambient baseline color (IKEA blue)'),
            -- ── LED brightness tiers (D-24) ───────────────────────────────────
            -- led_brightness.span = label-span tier (~50%) — NOT the idle baseline
            ('led_brightness.span',       '128',        'LED: label-span brightness ceiling (0-255, ~50%); D-24'),
            -- led_brightness.active = position/primary tier (100%)
            ('led_brightness.active',     '255',        'LED: active/position brightness ceiling (0-255, 100%); D-24'),
            -- led_brightness.ambient = idle baseline (low) — D-20/D-24/D-25
            ('led_brightness.ambient',    '40',         'LED: idle/ambient baseline brightness (0-255, low); D-24'),
            -- ── LED transitions ───────────────────────────────────────────────
            ('led_transition.position_style', '"pulse"', 'LED: primary cube transition style (pulse/fade/instant)'),
            ('led_transition.position_ms',    '800',     'LED: primary cube transition duration ms'),
            ('led_transition.span_style',     '"fade"',  'LED: label-span transition style (pulse/fade/instant)'),
            ('led_transition.span_ms',        '500',     'LED: label-span transition duration ms'),
            -- ── LED highlight lifecycle (D-21/D-23/D-25) ─────────────────────
            ('led_highlight.active_ttl_seconds',  '180',   'LED: highlight auto-revert TTL in seconds (D-21)'),
            ('led_highlight.retain_mode',         'false', 'LED: true = retain highlight on timeout (D-23)'),
            ('led_highlight.retain_ttl_seconds',  '900',   'LED: retain-mode highlight TTL in seconds (D-23)')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM gruvax.settings
        WHERE key IN (
            'led_color.position',
            'led_color.label_span',
            'led_color.error',
            'led_color.setup',
            'led_color.all_off',
            'led_color.ambient',
            'led_brightness.span',
            'led_brightness.active',
            'led_brightness.ambient',
            'led_transition.position_style',
            'led_transition.position_ms',
            'led_transition.span_style',
            'led_transition.span_ms',
            'led_highlight.active_ttl_seconds',
            'led_highlight.retain_mode',
            'led_highlight.retain_ttl_seconds'
        )
    """)
