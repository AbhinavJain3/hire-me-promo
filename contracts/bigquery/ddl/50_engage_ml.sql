-- ML (DATA_MODEL §3.6). ENGINE.
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ml.uplift_training_examples` (
  decision_id STRING, playbook_id STRING, user_id STRING, city_id INT64, decision_ts TIMESTAMP,
  arm STRING,                    -- holdout|treatment|exploration
  action STRING,                 -- none|reminder|pct_10|pct_15|pct_20|flat_30|flat_50
  features JSON,                 -- user_features_daily as of decision_ts - 1 day + trigger context (no leakage)
  converted_window BOOL, converted_24h BOOL, converted_7d BOOL,
  fare_value_inr NUMERIC(12,2), discount_cost_inr NUMERIC(12,2), sim_run_id STRING
) PARTITION BY DATE(decision_ts) CLUSTER BY playbook_id;
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ml.churn_training_examples` (
  as_of_date DATE, user_id STRING, features JSON, churned_30d BOOL
) PARTITION BY as_of_date;
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ml.score_log` (
  scored_at TIMESTAMP, decision_id STRING, model_id STRING, p0 FLOAT64, p1 JSON, churn FLOAT64, latency_ms INT64
) PARTITION BY DATE(scored_at);
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ml.model_registry` (
  model_id STRING, kind STRING, playbook_scope ARRAY<STRING>, trained_at TIMESTAMP, train_from DATE, train_to DATE,
  metrics JSON, artifact_uri STRING,
  status STRING                  -- candidate|shadow|active|retired
);
