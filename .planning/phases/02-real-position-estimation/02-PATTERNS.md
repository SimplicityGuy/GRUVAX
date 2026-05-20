# Phase 2: Real Position Estimation — Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 20 new/modified files
**Analogs found:** 19 / 20

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/gruvax/estimator/collection_snapshot.py` | service/cache | CRUD (load once) | `src/gruvax/estimator/boundary_cache.py` | exact |
| `src/gruvax/estimator/algorithm.py` (extend) | service | transform | `src/gruvax/estimator/algorithm.py` (existing) | exact |
| `src/gruvax/api/locate.py` (extend) | route | request-response | `src/gruvax/api/locate.py` (existing) | exact |
| `src/gruvax/api/search.py` (extend) | route | request-response | `src/gruvax/api/search.py` (existing) | exact |
| `src/gruvax/api/deps.py` (extend) | middleware/dep | request-response | `src/gruvax/api/deps.py` (existing) | exact |
| `src/gruvax/app.py` (extend) | config/lifespan | CRUD | `src/gruvax/app.py` (existing) | exact |
| `src/gruvax/db/queries.py` (extend) | service | CRUD | `src/gruvax/db/queries.py` (existing) | exact |
| `migrations/versions/0003_pg_trgm_indexes.py` | migration | batch | `migrations/versions/0001_create_schema.py` | exact |
| `tests/unit/test_algorithm.py` (extend) | test | batch | `tests/unit/test_algorithm.py` (existing) | exact |
| `tests/unit/test_collection_snapshot.py` | test | batch | `tests/unit/test_algorithm.py` | exact |
| `tests/property/test_estimator_props.py` | test/property | batch | `tests/property/test_parser_props.py` | exact |
| `tests/fixtures/synth_collection.py` | utility/fixture | batch | `tests/conftest.py` | role-match |
| `tests/fixtures/golden_cases.yaml` | config/fixture | batch | `tests/fixtures/boundaries.yaml` | role-match |
| `scripts/run_all_algorithms.py` | utility | batch | no exact analog | no-analog |
| `tests/integration/test_locate.py` (extend) | test | request-response | `tests/integration/test_locate.py` (existing) | exact |
| `tests/integration/test_search.py` (extend) | test | request-response | `tests/integration/test_search.py` (existing) | exact |
| `frontend/src/api/types.ts` (extend) | model | transform | `frontend/src/api/types.ts` (existing) | exact |
| `frontend/src/state/store.ts` (extend) | store | event-driven | `frontend/src/state/store.ts` (existing) | exact |
| `frontend/src/routes/kiosk/SubCubeBar.tsx` | component | request-response | `frontend/src/routes/kiosk/Cube.tsx` | role-match |
| `frontend/src/routes/kiosk/SpanUnderlay.tsx` | component | request-response | `frontend/src/routes/kiosk/ShelfGrid.tsx` | role-match |
| `frontend/src/routes/kiosk/DidYouMean.tsx` | component | request-response | `frontend/src/routes/kiosk/NoResultsRow.tsx` | exact |
| `frontend/src/routes/kiosk/Cube.tsx` (extend) | component | request-response | `frontend/src/routes/kiosk/Cube.tsx` (existing) | exact |
| `frontend/src/routes/kiosk/ShelfGrid.tsx` (extend) | component | request-response | `frontend/src/routes/kiosk/ShelfGrid.tsx` (existing) | exact |
| `frontend/src/routes/kiosk/KioskView.tsx` (extend) | component | event-driven | `frontend/src/routes/kiosk/KioskView.tsx` (existing) | exact |

---

## Pattern Assignments

### `src/gruvax/estimator/collection_snapshot.py` (service/cache, CRUD load-once)

**Analog:** `src/gruvax/estimator/boundary_cache.py`

**Imports pattern** (lines 1–20):
```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool
```

**Core pattern — frozen dataclass + class with `_load_rows` seam** (lines 22–100):
```python
@dataclass(frozen=True)
class BoundaryRow:
    unit_id: int
    row: int
    col: int
    first_label: str | None
    # ... more fields

class BoundaryCache:
    def __init__(self) -> None:
        self._rows: list[BoundaryRow] = []

    async def load(self, pool: AsyncConnectionPool[AsyncConnection[object]]) -> None:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT ... FROM gruvax.cube_boundaries ORDER BY unit_id, row, col"
            )
            rows_raw = await cur.fetchall()
            self._rows = [BoundaryRow(*row) for row in rows_raw]

    def _load_rows(self, rows: list[BoundaryRow]) -> None:
        """Internal seam for testing: bypass DB and load rows directly."""
        self._rows = list(rows)

    def get_boundaries(self) -> Sequence[BoundaryRow]:
        return self._rows

    def invalidate(self) -> None:
        self._rows = []
