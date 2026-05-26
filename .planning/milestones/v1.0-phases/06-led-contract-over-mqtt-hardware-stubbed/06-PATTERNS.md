# Phase 6: LED Contract over MQTT (Hardware Stubbed) — Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 10 new/modified files
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/gruvax/mqtt/publishers.py` | service | event-driven | `src/gruvax/mqtt/client.py` | role-match |
| `src/gruvax/mqtt/topics.py` | utility | transform | `src/gruvax/estimator/normalize.py` | partial |
| `src/gruvax/mqtt/client.py` (modify) | service | event-driven | `src/gruvax/mqtt/client.py` (self) | exact |
| `src/gruvax/api/illuminate.py` | controller | request-response | `src/gruvax/api/locate.py` | exact |
| `src/gruvax/api/admin/leds.py` | controller | request-response | `src/gruvax/api/admin/segments.py` | exact |
| `src/gruvax/api/admin/router.py` (modify) | config | request-response | `src/gruvax/api/admin/router.py` (self) | exact |
| `src/gruvax/api/admin/settings.py` (modify) | controller | CRUD | `src/gruvax/api/admin/settings.py` (self) | exact |
| `src/gruvax/settings.py` (modify) | config | — | `src/gruvax/settings.py` (self) | exact |
| `migrations/versions/0006_led_settings_seed.py` | migration | CRUD | `migrations/versions/0004_admin_tables.py` | role-match |
| `frontend/src/routes/admin/Settings.tsx` (modify) | component | request-response | `frontend/src/routes/admin/Settings.tsx` (self) | exact |

---

## Pattern Assignments

### `src/gruvax/mqtt/publishers.py` (service, event-driven)

**Analog:** `src/gruvax/mqtt/client.py`

**Imports pattern** (`src/gruvax/mqtt/client.py` lines 15–27):
```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiomqtt

from gruvax.settings import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)
```

**Degraded-mode guard pattern** (`src/gruvax/mqtt/client.py` lines 34–73) — every publish function takes `client: aiomqtt.Client | None` and short-circuits:
```python
async def connect_mqtt(app: FastAPI) -> None:
    try:
        client = aiomqtt.Client(...)
        await client.__aenter__()
        ...
        app.state.mqtt = client
        app.state.mqtt_ok = True
    except Exception as exc:
        logger.warning("MQTT connection failed ... Reason: %s", exc)
        app.state.mqtt = None
        app.state.mqtt_ok = False
```

**Settings-cache `.get()` with default pattern** (`src/gruvax/api/units.py` lines 108–110):
```python
nominal_capacity: int = int(
    getattr(request.app.state, "settings_cache", {}).get("cube.nominal_capacity", 95)
)
```
Apply the same `.get(key, default)` pattern for all `settings_cache` LED key reads — never bare `[]` (Pitfall D in RESEARCH.md).

**Core publish pattern** (from RESEARCH.md §Pattern 2 and §Pattern 3 — verified against installed aiomqtt 2.5.1):
```python
import asyncio
import json
import logging
from datetime import UTC, datetime

import aiomqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

logger = logging.getLogger(__name__)


def _make_expiry_props(seconds: int) -> Properties:
    props = Properties(PacketTypes.PUBLISH)
    props.MessageExpiryInterval = seconds
    return props


async def safe_publish(
    client: aiomqtt.Client,
    topic: str,
    payload: bytes,
    *,
    qos: int = 0,
    retain: bool = False,
    properties: Properties | None = None,
    timeout: float = 0.25,
) -> bool:
    """Non-blocking publish that swallows timeout and MQTT errors."""
    try:
        await client.publish(
            topic, payload, qos=qos, retain=retain,
            properties=properties, timeout=timeout,
        )
        return True
    except Exception as exc:
        logger.warning("MQTT publish failed (topic=%s): %s", topic, exc)
        return False
