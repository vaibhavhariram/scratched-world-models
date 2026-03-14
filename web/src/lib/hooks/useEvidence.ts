"use client";

import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

/**
 * Fetch full evidence for a building: polygon, assigned stops,
 * entrance candidates, score breakdown, validation notes.
 */
export function useEvidence(buildingId: number | null) {
  const { data, error, isLoading } = useSWR(
    buildingId ? `/api/buildings/${buildingId}/evidence` : null, fetcher
  );
  return { evidence: data, error, isLoading };
}