```

**CollectionSnapshot adapts this exact pattern:** replace `_rows: list[BoundaryRow]` with `_by_label: dict[str, list[RecordRow]]`, replace `get_boundaries()` with `get_label_records(label: str) -> list[RecordRow]`, replace SQL with `SELECT release_id, label, catalog_number FROM gruvax.v_collection`. The `_load_rows` testing seam maps to a `_load_snapshot(by_label: dict[str, list[RecordRow]])` seam. The `invalidate()` method empties `_by_label = {}`.

**Label key:** use `label.casefold()` as the dict key — exactly what `boundary_cache.py` line 78 uses for the label range check: `b.first_label.casefold() <= label.casefold()`.

---

### `src/gruvax/estimator/algorithm.py` (extend — add `locate_by_index` + `locate` dispatcher)

**Analog:** `src/gruvax/estimator/algorithm.py` (existing — lines 1–106)

**Imports pattern** (lines 1–28):
```python
from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.contract import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    CubeRef,
    LocateResult,
)
from gruvax.estimator.normalize import catalog_in_range

__all__ = ["CUBE_ONLY_CONFIDENCE", "NO_BOUNDARY_CONFIDENCE", "locate_cube_only"]
```

Phase 2 extends `__all__` to include `"locate_by_index"`, `"locate"` and adds import of `SubInterval` from contract, `parse_key` from normalize, and `CollectionSnapshot` from the new module.

**Core existing function signature pattern** (lines 31–36):
```python
def locate_cube_only(
    release_id: int,
    label: str,
    catalog_number: str,
    cache: BoundaryCache,
) -> LocateResult:
```

Phase 2 `locate_by_index` follows the same 4-arg signature pattern; the `locate` dispatcher adds a `snapshot: CollectionSnapshot` 5th arg.

**Error / no-boundary return pattern** (lines 87–94):
```python
if not covering:
    return LocateResult(
        release_id=release_id,
        primary_cube=None,
        label_span=[],
        sub_cube_interval=None,
        confidence=NO_BOUNDARY_CONFIDENCE,
    )
```

Phase 2 fallback to `locate_cube_only` follows the same pattern: always returns a `LocateResult`, never raises.

**Sorting pattern** (lines 97–98):
```python
sorted_span = sorted(covering, key=lambda c: (c.unit_id, c.row, c.col))
```

---

### `src/gruvax/api/locate.py` (extend)

**Analog:** `src/gruvax/api/locate.py` (existing — lines 1–99)

**Imports pattern** (lines 1–31):
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from gruvax.api.deps import get_boundary_cache, get_pool
from gruvax.db.queries import get_release_for_locate
from gruvax.estimator.algorithm import locate_cube_only
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.contract import CubeRef

logger = logging.getLogger(__name__)
router = APIRouter(tags=["locate"])
```

Phase 2 adds `get_collection_snapshot` to the deps import and `CollectionSnapshot` to the type import; replaces `locate_cube_only` import with `locate` dispatcher.

**Dependency injection pattern** (lines 41–47):
```python
@router.get("/locate")
async def locate(
    request: Request,
    release_id: int,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
) -> JSONResponse:
```

Phase 2 adds `snapshot: CollectionSnapshot = Depends(get_collection_snapshot)` as a 4th dep.

**404 pattern** (lines 65–74):
```python
record = await get_release_for_locate(pool, release_id)
if record is None:
    raise HTTPException(
        status_code=404,
        detail={
            "type": "release_not_in_collection",
            "release_id": release_id,
        },
    )
```

**Serialization pattern** (lines 87–98):
```python
body: dict[str, Any] = {
    "release_id": result.release_id,
    "primary_cube": _cube_ref_to_dict(result.primary_cube) if result.primary_cube else None,
    "label_span": [_cube_ref_to_dict(c) for c in result.label_span],
    "sub_cube_interval": None,
    "confidence": result.confidence,
    "generated_at": result.generated_at.isoformat(),
    "estimator_version": result.estimator_version,
}
return JSONResponse(content=body, status_code=200)
```

Phase 2 replaces `"sub_cube_interval": None` with a conditional serializer for the `SubInterval` dataclass fields (`start`, `end`, `crosses_boundary`, `next_cube`).

---

### `src/gruvax/api/search.py` (extend)

**Analog:** `src/gruvax/api/search.py` (existing — lines 1–56)

**Core response pattern** (lines 50–56):
```python
rows, took_ms = await search_collection(pool, q, limit)
return {
    "items": rows,
    "took_ms": round(took_ms, 2),
}
```

Phase 2 extends to:
```python
rows, took_ms, did_you_mean = await search_collection(pool, q, limit)
return {
    "items": rows,
    "took_ms": round(took_ms, 2),
    "did_you_mean": did_you_mean,
}
```