```

**Fire-and-forget fan-out pattern** (from RESEARCH.md §Pattern 4 and §Pitfall F):
```python
# Publish three command topics concurrently in one network RTT
await asyncio.gather(
    safe_publish(client, illuminate_topic, illuminate_bytes, qos=0, timeout=0.25),
    safe_publish(client, span_topic, span_bytes, qos=0, timeout=0.25),
    safe_publish(client, sub_topic, sub_bytes, qos=0, timeout=0.25),
    return_exceptions=True,
)
# Then publish retained state/* topics (QoS 1, retain=True, with expiry props)
await safe_publish(
    client, state_topic, state_bytes,
    qos=1, retain=True,
    properties=_make_expiry_props(settings.MQTT_STATE_EXPIRY_SECONDS),
    timeout=0.5,
)
```

**All-off enumeration pattern** (from RESEARCH.md §Pattern 7 — uses DB like `src/gruvax/api/units.py` lines 62–73):
```python
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute("SELECT id, rows, cols FROM gruvax.units ORDER BY ordering")
    units = await cur.fetchall()
tasks = []
for unit_id, rows, cols in units:
    for r in range(rows):
        for c in range(cols):
            state_topic = f"{prefix}/state/{unit_id}/{r}/{c}"
            tasks.append(safe_publish(client, state_topic, b'', retain=True, qos=1, timeout=0.5))
await asyncio.gather(*tasks, return_exceptions=True)
await safe_publish(client, f"{prefix}/all/off", b'{}', qos=1, retain=False, timeout=0.5)
```

**Diagnostic transient subscribe pattern** (from RESEARCH.md §Pattern 6 — uses `asyncio.timeout`, stdlib Python 3.11+, confirmed available on 3.14):
```python
status_topic = f"{prefix}/status/#"
await client.subscribe(status_topic, qos=1)
try:
    async with asyncio.timeout(5.0):
        async for msg in client.messages:
            logger.info(
                "LED status from firmware: topic=%s payload=%s",
                msg.topic, msg.payload,
            )
except TimeoutError:
    pass  # expected — no hardware in v1
finally:
    await client.unsubscribe(status_topic)
```

---

### `src/gruvax/mqtt/topics.py` (utility, transform)

**No direct analog** — new thin module. Use pure-function style (no class, no state). Pattern from RESEARCH.md §Code Examples:
```python
# src/gruvax/mqtt/topics.py
def illuminate_topic(prefix: str, unit_id: int, row: int, col: int) -> str:
    return f"{prefix}/illuminate/{unit_id}/{row}/{col}"

def span_topic(prefix: str, change_id: str) -> str:
    return f"{prefix}/span/{change_id}"

def sub_topic(prefix: str, unit_id: int, row: int, col: int) -> str:
    return f"{prefix}/sub/{unit_id}/{row}/{col}"

def state_topic(prefix: str, unit_id: int, row: int, col: int) -> str:
    return f"{prefix}/state/{unit_id}/{row}/{col}"

def all_off_topic(prefix: str) -> str:
    return f"{prefix}/all/off"

def diagnostic_topic(prefix: str) -> str:
    return f"{prefix}/diagnostic"

def status_wildcard(prefix: str) -> str:
    return f"{prefix}/status/#"
```

---

### `src/gruvax/mqtt/client.py` — MODIFY (add `protocol=ProtocolVersion.V5`)

**Analog:** `src/gruvax/mqtt/client.py` (self — one-line addition)

**Change:** Line 47 — add `protocol=ProtocolVersion.V5` to the `aiomqtt.Client(...)` constructor. No other changes to this file.

**Current pattern** (lines 47–59):
```python
client = aiomqtt.Client(
    hostname=settings.MQTT_HOST,
    port=settings.MQTT_PORT,
    username=settings.MQTT_USERNAME,
    password=settings.MQTT_PASSWORD,
    identifier="gruvax-api",
    will=aiomqtt.Will(
        topic=_HELLO_TOPIC,
        payload=_HELLO_DEAD,
        retain=True,
    ),
    keepalive=30,
)
```

**After modification** — add `protocol=ProtocolVersion.V5` (from RESEARCH.md §Pattern 1):
```python
from aiomqtt import Client, ProtocolVersion

client = aiomqtt.Client(
    hostname=settings.MQTT_HOST,
    port=settings.MQTT_PORT,
    username=settings.MQTT_USERNAME,
    password=settings.MQTT_PASSWORD,
    identifier="gruvax-api",
    protocol=ProtocolVersion.V5,          # ADD: enables MQTT 5 Properties wire encoding
    will=aiomqtt.Will(
        topic=_HELLO_TOPIC,
        payload=_HELLO_DEAD,
        retain=True,
    ),
    keepalive=30,
)
```

---

### `src/gruvax/api/illuminate.py` (controller, request-response)

**Analog:** `src/gruvax/api/locate.py`

**Imports pattern** (`src/gruvax/api/locate.py` lines 22–37):
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from gruvax.api.deps import get_collection_snapshot, get_pool, get_segment_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["locate"])
```

