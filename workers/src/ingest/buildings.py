"""
Ingest Manhattan building footprints from OpenStreetMap via Overpass API.
"""

import json
import requests
from shapely.geometry import shape, mapping

from src.common.config import PipelineConfig
from src.common.db import get_connection, get_cursor


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:300];
area["name"="Manhattan"]["admin_level"="7"]->.manhattan;
(
  way["building"](area.manhattan);
  relation["building"](area.manhattan);
);
out body;
>;
out skel qt;
"""


def _parse_osm_buildings(data: dict) -> list[dict]:
    """Parse Overpass JSON into building records with GeoJSON polygons."""
    nodes = {}
    ways = {}
    buildings = []

    for element in data.get("elements", []):
        if element["type"] == "node":
            nodes[element["id"]] = (element["lon"], element["lat"])
        elif element["type"] == "way":
            ways[element["id"]] = element

    for way_id, way in ways.items():
        tags = way.get("tags", {})
        if "building" not in tags:
            continue

        coords = [nodes[nid] for nid in way.get("nodes", []) if nid in nodes]
        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        geojson = {"type": "Polygon", "coordinates": [coords]}

        try:
            geom = shape(geojson)
            if not geom.is_valid:
                geom = geom.buffer(0)
            if geom.is_empty or geom.geom_type != "Polygon":
                continue
            geojson = mapping(geom)
        except Exception:
            continue

        address_parts = []
        if tags.get("addr:housenumber"):
            address_parts.append(tags["addr:housenumber"])
        if tags.get("addr:street"):
            address_parts.append(tags["addr:street"])

        buildings.append({
            "osm_id": way_id,
            "name": tags.get("name"),
            "address": " ".join(address_parts) if address_parts else None,
            "building_type": tags.get("building"),
            "geojson": json.dumps(geojson),
        })

    return buildings


def run_ingest_buildings(job_id: str, cfg: PipelineConfig) -> dict:
    """Download and ingest Manhattan building footprints."""
    print("Fetching buildings from Overpass API...")
    response = requests.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, timeout=600)
    response.raise_for_status()

    buildings = _parse_osm_buildings(response.json())
    if cfg.row_limit:
        buildings = buildings[:cfg.row_limit]
        print(f"Row limit applied: {len(buildings)} buildings")

    print(f"Parsed {len(buildings)} building footprints")

    if cfg.dry_run:
        print("[DRY RUN] Would insert/update {len(buildings)} buildings")
        return {"total_parsed": len(buildings), "dry_run": True}

    inserted = 0
    updated = 0

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            for b in buildings:
                cur.execute(
                    """
                    INSERT INTO logistics.buildings
                        (osm_id, name, address, building_type, footprint, area_sqm, perimeter_m)
                    VALUES (
                        %(osm_id)s, %(name)s, %(address)s, %(building_type)s,
                        ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326),
                        ST_Area(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326), 32618)),
                        ST_Perimeter(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326), 32618))
                    )
                    ON CONFLICT (osm_id) DO UPDATE SET
                        name = EXCLUDED.name, address = EXCLUDED.address,
                        building_type = EXCLUDED.building_type,
                        footprint = EXCLUDED.footprint,
                        area_sqm = EXCLUDED.area_sqm, perimeter_m = EXCLUDED.perimeter_m,
                        updated_at = now()
                    """,
                    b,
                )
                if cur.statusmessage == "INSERT 0 1":
                    inserted += 1
                else:
                    updated += 1

                if (inserted + updated) % 500 == 0:
                    conn.commit()
                    print(f"  Progress: {inserted + updated}/{len(buildings)}")

        conn.commit()

    return {"total_parsed": len(buildings), "inserted": inserted, "updated": updated}