No changes to the `@router.get("/search")` decorator or `Query` params pattern.

---

### `src/gruvax/api/deps.py` (extend)

**Analog:** `src/gruvax/api/deps.py` (existing — lines 1–56)

**Dependency provider pattern** (lines 38–56):
```python
def get_boundary_cache(request: Request) -> BoundaryCache:
    """FastAPI dependency: return the app-level BoundaryCache.

    Returns HTTP 503 if the cache is not yet on ``app.state``.
    """
    cache: BoundaryCache | None = getattr(request.app.state, "boundary_cache", None)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Boundary cache not ready",
        )
    return cache
```

Phase 2 adds `get_collection_snapshot(request: Request) -> CollectionSnapshot` with identical structure: `getattr(request.app.state, "collection_snapshot", None)`, 503 on `None`, detail `"Collection snapshot not ready"`.

---

### `src/gruvax/app.py` (extend — lifespan startup)

**Analog:** `src/gruvax/app.py` (existing — lines 58–101)

**Lifespan startup pattern** (lines 83–92):
```python
# ── 3. Boundary cache (POS-04) ───────────────────────────────────────────
cache = BoundaryCache()
try:
    await cache.load(pool)  # type: ignore[arg-type]
    logger.info("Boundary cache loaded (%d rows)", len(list(cache.get_boundaries())))
except Exception as exc:
    logger.error("Boundary cache load failed: %s", exc)
    # Proceed with empty cache — locate will return no-boundary results.
app.state.boundary_cache = cache
```

Phase 2 inserts a step 3b immediately after step 3, following the identical try/except/log/state pattern:
```python
# ── 3b. Collection snapshot (POS-03) ────────────────────────────────────
from gruvax.estimator.collection_snapshot import CollectionSnapshot
snapshot = CollectionSnapshot()
try:
    await snapshot.load(pool)  # type: ignore[arg-type]
    logger.info("Collection snapshot loaded (%d labels)", len(snapshot._by_label))
except Exception as exc:
    logger.error("Collection snapshot load failed: %s", exc)
app.state.collection_snapshot = snapshot
```

---

### `src/gruvax/db/queries.py` (extend)

**Analog:** `src/gruvax/db/queries.py` (existing — lines 1–175)

**SQL function signature pattern** (lines 23–31):
```python
async def search_collection(
    pool: AsyncConnectionPool,
    q: str,
    limit: int,
) -> tuple[list[SearchRow], float]:
```

Phase 2 extends return type to `tuple[list[SearchRow], float, str | None]` (adds `did_you_mean`).

**SQL CTE pattern** (lines 61–135):
```python
sql = """
WITH fts AS (
    SELECT v.release_id, ..., ts_rank_cd(v.fts_vector, tsq.query, 4) AS score
    FROM gruvax.v_collection v
    CROSS JOIN websearch_to_tsquery('english', %s) AS tsq(query)
    WHERE v.fts_vector @@ tsq.query
    LIMIT 40
),
cat AS (
    SELECT release_id, ..., 0.9::float AS score
    FROM gruvax.v_collection
    WHERE lower(regexp_replace(catalog_number, '[\\s\\-_./]+', '', 'g'))
          LIKE lower(regexp_replace(%s, '[\\s\\-_./]+', '', 'g')) || '%%'
    LIMIT 20
),
combined AS (SELECT ... FROM fts UNION ALL SELECT ... FROM cat)
SELECT DISTINCT ON (release_id) ... FROM combined ORDER BY release_id, score DESC LIMIT %s
"""
t0 = time.perf_counter()
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(sql, (q, q, limit))
    rows_raw = await cur.fetchall()
    cols = [desc[0] for desc in (cur.description or [])]
took_ms = (time.perf_counter() - t0) * 1000.0
rows: list[SearchRow] = [dict(zip(cols, row, strict=True)) for row in rows_raw]
rows.sort(key=lambda r: r.get("rank", 0) or 0, reverse=True)
return rows, took_ms
```

Phase 2 additions follow this same pattern:
1. `is_catalog_query(q: str) -> bool` — a pure helper using `re.compile` with `_LEADING_DIGIT` / `_PREFIX_DIGITS` constants, no async, no pool.
2. `did_you_mean_query(pool, q) -> str | None` — new async function with its own SQL, same `async with pool.connection()` pattern, wraps in `try/except` for `psycopg.errors.UndefinedFunction` (Pitfall E graceful degrade).
3. Catalog boost: conditional branch inside `search_collection` — `if is_catalog_query(q):` uses modified FTS weights via `setweight()`; `else:` uses the existing path. All `%s` parameterized — never f-string interpolation (T-01-07).

