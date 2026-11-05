-- Engine operations mirror (DATA_MODEL §3.5). ENGINE, append-only (D-007): a status change appends a new row;
-- read the latest with QUALIFY ROW_NUMBER() OVER (PARTITION BY <id> ORDER BY updated_at DESC) = 1.
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.decisions` (
  decision_id STRING, updated_at TIMESTAMP, user_id STRING, city_id INT64,
  playbook_id STRING, playbook_version INT64, campaign_id STRING,
  trigger_event_uuid STRING, trigger_event_name STRING, trigger_event_ts TIMESTAMP, timer_id STRING,
  arm STRING,                    -- treatment|holdout|exploration
  status STRING,                 -- DATA_MODEL §4.6 status machine
  reason_code STRING, reason_detail STRING,
  scores JSON, offer JSON,
  channel STRING, send_at TIMESTAMP, template_id STRING, autonomy_effective INT64, approval_id STRING,
  guardrails JSON,
  attribution_window_hours INT64, clock_mode STRING, sim_run_id STRING
) PARTITION BY DATE(updated_at) CLUSTER BY playbook_id, city_id, user_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.messages` (
  message_id STRING, updated_at TIMESTAMP, decision_id STRING, user_id STRING, channel STRING, provider STRING,
  provider_message_id STRING, template_id STRING, language STRING, llm_used BOOL, llm_model STRING,
  status STRING,                 -- queued|sending|sent|delivered|failed|undeliverable|dlq|cancelled
  attempt INT64, error_code STRING, sent_at TIMESTAMP, delivered_at TIMESTAMP, opened_at TIMESTAMP,
  cost_inr NUMERIC(12,4)
) PARTITION BY DATE(updated_at) CLUSTER BY channel, decision_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.promos` (
  promo_ref STRING, updated_at TIMESTAMP, promo_id INT64, code STRING, decision_id STRING, campaign_id STRING,
  playbook_id STRING, user_id STRING, city_id INT64, type STRING, value NUMERIC(12,2), max_discount_inr NUMERIC(12,2),
  liability_inr NUMERIC(12,2), valid_from TIMESTAMP, valid_to TIMESTAMP,
  status STRING,                 -- creating|active|redeemed|expired|deactivated|failed
  redeemed_at TIMESTAMP, ride_id STRING, cost_inr NUMERIC(12,2),
  created_by STRING              -- ai|admin
) PARTITION BY DATE(updated_at) CLUSTER BY playbook_id, user_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.budget_ledger_entries` (
  entry_id STRING, created_at TIMESTAMP, ledger_date DATE, city_id INT64, playbook_id STRING,
  kind STRING,                   -- commit|redeem|release
  amount_inr NUMERIC(12,2), promo_ref STRING, decision_id STRING
) PARTITION BY ledger_date CLUSTER BY city_id, playbook_id;

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.audit_log` (
  audit_id STRING, created_at TIMESTAMP, actor_type STRING, actor_id STRING, actor_role STRING,
  action STRING, target_type STRING, target_id STRING, before_json JSON, after_json JSON, reason STRING, request_id STRING
) PARTITION BY DATE(created_at);

CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.playbook_versions` (
  playbook_id STRING, version INT64, created_at TIMESTAMP, created_by STRING, config JSON, approved_by STRING, approved_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.approvals` (
  approval_id STRING, updated_at TIMESTAMP, kind STRING, status STRING, payload JSON, decided_by STRING, decided_at TIMESTAMP
) PARTITION BY DATE(updated_at);
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_ops.timers_log` (
  timer_id STRING, updated_at TIMESTAMP, playbook_id STRING, user_id STRING, status STRING, fire_at TIMESTAMP, reason STRING
) PARTITION BY DATE(updated_at);
