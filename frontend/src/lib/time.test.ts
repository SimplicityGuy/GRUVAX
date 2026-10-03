import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  formatIsoRelativeTime,
  formatRelativeTime,
  formatRelativeAge,
  stalenessStatus,
} from './time'

const now = Date.parse('2026-10-03T12:00:00Z')
beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(now)
})
afterEach(() => vi.restoreAllMocks())

it.each([
  [0, '0s ago'],
  [59, '59s ago'],
  [60, '1 min ago'],
  [3599, '59 min ago'],
  [3600, '1h ago'],
  [48 * 3600 - 1, '47h ago'],
  [48 * 3600, '2d ago'],
  [14 * 86400, '14d ago'],
])('formats an age of %s seconds consistently for epoch and ISO callers', (age, expected) => {
  const timestamp = now / 1000 - Number(age)
  expect(formatRelativeTime(timestamp)).toBe(expected)
  expect(formatRelativeAge(Number(age))).toBe(expected)
  expect(formatIsoRelativeTime(new Date(timestamp * 1000).toISOString())).toBe(expected)
})
it.each([
  [null, 'ok'],
  [3 * 86400, 'ok'],
  [3 * 86400 + 1, 'stale'],
  [14 * 86400, 'stale'],
  [14 * 86400 + 1, 'outdated'],
])('preserves the strict staleness threshold for %s seconds', (age, expected) => {
  expect(stalenessStatus(age as number | null)).toBe(expected)
})
it('retains the never-synced ISO sentinel', () => {
  expect(formatIsoRelativeTime(null)).toBe('Never synced')
})