---

### `migrations/versions/0003_pg_trgm_indexes.py` (new migration)

**Analog:** `migrations/versions/0001_create_schema.py` (lines 1–82)

**Header/metadata pattern** (lines 1–19):
```python
"""Create gruvax schema, units table, and cube_boundaries table.

Revision ID: 0001
Revises:
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None
```

Phase 2 migration: `revision = "0003"`, `down_revision = "0002"`. Uses `op.execute()` for raw SQL — same as Phase 1.

**Upgrade/downgrade pattern** (lines 22–81):
```python
def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS gruvax")
    op.execute("""CREATE TABLE gruvax.units (...)""")

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gruvax.cube_boundaries")
```

Phase 2 uses:
```python
def upgrade() -> None:
    # pg_trgm: attempt silently; app degrades if unavailable (Pitfall E)
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception:
        pass  # Insufficient privileges — SRCH-07/08 degrade gracefully

def downgrade() -> None:
    pass  # Never drop a shared extension; GIN indexes dropped with schema
```

---

### `tests/unit/test_algorithm.py` (extend)

**Analog:** `tests/unit/test_algorithm.py` (existing — lines 1–319)

**Unit test structure pattern** (lines 1–26):
```python
from __future__ import annotations

import pytest

from gruvax.estimator.algorithm import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    locate_cube_only,
)
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.contract import CubeRef, LocateResult, SubInterval
```

Phase 2 adds imports: `locate_by_index`, `locate` from `algorithm`, `CollectionSnapshot`, `RecordRow` from `collection_snapshot`.

**Synthetic cache builder pattern** (lines 78–95):
```python
def _make_cache_from_yaml(boundary_rows: list[dict]) -> BoundaryCache:
    cache = BoundaryCache()
    rows = [BoundaryRow(...) for row in boundary_rows]
    cache._load_rows(rows)  # seam method for testing without DB
    return cache
```

Phase 2 adds an analogous `_make_snapshot(records: list[dict]) -> CollectionSnapshot` helper using `snapshot._load_snapshot(by_label)`.

**Assertion pattern** (lines 115–148):
```python
def test_covered_record_confidence(boundary_cache: list[dict]) -> None:
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(release_id=1, label="Blue Note", catalog_number="BLP 4010", cache=cache)
    assert result.confidence == CUBE_ONLY_CONFIDENCE == 0.30
```

**Benchmark test pattern** — use `pytest-benchmark` `benchmark` fixture directly:
```python
def test_locate_benchmark(benchmark, ...):
    result = benchmark(lambda: [locate(...) for rid in release_ids[:100]])
    assert benchmark.stats['percentile_95'] < 50  # ms gate POS-03
```

**Synthetic cache with specific boundary rows** (lines 257–279) — exact pattern for golden cases:
```python
rows = [
    BoundaryRow(
        unit_id=1, row=0, col=0,
        first_label="TestLabel", first_catalog="BLP 10",
        last_label="TestLabel", last_catalog="BLP 20",
        is_empty=False,
    )
]
cache = BoundaryCache()
cache._load_rows(rows)
```

---

### `tests/unit/test_collection_snapshot.py` (new)

**Analog:** `tests/unit/test_algorithm.py` (structure and helper patterns above)

Tests to mirror from the algorithm test pattern:
- `test_snapshot_load_groups_by_label` — after `_load_snapshot(by_label)`, `get_label_records("Blue Note")` returns the right records
- `test_snapshot_label_case_folded` — `get_label_records("BLUE NOTE")` == `get_label_records("blue note")`
- `test_snapshot_invalidate_empties` — mirrors `test_cache_invalidate_empties` (lines 104–109)
- `test_snapshot_unknown_label_returns_empty` — `get_label_records("NONEXISTENT")` == `[]`
- `test_snapshot_load_from_db` — mirrors `test_cache_load_from_db` (lines 307–319), `@pytest.mark.asyncio(loop_scope="session")`

---

### `tests/property/test_estimator_props.py` (new)

**Analog:** `tests/property/test_parser_props.py` (existing — lines 1–180)

**Imports + strategy pattern** (lines 1–20):
```python
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from gruvax.estimator.normalize import (
    catalog_in_range,
    compare_catalogs,
    normalize_catalog,
    parse_key,
)
```

Phase 2 imports: `locate`, `locate_by_index` from `algorithm`; `CollectionSnapshot`, `RecordRow` from `collection_snapshot`; `BoundaryCache`, `BoundaryRow` from `boundary_cache`.

