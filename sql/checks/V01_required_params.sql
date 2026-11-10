-- V1: every event carries event_uuid, contract_version, origin and its required params; user_id set unless nullable.
WITH req AS (SELECT * FROM UNNEST(${REQUIRED_PARAMS})),           -- STRUCT<event_name, key>; '*' = every event
ev AS (
  SELECT event_name, user_id, ARRAY(SELECT p.key FROM UNNEST(event_params) p
         WHERE COALESCE(p.value.string_value, CAST(p.value.int_value AS STRING),
                        CAST(p.value.double_value AS STRING), CAST(p.value.float_value AS STRING)) IS NOT NULL) AS keys
  FROM `${PROJECT}.${GA4_DATASET}.events_*`),
miss AS (
  SELECT r.event_name AS req_event, e.event_name, r.key, COUNTIF(r.key NOT IN UNNEST(e.keys)) AS n
  FROM ev e JOIN req r ON r.event_name IN (e.event_name, '*')
  GROUP BY 1, 2, 3 HAVING n > 0)
SELECT 'missing required params' AS metric, CAST(IFNULL(SUM(n), 0) AS FLOAT64) AS value, 0.0 AS lo, 0.0 AS hi,
       IFNULL(SUM(n), 0) = 0 AS ok,
       IFNULL(STRING_AGG(FORMAT('%s.%s: %d', event_name, key, n), ', ' ORDER BY n DESC LIMIT 8), 'none') AS detail
FROM miss
UNION ALL
SELECT 'events without user_id (non-nullable events)', COUNTIF(user_id IS NULL), 0, 0, COUNTIF(user_id IS NULL) = 0,
       FORMAT('%d events checked', COUNT(*))
FROM ev WHERE event_name NOT IN UNNEST(${NULLABLE_USER_EVENTS})
