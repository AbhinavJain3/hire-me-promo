-- V6: lapsing/lapsed/dormant riders' last ride falls in their band before the history end (>= 95 %).
WITH w AS (SELECT MAX(PARSE_DATE('%Y%m%d', event_date)) AS end_d FROM `${PROJECT}.${GA4_DATASET}.events_*`),
prop AS (SELECT user_id, MAX((SELECT value.string_value FROM UNNEST(user_properties) WHERE key = 'last_ride_date')) AS d
         FROM `${PROJECT}.${GA4_DATASET}.events_*` WHERE user_id IS NOT NULL GROUP BY 1),
ride AS (SELECT user_id, MAX(DATE(completed_ts, 'Asia/Kolkata')) AS d
         FROM `${PROJECT}.hireme_backend_stub.rides` WHERE status = 'completed' GROUP BY 1),
u AS (SELECT p.persona_id, COALESCE(GREATEST(SAFE.PARSE_DATE('%Y-%m-%d', prop.d), ride.d),
                                    SAFE.PARSE_DATE('%Y-%m-%d', prop.d), ride.d,
                                    SAFE.PARSE_DATE('%Y-%m-%d', JSON_VALUE(p.latent, '$.active_until'))) AS last_d
      FROM `${PROJECT}.engage_sim.personas` p LEFT JOIN prop USING (user_id) LEFT JOIN ride USING (user_id)
      WHERE p.persona_id IN ('P07', 'P08', 'P09')),
b AS (SELECT persona_id, CASE persona_id WHEN 'P07' THEN 7 WHEN 'P08' THEN 30 ELSE 90 END lo_d,
             CASE persona_id WHEN 'P07' THEN 14 WHEN 'P08' THEN 89 ELSE 10000 END hi_d,
             DATE_DIFF(w.end_d, last_d, DAY) AS age
      FROM u, w)
SELECT FORMAT('%s last ride %d-%d days before end', persona_id, ANY_VALUE(lo_d), ANY_VALUE(hi_d)) metric,
       SAFE_DIVIDE(COUNTIF(age BETWEEN lo_d AND hi_d), COUNT(*)) value, 0.95 lo, 1.0 hi,
       SAFE_DIVIDE(COUNTIF(age BETWEEN lo_d AND hi_d), COUNT(*)) >= 0.95 ok,
       FORMAT('%d/%d riders', COUNTIF(age BETWEEN lo_d AND hi_d), COUNT(*)) detail
FROM b GROUP BY persona_id
