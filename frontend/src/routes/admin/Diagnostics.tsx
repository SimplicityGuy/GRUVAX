/**
 * Diagnostics page — /admin/diagnostics (UI-SPEC §Phase 8, Surface 1).
 *
 * Phase 8 (OBS-05, OBS-06, OBS-07) — plan 08-04.
 *
 * Renders the 7 SC#2 diagnostic rows:
 *   1. DiagnosticsToolbar  — REFRESH button + last-refreshed timestamp
 *   2. StalenessSection    — sync staleness + OK/STALE/OUTDATED badge
 *   3. TopSearchedSection  — top-10 table + inline RESET STATS confirm flow
 *   4. SlowQuerySection    — slow-query ring buffer (newest-first)
 *   5. SystemStatusSection — MQTT status, Postgres pool, phantom boundaries
 *   6. RecentLogsSection   — dark terminal (last 20 lines, newest-first)
 *
 * Data loads on mount via useEffect + explicit REFRESH. No polling, no SSE (D-11 locked).
 * DOM for recent logs is built via el() + replaceChildren() — never innerHTML.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { el } from '../../lib/dom'
import type { DiagnosticsData, LogEntry, ProfileDiagnosticEntry, SlowQueryEntry, TopSearchedRow } from '../../api/adminClient'
import { getDiagnostics, resetStats } from '../../api/adminClient'
import { ProfileDiagnosticsCard } from './ProfileDiagnosticsCard'
import { formatRelativeTime, stalenessStatus } from '../../lib/time'
import './Diagnostics.css'

// ── Time formatting helpers ────────────────────────────────────────────────────

// formatRelativeTime + stalenessStatus imported from lib/time (shared with ProfileDiagnosticsCard)

function formatSyncAge(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 3600) return '< 1h ago'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  if (days === 0) return `${hours}h ago`
  if (hours === 0) return `${days}d ago`
  return `${days}d ${hours}h ago`
}

function formatLastRefreshed(ts: Date | null): string {
  if (!ts) return '—'
  const diffMs = Date.now() - ts.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 5) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} min ago`
  return ts.toLocaleTimeString()
}

// ── Shimmer skeleton (loading state per section) ──────────────────────────────

function SectionSkeleton(): React.ReactElement {
  return <div className="diag-skeleton" aria-hidden="true" />
}

// ── Staleness Section ─────────────────────────────────────────────────────────

interface StalenessSectionProps {
  syncAgeSec: number | null
  loading: boolean
}

function StalenessSection({ syncAgeSec, loading }: StalenessSectionProps): React.ReactElement {
  const status = stalenessStatus(syncAgeSec)

  return (
    <section className="settings-section">
      <h2 className="diag-heading">SYNC STATUS</h2>
      {loading ? (
        <SectionSkeleton />
      ) : (
        <div className={`diag-staleness-row diag-staleness-row--${status}`}>
          <span className="diag-row-label">DISCOGSOGRAPHY LAST SYNC</span>
          <span className="diag-row-value">{formatSyncAge(syncAgeSec)}</span>
          <span className={`diag-badge diag-badge--${status}`} aria-label={`Sync status: ${status}`}>
            {status === 'ok' ? 'OK' : status === 'stale' ? 'STALE' : 'OUTDATED'}
          </span>
        </div>
      )}
    </section>
  )
}

// ── Reset stats inline-confirm state ─────────────────────────────────────────

type ResetState = 'idle' | 'confirm' | 'resetting' | 'success' | 'error'

interface TopSearchedSectionProps {
  rows: TopSearchedRow[]
  loading: boolean
  onResetComplete: () => void
}

function TopSearchedSection({ rows, loading, onResetComplete }: TopSearchedSectionProps): React.ReactElement {
  const [resetState, setResetState] = useState<ResetState>('idle')
  const [resetError, setResetError] = useState('')
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleResetClick = useCallback(() => {
    setResetState('confirm')
  }, [])

  const handleKeepStats = useCallback(() => {
    setResetState('idle')
  }, [])

  const handleYesReset = useCallback(async () => {
    setResetState('resetting')
    setResetError('')
    try {
      await resetStats()
      setResetState('success')
      onResetComplete()
      // Auto-hide success message after 3s (UI-SPEC)
      successTimerRef.current = setTimeout(() => {
        setResetState('idle')
      }, 3000)
    } catch {
      setResetState('error')
      setResetError('Could not reset stats. Try again.')
      // Return to idle after 4s (UI-SPEC)
      successTimerRef.current = setTimeout(() => {
        setResetState('idle')
        setResetError('')
      }, 4000)
    }
  }, [onResetComplete])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current)
    }
  }, [])

  const isEmpty = rows.length === 0

  return (
    <section className="settings-section">
      <h2 className="diag-heading">TOP SEARCHED</h2>
      {loading ? (
        <SectionSkeleton />
      ) : isEmpty ? (
        <p className="diag-empty-state">
          No search data yet. Stats accumulate as records are searched.
        </p>
      ) : (
        <div className="diag-table-wrapper" role="region" aria-label="Top searched records">
          <table className="diag-table">
            <thead>
              <tr>
                <th className="diag-col-header">ARTIST / TITLE</th>
                <th className="diag-col-header diag-col-number">SEARCHES ALL-TIME</th>
                <th className="diag-col-header diag-col-number">SEARCHES 7-DAY</th>
                <th className="diag-col-header diag-col-number">SELECTED ALL-TIME</th>
                <th className="diag-col-header diag-col-number">SELECTED 7-DAY</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.release_id} className="diag-table-row">
                  <td className="diag-cell-text">
                    <span className="diag-artist">{row.primary_artist}</span>
                    {' — '}
                    <span className="diag-title">{row.title}</span>
                  </td>
                  <td className="diag-cell-mono">{row.search_count}</td>
                  <td className="diag-cell-mono">{row.search_count_7d}</td>
                  <td className="diag-cell-mono">{row.selection_count}</td>
                  <td className="diag-cell-mono">{row.selection_count_7d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Reset stats destructive action (D-06) */}
      <div className="diag-reset-row">
        {resetState === 'idle' && (
          <button
            type="button"
            className="diag-btn-destructive"
            onClick={handleResetClick}
            aria-label="Reset search stats"
          >
            RESET STATS
          </button>
        )}
        {resetState === 'confirm' && (
          <div className="diag-confirm-row" role="group" aria-label="Confirm reset stats">
            <span className="diag-confirm-label">CONFIRM RESET?</span>
            <button
              type="button"
              className="diag-btn-destructive-filled"
              onClick={() => { void handleYesReset() }}
              aria-label="Confirm reset stats"
            >
              YES, RESET
            </button>
            <button
              type="button"
              className="diag-btn-secondary"
              onClick={handleKeepStats}
              aria-label="Keep stats, cancel reset"
            >
              KEEP STATS
            </button>
          </div>
        )}
        {resetState === 'resetting' && (
          <button type="button" className="diag-btn-destructive" disabled aria-disabled="true">
            RESETTING…
          </button>
        )}
        {resetState === 'success' && (
          <p className="diag-reset-success" role="status" aria-live="polite">
            Stats cleared.
          </p>
        )}
        {resetState === 'error' && (
          <p className="diag-reset-error" role="alert">
            {resetError}
          </p>
        )}
      </div>
    </section>
  )
}