**Public endpoint pattern — no `require_admin`, asyncio.create_task fire-and-forget** (from RESEARCH.md §Pattern 4):
```python
# src/gruvax/api/illuminate.py
import asyncio
from datetime import UTC, datetime
from typing import Any

import aiomqtt
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["illuminate"])


class IlluminateRequest(BaseModel):
    """Body: the LocateResult the kiosk already holds from /api/locate (D-03)."""
    release_id: int
    primary_cube: dict[str, int] | None
    label_span: list[dict[str, int]]
    sub_cube_interval: dict[str, Any] | None
    confidence: float


@router.post("/illuminate")
async def illuminate(
    request: Request,
    body: IlluminateRequest,
) -> dict[str, Any]:
    client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
    settings_cache: dict = getattr(request.app.state, "settings_cache", {})

    if client is not None:
        asyncio.create_task(
            publishers.fan_out_illuminate(client, body, settings_cache)
        )

    return {"published": client is not None, "accepted_at": datetime.now(UTC).isoformat()}
```

**Router registration pattern** — add to `src/gruvax/app.py` following lines 207–211 (public routers before admin):
```python
from gruvax.api.illuminate import router as illuminate_router
app.include_router(illuminate_router, prefix="/api")
```

---

### `src/gruvax/api/admin/leds.py` (controller, request-response)

**Analog:** `src/gruvax/api/admin/segments.py`

**Imports pattern** (`src/gruvax/api/admin/segments.py` lines 44–70):
```python
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gruvax.api.deps import (
    get_pool,
    require_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-leds"])
```

**Admin endpoint pattern: require_admin + BackgroundTasks** (from RESEARCH.md §Pattern 5):
```python
# POST /api/admin/leds/diagnostic
from fastapi import BackgroundTasks

@router.post("/leds/diagnostic")
async def start_diagnostic(
    request: Request,
    background_tasks: BackgroundTasks,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    run_id = str(_uuid.uuid4())
    client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
    settings_cache: dict = getattr(request.app.state, "settings_cache", {})

    background_tasks.add_task(
        publishers.run_diagnostic,
        client=client,
        pool=pool,
        settings_cache=settings_cache,
        run_id=run_id,
    )
    return {"run_id": run_id, "started_at": datetime.now(UTC).isoformat()}
```

**Admin endpoint pattern: require_admin + idempotent action** — all-off follows the same pattern as `segments.py` POST handlers (lines 317–447): `_admin = Depends(require_admin)` guard, pool for DB, return JSONResponse:
```python
@router.post("/leds/off")
async def leds_all_off(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
    settings_cache: dict = getattr(request.app.state, "settings_cache", {})
    published = 0
    if client is not None:
        published = await publishers.publish_all_off(client, pool, settings_cache)
    return {"published": published}
```

**Error handling pattern** — mirror `locate.py` (lines 90–99): use `raise HTTPException(status_code=...)` for hard failures, return 200 with body for soft degraded-mode (MQTT None):
```python
# Degraded mode: don't raise on client=None — return {"published": False}
# Only raise HTTP 503 for infrastructure failures the caller must know about
```

---

### `src/gruvax/api/admin/router.py` — MODIFY

**Analog:** `src/gruvax/api/admin/router.py` (self, lines 14–40)

**Pattern to extend** (lines 24–39) — add `leds_router` import inside `create_admin_router()`:
```python
def create_admin_router() -> APIRouter:
    from gruvax.api.admin.cubes import router as cubes_router
    from gruvax.api.admin.editing import router as editing_router
    from gruvax.api.admin.history import router as history_router
    from gruvax.api.admin.labels import router as labels_router
    from gruvax.api.admin.leds import router as leds_router        # ADD
    from gruvax.api.admin.login import router as login_router
    from gruvax.api.admin.segments import router as segments_router
    from gruvax.api.admin.settings import router as settings_router

    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(login_router)
    router.include_router(cubes_router)
    router.include_router(history_router)
    router.include_router(settings_router)
    router.include_router(editing_router)
    router.include_router(segments_router)
    router.include_router(labels_router)
    router.include_router(leds_router)                              # ADD
    return router
```

