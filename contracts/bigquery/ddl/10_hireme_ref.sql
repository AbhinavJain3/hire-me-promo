-- Reference data (DATA_MODEL §3.2). ENGINE-owned, kept after handoff.
CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_ref.cities` (
  city_id INT64 NOT NULL, city_name STRING NOT NULL, state STRING, country STRING,
  timezone STRING NOT NULL,      -- 'Asia/Kolkata'
  currency STRING NOT NULL,      -- 'INR'
  is_pilot BOOL NOT NULL
);
CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_ref.zones` (
  zone_id STRING NOT NULL,       -- '<CITY3>-<CODE>', e.g. NOI-S62, DEL-IGI-T3 (D-037)
  city_id INT64 NOT NULL, zone_name STRING NOT NULL,
  zone_type STRING NOT NULL,     -- residential|business|airport|railway|mall|nightlife|education
  lat FLOAT64, lng FLOAT64, base_demand_weight FLOAT64
);
CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_ref.vehicle_types` (
  vehicle_type STRING NOT NULL,  -- mini|sedan|prime|suv
  display_name STRING, base_fare_inr NUMERIC(12,2), per_km_inr NUMERIC(12,2), per_min_inr NUMERIC(12,2)
);
CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_ref.calendar_events` (
  event_date DATE, city_id INT64, kind STRING, name STRING, demand_multiplier FLOAT64   -- e.g. Diwali 2026-11-08
);
