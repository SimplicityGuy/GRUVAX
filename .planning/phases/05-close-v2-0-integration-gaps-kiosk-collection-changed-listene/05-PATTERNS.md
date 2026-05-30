# Phase 5: Close v2.0 Integration Gaps (B-01 + B-02) — Pattern Map

**Mapped:** 2026-05-30
**Files analyzed:** 5 (2 new-test files + 3 modified source files)
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `frontend/src/routes/kiosk/KioskView.tsx` | component | event-driven | same file — existing `boundary_changed` / `server_hello` listeners | exact |
| `src/gruvax/api/search.py` | controller | request-response | same file — existing `profile_id` + `_snapshot` dep wiring | exact |
| `src/gruvax/api/locate.py` | controller | request-response | same file — existing `profile_id` + `segment_cache`/`snapshot` dep wiring | exact |
| `tests/integration/test_search_b02.py` (new) | test | request-response | `tests/integration/test_search.py` — module-scoped client + browse-binding cookie | exact |
| `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` | test | event-driven | same file — existing `boundary_changed` dispatch + `invalidateQueries` spy | exact |

---

## Pattern Assignments

### `frontend/src/routes/kiosk/KioskView.tsx` — B-01: add `collection_changed` listener

**Analog:** same file — existing named-event listeners in the SSE `useEffect`

**Existing listener-registration idiom** (`KioskView.tsx` lines 280–303, `boundary_changed`; lines 309–323, `admin_editing`; lines 326–333, `server_hello`; lines 335–339, `server_shutdown`):

```typescript
// Pattern: es.addEventListener('<event>', (e: MessageEvent) => { ... })
// Wrapped in try/catch for IN-02 (malformed frame degrades gracefully).
// Store mutations use useGruvaxStore.getState() — never the outer destructure (Pitfall 5).

es.addEventListener('boundary_changed', (e: MessageEvent) => {
  try {
    const { cube_ids } = JSON.parse(e.data) as {
      cube_ids: ShimmerCube[]
      change_set_id: string
    }
    void queryClient.invalidateQueries({ queryKey: ['cubes'] })
    void queryClient.invalidateQueries({ queryKey: ['units'] })
    // ...per-cube and re-locate calls...
  } catch (err) {
    console.error('[SSE] boundary_changed parse error — degrading gracefully', err)
  }
})

// Simpler event — no payload needed:
es.addEventListener('server_hello', () => {
  resync()
  void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
})

es.addEventListener('server_shutdown', () => {
  useGruvaxStore.getState().setSseConnected(false)
})
```

**Cleanup pattern** (`KioskView.tsx` lines 337–339):
```typescript
// Cleanup: close the connection on unmount (the ONLY es.close() call — Pitfall 4)
return () => {
  es.close()
}
```
The cleanup does NOT need to remove individual listeners — `es.close()` is the single teardown point. The new `collection_changed` listener lives inside the same `useEffect` and is cleaned up automatically with the `EventSource` itself.

**`resync()` function** (`KioskView.tsx` lines 245–255) — what it currently invalidates:
```typescript
const resync = () => {
  void queryClient.invalidateQueries({ queryKey: ['units'] })
  void queryClient.invalidateQueries({ queryKey: ['cubes'] })
  relocateActiveSelection()
}
```
**Important:** `resync()` does NOT invalidate `['search', ...]`. The `collection_changed` handler must add explicit search (and optionally health) invalidations — it must NOT just call `resync()` because that only covers grid data.

**Actual search query key** (`KioskView.tsx` line 169):
```typescript
queryKey: ['search', debouncedQuery, boundProfileId],
```
To bust ALL search results (not just the current query), invalidate by prefix key `['search']`:
```typescript
void queryClient.invalidateQueries({ queryKey: ['search'] })
```
This matches TanStack Query's prefix-invalidation semantics — all cached queries whose key starts with `['search']` will be refetched.

