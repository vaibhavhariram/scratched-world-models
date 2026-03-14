"use client";

interface Score {
  difficulty: number;
  stop_variance: number;
  road_distance: number;
  entrance_count: number;
  dwell_time: number;
  sample_size: number;
}

interface ScoreBreakdownProps {
  score: Score;
}

const DIMENSIONS = [
  { key: "stop_variance" as const, label: "Stop Variance", description: "Spatial spread of stops" },
  { key: "road_distance" as const, label: "Road Distance", description: "Distance from building edge" },
  { key: "entrance_count" as const, label: "Entrance Count", description: "Number of inferred entrances" },
  { key: "dwell_time" as const, label: "Dwell Time", description: "Average dwell at entrances" },
];

function barColor(value: number): string {
  if (value > 0.7) return "bg-red-500";
  if (value > 0.4) return "bg-yellow-500";
  return "bg-green-500";
}

export function ScoreBreakdown({ score }: ScoreBreakdownProps) {
  return (
    <div className="space-y-2">
      {DIMENSIONS.map((dim) => {
        const value = score[dim.key];
        return (
          <div key={dim.key} className="space-y-0.5">
            <div className="flex justify-between text-xs">
              <span className="text-gray-300" title={dim.description}>
                {dim.label}
              </span>
              <span className="text-gray-400">
                {(value * 100).toFixed(0)}
              </span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${barColor(value)}`}
                style={{ width: `${value * 100}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