**Property test pattern** (lines 25–31):
```python
@given(a=st.text(), b=st.text())
@settings(max_examples=500)
def test_compare_catalogs_returns_valid_value(a: str, b: str) -> None:
    """compare_catalogs must always return -1, 0, or 1."""
    result = compare_catalogs(a, b)
    assert result in (-1, 0, 1), f"compare_catalogs({a!r}, {b!r}) = {result!r}"
```

Phase 2 Hypothesis invariants (per INTERPOLATION §7.3):
- `primary_cube ∈ label_span` — `@given(release_id=st.sampled_from(all_synth_ids))`
- `0 ≤ start ≤ end ≤ 1` — same strategy
- monotone within label — `@given(label=st.sampled_from(multi_record_labels))`
- cosmetic stability — `@given(..., noise=cosmetic_perturbations_strategy())`

Use session-scoped `synth_snapshot` and `synth_cache` fixtures (built from `synth_collection.py` without DB) following the conftest `boundary_cache` fixture pattern (lines 61–78 in conftest.py).

---

### `tests/fixtures/synth_collection.py` (new utility/fixture)

**Analog:** `tests/conftest.py` (fixture-building pattern, lines 61–78)

**Fixture YAML loading pattern** (conftest.py lines 61–78):
```python
@pytest.fixture(scope="session")
def boundary_cache() -> list[dict[str, Any]]:
    data: dict[str, Any] = yaml.safe_load(BOUNDARIES_YAML.read_text())
    cubes: list[dict[str, Any]] = []
    for unit in data["units"]:
        unit_id: int = unit["unit_id"]
        for cube in unit["cubes"]:
            cubes.append({**cube, "unit_id": unit_id})
    return cubes
```

`synth_collection.py` is NOT a pytest conftest file — it is a plain Python module with factory functions returning `(BoundaryCache, CollectionSnapshot, dict[int, float])` triplets (the last value is the planted truth). Each factory uses `BoundaryCache._load_rows()` and `CollectionSnapshot._load_snapshot()` seams (no DB). The module is imported by both `tests/property/test_estimator_props.py` and `scripts/run_all_algorithms.py`.

---

### `tests/fixtures/golden_cases.yaml` (new)

**Analog:** `tests/fixtures/boundaries.yaml` (YAML fixture structure — not read in this session but referenced at conftest.py lines 26–27)

Structure mirrors `boundaries.yaml` — a YAML file with top-level keys; unit tests load it via `yaml.safe_load()` then iterate over entries. Each golden case entry: `id`, `label`, `catalog_number`, `k` (label size), `expected_start`, `expected_end`, `expected_confidence`, `expected_crosses_boundary`.

---

### `tests/integration/test_locate.py` (extend)

**Analog:** `tests/integration/test_locate.py` (existing — lines 1–198)

**Integration test client fixture pattern** (lines 42–49):
```python
@pytest_asyncio.fixture(scope="module")
async def client(db_pool):
    app = create_app()
    async with LifespanManager(app) as manager, AsyncClient(
        transport=ASGITransport(app=manager.app),
        base_url="http://test",
    ) as ac:
        yield ac
```

**Integration assertion pattern** (lines 52–89):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_locate_covered(client) -> None:
    response = await client.get("/api/locate", params={"release_id": COVERED_RELEASE_ID})
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == pytest.approx(CUBE_ONLY_CONFIDENCE)
    assert body["sub_cube_interval"] is None
```

Phase 2 adds tests: `test_sub_cube_interval_populated`, `test_sub_cube_interval_bounds`, `test_multi_cube_label_span`, `test_singleton_full_cube_band`. Each follows the same `await client.get(...) → assert status 200 → assert body fields` pattern.

---

### `tests/integration/test_search.py` (extend)

**Analog:** `tests/integration/test_search.py` (existing — lines 1–182)

**No-results assertion pattern** (lines 99–107):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_no_results(client) -> None:
    response = await client.get("/api/search", params={"q": "zzznomatch"})
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "took_ms": body["took_ms"]}
    assert body["items"] == []
```

Phase 2 tests: `test_did_you_mean` — query with near-miss term, assert `body["did_you_mean"]` is non-null and a string; `test_catalog_boost` — two queries (one catalog-like `"BLP 4195"`, one artist `"Miles Davis"`), assert ranked order. Both follow existing `await client.get → assert 200 → assert body` pattern.

---

### `frontend/src/api/types.ts` (extend)

**Analog:** `frontend/src/api/types.ts` (existing — lines 1–67)

**Interface pattern** (lines 26–39):
```typescript
export interface CubeRef {
  unit_id: number
  row: number
  col: number
}

export interface LocateResult {
  release_id: number
  primary_cube: CubeRef | null
  label_span: CubeRef[]
  sub_cube_interval: null        // ← Phase 2 changes this to SubInterval | null
  confidence: number
  generated_at: string
  estimator_version: string
}
```

