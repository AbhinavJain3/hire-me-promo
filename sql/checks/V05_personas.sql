-- V5: persona sanity on completed rides (IST weekdays). Reads ground truth for validation only.
WITH w AS (SELECT MAX(PARSE_DATE('%Y%m%d', event_date)) AS end_d FROM `${PROJECT}.${GA4_DATASET}.events_*`),
r AS (SELECT p.persona_id, r.status, DATE(r.completed_ts, 'Asia/Kolkata') AS done_d,
             EXTRACT(DAYOFWEEK FROM DATETIME(r.booked_ts, 'Asia/Kolkata')) AS dow   -- 1 = Sunday
      FROM `${PROJECT}.hireme_backend_stub.rides` r JOIN `${PROJECT}.engage_sim.personas` p USING (user_id))
SELECT 'commuter (P02) weekday share' metric,
       SAFE_DIVIDE(COUNTIF(dow BETWEEN 2 AND 6), COUNT(*)) value, 0.8 lo, 1.0 hi,
       SAFE_DIVIDE(COUNTIF(dow BETWEEN 2 AND 6), COUNT(*)) > 0.8 ok, FORMAT('%d completed rides', COUNT(*)) detail
FROM r WHERE persona_id = 'P02' AND status = 'completed'
UNION ALL
SELECT 'weekend (P03) Fri-Sun share', SAFE_DIVIDE(COUNTIF(dow IN (6, 7, 1)), COUNT(*)), 0.7, 1.0,
       SAFE_DIVIDE(COUNTIF(dow IN (6, 7, 1)), COUNT(*)) > 0.7, FORMAT('%d completed rides', COUNT(*))
FROM r WHERE persona_id = 'P03' AND status = 'completed'
UNION ALL
SELECT 'dormant (P09) rides in the last 90 days', COUNT(*), 0, 0, COUNT(*) = 0, 'completed rides'
FROM r, w WHERE persona_id = 'P09' AND status = 'completed' AND done_d > DATE_SUB(w.end_d, INTERVAL 90 DAY)
UNION ALL
SELECT 'not-activated (P05) rides', COUNT(*), 0, 0, COUNT(*) = 0, 'any status' FROM r WHERE persona_id = 'P05'
