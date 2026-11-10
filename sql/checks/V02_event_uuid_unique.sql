-- V2: event_uuid unique across all shards.
WITH ids AS (SELECT (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'event_uuid') AS id
             FROM `${PROJECT}.${GA4_DATASET}.events_*`)
SELECT 'duplicate event_uuid' AS metric, CAST(COUNT(id) - COUNT(DISTINCT id) AS FLOAT64) AS value, 0.0 AS lo, 0.0 AS hi,
       COUNT(id) = COUNT(DISTINCT id) AS ok, FORMAT('%d events', COUNT(*)) AS detail
FROM ids