Phase 2 adds `SubInterval` interface above `LocateResult` and changes `sub_cube_interval` type; adds `did_you_mean: string | null` to `SearchResponse`.

---

### `frontend/src/state/store.ts` (extend)

**Analog:** `frontend/src/state/store.ts` (existing — lines 1–59)

**Store slice pattern** (lines 4–30):
```typescript
interface GruvaxStore {
  query: string
  setQuery: (q: string) => void
  selectedReleaseId: number | null
  setSelectedReleaseId: (id: number | null) => void
  highlight: HighlightState
  setHighlightCube: (cube: CubeRef | null) => void
  animationToken: number
  clearSearch: () => void
}
```

**Action with token increment pattern** (lines 43–47):
```typescript
setHighlightCube: (cube) =>
  set((s) => ({
    highlight: { primaryCube: cube },
    animationToken: s.animationToken + 1,
  })),
```

Phase 2 adds `labelSpan: CubeRef[]`, `subCubeInterval: SubInterval | null`, `confidence: number` to the interface, and a new `setLocateResult(result: LocateResult)` action that sets all three fields atomically AND increments `animationToken` in one `set((s) => ...)` call — same pattern as `setHighlightCube`. The `clearSearch` action gains `labelSpan: [], subCubeInterval: null, confidence: 0` resets.

---

### `frontend/src/routes/kiosk/SubCubeBar.tsx` (new component)

**Analog:** `frontend/src/routes/kiosk/Cube.tsx` (existing — lines 1–35)

**Component structure pattern** (lines 1–35):
```typescript
import type { CubeState } from '../../api/types'

interface CubeProps {
  unitId: number
  row: number
  col: number
  state: CubeState
  address: string
}

export function Cube({ unitId, row, col, state, address }: CubeProps) {
  return (
    <div
      className="cube"
      data-state={state}
      data-unit-id={unitId}
      data-row={row}
      data-col={col}
      aria-label={`Cube ${address}`}
    >
      <span className="cube__address">{address}</span>
    </div>
  )
}
```

`SubCubeBar` follows this pattern: named export of a function component with a typed `interface SubCubeBarProps`, returns a single `<div>` with CSS class tokens only — no inline hex. `pointer-events: none` (decoration only). The `isSingleton` boolean drives the class variant (`sub-cube-bar--singleton`). CSS handles the opacity formula; the component passes `style={{ '--confidence': confidence }}` as a CSS custom property for the opacity computation in the stylesheet.

The `aria-label="approximate position"` (when `confidence <= 0.50`) mirrors `Cube`'s `aria-label` pattern. The `~` low-confidence cue span follows `<span className="cube__address">` as a sibling span pattern.

---

### `frontend/src/routes/kiosk/SpanUnderlay.tsx` (new component)

**Analog:** `frontend/src/routes/kiosk/ShelfGrid.tsx` (existing — lines 1–69)

**Grid geometry computation pattern** (ShelfGrid.tsx lines 30–65):
```typescript
export function ShelfGrid({ unit, shelfIndex, litCube, emptyCubes }: ShelfGridProps) {
  for (let r = 0; r < unit.rows; r++) {
    for (let c = 0; c < unit.cols; c++) {
      const isLit = litCube != null && litCube.unit_id === unit.id
        && litCube.row === r && litCube.col === c
      ...
      cells.push(<Cube key={address} ... />)
    }
  }
  return <div className="shelf-grid">{cells}</div>
}
```

`SpanUnderlay` uses `labelSpan: CubeRef[]` (sorted) to compute band segments. It renders `position: absolute` `<div>` elements within the `.shelf-area` positioning context, using `cellSize` and `cellGap` props (from CSS tokens) for coordinate math — not `getBoundingClientRect()`. Groups spans by `(unit_id, row)` to handle row-wrapping geometry. Each band: `className="span-underlay__band"`, `style={{ left, top, width }}` — only layout values come from inline style; color/border come from CSS.

No GSAP in this component itself — GSAP `fromTo` on `spanUnderlayRef` is owned by `KioskView.tsx`.

---

### `frontend/src/routes/kiosk/DidYouMean.tsx` (new component)

**Analog:** `frontend/src/routes/kiosk/NoResultsRow.tsx` (existing — lines 1–33)

**NoResultsRow pattern** (lines 1–33):
```typescript
export function NoResultsRow() {
  return (
    <div className="no-results-row">
      <svg className="no-results-row__icon" viewBox="0 0 24 24" ...
        aria-hidden="true">
        ...
      </svg>
      <div className="no-results-row__text">
        <span className="no-results-row__heading">No records found</span>
        <span className="no-results-row__body">Try a different search...</span>
      </div>
    </div>
  )
}
```

