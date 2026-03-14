export type BBox = [number, number, number, number]; // [west, south, east, north]

export function viewportToBBox(viewport: {
  longitude: number; latitude: number; zoom: number; width: number; height: number;
}): BBox {
  const { longitude, latitude, zoom, width, height } = viewport;
  const degPerPxX = 360 / (256 * Math.pow(2, zoom));
  const degPerPxY = degPerPxX * Math.cos((latitude * Math.PI) / 180);
  return [
    longitude - (width / 2) * degPerPxX,
    latitude - (height / 2) * degPerPxY,
    longitude + (width / 2) * degPerPxX,
    latitude + (height / 2) * degPerPxY,
  ];
}

export function bboxToString(bbox: BBox): string {
  return bbox.map((v) => v.toFixed(6)).join(",");
}