**Locate query:** Locate is imperative (called via `locateRelease(...)` directly, not a `useQuery` with a `['locate', id]` key — see `KioskView.EventSource.test.tsx` line 5 comment). The active selection re-locate after `collection_changed` is already handled by `relocateActiveSelection()` which is part of `resync()`. Call `resync()` AND add the `['search']` invalidation.

**New `collection_changed` handler to write** (mirrors `server_hello` — no payload expected from the publisher):
```typescript
// collection_changed: sync completed → invalidate search results + resync grid (B-01)
es.addEventListener('collection_changed', () => {
  void queryClient.invalidateQueries({ queryKey: ['search'] })
  resync()
})
```
Place immediately after `server_shutdown` listener (lines 335–339), before the cleanup `return`.

---

### `src/gruvax/api/search.py` — B-02: make `profile_id` optional

**Analog:** same file — existing `profile_id: str = Query()` at line 43 and the `_snapshot` Depends at line 45.

**Current signature** (`search.py` lines 38–46):
```python
@router.get("/search")
async def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    profile_id: str = Query(),                               # line 43 — CHANGE THIS
    pool: Any = Depends(get_pool),
    _snapshot: Any = Depends(get_snapshot_for_profile),      # line 45 — validates 400/403
) -> dict[str, Any]:
```

**Target signature** after B-02 fix:
```python
profile_id: str | None = Query(default=None),
```

**How `profile_id` currently flows to the data query** (`search.py` line 65):
```python
rows, took_ms, did_you_mean = await search_collection(pool, q, limit, profile_id)
```
After the fix, `profile_id` must be the resolved UUID (not raw `None`) before reaching `search_collection`. Resolution path:

**`resolve_profile_from_request` signature** (`deps.py` lines 179–233):
```python
async def resolve_profile_from_request(
    request: Request,
    pool: Any,
) -> tuple[str, str | None]:
    """Returns (profile_id_str, device_id_str|None).
    Raises 403 device_unknown, 403 device_revoked, or 400 session_unbound."""
```
The first element of the returned tuple is the authoritative `profile_id` string.

**D2-04 validation that must be preserved when `profile_id` IS supplied** (currently lives inside `get_snapshot_for_profile`, `deps.py` lines 293–323):
```python
async def get_snapshot_for_profile(profile_id: str, request: Request, pool: Any = Depends(get_pool)) -> CollectionSnapshot:
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
    if resolved_profile_id != profile_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail={"type": "profile_mismatch"})
    # ... registry lookup ...
```
When `profile_id` is **omitted**, the handler calls `resolve_profile_from_request` directly and uses the returned UUID as the effective `profile_id` — passing it to both `search_collection(...)` and the `get_snapshot_for_profile` dep call. When `profile_id` is **present**, the existing dep validates it (400/403) — no change needed.

**The `_snapshot` dep** currently depends on `profile_id` as a query parameter implicitly (FastAPI injects it from the same query params). After making `profile_id` optional, the dep will receive `None` when omitted, which will cause a type mismatch in `get_snapshot_for_profile(profile_id: str, ...)`. The fix requires **resolving `profile_id` in the handler body** (before calling the collection query), not relying solely on the existing dep for the resolved UUID. The `_snapshot` dep can be removed from the handler signature and its validation logic inlined, or the dep can be updated to accept `str | None` — the planner should choose the approach that minimizes diff surface while preserving the 400/403 contract.

---

### `src/gruvax/api/locate.py` — B-02: make `profile_id` optional

**Analog:** same file, same pattern as `search.py` above.

**Current signature** (`locate.py` lines 74–82):
```python
@router.get("/locate")
async def locate_endpoint(
    request: Request,
    release_id: int,
    profile_id: str = Query(),                                        # line 78 — CHANGE THIS
    pool: Any = Depends(get_pool),
    segment_cache: SegmentCache = Depends(get_segment_cache_for_profile),  # line 80 — 400/403
    snapshot: CollectionSnapshot = Depends(get_snapshot_for_profile),      # line 81 — 400/403
) -> JSONResponse:
```

**How `profile_id` flows to the data query** (`locate.py` line 106):
```python
record = await get_release_for_locate(pool, release_id, profile_id)
```

