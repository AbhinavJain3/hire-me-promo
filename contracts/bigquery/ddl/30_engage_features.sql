-- Features (DATA_MODEL §3.4). ENGINE.
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_features.user_features_daily` (
  snapshot_date DATE NOT NULL,                 -- IST day the snapshot describes (as of 23:59:59 IST)
  user_id STRING NOT NULL, city_id INT64, feature_version STRING NOT NULL,   -- 'fv1'
  signup_date DATE, days_since_signup INT64,
  total_rides INT64, rides_7d INT64, rides_30d INT64, rides_90d INT64,
  last_ride_date DATE, days_since_last_ride INT64, avg_weekly_rides_prior_8w FLOAT64,
  weekday_ride_share_90d FLOAT64, weekend_ride_share_90d FLOAT64, airport_rides_90d INT64,
  commute_regularity_score FLOAT64, commute_hour_mode INT64, home_zone STRING, work_zone STRING,
  fare_checks_7d INT64, fare_checks_30d INT64, fare_checks_per_ride_30d FLOAT64, fare_checks_no_book_7d INT64,
  abandons_30d INT64, surge_abandon_rate_30d FLOAT64,
  promo_ride_share_90d FLOAT64, promo_redemptions_30d INT64,
  avg_fare_90d NUMERIC(12,2), spend_30d NUMERIC(12,2), spend_90d NUMERIC(12,2),
  preferred_vehicle STRING, preferred_payment STRING, long_trip_mini_share_90d FLOAT64,
  low_rating_7d BOOL, support_ticket_7d BOOL,
  notif_sent_30d INT64, notif_open_rate_30d FLOAT64, best_open_hour_ist INT64,
  price_sensitivity_score FLOAT64, price_sensitivity_band STRING,   -- low|medium|high (D-062)
  churn_score FLOAT64,                                              -- NULL in Phase 1
  discount_trained_flag BOOL, fraud_flag BOOL, fraud_reasons ARRAY<STRING>,
  ltv_band STRING, language STRING, segments ARRAY<STRING>
) PARTITION BY snapshot_date CLUSTER BY city_id, user_id
OPTIONS (partition_expiration_days = 400);

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_features.segment_membership_daily` (
  snapshot_date DATE, segment_id STRING, user_id STRING, city_id INT64
) PARTITION BY snapshot_date CLUSTER BY segment_id, city_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_features.playbook_base_rates` (   -- feeds heuristic_v1 (D-029)
  computed_date DATE, playbook_id STRING, city_id INT64, price_sensitivity_band STRING, recency_band STRING,
  n_triggers INT64, p0_conversion FLOAT64, p0_ci_low FLOAT64, p0_ci_high FLOAT64,
  source STRING                  -- history_no_msg|holdout
);

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_features.fraud_flags_daily` (
  snapshot_date DATE, user_id STRING,
  reason STRING,                 -- multi_account_device|shared_payment|repeat_welcome|code_only_booker
  evidence JSON
) PARTITION BY snapshot_date;

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_features.zone_hour_stats` (
  stat_hour TIMESTAMP, zone_id STRING, fare_checks INT64, bookings INT64, no_driver_found INT64,
  avg_surge FLOAT64, conversion_rate FLOAT64
) PARTITION BY DATE(stat_hour) CLUSTER BY zone_id;
