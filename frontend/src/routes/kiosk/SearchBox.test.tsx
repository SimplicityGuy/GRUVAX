/**
 * SearchBox component tests — OFF-02, D-06.
 *
 * Covers the isOffline prop degraded-mode gating:
 *   - isOffline=true  → input is disabled, placeholder swapped to "Search unavailable while offline"
 *   - isOffline=false → input is enabled, original placeholder shown
 *   - isOffline not set → defaults to enabled (backward compatible)
 *
 * Also covers that loading/error affordances are suppressed while offline.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { SearchBox } from './SearchBox'
import { useGruvaxStore } from '../../state/store'

const noop = () => {}

describe('SearchBox', () => {
  describe('online (default / isOffline=false)', () => {
    it('renders an enabled input when isOffline is not set', () => {
      render(<SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} />)
      const input = screen.getByRole('searchbox')
      expect(input).not.toBeDisabled()
    })

    it('shows the default placeholder when isOffline=false', () => {
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} isOffline={false} />,
      )
      const input = screen.getByRole('searchbox')
      expect(input.getAttribute('placeholder')).toBe('Type artist, title, label or catalog#')
    })

    it('renders the loading indicator when isLoading=true and online', () => {
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={true} hasError={false} isOffline={false} />,
      )
      // The loading status should be present
      const status = screen.queryByRole('status')
      expect(status).not.toBeNull()
    })

    it('adds error class when hasError=true and online', () => {
      const { container } = render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={true} isOffline={false} />,
      )
      const box = container.querySelector('.search-box')
      expect(box?.classList.contains('search-box--error')).toBe(true)
    })
  })

  describe('offline (isOffline=true) — OFF-02, D-06', () => {
    it('the input is disabled when isOffline=true', () => {
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} isOffline={true} />,
      )
      const input = screen.getByRole('searchbox')
      expect(input).toBeDisabled()
    })

    it('shows "Search unavailable while offline" placeholder when isOffline=true', () => {
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} isOffline={true} />,
      )
      const input = screen.getByRole('searchbox')
      expect(input.getAttribute('placeholder')).toBe('Search unavailable while offline')
    })

    it('does NOT show the original placeholder when offline', () => {
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} isOffline={true} />,
      )
      const input = screen.getByRole('searchbox')
      expect(input.getAttribute('placeholder')).not.toBe('Type artist, title, label or catalog#')
    })

    it('suppresses loading indicator while offline even if isLoading=true', () => {
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={true} hasError={false} isOffline={true} />,
      )
      const status = screen.queryByRole('status')
      expect(status).toBeNull()
    })

    it('suppresses error class while offline even if hasError=true', () => {
      const { container } = render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={true} isOffline={true} />,
      )
      const box = container.querySelector('.search-box')
      expect(box?.classList.contains('search-box--error')).toBe(false)
    })

    it('adds offline class when isOffline=true', () => {
      const { container } = render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} isOffline={true} />,
      )
      const box = container.querySelector('.search-box')
      expect(box?.classList.contains('search-box--offline')).toBe(true)
    })

    it('suppresses the clear-X button while offline even when query is non-empty', () => {
      // Set the store query to simulate a non-empty search
      useGruvaxStore.setState({ query: 'Blue Note' })
      render(
        <SearchBox onDebouncedQuery={noop} isLoading={false} hasError={false} isOffline={true} />,
      )
      const clearButton = screen.queryByRole('button', { name: /clear search/i })
      expect(clearButton).toBeNull()
      // Restore
      useGruvaxStore.setState({ query: '' })
    })

    it('onDebouncedQuery is not called from disabled input interactions', () => {
      const onQuery = vi.fn()
      render(
        <SearchBox
          onDebouncedQuery={onQuery}
          isLoading={false}
          hasError={false}
          isOffline={true}
        />,
      )
      // When input is disabled, fireEvent.change won't trigger our handler
      const input = screen.getByRole('searchbox')
      expect(input).toBeDisabled()
      // Assert: onDebouncedQuery was never called (disabled input won't propagate events)
      expect(onQuery).not.toHaveBeenCalled()
    })
  })
})

describe('controlled query cancels pending debounce (gruvax-sit7)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useGruvaxStore.getState().clearSearch()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not let a pending keystroke overwrite a tapped suggestion', () => {
    const onQuery = vi.fn()
    useGruvaxStore.getState().setQuery('beatls')
    render(<SearchBox onDebouncedQuery={onQuery} isLoading={false} hasError={false} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'beatlsx' } })
    act(() => {
      // Same controlled query write + immediate search used by handleDidYouMean.
      useGruvaxStore.getState().setQuery('beatles')
      onQuery('beatles')
      vi.advanceTimersByTime(250)
    })
    expect(screen.getByRole('searchbox')).toHaveValue('beatles')
    expect(onQuery).toHaveBeenCalledExactlyOnceWith('beatles')
  })

  it('still debounces ordinary typing and keeps only the latest keystroke', () => {
    const onQuery = vi.fn()
    render(<SearchBox onDebouncedQuery={onQuery} isLoading={false} hasError={false} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'beatl' } })
    act(() => {
      vi.advanceTimersByTime(200)
    })
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'beatles' } })
    act(() => {
      vi.advanceTimersByTime(249)
    })
    expect(onQuery).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(onQuery).toHaveBeenCalledExactlyOnceWith('beatles')
  })

  it.each(['reset', 'unmount'] as const)('cancels an armed timer on %s', (action) => {
    const onQuery = vi.fn()
    const view = render(<SearchBox onDebouncedQuery={onQuery} isLoading={false} hasError={false} />)
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'private query' } })
    if (action === 'reset')
      act(() => {
        useGruvaxStore.getState().clearSearch()
      })
    else view.unmount()
    act(() => {
      vi.advanceTimersByTime(250)
    })
    expect(onQuery).not.toHaveBeenCalled()
  })
})
