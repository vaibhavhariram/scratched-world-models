"use client";

import { useBuilding } from "@/lib/hooks/useBuilding";
import { ScoreBreakdown } from "./ScoreBreakdown";

interface BuildingDetailProps {
  buildingId: number;
  onClose: () => void;
}

export function BuildingDetail({ buildingId, onClose }: BuildingDetailProps) {
  const { building, isLoading, error } = useBuilding(buildingId);

  return (
    <div className="absolute top-4 right-4 w-80 max-h-[calc(100vh-2rem)] overflow-y-auto bg-gray-900/95 text-white rounded-lg shadow-lg backdrop-blur-sm">
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <h3 className="font-semibold text-sm">Building Details</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white text-lg leading-none"
        >
          x
        </button>
      </div>

      {isLoading && (
        <div className="p-4 text-sm text-gray-400">Loading...</div>
      )}

      {error && (
        <div className="p-4 text-sm text-red-400">
          Failed to load building data
        </div>
      )}

      {building && (
        <div className="p-4 space-y-4">
          <div className="space-y-1">
            <div className="text-xs text-gray-400">
              ID: {building.id} | OSM: {building.osm_id}
            </div>
            {building.name && (
              <div className="font-medium">{building.name}</div>
            )}
            {building.address && (
              <div className="text-sm text-gray-300">{building.address}</div>
            )}
            <div className="text-xs text-gray-400">
              Type: {building.building_type || "unknown"} |{" "}
              {building.area_sqm?.toFixed(0)} m&sup2;
            </div>
          </div>

          {building.score && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Difficulty Score</span>
                <span
                  className={`text-lg font-bold ${
                    building.score.difficulty > 0.7
                      ? "text-red-400"
                      : building.score.difficulty > 0.4
                        ? "text-yellow-400"
                        : "text-green-400"
                  }`}
                >
                  {(building.score.difficulty * 100).toFixed(0)}
                </span>
              </div>
              <ScoreBreakdown score={building.score} />
              <div className="text-xs text-gray-500">
                Based on {building.score.sample_size} stop events
              </div>
            </div>
          )}

          {building.entrances && building.entrances.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium">
                Entrances ({building.entrances.length})
              </h4>
              {building.entrances.map(
                (entrance: {
                  id: number;
                  confidence: number;
                  cluster_size: number;
                  side: string;
                  avg_dwell_sec: number;
                }) => (
                  <div
                    key={entrance.id}
                    className="bg-gray-800 rounded p-2 text-xs space-y-1"
                  >
                    <div className="flex justify-between">
                      <span>
                        Confidence:{" "}
                        {(entrance.confidence * 100).toFixed(0)}%
                      </span>
                      <span className="text-gray-400">
                        {entrance.side} side
                      </span>
                    </div>
                    <div className="text-gray-400">
                      {entrance.cluster_size} stops | avg dwell:{" "}
                      {entrance.avg_dwell_sec?.toFixed(0)}s
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
