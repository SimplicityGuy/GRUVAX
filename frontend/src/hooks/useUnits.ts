import { useQuery } from '@tanstack/react-query'
import { fetchUnits } from '../api/client'

/** Existing shared layout query: names, dimensions and physical ordering are API-owned. */
export function useUnits() {
  return useQuery({ queryKey: ['units'], queryFn: fetchUnits, staleTime: Infinity })
}
