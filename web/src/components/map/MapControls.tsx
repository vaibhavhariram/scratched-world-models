"use client";

interface MapControlsProps {
  showHeatmap: boolean;
  showEntrances: boolean;
  scoreRange: [number, number];
  onToggleHeatmap: () => void;
  onToggleEntrances: () => void;
  onScoreRangeChange: (range: [number, number]) => void;
  isLoading: boolean;
  zoom: number;
}

export function MapControls({
  showHeatmap, showEntrances, scoreRange,
  onToggleHeatmap, onToggleEntrances, onScoreRangeChange,
  isLoading, zoom,
}: MapControlsProps) {
  return (
    <div className="absolute top-4 left-4 bg-gray-900/90 text-white p-4 rounded-lg shadow-lg space-y-3 w-64 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">Logistics World Graph</h3>
        {isLoading && <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />}
      </div>
      <div className="text-xs text-gray-400">Zoom: {zoom.toFixed(1)}</div>
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={showHeatmap} onChange={onToggleHeatmap} className="rounded" />
          Difficulty Heatmap <span className="text-xs text-gray-500">(z&lt;15)</span>
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={showEntrances} onChange={onToggleEntrances} className="rounded" />
          Entrance Points <span className="text-xs text-gray-500">(z&ge;16)</span>
        </label>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-gray-400">
          Difficulty: {scoreRange[0].toFixed(1)} - {scoreRange[1].toFixed(1)}
        </label>
        <input type="range" min={0} max={1} step={0.05} value={scoreRange[1]}
          onChange={(e) => onScoreRangeChange([scoreRange[0], parseFloat(e.target.value)])} className="w-full" />
      </div>
      <div className="flex items-center gap-2 text-xs">
        <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-sm bg-green-500" /><span>Easy</span></div>
        <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-sm bg-yellow-500" /><span>Med</span></div>
        <div className="flex items-center gap-1"><div className="w-3 h-3 rounded-sm bg-red-500" /><span>Hard</span></div>
      </div>
    </div>
  );
}
