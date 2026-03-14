/**
 * Map a difficulty score (0-1) to an RGBA color.
 * Green (easy) → Yellow (medium) → Red (hard)
 */
export function difficultyToRGBA(
  score: number | null | undefined
): [number, number, number, number] {
  if (score == null) return [128, 128, 128, 160]; // gray for unscored

  const s = Math.max(0, Math.min(1, score));

  let r: number, g: number, b: number;
  if (s < 0.5) {
    // Green to Yellow
    const t = s * 2;
    r = Math.round(255 * t);
    g = 200;
    b = 50;
  } else {
    // Yellow to Red
    const t = (s - 0.5) * 2;
    r = 255;
    g = Math.round(200 * (1 - t));
    b = 50;
  }

  return [r, g, b, 180];
}

/**
 * Map a confidence score (0-1) to an RGBA color.
 * Low confidence = light blue, high confidence = deep blue.
 */
export function confidenceToRGBA(
  confidence: number | null | undefined
): [number, number, number, number] {
  if (confidence == null) return [100, 100, 200, 160];

  const c = Math.max(0, Math.min(1, confidence));
  const r = Math.round(30 + 70 * (1 - c));
  const g = Math.round(100 + 80 * (1 - c));
  const b = 255;

  return [r, g, b, Math.round(120 + 135 * c)];
}
