"use client";

import { useCallback, useState, useRef } from "react";
import Map from "react-map-gl/mapbox";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import "mapbox-gl/dist/mapbox-gl.css";

import { useMapData } from "@/lib/hooks/useMapData";
import { viewportToBBox, BBox } from "@/lib/utils/geo";
import { difficultyToRGBA, confidenceToRGBA } from "@/lib/utils/colors";
import { MapControls } from "./MapControls";
import { BuildingDetail } from "../panels/BuildingDetail";

const INITIAL_VIEW_STATE = {
  longitude: -73.985,
  latitude: 40.748,
  zoom: 14,
  pitch: 0,
  bearing: 0,
};

export function MapContainer() {
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [bbox, setBBox] = useState<BBox | null>(null);
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(
    null
  );
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showEntrances, setShowEntrances] = useState(true);
  const [scoreRange, setScoreRange] = useState<[number, number]>([0, 1]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);

  const { buildings, entrances, isLoading } = useMapData(
    bbox,
    viewState.zoom
  );

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const onViewStateChange = useCallback((params: any) => {
    const vs = params.viewState;
    setViewState(vs);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const el = containerRef.current;
      if (el) {
        setBBox(
          viewportToBBox({
            longitude: vs.longitude,
            latitude: vs.latitude,
            zoom: vs.zoom,
            width: el.clientWidth,
            height: el.clientHeight,
          })
        );
      }
    }, 300);
  }, []);

  // Build centroids for heatmap from building features
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const buildingCentroids = (buildings?.features ?? []).map((f: any) => ({
    coordinates: [
      f.geometry.coordinates[0].reduce(
        (sum: number, c: number[]) => sum + c[0],
        0
      ) / f.geometry.coordinates[0].length,
      f.geometry.coordinates[0].reduce(
        (sum: number, c: number[]) => sum + c[1],
        0
      ) / f.geometry.coordinates[0].length,
    ],
    difficulty: f.properties.difficulty ?? 0.5,
  }));

  const layers = [
    // Layer 1: Building polygons
    new GeoJsonLayer({
      id: "buildings",
      data: buildings,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      getFillColor: (f: any) => difficultyToRGBA(f.properties?.difficulty),
      getLineColor: [80, 80, 80, 200],
      getLineWidth: 1,
      lineWidthMinPixels: 1,
      pickable: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onClick: (info: any) => {
        if (info.object) setSelectedBuildingId(info.object.properties.id);
      },
      updateTriggers: {
        getFillColor: [scoreRange],
      },
    }),

    // Layer 2: Entrance candidates (visible at zoom >= 16)
    showEntrances &&
      new ScatterplotLayer({
        id: "entrances",
        data: entrances?.features ?? [],
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getPosition: (f: any) => f.geometry.coordinates,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getRadius: (f: any) => Math.sqrt(f.properties.cluster_size) * 2,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getFillColor: (f: any) => confidenceToRGBA(f.properties.confidence),
        radiusMinPixels: 4,
        radiusMaxPixels: 20,
        pickable: true,
        visible: viewState.zoom >= 16,
      }),

    // Layer 3: Difficulty heatmap (visible at zoom < 15)
    showHeatmap &&
      new HeatmapLayer({
        id: "difficulty-heatmap",
        data: buildingCentroids,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getPosition: (d: any) => d.coordinates,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getWeight: (d: any) => d.difficulty,
        radiusPixels: 30,
        intensity: 1,
        threshold: 0.1,
        visible: viewState.zoom < 15,
      }),
  ].filter(Boolean);

  return (
    <div ref={containerRef} className="relative w-full h-full">
      <DeckGL
        viewState={viewState}
        onViewStateChange={onViewStateChange}
        controller={true}
        layers={layers}
      >
        <Map
          mapboxAccessToken={process.env.NEXT_PUBLIC_MAPBOX_TOKEN}
          mapStyle="mapbox://styles/mapbox/dark-v11"
        />
      </DeckGL>

      <MapControls
        showHeatmap={showHeatmap}
        showEntrances={showEntrances}
        scoreRange={scoreRange}
        onToggleHeatmap={() => setShowHeatmap(!showHeatmap)}
        onToggleEntrances={() => setShowEntrances(!showEntrances)}
        onScoreRangeChange={setScoreRange}
        isLoading={isLoading}
        zoom={viewState.zoom}
      />

      {selectedBuildingId && (
        <BuildingDetail
          buildingId={selectedBuildingId}
          onClose={() => setSelectedBuildingId(null)}
        />
      )}
    </div>
  );
}