---

### `src/gruvax/api/admin/settings.py` — MODIFY (extend `_ALLOWED_SETTINGS_KEYS`)

**Analog:** `src/gruvax/api/admin/settings.py` (self)

**Pattern to extend** (line 28 — the frozenset, and lines 71–86 — the key_map):
```python
# Current (line 28):
_ALLOWED_SETTINGS_KEYS = frozenset({"cube.nominal_capacity", "session.idle_ttl_seconds"})

# After extension:
_ALLOWED_SETTINGS_KEYS = frozenset({
    "cube.nominal_capacity",
    "session.idle_ttl_seconds",
    # Phase 6: LED presentation settings
    "led_color.position",
    "led_color.label_span",
    "led_color.error",
    "led_color.setup",
    "led_color.all_off",
    "led_brightness.ambient",
    "led_brightness.active",
    "led_transition.position_style",
    "led_transition.position_ms",
    "led_transition.span_style",
    "led_transition.span_ms",
})
```

**Settings read/write pattern** (lines 41–101) — extend `get_settings` response to include LED keys; extend `update_settings` key_map to include LED keys. Follow the existing `key_map` dict pattern (lines 71–75):
```python
key_map = {
    "cube_nominal_capacity": "cube.nominal_capacity",
    "session_idle_ttl_seconds": "session.idle_ttl_seconds",
    # Phase 6 LED keys:
    "led_color_position": "led_color.position",
    "led_color_label_span": "led_color.label_span",
    "led_color_error": "led_color.error",
    "led_color_setup": "led_color.setup",
    "led_color_all_off": "led_color.all_off",
    "led_brightness_ambient": "led_brightness.ambient",
    "led_brightness_active": "led_brightness.active",
}
```

**Settings cache refresh pattern** (lines 91–99) — POST /settings already refreshes; the same `load_settings_cache` call pattern must be applied after any LED settings write:
```python
from gruvax.db.queries import load_settings_cache
try:
    request.app.state.settings_cache = await load_settings_cache(pool)
except Exception as exc:
    logger.warning("Settings cache refresh failed after PUT /settings: %s", exc)
```

---

### `src/gruvax/settings.py` — MODIFY (add MQTT_TOPIC_PREFIX + MQTT_STATE_EXPIRY_SECONDS)

**Analog:** `src/gruvax/settings.py` (self — lines 27–32, existing MQTT block)

**Current MQTT block** (lines 27–32):
```python
# ── MQTT ─────────────────────────────────────────────────────────────────────
MQTT_HOST: str = "localhost"
MQTT_PORT: int = 1883
MQTT_USERNAME: str = "gruvax"
MQTT_PASSWORD: str = "gruvax"
```

**After extension:**
```python
# ── MQTT ─────────────────────────────────────────────────────────────────────
MQTT_HOST: str = "localhost"
MQTT_PORT: int = 1883
MQTT_USERNAME: str = "gruvax"
MQTT_PASSWORD: str = "gruvax"
# Topic prefix separates dev and prod retained messages (D-14, Pitfall 3).
# Dev: "gruvax/v1/dev/leds"  Prod: "gruvax/v1/leds"
MQTT_TOPIC_PREFIX: str = "gruvax/v1/dev/leds"
# Default retained-state expiry in seconds (D-12 — 4h default, "no expiry" rejected).
MQTT_STATE_EXPIRY_SECONDS: int = 14400  # 4 * 3600
```

Pattern: no default for `DATABASE_URL` (required) vs. defaults for optional knobs — `MQTT_TOPIC_PREFIX` and `MQTT_STATE_EXPIRY_SECONDS` both have sensible defaults (topology operators may override via env).

---

### `migrations/versions/0006_led_settings_seed.py` (migration, CRUD)

**Analog:** `migrations/versions/0004_admin_tables.py`

**Header pattern** (`migrations/versions/0004_admin_tables.py` lines 1–33):
```python
"""Seed LED color/brightness/transition defaults in gruvax.settings.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-23

Phase 6: LED Contract over MQTT (Hardware Stubbed)
...

Conventions (carried from 0001-0005):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() removes only the rows seeded here (DELETE WHERE key IN ...).
"""

from __future__ import annotations

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None
```

