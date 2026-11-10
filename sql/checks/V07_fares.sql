-- V7: fares in bounds; Sector 62 -> Connaught Place mini median ₹330-430 (needs >= 20 rides, else informational).
WITH r AS (SELECT * FROM `${PROJECT}.hireme_backend_stub.rides`),
s AS (SELECT APPROX_QUANTILES(CAST(gross_fare_inr AS FLOAT64), 2)[OFFSET(1)] med, COUNT(*) n
      FROM r WHERE status = 'completed' AND vehicle_type = 'mini' AND pickup_zone = 'NOI-S62' AND drop_zone = 'DEL-CP')
SELECT 'fares outside ₹40-₹3000' metric, COUNTIF(gross_fare_inr IS NOT NULL AND gross_fare_inr NOT BETWEEN 40 AND 3000) value,
       0.0 lo, 0.0 hi, COUNTIF(gross_fare_inr IS NOT NULL AND gross_fare_inr NOT BETWEEN 40 AND 3000) = 0 ok,
       FORMAT('%d rides', COUNT(*)) detail FROM r
UNION ALL
SELECT 'NOI-S62 -> DEL-CP mini median fare', med, 330, 430, IF(n >= 20, med BETWEEN 330 AND 430, TRUE),
       IF(n >= 20, FORMAT('%d rides', n), FORMAT('only %d rides; informational below 20', n)) FROM s
