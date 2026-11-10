-- V10: fraud ring = shared devices; exactly the P12 accounts share devices (>= 3 accounts each).
-- The engine's fraud_flags_daily check is added when the features job exists (M0.5).
WITH s AS (SELECT * FROM `${PROJECT}.hireme_backend_stub.riders_snapshot`
           WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `${PROJECT}.hireme_backend_stub.riders_snapshot`)),
d AS (SELECT device_id_hash, COUNT(*) k FROM s GROUP BY 1),
u AS (SELECT s.user_id, d.k >= 3 AS shared, p.persona_id = 'P12' AS fraud
      FROM s JOIN d USING (device_id_hash) JOIN `${PROJECT}.engage_sim.personas` p USING (user_id))
SELECT 'devices with >= 3 accounts' metric, CAST((SELECT COUNTIF(k >= 3) FROM d) AS FLOAT64) value,
       CAST(CEIL(COUNTIF(fraud) / ${ACCOUNTS_PER_DEVICE}) AS FLOAT64) lo, CAST(CEIL(COUNTIF(fraud) / ${ACCOUNTS_PER_DEVICE}) AS FLOAT64) hi,
       (SELECT COUNTIF(k >= 3) FROM d) = CEIL(COUNTIF(fraud) / ${ACCOUNTS_PER_DEVICE}) ok, FORMAT('%d fraud accounts', COUNTIF(fraud)) detail FROM u
UNION ALL
SELECT 'fraud accounts not on a shared device', COUNTIF(fraud AND NOT shared), 0, 0, COUNTIF(fraud AND NOT shared) = 0, '' FROM u
UNION ALL
SELECT 'non-fraud accounts on a shared device', COUNTIF(shared AND NOT fraud), 0, 0, COUNTIF(shared AND NOT fraud) = 0, '' FROM u
