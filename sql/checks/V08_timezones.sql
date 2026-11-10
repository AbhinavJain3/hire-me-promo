-- V8: event_date is the IST date of event_timestamp for every row.
SELECT 'rows where event_date != IST date' metric,
       CAST(COUNTIF(event_date != FORMAT_DATE('%Y%m%d', DATE(TIMESTAMP_MICROS(event_timestamp), 'Asia/Kolkata'))) AS FLOAT64) value,
       0.0 lo, 0.0 hi,
       COUNTIF(event_date != FORMAT_DATE('%Y%m%d', DATE(TIMESTAMP_MICROS(event_timestamp), 'Asia/Kolkata'))) = 0 ok,
       FORMAT('%d rows', COUNT(*)) detail
FROM `${PROJECT}.${GA4_DATASET}.events_*`
