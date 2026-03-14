/** Difficulty score (0-1) → RGBA. Green→Yellow→Red. */
export function difficultyToRGBA(score: number | null | undefined): [number, number, number, number] {
  if (score == null) return [128, 128, 128, 160];
  const s = Math.max(0, Math.min(1, score));
  if (s < 0.5) {
    return [Math.round(255 * s * 2), 200, 50, 180];
  }
  return [255, Math.round(200 * (1 - (s - 0.5) * 2)), 50, 180];
}

/** Confidence (0-1) → RGBA. Light blue → Deep blue. */
export function confidenceToRGBA(c: number | null | undefined): [number, number, number, number] {
  if (c == null) return [100, 100, 200, 160];
  const v = Math.max(0, Math.min(1, c));
  return [Math.round(30 + 70 * (1 - v)), Math.round(100 + 80 * (1 - v)), 255, Math.round(120 + 135 * v)];
}

/** Stop event type → color. */
export function eventTypeColor(type: string): [number, number, number, number] {
  return type === "pickup" ? [0, 200, 100, 180] : [255, 100, 50, 180];
}
