/**
 * recentlyPulledStore — Wave-0 RED tests (SRCH-09 / PRIV-01).
 *
 * Tests:
 *   1. addItem dedupe — re-adding an existing release_id moves it to front, no duplicate
 *   2. addItem cap-at-8 — max 8 items; oldest item dropped when cap exceeded
 *   3. clear — empties items array
 *   4. Storage key — written to sessionStorage under 'gruvax-kiosk-recent', NOT to
 *      localStorage under 'gruvax-admin' key (PRIV-01 isolation)
 *
 * These tests are RED until recentlyPulledStore.ts is created (Task 1 GREEN phase).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ── Storage mock helpers ──────────────────────────────────────────────────────

/**
 * Simple in-memory localStorage / sessionStorage mock compatible with Zustand persist.
 * We need separate instances for localStorage and sessionStorage.
 */
function makeStorageMock() {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
    get length() { return Object.keys(store).length },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const item = (n: number) => ({
  release_id: n,
  title: `Album ${n}`,
  primary_artist: `Artist ${n}`,
  catalog_number: `CAT-${n.toString().padStart(3, '0')}`,
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('recentlyPulledStore', () => {
  let sessionStorageMock: ReturnType<typeof makeStorageMock>
  let localStorageMock: ReturnType<typeof makeStorageMock>

  beforeEach(async () => {
    // Provide fresh storage mocks before each test
    sessionStorageMock = makeStorageMock()
    localStorageMock = makeStorageMock()

    vi.stubGlobal('sessionStorage', sessionStorageMock)
    vi.stubGlobal('localStorage', localStorageMock)

    // Reset Zustand module so the store is re-created with the fresh storage mocks.
    // This prevents state leakage across tests.
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('addItem — dedupe: re-adding existing release_id moves it to front with no duplicate', async () => {
    const { useRecentlyPulledStore } = await import('./recentlyPulledStore')

    useRecentlyPulledStore.getState().addItem(item(1))
    useRecentlyPulledStore.getState().addItem(item(2))
    useRecentlyPulledStore.getState().addItem(item(3))

    // Re-add item 1 — should move to front, no duplicate
    useRecentlyPulledStore.getState().addItem(item(1))

    const items = useRecentlyPulledStore.getState().items
    expect(items.length).toBe(3)
    expect(items[0].release_id).toBe(1) // most recent at front
    expect(items[1].release_id).toBe(3)
    expect(items[2].release_id).toBe(2)
    // No duplicates
    const ids = items.map((i) => i.release_id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('addItem — cap-at-8: 9th item drops the oldest', async () => {
    const { useRecentlyPulledStore } = await import('./recentlyPulledStore')

    // Add 9 distinct items
    for (let n = 1; n <= 9; n++) {
      useRecentlyPulledStore.getState().addItem(item(n))
    }

    const items = useRecentlyPulledStore.getState().items
    expect(items.length).toBe(8)
    // Most recent (9) is first; item 1 (oldest) is dropped
    expect(items[0].release_id).toBe(9)
    expect(items.find((i) => i.release_id === 1)).toBeUndefined()
  })

  it('clear — empties the items array', async () => {
    const { useRecentlyPulledStore } = await import('./recentlyPulledStore')

    useRecentlyPulledStore.getState().addItem(item(1))
    useRecentlyPulledStore.getState().addItem(item(2))
    expect(useRecentlyPulledStore.getState().items.length).toBe(2)

    useRecentlyPulledStore.getState().clear()
    expect(useRecentlyPulledStore.getState().items.length).toBe(0)
  })

  it('storage key — writes to sessionStorage under gruvax-kiosk-recent (PRIV-01)', async () => {
    const { useRecentlyPulledStore } = await import('./recentlyPulledStore')

    useRecentlyPulledStore.getState().addItem(item(42))

    // The sessionStorage must have the 'gruvax-kiosk-recent' key
    const sessionValue = sessionStorageMock.getItem('gruvax-kiosk-recent')
    expect(sessionValue).not.toBeNull()
    expect(typeof sessionValue).toBe('string')

    // Parse and confirm item is in there
    const parsed = JSON.parse(sessionValue!) as { state?: { items?: unknown[] } }
    expect(parsed?.state?.items).toBeDefined()
    expect(Array.isArray(parsed.state?.items)).toBe(true)

    // The gruvax-admin localStorage key must NOT contain recently-pulled items (PRIV-01)
    const adminValue = localStorageMock.getItem('gruvax-admin')
    // Either null (not written at all) or does not contain our release_id
    if (adminValue !== null) {
      expect(adminValue).not.toContain('"release_id":42')
      expect(adminValue).not.toContain('"gruvax-kiosk-recent"')
    }
  })

  it('item shape uses primary_artist field (not artist)', async () => {
    const { useRecentlyPulledStore } = await import('./recentlyPulledStore')

    const testItem = {
      release_id: 99,
      title: 'Test Album',
      primary_artist: 'Test Artist',
      catalog_number: 'TA-001',
    }
    useRecentlyPulledStore.getState().addItem(testItem)

    const stored = useRecentlyPulledStore.getState().items[0]
    expect(stored.primary_artist).toBe('Test Artist')
    // TypeScript shape check — no 'artist' field should exist
    expect('artist' in stored).toBe(false)
  })
})
