-- Canonical flattened event view (DATA_MODEL §3.1). Works unchanged on the synthetic dataset and the real GA4 export.
-- events_* matches both events_YYYYMMDD and events_intraday_YYYYMMDD; dedupe with
-- QUALIFY ROW_NUMBER() OVER (PARTITION BY event_key ORDER BY table_suffix) = 1   (daily shard wins over intraday).
-- event_key = event_uuid, or for Firebase automatic events without one (app_remove) a hash of
-- user_pseudo_id|event_timestamp|event_name|event_bundle_sequence_id (the same inputs as the poller's UUIDv5, D-072).
CREATE OR REPLACE VIEW `${PROJECT}.engage_features.v_events_flat` AS
SELECT
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'event_uuid') AS event_uuid,
  COALESCE(
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'event_uuid'),
    TO_HEX(MD5(CONCAT(IFNULL(user_pseudo_id, ''), '|', CAST(event_timestamp AS STRING), '|', event_name, '|',
                      IFNULL(CAST(event_bundle_sequence_id AS STRING), ''))))) AS event_key,
  event_name,
  TIMESTAMP_MICROS(event_timestamp) AS event_ts,
  PARSE_DATE('%Y%m%d', event_date) AS event_date_ist,
  user_id, user_pseudo_id, platform,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'city_id') AS city_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'origin') AS origin,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'contract_version') AS contract_version,
  event_params, user_properties, _TABLE_SUFFIX AS table_suffix
FROM `${PROJECT}.${GA4_DATASET}.events_*`;