**Target signature change** (same as search):
```python
profile_id: str | None = Query(default=None),
```

**Both `segment_cache` and `snapshot` deps** take `profile_id: str` as their first param and call `resolve_profile_from_request` + profile_mismatch check (same pattern as `get_snapshot_for_profile` above). Same resolution strategy applies: resolve effective `profile_id` in the handler body when the query param is `None`, then use the resolved UUID for both deps and the data query call.

---

### `tests/integration/test_search_b02.py` (new RED tests — backend B-02)

**Analog:** `tests/integration/test_search.py` — module-scoped fixture with browse-binding cookie + `LifespanManager`.

**Client fixture pattern** (`test_search.py` lines 35–51) — copy verbatim, then add a second no-cookie client for the 400 case:
```python
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"

@pytest_asyncio.fixture(scope="module")
async def client(db_pool):
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
            cookies={BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID},
        ) as ac,
    ):
        yield ac
```

**Test marker pattern** (`test_search.py` line 54):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_...(client) -> None:
```

**Pattern for the B-02 RED tests** (what to assert):
```python
# RED test 1: search with no profile_id but valid browse-binding cookie → 200
response = await client.get("/api/search", params={"q": "Blue Note"})  # no profile_id
assert response.status_code == 200   # currently 422 before the fix

# RED test 2: locate with no profile_id but valid browse-binding cookie → 200
response = await client.get("/api/locate", params={"release_id": 1})   # no profile_id
assert response.status_code == 200   # currently 422 before the fix

# Preservation test 3: existing 400 path — no profile_id, no cookie → 400 session_unbound
# (needs a separate no-cookie client fixture)
response = await no_cookie_client.get("/api/search", params={"q": "Blue Note"})
assert response.status_code == 400
assert response.json()["detail"]["type"] == "session_unbound"

# Preservation test 4: existing 403 path — profile_id present but mismatched → 403
response = await client.get(
    "/api/search",
    params={"q": "Blue Note", "profile_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"},
)
assert response.status_code == 403
assert response.json()["detail"]["type"] == "profile_mismatch"
```

**No `dependency_overrides` needed here** — these are integration tests with a live DB pool (same as `test_search.py`). The `dependency_overrides` pattern (from `test_admin_led_settings.py` lines 128–146) is for unit tests that stub the pool. For B-02 backend tests, use the full `LifespanManager` + real pool (same as `test_search.py`).

**`dependency_overrides` pattern** for reference (unit test analog, `test_admin_led_settings.py` lines 128–146):
```python
from gruvax.api.deps import get_pool, require_admin
from gruvax.app import create_app

app = create_app()
app.dependency_overrides[require_admin] = _stub_require_admin

def _stub_get_pool() -> _FakePool:
    return fake_pool

