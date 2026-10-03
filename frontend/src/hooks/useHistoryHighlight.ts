import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { getHistory } from '../api/adminClient'
import type { ChangeSetHistoryItem } from '../api/types'
import { useSessionStore } from '../state/sessionStore'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** Profile-owned recent/target history plus the display-time deep-link acknowledgement. */
export function useHistoryHighlight() {
  const profileId = useSessionStore((state) => state.boundProfileId)
  const [params, setParams] = useSearchParams()
  const rawHighlight = params.get('highlight')
  const highlight = rawHighlight && UUID.test(rawHighlight) ? rawHighlight.toLowerCase() : null
  const recent = useQuery({
    queryKey: ['admin', 'history', profileId, 'recent'],
    queryFn: () => getHistory().then((response) => response.history),
    refetchOnWindowFocus: false,
  })
  const needsTarget = Boolean(
    highlight && recent.isSuccess && !recent.data.some((item) => item.change_set_id === highlight),
  )
  const target = useQuery({
    queryKey: ['admin', 'history', profileId, 'change-set', highlight],
    queryFn: () => getHistory(highlight!).then((response) => response.history),
    enabled: needsTarget,
    refetchOnWindowFocus: false,
  })
  const linked = needsTarget
    ? target.data?.find((item) => item.change_set_id === highlight)
    : undefined
  const [displayedTarget, setDisplayedTarget] = useState<{
    profileId: string | null
    item: ChangeSetHistoryItem
  } | null>(null)
  const remembered = displayedTarget?.profileId === profileId ? displayedTarget.item : undefined
  const selected = linked ?? remembered
  const items = useMemo(
    () =>
      selected && !recent.data?.some((item) => item.change_set_id === selected.change_set_id)
        ? [...(recent.data ?? []), selected].sort(
            (a, b) => Date.parse(b.changed_at) - Date.parse(a.changed_at),
          )
        : (recent.data ?? []),
    [recent.data, selected],
  )
  const matchedCard = useRef<HTMLLIElement>(null)
  const matchCard = useCallback(
    (card: HTMLLIElement | null) => {
      matchedCard.current = card
      if (card && linked) {
        // Retain the actual displayed result after consuming the URL, still scoped to its profile.
        setDisplayedTarget((previous) =>
          previous?.profileId === profileId && previous.item.change_set_id === linked.change_set_id
            ? previous
            : { profileId, item: linked },
        )
      }
    },
    [linked, profileId],
  )
  const lastDisplayed = useRef<string | null>(null)
  const lastHighlighted = useRef<HTMLLIElement | null>(null)

  useEffect(() => {
    if (!highlight) {
      lastDisplayed.current = null
      return
    }
    const card = matchedCard.current
    const identity = `${profileId}:${highlight}`
    if (!card || card.dataset.changeSetId !== highlight || lastDisplayed.current === identity)
      return
    // Scrolling and its lit-state are one DOM acknowledgement, after the matching card exists.
    // Keep the lit-state after consuming the URL; a new target retires the prior card's state.
    lastHighlighted.current?.classList.remove('history-card--highlighted')
    card.classList.add('history-card--highlighted')
    card.scrollIntoView({ behavior: 'smooth', block: 'center' })
    lastHighlighted.current = card
    lastDisplayed.current = identity
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('highlight')
        return next
      },
      { replace: true },
    )
  }, [highlight, items, profileId, setParams])

  let notice: string | null = null
  if (rawHighlight && !highlight) notice = 'Invalid change-set link.'
  else if (needsTarget && target.isPending) notice = 'Loading linked change set…'
  else if (needsTarget && target.isError)
    notice = 'Could not load linked change set. Try refreshing.'
  else if (needsTarget && target.isSuccess && !linked)
    notice = 'Linked change set unavailable for this profile.'

  return {
    items,
    isLoading: recent.isPending,
    isError: recent.isError,
    highlight,
    matchCard,
    notice,
  }
}
