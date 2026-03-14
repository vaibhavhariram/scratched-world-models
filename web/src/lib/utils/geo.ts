export type BBox = [number, number, number, number]; // [west, south, east, north]

/**
 * Extract a bounding box from a deck.gl/mapbox viewport.
 */
export function viewportToBBox(viewport: {
  longitude: number;
  latitude: number;
  zoom: number;
  width: number;
  height: number;
}): BBox {
  const { longitude, latitude, zoom, width, height } = viewport;

  // Approximate degrees per pixel at this zoom level
  const degreesPerPixelX = 360 / (256 * Math.pow(2, zoom));
  const degreesPerPixelY =
    (360 / (256 * Math.pow(2, zoom))) *
    Math.cos((latitude * Math.PI) / 180);

  const halfWidthDeg = (width / 2) * degreesPerPixelX;
  const halfHeightDeg = (height / 2) * degreesPerPixelY;

  return [
    longitude - halfWidthDeg, // west
    latitude - halfHeightDeg, // south
    longitude + halfWidthDeg, // east
    latitude + halfHeightDeg, // north
  ];
}

/**
 * Format a bbox array as a comma-separated string for API calls.
 */
export function bboxToString(bbox: BBox): string {
  return bbox.map((v) => v.toFixed(6)).join(",");
}