app.dependency_overrides[get_pool] = _stub_get_pool
```

---

### `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` — B-01 + B-02 frontend RED tests

**Analog:** same file — existing `boundary_changed` dispatch + `invalidateQueries` spy tests.

**Test harness pattern** (`KioskView.EventSource.test.tsx` lines 84–103) — render + flush:
```typescript
async function renderKioskAndFlush(queryClient: QueryClient): Promise<MockEventSource> {
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <KioskView />
      </QueryClientProvider>,
    )
  })
  return MockEventSource.instances[MockEventSource.instances.length - 1]
}
```

**beforeEach session-store seed** (`KioskView.EventSource.test.tsx` lines 108–133) — required so the SSE effect creates an EventSource:
```typescript
useSessionStore.setState({
  profileCount: 1,
  boundProfileId: TEST_PROFILE_ID,
  profiles: [{ id: TEST_PROFILE_ID, ... }],
})
```

**`invalidateQueries` spy pattern** (`KioskView.EventSource.test.tsx` lines 155–169):
```typescript
const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
// ...trigger event...
const calledKeys = invalidateSpy.mock.calls.map(
  (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
)
expect(calledKeys).toContainEqual(['units'])
expect(calledKeys).toContainEqual(['cubes'])
```

**B-01 RED test to add** — `collection_changed` invalidates `['search']`:
```typescript
it('collection_changed invalidates search query key (B-01)', async () => {
  const qc = makeQueryClient()
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
  const es = await renderKioskAndFlush(qc)

  await act(async () => {
    es.dispatchEvent('collection_changed', {})
  })

  const calledKeys = invalidateSpy.mock.calls.map(
    (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
  )
  expect(calledKeys).toContainEqual(['search'])   // RED until B-01 listener is added
})
```

**B-02 frontend RED test** — search query disabled when `boundProfileId` is null:
```typescript
it('search query is disabled when boundProfileId is null (B-02)', async () => {
  // Override session store: unbound state
  useSessionStore.setState({ profileCount: 0, boundProfileId: null, profiles: [] })

  const qc = makeQueryClient()
  const fetchSpy = vi.spyOn(global, 'fetch')
  await renderKioskAndFlush(qc)

  // Simulate a search query arriving before session bootstrap resolves
  // (in the real component this comes via debouncedQuery, but here we
  // just assert no fetch was fired to /api/search)
  expect(fetchSpy).not.toHaveBeenCalledWith(
    expect.stringContaining('/api/search'),
    expect.anything(),
  )
})
```

**`boundProfileId` read from session store** (`KioskView.tsx` line 42):
```typescript
const boundProfileId = useSessionStore((s) => s.boundProfileId)
```

**Existing `enabled` gate** (`KioskView.tsx` line 171) — currently gates on query length only:
```typescript
enabled: debouncedQuery.trim().length > 0,
```

**Target `enabled` gate** after B-02 fix:
```typescript
enabled: !!boundProfileId && debouncedQuery.trim().length > 0,
```

---

## Shared Patterns

### SSE `es.addEventListener` idiom
**Source:** `frontend/src/routes/kiosk/KioskView.tsx` lines 280–339
**Apply to:** B-01 new `collection_changed` listener
- Named listeners use `es.addEventListener(name, handler)` — NOT `es.onmessage`.
- Simple no-payload events (like `server_hello`, `server_shutdown`) use `() => { ... }` — no `e` parameter, no try/catch needed.
- Events with payloads use `(e: MessageEvent) => { try { JSON.parse(e.data) } catch(err) { console.error(...) } }`.
- `collection_changed` has no payload per the publisher at `profile_sync.py:356` (`bus.publish('collection_changed')`), so it uses the simple form.

### TanStack Query invalidation
**Source:** `frontend/src/routes/kiosk/KioskView.tsx` lines 287–291
**Apply to:** B-01 `collection_changed` handler
```typescript
void queryClient.invalidateQueries({ queryKey: ['search'] })
```
Prefix-key invalidation (single-element array) busts all `['search', q, profileId]` cache entries at once.

### `resolve_profile_from_request` fallback
**Source:** `src/gruvax/api/deps.py` lines 179–233
**Apply to:** B-02 handler body in `search.py` and `locate.py`
```python
resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
```
Returns `(str, str | None)`. First element is the authoritative profile UUID string. Raises 400 `session_unbound` or 403 `device_unknown`/`device_revoked` — these propagate as HTTP errors automatically.

### Integration test fixture
**Source:** `tests/integration/test_search.py` lines 35–51
**Apply to:** new `tests/integration/test_search_b02.py` and `tests/integration/test_locate_b02.py`
Module-scoped `AsyncClient` with `cookies={BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID}` + `LifespanManager` + `@pytest.mark.asyncio(loop_scope="session")`.

---

## No Analog Found

None — all five changes have direct in-repo analogs.

---

## Metadata

**Analog search scope:** `frontend/src/`, `src/gruvax/api/`, `tests/integration/`, `tests/unit/`
**Files read:** `KioskView.tsx`, `client.ts`, `search.py`, `locate.py`, `deps.py` (lines 1–357), `sessionStore.ts`, `KioskView.EventSource.test.tsx`, `test_search.py`, `test_locate.py`, `test_admin_led_settings.py`
**Pattern extraction date:** 2026-05-30