**Seed pattern** — `gruvax.settings` uses `ON CONFLICT (key) DO NOTHING` so reruns are safe (same idiom as the Phase 3 seed in migration 0004):
```python
def upgrade() -> None:
    op.execute("""
        INSERT INTO gruvax.settings (key, value, description)
        VALUES
            ('led_color.position',        '"#FFD700"', 'LED: primary/position cube color (gold)'),
            ('led_color.label_span',      '"#7C3AED"', 'LED: label-span cube color (purple)'),
            ('led_color.error',           '"#E63946"', 'LED: error state color'),
            ('led_color.setup',           '"#0077B6"', 'LED: setup/diagnostic color'),
            ('led_color.all_off',         '"#000000"', 'LED: all-off color'),
            ('led_brightness.ambient',    '128',       'LED: ambient brightness ceiling (0-255, ~50%)'),
            ('led_brightness.active',     '255',       'LED: active brightness ceiling (0-255, 100%)'),
            ('led_transition.position_style', '"pulse"', 'LED: primary cube transition style'),
            ('led_transition.position_ms',    '800',     'LED: primary cube transition duration ms'),
            ('led_transition.span_style',     '"fade"',  'LED: label-span transition style'),
            ('led_transition.span_ms',        '500',     'LED: label-span transition duration ms')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM gruvax.settings
        WHERE key IN (
            'led_color.position', 'led_color.label_span', 'led_color.error',
            'led_color.setup', 'led_color.all_off',
            'led_brightness.ambient', 'led_brightness.active',
            'led_transition.position_style', 'led_transition.position_ms',
            'led_transition.span_style', 'led_transition.span_ms'
        )
    """)
```

Note: colors stored as JSON strings `'"#FFD700"'` (consistent with `auth.pin_hash` storage pattern in `admin/settings.py` lines 163–170 which wraps hashes in `f'"{new_hash}"'`).

---

### `frontend/src/routes/admin/Settings.tsx` — MODIFY (add LEDs section)

**Analog:** `frontend/src/routes/admin/Settings.tsx` (self — existing sections as template)

**Section structure pattern** (lines 111–166, "CHANGE PIN" section):
```tsx
{/* ── LEDs ──────────────────────────────────────────────────────────── */}
<section className="settings-section" aria-labelledby="leds-heading">
  <h2 id="leds-heading" className="settings-heading">LEDS</h2>

  {/* Color picker per state */}
  <div className="settings-field">
    <label className="settings-label" htmlFor="led-color-position">
      POSITION COLOR
    </label>
    <input
      id="led-color-position"
      type="color"
      value={ledColorPosition}
      onChange={(e) => setLedColorPosition(e.target.value)}
      className="settings-color-input"
    />
    {/* Inline color-blind preview — no external deps */}
    <ColorBlindPreview hex={ledColorPosition} />
  </div>

  {/* Brightness slider (ambient ceiling) */}
  <div className="settings-field">
    <label className="settings-label" htmlFor="led-brightness-ambient">
      AMBIENT BRIGHTNESS (LABEL SPAN)
    </label>
    <input
      id="led-brightness-ambient"
      type="range"
      min={0}
      max={255}
      value={ledBrightnessAmbient}
      onChange={(e) => setLedBrightnessAmbient(parseInt(e.target.value, 10))}
      className="settings-range-input"
    />
    <span className="settings-value-mono">{ledBrightnessAmbient}</span>
  </div>

  {ledsError && <p className="settings-error" role="alert">{ledsError}</p>}
  {ledsStatus === 'saved' && <p className="settings-success" role="status">LED settings saved.</p>}

  <div className="settings-actions">
    <button
      type="button"
      className="settings-btn-primary"
      onClick={() => { void handleSaveLeds() }}
      disabled={ledsStatus === 'saving'}
    >
      {ledsStatus === 'saving' ? 'SAVING…' : 'SAVE LED SETTINGS'}
    </button>
    <button
      type="button"
      className="settings-btn-secondary"
      onClick={() => { void handleLedsAllOff() }}
    >
      ALL OFF
    </button>
    <button
      type="button"
      className="settings-btn-secondary"
      onClick={() => { void handleLedsDiagnostic() }}
    >
      RUN DIAGNOSTIC
    </button>
  </div>
</section>
```

