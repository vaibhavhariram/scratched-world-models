"use client";

import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useBuilding(buildingId: number | null) {
  const { data, error, isLoading } = useSWR(
    buildingId ? `/api/buildings/${buildingId}` : null, fetcher
  );
  return { building: data, error, isLoading };
}
