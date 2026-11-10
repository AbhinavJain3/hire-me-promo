-- Window: event shards are contiguous days, and the backend stub covers the same window.
-- Detects data the BigQuery sandbox has already expired (partitions older than 60 days, D-082/D-089).
WITH e AS (SELECT MIN(PARSE_DATE('%Y%m%d', event_date)) lo, MAX(PARSE_DATE('%Y%m%d', event_date)) hi,
                  COUNT(DISTINCT event_date) days FROM `${PROJECT}.${GA4_DATASET}.events_*`),
r AS (SELECT MIN(DATE(booked_ts, 'Asia/Kolkata')) lo, MAX(DATE(booked_ts, 'Asia/Kolkata')) hi FROM `${PROJECT}.hireme_backend_stub.rides`)
SELECT 'event shards contiguous' metric, CAST(e.days AS FLOAT64) value, DATE_DIFF(e.hi, e.lo, DAY) + 1.0 lo, DATE_DIFF(e.hi, e.lo, DAY) + 1.0 hi,
       e.days = DATE_DIFF(e.hi, e.lo, DAY) + 1 ok, FORMAT('%t .. %t', e.lo, e.hi) detail FROM e
UNION ALL
SELECT 'rides start within 1 day of the first event shard', CAST(DATE_DIFF(r.lo, e.lo, DAY) AS FLOAT64), -1, 1,
       ABS(DATE_DIFF(r.lo, e.lo, DAY)) <= 1, FORMAT('rides %t .. %t; sandbox drops ride partitions from %t', r.lo, r.hi,
       DATE_ADD(r.lo, INTERVAL 60 DAY)) FROM e, r