**Admin API call pattern** — follow `adminClient.ts` `adminFetch` + CSRF wrapper (lines 52–77). Add these to `adminClient.ts`:
```typescript
/** GET/PUT /api/admin/settings — LED section extends existing endpoint */
// (Already covered by existing getAdminSettings / putAdminSettings;
//  add LED keys to the AdminSettings type in types.ts)

/** POST /api/admin/leds/off — idempotent all-off */
export async function ledsAllOff(): Promise<{ published: number }> {
  const res = await adminFetch('/api/admin/leds/off', { method: 'POST' })
  if (!res.ok) throw new Error(`LEDs all-off failed: ${res.status}`)
  return res.json() as Promise<{ published: number }>
}

/** POST /api/admin/leds/diagnostic — returns run_id immediately */
export async function ledsDiagnostic(): Promise<{ run_id: string; started_at: string }> {
  const res = await adminFetch('/api/admin/leds/diagnostic', { method: 'POST' })
  if (!res.ok) throw new Error(`LED diagnostic failed: ${res.status}`)
  return res.json() as Promise<{ run_id: string; started_at: string }>
}
```

**SaveStatus pattern** — reuse the `'idle' | 'saving' | 'saved' | 'error'` union (line 21) and the `setTimeout(() => setStatus('idle'), 2000)` reset (lines 61–62). No new state machine needed.

**Color-blind preview** — inline component using matrix multiply (from RESEARCH.md §Code Examples, no new packages):
```typescript
// ColorBlindPreview.tsx or inline in Settings.tsx
const MATRICES = {
  deuteranopia: [[0.625, 0.375, 0.000], [0.700, 0.300, 0.000], [0.000, 0.300, 0.700]],
  protanopia:   [[0.567, 0.433, 0.000], [0.558, 0.442, 0.000], [0.000, 0.242, 0.758]],
  tritanopia:   [[0.950, 0.050, 0.000], [0.000, 0.433, 0.567], [0.000, 0.475, 0.525]],
} as const

function simulateColorBlindness(hex: string, type: keyof typeof MATRICES): string {
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const m = MATRICES[type]
  const nr = Math.round((m[0][0]*r + m[0][1]*g + m[0][2]*b) * 255)
  const ng = Math.round((m[1][0]*r + m[1][1]*g + m[1][2]*b) * 255)
  const nb = Math.round((m[2][0]*r + m[2][1]*g + m[2][2]*b) * 255)
  return `#${nr.toString(16).padStart(2,'0')}${ng.toString(16).padStart(2,'0')}${nb.toString(16).padStart(2,'0')}`
}
```

---

### Kiosk illuminate call — MODIFY `ResultsList.tsx` or `KioskView.tsx`

**Analog:** `frontend/src/routes/kiosk/ResultsList.tsx` lines 64–78 (the `locateRelease` imperative call pattern)

**Fire-and-forget POST /api/illuminate after locate** — add immediately after `setLocateResult(result)`:
```typescript
// In ResultsList.tsx, after setLocateResult(result):
void locateRelease(top.release_id)
  .then((result) => {
    setLocateResult(result)
    // Phase 6: fire-and-forget illuminate — never block locate path
    void illuminateRecord(result).catch(() => {
      // Swallow — broker may be in degraded mode
    })
  })
  .catch(() => {
    setHighlightCube(null)
  })
```

**`illuminateRecord` in `client.ts`** — add alongside `locateRelease` (lines 25–35) following same fetch-wrapper pattern:
```typescript
import type { LocateResult } from './types'

