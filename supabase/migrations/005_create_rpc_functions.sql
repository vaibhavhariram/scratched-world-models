-- Get a single building with its entrances and score
CREATE OR REPLACE FUNCTION logistics.get_building(p_id BIGINT)
RETURNS JSON AS $$
    SELECT json_build_object(
        'id', b.id,
        'osm_id', b.osm_id,
        'name', b.name,
        'address', b.address,
        'building_type', b.building_type,
        'footprint', ST_AsGeoJSON(b.footprint)::json,
        'centroid', ST_AsGeoJSON(b.centroid)::json,
        'area_sqm', b.area_sqm,
        'perimeter_m', b.perimeter_m,
        'score', (
            SELECT json_build_object(
                'difficulty', s.difficulty,
                'stop_variance', s.stop_variance,
                'road_distance', s.road_distance,
                'entrance_count', s.entrance_count,
                'dwell_time', s.dwell_time,
                'sample_size', s.sample_size
            )
            FROM logistics.building_scores s
            WHERE s.building_id = b.id
        ),
        'entrances', COALESCE((
            SELECT json_agg(json_build_object(
                'id', ec.id,
                'location', ST_AsGeoJSON(ec.location)::json,
                'cluster_size', ec.cluster_size,
                'confidence', ec.confidence,
                'avg_dwell_sec', ec.avg_dwell_sec,
                'stddev_position', ec.stddev_position,
                'side', ec.side
            ))
            FROM logistics.entrance_candidates ec
            WHERE ec.building_id = b.id
        ), '[]'::json)
    )
    FROM logistics.buildings b
    WHERE b.id = p_id;
$$ LANGUAGE sql STABLE;


-- Get buildings within a bounding box as GeoJSON FeatureCollection
CREATE OR REPLACE FUNCTION logistics.get_buildings_in_bbox(
    p_west FLOAT,
    p_south FLOAT,
    p_east FLOAT,
    p_north FLOAT,
    p_min_score FLOAT DEFAULT 0,
    p_max_score FLOAT DEFAULT 1,
    p_limit INT DEFAULT 500
)
RETURNS JSON AS $$
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(b.footprint)::json,
            'properties', json_build_object(
                'id', b.id,
                'osm_id', b.osm_id,
                'name', b.name,
                'building_type', b.building_type,
                'difficulty', bs.difficulty,
                'entrance_count', (
                    SELECT COUNT(*)
                    FROM logistics.entrance_candidates ec
                    WHERE ec.building_id = b.id
                ),
                'sample_size', bs.sample_size
            )
        ) AS feature
        FROM logistics.buildings b
        LEFT JOIN logistics.building_scores bs ON bs.building_id = b.id
        WHERE b.footprint && ST_MakeEnvelope(p_west, p_south, p_east, p_north, 4326)
          AND COALESCE(bs.difficulty, 0) BETWEEN p_min_score AND p_max_score
        LIMIT p_limit
    ) sub;
$$ LANGUAGE sql STABLE;


-- Get entrance candidates within a bounding box as GeoJSON FeatureCollection
CREATE OR REPLACE FUNCTION logistics.get_entrances_in_bbox(
    p_west FLOAT,
    p_south FLOAT,
    p_east FLOAT,
    p_north FLOAT,
    p_limit INT DEFAULT 1000
)
RETURNS JSON AS $$
    SELECT json_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(json_agg(feature), '[]'::json)
    )
    FROM (
        SELECT json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(ec.location)::json,
            'properties', json_build_object(
                'id', ec.id,
                'building_id', ec.building_id,
                'cluster_size', ec.cluster_size,
                'confidence', ec.confidence,
                'avg_dwell_sec', ec.avg_dwell_sec,
                'side', ec.side
            )
        ) AS feature
        FROM logistics.entrance_candidates ec
        WHERE ec.location && ST_MakeEnvelope(p_west, p_south, p_east, p_north, 4326)
        LIMIT p_limit
    ) sub;
$$ LANGUAGE sql STABLE;