`DidYouMean` follows the same DOM structure but adds:
- `interface DidYouMeanProps { suggestion: string; onTap: (term: string) => void }`
- `role="button"`, `tabIndex={0}`, `onKeyDown` handling Enter/Space (keyboard accessible — mirrors `ResultRow.tsx` lines 21–27 keyboard pattern)
- `aria-label={`Search for ${suggestion}`}`
- `min-height: 44px` touch target via CSS
- Suggestion term rendered uppercase: `suggestion.toUpperCase()`
- `onClick` and `onKeyDown` handlers call `onTap(suggestion)` — same shallow handler pattern as `ResultRow` `handleClick` / `handleKeyDown`

---

### `frontend/src/routes/kiosk/Cube.tsx` (extend)

**Analog:** `frontend/src/routes/kiosk/Cube.tsx` (existing — lines 1–35)

Phase 2 adds `subInterval?: SubInterval | null` and `confidence?: number` props to `CubeProps`. When `subInterval` is provided, renders a `<SubCubeBar>` child inside the cube `<div>`. The existing `data-state`, `data-unit-id`, `data-row`, `data-col` attributes are unchanged. The `SubCubeBar` is rendered as an absolutely-positioned child — no layout impact on the address overlay.

---

### `frontend/src/routes/kiosk/ShelfGrid.tsx` (extend)

**Analog:** `frontend/src/routes/kiosk/ShelfGrid.tsx` (existing — lines 1–69)

Phase 2 adds `labelSpan?: CubeRef[]`, `subCubeInterval?: SubInterval | null`, `confidence?: number` to `ShelfGridProps`. Passes `subInterval` and `confidence` down to `Cube` components matching `litCube`. Renders `<SpanUnderlay>` as a sibling to the `<div className="shelf-grid">` when `labelSpan && labelSpan.length > 1`. The `emptyCubes` prop pattern (optional Set with `??` fallback, lines 49–50) is the model for the optional new props.

---

### `frontend/src/routes/kiosk/KioskView.tsx` (extend — GSAP timeline + locate result wiring)

**Analog:** `frontend/src/routes/kiosk/KioskView.tsx` (existing — lines 1–166)

**useRef timer/cleanup pattern** (lines 25–31):
```typescript
const loadingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
// ...
useEffect(() => {
  if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current)
  // ...
  return () => {
    if (loadingTimerRef.current) clearTimeout(loadingTimerRef.current)
  }
}, [isFetching, debouncedQuery])
```

Phase 2 GSAP timeline pattern — same `useRef` + `useEffect` with cleanup:
```typescript
// Source: 02-UI-SPEC.md §GSAP hard-cancel pattern + 02-RESEARCH.md §CUBE-08
const timelineRef = useRef<gsap.core.Timeline | null>(null)
const spanUnderlayRef = useRef<HTMLElement | null>(null)
const primaryCubeRef = useRef<HTMLElement | null>(null)
const barRef = useRef<HTMLElement | null>(null)

useEffect(() => {
  timelineRef.current?.kill()           // Hard-cancel — D-06
  gsap.set(spanUnderlayRef.current, { opacity: 0 })
  gsap.set(barRef.current, { scaleX: 0 })

  const tl = gsap.timeline()
  tl.fromTo(spanUnderlayRef.current,
    { opacity: 0 }, { opacity: 0.60, duration: 0.15, ease: 'power2.out' })
  tl.fromTo(primaryCubeRef.current,
    { scale: 1 }, { scale: 1.04, duration: 0.10, ease: 'back.out(1.7)' })
  tl.to(primaryCubeRef.current,
    { scale: 1, duration: 0.10, ease: 'power2.inOut' })
  tl.fromTo(barRef.current,
    { scaleX: 0, transformOrigin: 'left center' },
    { scaleX: 1, duration: 0.20, ease: 'power2.out' }, '-=0.10')

  timelineRef.current = tl
  return () => { tl.kill() }
}, [animationToken])  // animationToken from Zustand
```

**TanStack Query imperative locate pattern** — follows the existing search query pattern (lines 53–62):
```typescript
const { data: searchData, isFetching, isError } = useQuery({
  queryKey: ['search', debouncedQuery],
  queryFn: () => searchCollection(debouncedQuery, 10),
  enabled: debouncedQuery.trim().length > 0,
  staleTime: 30_000,
})
```

Phase 2 adds a locate query with `enabled: selectedReleaseId !== null` and `onSuccess` calling `setLocateResult(data)`.

**ShelfGrid prop pass-through** — existing pattern (lines 136–143):
```typescript
<ShelfGrid
  unit={unit}
  shelfIndex={idx}
  litCube={highlight.primaryCube}
  emptyCubes={emptyCubes}
/>
```