export async function illuminateRecord(result: LocateResult): Promise<void> {
  const res = await fetch('/api/illuminate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(result),
  })
  if (!res.ok) {
    throw new Error(`Illuminate failed: ${res.status}`)
  }
}
```

No auth header needed — `POST /api/illuminate` is public (D-03, unauthenticated per ARCHITECTURE). No CSRF (`adminFetch` is only for admin routes). Use plain `fetch`, not `adminFetch`.

---

## Shared Patterns

### Authentication / Authorization Split
**Source:** `src/gruvax/api/deps.py` lines 132–222 (`require_admin`)
**Apply to:** `api/admin/leds.py` — all handlers get `_admin: dict[str, str] = Depends(require_admin)`.
**Do NOT apply to:** `api/illuminate.py` — public endpoint (D-03).

```python
# Admin-gated handler signature:
async def handler(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    ...

# Public handler signature (no require_admin):
async def illuminate(request: Request, body: IlluminateRequest) -> dict[str, Any]:
    ...
```

### CSRF Pattern
**Source:** `frontend/src/api/adminClient.ts` lines 47–77 (`adminFetch` wrapper)
**Apply to:** All new admin API calls in `adminClient.ts` (`ledsAllOff`, `ledsDiagnostic`).
**Do NOT apply to:** `illuminateRecord` in `client.ts` — public endpoint, no CSRF needed.

### Settings Cache Access
**Source:** `src/gruvax/api/units.py` lines 108–110
**Apply to:** `publishers.py` — all `settings_cache.get(key, default)` reads.

```python
# Always .get() with a hardcoded default — never bare dict[] access:
color_hex: str = str(settings_cache.get("led_color.position", "#FFD700"))
brightness_active: int = int(settings_cache.get("led_brightness.active", 255))
```

### Degraded-Mode Posture
**Source:** `src/gruvax/mqtt/client.py` lines 64–73
**Apply to:** All publisher functions and both new API endpoints.

```python
# Pattern: check client not None, log warning, continue serving
client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
if client is None:
    logger.warning("MQTT not connected — illuminate request acknowledged but not published")
    return {"published": False, "accepted_at": datetime.now(UTC).isoformat()}
```

### Logging Pattern
**Source:** `src/gruvax/mqtt/client.py` lines 27, 64, 70
**Apply to:** All new Python files.

```python
logger = logging.getLogger(__name__)
# Use % formatting (not f-strings) for log messages:
logger.warning("MQTT publish failed (topic=%s): %s", topic, exc)
logger.info("LED all-off: published %d clear-retained payloads", count)
```

### Pydantic v2 Payload Models
**Source:** `src/gruvax/estimator/contract.py` (dataclass pattern) + RESEARCH.md §Code Examples (Pydantic for MQTT payloads)
**Apply to:** `src/gruvax/mqtt/publishers.py` or a separate `src/gruvax/mqtt/schemas.py`

```python
# Use Pydantic BaseModel (not dataclass) for MQTT payload schemas —
# they need .model_dump_json() for JSON serialization.
from pydantic import BaseModel
from typing import Literal

class RGBColor(BaseModel):
    r: int  # 0..255
    g: int
    b: int

class TransitionSpec(BaseModel):
    style: Literal["pulse", "fade", "instant"]
    duration_ms: int

class IlluminatePayload(BaseModel):
    schema_: str = "gruvax.illuminate.v1"
    issued_at: str
    unit_id: int
    row: int
    col: int
    color: RGBColor
    brightness: int  # 0..255, server-clamped
    duration_ms: int | None = None
    transition: TransitionSpec

    model_config = {"populate_by_name": True}
```

### DB Query Pattern (psycopg async, %s placeholders)
**Source:** `src/gruvax/db/queries.py` lines 66–110 (pool connection pattern)
**Apply to:** `publishers.py` `publish_all_off` (unit enumeration), `run_diagnostic` (unit list fetch).

```python
# Short-lived connection — open and close for the fetch only:
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute("SELECT id, rows, cols FROM gruvax.units ORDER BY ordering")
    units = await cur.fetchall()
# Do not hold connection open through the publish loop.
```

### Admin Client Error Class Pattern
**Source:** `frontend/src/api/adminClient.ts` lines 531–572
**Apply to:** No new error classes needed for LED endpoints — `ledsAllOff` and `ledsDiagnostic` use plain `Error` (they have no structured 400 responses like `BulkSaveError`).

---

## No Analog Found

All files have codebase analogs. None require falling back to RESEARCH.md patterns alone — but RESEARCH.md §Pattern 2 (MQTT 5 Properties) and §Code Examples (color-blind matrices) supplement the codebase analogs for the MQTT 5-specific logic and frontend matrix math that has no prior codebase example.

---

## Metadata

**Analog search scope:** `src/gruvax/`, `frontend/src/`, `migrations/versions/`
**Files scanned:** 15 Python source files, 8 TypeScript/TSX files, 5 Alembic migrations
**Pattern extraction date:** 2026-05-23
