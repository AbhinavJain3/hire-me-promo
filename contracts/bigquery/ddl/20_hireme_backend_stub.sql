-- Backend stand-ins (DATA_MODEL §3.3). NOW -> RIDER-API / backend export after handoff.
-- Partitioning uses the UTC date of the timestamp: BigQuery partition expressions cannot take a time zone (D-075).
CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_backend_stub.riders_snapshot` (   -- daily copy of Firestore hireme_riders, PII-free columns only
  snapshot_date DATE, user_id STRING, city_id INT64, signup_ts TIMESTAMP, language STRING,
  has_email BOOL, has_push_token BOOL, push_platform STRING,
  consent_push BOOL, consent_email BOOL, consent_sms BOOL, consent_whatsapp BOOL,
  wallet_balance_inr NUMERIC(12,2), device_id_hash STRING, payment_fingerprints ARRAY<STRING>,
  referral_code_used STRING, referred_by_user_id STRING, birth_month_day STRING, is_synthetic BOOL
) PARTITION BY snapshot_date CLUSTER BY city_id, user_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_backend_stub.rides` (            -- source of truth for fares after handoff
  ride_id STRING, user_id STRING, city_id INT64,
  status STRING,                 -- completed|cancelled|no_driver
  booked_ts TIMESTAMP, started_ts TIMESTAMP, completed_ts TIMESTAMP, is_scheduled BOOL, scheduled_ts TIMESTAMP,
  pickup_zone STRING, drop_zone STRING, distance_km FLOAT64, vehicle_type STRING, payment_method STRING,
  gross_fare_inr NUMERIC(12,2), discount_inr NUMERIC(12,2), final_fare_inr NUMERIC(12,2),
  promo_code STRING, promo_id INT64, surge_multiplier FLOAT64, driver_id STRING, rating INT64
) PARTITION BY DATE(booked_ts) CLUSTER BY city_id, user_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.hireme_backend_stub.promo_redemptions` (
  promo_id INT64, code STRING, user_id STRING, ride_id STRING, redeemed_ts TIMESTAMP, discount_inr NUMERIC(12,2)
) PARTITION BY DATE(redeemed_ts);