// ── Slow Query Section ────────────────────────────────────────────────────────

interface SlowQuerySectionProps {
  entries: SlowQueryEntry[]
  loading: boolean
}

function SlowQuerySection({ entries, loading }: SlowQuerySectionProps): React.ReactElement {
  return (
    <section className="settings-section">
      <h2 className="diag-heading">SLOW QUERIES</h2>
      <p className="diag-sub-label">
        Requests exceeding SLO threshold (search &gt; 200 ms · locate &gt; 50 ms)
      </p>
      {loading ? (
        <SectionSkeleton />
      ) : entries.length === 0 ? (
        <p className="diag-empty-state">
          No slow queries logged. The ring buffer resets on restart.
        </p>
      ) : (
        <div className="diag-table-wrapper" role="region" aria-label="Slow query log">
          <table className="diag-table">
            <thead>
              <tr>
                <th className="diag-col-header">ENDPOINT</th>
                <th className="diag-col-header diag-col-number">TOTAL (ms)</th>
                <th className="diag-col-header diag-col-number">DB (ms)</th>
                <th className="diag-col-header diag-col-number">THRESHOLD (ms)</th>
                <th className="diag-col-header">TIME</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => (
                <tr key={i} className="diag-table-row">
                  <td className="diag-cell-path">{entry.path}</td>
                  <td className="diag-cell-mono">{Math.round(entry.total_ms)}</td>
                  <td className="diag-cell-mono">{Math.round(entry.db_ms)}</td>
                  <td className="diag-cell-mono diag-cell-muted">{entry.threshold_ms}</td>
                  <td className="diag-cell-time">{formatRelativeTime(entry.ts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// ── System Status Section ─────────────────────────────────────────────────────

interface SystemStatusSectionProps {
  mqttStatus: 'connected' | 'disconnected'
  poolSizeUsed: number
  poolSizeMin: number
  phantomCount: number
  loading: boolean
}

function SystemStatusSection({
  mqttStatus,
  poolSizeUsed,
  poolSizeMin,
  phantomCount,
  loading,
}: SystemStatusSectionProps): React.ReactElement {
  const mqttConnected = mqttStatus === 'connected'
  const hasPhantoms = phantomCount > 0

  return (
    <section className="settings-section">
      <h2 className="diag-heading">SYSTEM</h2>
      {loading ? (
        <SectionSkeleton />
      ) : (
        <div className="diag-status-rows">
          {/* MQTT BROKER */}
          <div className="diag-status-row">
            <div className="diag-status-left">
              <span
                className={`diag-status-dot diag-status-dot--${mqttConnected ? 'ok' : 'error'}`}
                aria-hidden="true"
              />
              <span className="diag-row-label">MQTT BROKER</span>
            </div>
            <span className="diag-status-value">
              {mqttConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          {/* POSTGRES POOL */}
          <div className="diag-status-row">
            <div className="diag-status-left">
              <span className="diag-status-dot diag-status-dot--ok" aria-hidden="true" />
              <span className="diag-row-label">POSTGRES POOL</span>
            </div>
            <div className="diag-status-value-group">
              <span className="diag-cell-mono">{poolSizeUsed} / {poolSizeMin}</span>
              <span className="diag-sub-label">connections used / min pool size</span>
            </div>
          </div>

          {/* PHANTOM BOUNDARIES */}
          <div className="diag-status-row">
            <div className="diag-status-left">
              <span
                className={`diag-status-dot diag-status-dot--${hasPhantoms ? 'warning' : 'ok'}`}
                aria-hidden="true"
              />
              <span className="diag-row-label">PHANTOM BOUNDARIES</span>
            </div>
            <div className="diag-status-value-group">
              <span className="diag-cell-mono">{phantomCount}</span>
              <span className="diag-sub-label">
                boundaries referencing records not in v_collection
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Recent Logs Section (imperative DOM via el()/replaceChildren()) ────────────

interface RecentLogsSectionProps {
  logs: LogEntry[]
  loading: boolean
}

function RecentLogsSection({ logs, loading }: RecentLogsSectionProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    if (loading) {
      container.replaceChildren(
        el('p', { className: 'diag-logs-empty', textContent: '—' })
      )
      return
    }

    if (logs.length === 0) {
      container.replaceChildren(
        el('p', {
          className: 'diag-logs-empty',
          textContent: 'No log entries in buffer.',
        })
      )
      return
    }

    const lines = logs.map((entry) => {
      const levelClass =
        entry.level === 'ERROR' ? 'diag-log-error'
        : entry.level === 'WARNING' ? 'diag-log-warning'
        : entry.level === 'DEBUG' ? 'diag-log-debug'
        : 'diag-log-info'

      const ts = new Date(entry.ts * 1000).toISOString().replace('T', ' ').slice(0, 19)

      const tsEl = el('span', {
        className: 'diag-log-ts',
        textContent: ts + ' ',
      })
      const levelEl = el('span', {
        className: `diag-log-level ${levelClass}`,
        textContent: `[${entry.level}] `,
      })
      const msgEl = el('span', {
        className: 'diag-log-msg',
        textContent: entry.msg,
      })

      return el('div', { className: 'diag-log-line' }, tsEl, levelEl, msgEl)
    })

    container.replaceChildren(...lines)
  }, [logs, loading])

  return (
    <section className="settings-section">
      <h2 className="diag-heading">RECENT LOGS</h2>
      <div
        ref={containerRef}
        className="diag-logs-terminal"
        aria-label="Recent log entries"
        tabIndex={0}
        role="log"
        aria-live="off"
      />
    </section>
  )
}

// ── Profiles Diagnostics Section (D4-15, D4-16) ──────────────────────────────

interface ProfilesDiagnosticsSectionProps {
  profiles: ProfileDiagnosticEntry[]
  loading: boolean
}

function ProfilesDiagnosticsSection({
  profiles,
  loading,
}: ProfilesDiagnosticsSectionProps): React.ReactElement {
  return (
    <section className="settings-section" aria-labelledby="profiles-diag-heading">
      <h2 id="profiles-diag-heading" className="diag-profiles-heading">PROFILES</h2>
      {loading ? (
        <SectionSkeleton />
      ) : profiles.length === 0 ? (
        <p className="diag-empty-state">
          No profiles yet. Create a profile to see sync diagnostics.
        </p>
      ) : (
        <div className="diag-profiles-grid">
          {profiles.map((p) => (
            <ProfileDiagnosticsCard key={p.id} profile={p} />
          ))}
        </div>
      )}
    </section>
  )
}

// ── Main Diagnostics Page ─────────────────────────────────────────────────────

export function Diagnostics(): React.ReactElement {
  const [data, setData] = useState<DiagnosticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  // Per-profile diagnostics polling (D4-16): separate TanStack Query with 30s refetchInterval.
  // Kept separate from the existing imperative load() to minimise refactor risk (PATTERNS §lower-risk).
  // Background refetch shows NO spinner (UI-SPEC Interaction States).
  const { data: profilesQueryData, isLoading: profilesLoading } = useQuery({
    queryKey: ['admin', 'diagnostics'],
    queryFn: getDiagnostics,
    refetchInterval: 30_000,
  })

  const load = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const result = await getDiagnostics()
      setData(result)
      setLastRefreshed(new Date())
    } catch {
      setError('Could not load diagnostics. Check that the API is reachable.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  // Load on mount (D-11 — single useEffect, no polling)
  useEffect(() => {
    // setRefreshing(true) and setError(null) run synchronously before the await, which is
    // intentional (loading indicator). React 18 batches both into one re-render. The rule
    // is suppressed because this pattern is deliberate, not a cascading-render bug.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  const handleRefresh = useCallback(() => {
    void load()
  }, [load])

  // Called after a successful reset — reload data to reflect empty top_searched
  const handleResetComplete = useCallback(() => {
    void load()
  }, [load])

  const isLoading = loading || refreshing

  return (
    <div className="settings-page">
      {/* Toolbar */}
      <div className="diag-toolbar">
        <button
          type="button"
          className="settings-btn-primary diag-refresh-btn"
          onClick={handleRefresh}
          disabled={isLoading}
          aria-label="Refresh diagnostics"
        >
          {isLoading ? 'REFRESHING…' : 'REFRESH'}
        </button>
        <span className="diag-last-refreshed">
          Last refreshed: {formatLastRefreshed(lastRefreshed)}
        </span>
      </div>

      {/* Error state */}
      {error && (
        <div className="settings-section">
          <p className="diag-load-error" role="alert">
            {error}{' '}
            <button type="button" className="diag-retry-link" onClick={handleRefresh}>
              Try again
            </button>
          </p>
        </div>
      )}

      {/* Section cards */}
      <StalenessSection
        syncAgeSec={data?.sync_age_seconds ?? null}
        loading={isLoading && !data}
      />
      <TopSearchedSection
        rows={data?.top_searched ?? []}
        loading={isLoading && !data}
        onResetComplete={handleResetComplete}
      />
      <SlowQuerySection
        entries={data?.slow_queries ?? []}
        loading={isLoading && !data}
      />
      <SystemStatusSection
        mqttStatus={data?.mqtt ?? 'disconnected'}
        poolSizeUsed={data?.pool.size_used ?? 0}
        poolSizeMin={data?.pool.size_min ?? 0}
        phantomCount={data?.phantom_boundary_count ?? 0}
        loading={isLoading && !data}
      />
      <ProfilesDiagnosticsSection
        profiles={profilesQueryData?.profiles ?? []}
        loading={profilesLoading && !profilesQueryData}
      />
      <RecentLogsSection
        logs={data?.recent_logs ?? []}
        loading={isLoading && !data}
      />
    </div>
  )
}
