-- V4: funnel ratios (D-081).
WITH c AS (SELECT COUNTIF(event_name = 'fare_check') fc, COUNTIF(event_name = 'ride_booked') b,
                  COUNTIF(event_name = 'ride_completed') rc, COUNTIF(event_name = 'booking_abandoned') ab
           FROM `${PROJECT}.${GA4_DATASET}.events_*`),
m AS (SELECT 'fare_check -> ride_booked' metric, SAFE_DIVIDE(b, fc) value, 0.30 lo, 0.45 hi, FORMAT('%d / %d', b, fc) detail FROM c
      UNION ALL SELECT 'ride_booked -> ride_completed', SAFE_DIVIDE(rc, b), 0.85, 0.92, FORMAT('%d / %d', rc, b) FROM c
      UNION ALL SELECT 'abandon share of booking flows', SAFE_DIVIDE(ab, ab + b), 0.20, 0.30, FORMAT('%d / %d', ab, ab + b) FROM c)
SELECT metric, value, lo, hi, value BETWEEN lo AND hi AS ok, detail FROM m
