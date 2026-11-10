-- V14: no real-looking personal data in BigQuery: phone- or email-like strings in event params or user properties
-- must be synthetic (+919990xxxxxx, @example.test). The PII-free snapshot must flag every rider is_synthetic.
WITH vals AS (
  SELECT v FROM `${PROJECT}.${GA4_DATASET}.events_*`,
    UNNEST(ARRAY_CONCAT(ARRAY(SELECT value.string_value FROM UNNEST(event_params)),
                        ARRAY(SELECT value.string_value FROM UNNEST(user_properties)))) v
  WHERE v IS NOT NULL
    -- whole-value matches only: ids and hashes often contain digit runs like 91xxxxxxxxxx
    AND (REGEXP_CONTAINS(v, r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$') OR REGEXP_CONTAINS(v, r'^\+?(91)?[6-9][0-9]{9}$')))
SELECT 'non-synthetic phone/email strings in events' metric,
       CAST(COUNTIF(NOT (ENDS_WITH(v, '@example.test') OR REGEXP_CONTAINS(v, r'^\+919990[0-9]{6}$'))) AS FLOAT64) value,
       0.0 lo, 0.0 hi, COUNTIF(NOT (ENDS_WITH(v, '@example.test') OR REGEXP_CONTAINS(v, r'^\+919990[0-9]{6}$'))) = 0 ok,
       FORMAT('%d phone/email-like values', COUNT(*)) detail FROM vals
UNION ALL
SELECT 'snapshot rows not marked is_synthetic', COUNTIF(is_synthetic IS NOT TRUE), 0, 0, COUNTIF(is_synthetic IS NOT TRUE) = 0,
       FORMAT('%d rows', COUNT(*)) FROM `${PROJECT}.hireme_backend_stub.riders_snapshot`
