-- Spatial indexes (GIST)
CREATE INDEX idx_buildings_footprint ON logistics.buildings USING GIST (footprint);
CREATE INDEX idx_buildings_centroid  ON logistics.buildings USING GIST (centroid);
CREATE INDEX idx_stop_events_location ON logistics.stop_events USING GIST (location);
CREATE INDEX idx_entrance_location ON logistics.entrance_candidates USING GIST (location);

-- B-tree indexes
CREATE INDEX idx_buildings_osm_id ON logistics.buildings (osm_id);
CREATE INDEX idx_stop_events_timestamp ON logistics.stop_events (event_timestamp);
CREATE INDEX idx_stop_events_batch ON logistics.stop_events (batch_id);
CREATE INDEX idx_bse_building ON logistics.building_stop_events (building_id);
CREATE INDEX idx_bse_stop ON logistics.building_stop_events (stop_event_id);
CREATE INDEX idx_entrance_building ON logistics.entrance_candidates (building_id);
CREATE INDEX idx_scores_difficulty ON logistics.building_scores (difficulty);
CREATE INDEX idx_scores_building ON logistics.building_scores (building_id);
