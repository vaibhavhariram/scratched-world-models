"use client";

import { useEvidence } from "@/lib/hooks/useEvidence";

interface EvidencePanelProps {
  buildingId: number;
  onClose: () => void;
}

/**
 * Debug-oriented evidence inspector.
 *
 * On building click, shows:
 * - Building polygon metadata
 * - Assigned stop points with event types and distances
 * - Inferred entrance candidates with confidence
 * - Score breakdown with all sub-scores
 * - Sample size
 * - Validation notes from QA
 */
export function EvidencePanel({ buildingId, onClose }: EvidencePanelProps) {
  const { evidence, isLoading, error } = useEvidence(buildingId);

  const building = evidence?.building;
  const stops = evidence?.stops;
  const stopCount = evidence?.stop_count ?? 0;
  const validationNotes = evidence?.validation_notes ?? [];

  return (
    <div className="absolute top-4 right-4 w-96 max-h-[calc(100vh-2rem)] overflow-y-auto bg-gray-900/95 text-white rounded-lg shadow-lg backdrop-blur-sm text-sm">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700 sticky top-0 bg-gray-900/95">
        <h3 className="font-semibold">Evidence Inspector</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-white text-lg leading-none px-1">x</button>
      </div>

      {isLoading && <div className="p-4 text-gray-400">Loading evidence...</div>}
      {error && <div className="p-4 text-red-400">Failed to load evidence</div>}

      {building && (
        <div className="divide-y divide-gray-800">
          {/* Building info */}
          <div className="p-3 space-y-1">
            <div className="text-xs text-gray-500">BUILDING</div>
            <div className="font-medium">{building.name || building.address || `ID ${building.id}`}</div>
            <div className="text-xs text-gray-400 space-x-2">
              <span>OSM: {building.osm_id}</span>
              <span>Type: {building.building_type || "?"}</span>
              <span>{building.area_sqm?.toFixed(0)} m&sup2;</span>
            </div>
          </div>

          {/* Score breakdown */}
          {building.score && (
            <div className="p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">DIFFICULTY SCORE</span>
                <span className={`text-lg font-bold ${
                  building.score.difficulty > 0.7 ? "text-red-400" :
                  building.score.difficulty > 0.4 ? "text-yellow-400" : "text-green-400"
                }`}>
                  {(building.score.difficulty * 100).toFixed(0)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                {[
                  { key: "stop_variance", label: "Stop Variance" },
                  { key: "road_distance", label: "Road Distance" },
                  { key: "entrance_count", label: "Entrance Count" },
                  { key: "dwell_time", label: "Dwell Time" },
                ].map(({ key, label }) => {
                  const val = building.score[key] as number;
                  return (
                    <div key={key} className="flex justify-between">
                      <span className="text-gray-400">{label}</span>
                      <span>{(val * 100).toFixed(0)}</span>
                    </div>
                  );
                })}
              </div>
              <div className="text-xs text-gray-500">
                Sample size: {building.score.sample_size} stops
              </div>
            </div>
          )}

          {/* Entrance candidates */}
          {building.entrances?.length > 0 && (
            <div className="p-3 space-y-2">
              <div className="text-xs text-gray-500">ENTRANCES ({building.entrances.length})</div>
              {building.entrances.map((e: {
                id: number; confidence: number; cluster_size: number;
                side: string; avg_dwell_sec: number; stddev_position: number;
              }) => (
                <div key={e.id} className="bg-gray-800 rounded p-2 text-xs grid grid-cols-2 gap-1">
                  <span>Confidence: {(e.confidence * 100).toFixed(0)}%</span>
                  <span className="text-right text-gray-400">{e.side} side</span>
                  <span>Cluster: {e.cluster_size} stops</span>
                  <span className="text-right">Spread: {e.stddev_position?.toFixed(1)}m</span>
                  <span>Dwell: {e.avg_dwell_sec?.toFixed(0)}s avg</span>
                </div>
              ))}
            </div>
          )}

          {/* Assigned stops summary */}
          <div className="p-3 space-y-2">
            <div className="text-xs text-gray-500">ASSIGNED STOPS ({stopCount})</div>
            {stops?.features?.length > 0 ? (
              <div className="space-y-1">
                {/* Show first 20 stops */}
                {stops.features.slice(0, 20).map((f: {
                  properties: {
                    id: number; event_type: string; distance_m: number;
                    dwell_seconds: number | null; event_timestamp: string;
                  };
                }) => (
                  <div key={f.properties.id} className="text-xs flex justify-between text-gray-300">
                    <span className={f.properties.event_type === "pickup" ? "text-green-400" : "text-orange-400"}>
                      {f.properties.event_type}
                    </span>
                    <span>{f.properties.distance_m?.toFixed(1)}m</span>
                    <span className="text-gray-500">
                      {new Date(f.properties.event_timestamp).toLocaleDateString()}
                    </span>
                  </div>
                ))}
                {stops.features.length > 20 && (
                  <div className="text-xs text-gray-500 text-center">
                    ...and {stops.features.length - 20} more
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-gray-500">No stops assigned</div>
            )}
          </div>

          {/* Validation notes */}
          {validationNotes.length > 0 && (
            <div className="p-3 space-y-2">
              <div className="text-xs text-gray-500">VALIDATION NOTES ({validationNotes.length})</div>
              {validationNotes.map((v: { id: number; status: string; note: string; created_at: string }) => (
                <div key={v.id} className="bg-gray-800 rounded p-2 text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className={
                      v.status === "good_candidate" ? "text-green-400" :
                      v.status === "plausible" ? "text-blue-400" :
                      v.status === "needs_tuning" ? "text-yellow-400" : "text-red-400"
                    }>
                      {v.status}
                    </span>
                    <span className="text-gray-500">{new Date(v.created_at).toLocaleDateString()}</span>
                  </div>
                  {v.note && <div className="text-gray-300">{v.note}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