Phase 2 adds `labelSpan={labelSpan}`, `subCubeInterval={subCubeInterval}`, `confidence={confidence}` to this spread.

---

## Shared Patterns

### Dependency Injection via `app.state`
**Source:** `src/gruvax/api/deps.py` (lines 16–56)
**Apply to:** `get_collection_snapshot` (new dep), any future state-backed deps
```python
def get_boundary_cache(request: Request) -> BoundaryCache:
    cache: BoundaryCache | None = getattr(request.app.state, "boundary_cache", None)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Boundary cache not ready",
        )
    return cache
```

### Lifespan Startup Load + Error Tolerance
**Source:** `src/gruvax/app.py` (lines 83–92)
**Apply to:** `CollectionSnapshot` startup load in `app.py`
```python
cache = BoundaryCache()
try:
    await cache.load(pool)
    logger.info("Boundary cache loaded (%d rows)", len(list(cache.get_boundaries())))
except Exception as exc:
    logger.error("Boundary cache load failed: %s", exc)
    # Proceed with empty — endpoint returns degraded result, not 500
app.state.boundary_cache = cache
```

### Parameterized SQL (Never f-string)
**Source:** `src/gruvax/db/queries.py` (lines 57–134)
**Apply to:** did_you_mean_query, catalog-boost SQL in queries.py
```python
# psycopg uses %s placeholders; q is never interpolated into SQL (T-01-07)
await cur.execute(sql, (q, q, limit))
```

### Testing Seam (`_load_rows`)
**Source:** `src/gruvax/estimator/boundary_cache.py` (lines 75–81)
**Apply to:** `CollectionSnapshot._load_snapshot()`, `synth_collection.py` factory functions
```python
def _load_rows(self, rows: list[BoundaryRow]) -> None:
    """Internal seam for testing: bypass DB and load rows directly."""
    self._rows = list(rows)
```

### pytest-asyncio Integration Test Client
**Source:** `tests/integration/test_locate.py` (lines 42–49)
**Apply to:** All integration test files (`test_locate.py` extension, `test_search.py` extension)
```python
@pytest_asyncio.fixture(scope="module")
async def client(db_pool):
    app = create_app()
    async with LifespanManager(app) as manager, AsyncClient(
        transport=ASGITransport(app=manager.app),
        base_url="http://test",
    ) as ac:
        yield ac
```

### `@pytest.mark.asyncio(loop_scope="session")`
**Source:** `tests/integration/test_locate.py` (lines 52, 92, 107, etc.)
**Apply to:** All async integration tests — required by pytest-asyncio 1.x to share session event loop with session-scoped `db_pool` fixture.

### React Component Props Interface
**Source:** `frontend/src/routes/kiosk/Cube.tsx` (lines 1–13)
**Apply to:** `SubCubeBar`, `SpanUnderlay`, `DidYouMean`
```typescript
import type { SomeType } from '../../api/types'

interface ComponentProps {
  // typed fields only
}

export function ComponentName({ ...props }: ComponentProps) {
  return (...)
}
```

### Keyboard Accessibility Pattern
**Source:** `frontend/src/routes/kiosk/ResultRow.tsx` (lines 21–27)
**Apply to:** `DidYouMean` (tappable button row)
```typescript
const handleKeyDown = (e: React.KeyboardEvent) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    onSelect(result)
  }
}
```

### CSS Token Consumption (No Hardcoded Hex)
**Source:** `design/gruvax-design-tokens.css` / `.json`
**Apply to:** All Phase 2 React components (`SubCubeBar`, `SpanUnderlay`, `DidYouMean`)

Use only `var(--gruvax-*)` references. The tokens that matter for Phase 2:
- `--gruvax-yellow` — bar fill, underlay
- `--gruvax-yellow-faint` = `rgba(255,218,0,0.12)` — underlay at rest, singleton band
- `--gruvax-yellow-glow` = `rgba(255,218,0,0.35)` — underlay border
- `--gruvax-warning` — did-you-mean icon
- `--gruvax-text-muted` — "~" cue
- `--gruvax-text-secondary` — did-you-mean suggestion text
- `--gruvax-space-1` through `--gruvax-space-4` — spacing
- `--gruvax-radius-sm` (4px), `--gruvax-radius-pill` (9999px)

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `scripts/run_all_algorithms.py` | utility/harness | batch | No precedent for a developer CLI script in this codebase. Closest analogy is the `benchmark` pytest test but this is a standalone script. Use standard `argparse` / `if __name__ == "__main__"` pattern with a `--ci` flag that skips the local CSV path. |

---

## Metadata

**Analog search scope:** `src/gruvax/`, `tests/`, `frontend/src/`, `migrations/`
**Files scanned:** 24 source files read
**Pattern extraction date:** 2026-05-20
