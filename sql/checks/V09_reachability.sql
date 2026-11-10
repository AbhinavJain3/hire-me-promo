-- V9: consent and reachability shares within ±2 points (widened to 3 standard errors for small samples).
-- phone_dnd is not in the PII-free snapshot; it is checked locally by sim.validate.
WITH s AS (SELECT * FROM `${PROJECT}.hireme_backend_stub.riders_snapshot`
           WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `${PROJECT}.hireme_backend_stub.riders_snapshot`)),
v AS (SELECT 'consent_push' k, AVG(IF(consent_push, 1, 0)) v, COUNT(*) n FROM s
      UNION ALL SELECT 'consent_email', AVG(IF(consent_email, 1, 0)), COUNT(*) FROM s
      UNION ALL SELECT 'consent_sms', AVG(IF(consent_sms, 1, 0)), COUNT(*) FROM s
      UNION ALL SELECT 'consent_whatsapp', AVG(IF(consent_whatsapp, 1, 0)), COUNT(*) FROM s
      UNION ALL SELECT 'has_email', AVG(IF(has_email, 1, 0)), COUNT(*) FROM s
      UNION ALL SELECT 'push_token_present', AVG(IF(has_push_token, 1, 0)), COUNT(*) FROM s),
t AS (SELECT * FROM UNNEST(${REACH_TARGETS})),                  -- STRUCT<k, target>
j AS (SELECT v.k, v.v, v.n, t.target, GREATEST(0.02, 3 * SQRT(t.target * (1 - t.target) / v.n)) tol FROM v JOIN t USING (k))
SELECT k metric, v value, target - tol lo, target + tol hi, ABS(v - target) <= tol ok, FORMAT('target %.2f, %d riders', target, n) detail FROM j
