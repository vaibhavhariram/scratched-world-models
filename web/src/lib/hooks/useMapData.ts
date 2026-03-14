"use client";

import { useCallback, useRef, useState } from "react";
import useSWR from "swr";
import { BBox, bboxToString } from "@/lib/utils/geo";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

/**
 * Fetch buildings and entrances for the current map viewport.
 * Debounces requests on viewport change.
 */
export function useMapData(bbox: BBox | null, zoom: number) {
  const bboxStr = bbox ? bboxToString(bbox) : null;

  const { data: buildings, isLoading: buildingsLoading } = useSWR(
    bboxStr ? `/api/buildings?bbox=${bboxStr}` : null,
    fetcher,
    { dedupingInterval: 2000 }
  );

  const { data: entrances, isLoading: entrancesLoading } = useSWR(
    bboxStr && zoom >= 16 ? `/api/entrances?bbox=${bboxStr}` : null,
    fetcher,
    { dedupingInterval: 2000 }
  );

  return {
    buildings: buildings ?? { type: "FeatureCollection", features: [] },
    entrances: entrances ?? { type: "FeatureCollection", features: [] },
    isLoading: buildingsLoading || entrancesLoading,
  };
}
