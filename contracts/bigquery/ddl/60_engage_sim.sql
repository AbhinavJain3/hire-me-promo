-- Synthetic ground truth (DATA_MODEL §3.9). DEV ONLY. The engine and model service accounts have no access (D-012).
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_sim.personas` (
  user_id STRING NOT NULL, persona_id STRING NOT NULL, generation_id STRING, latent JSON
);
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_sim.true_effects` (
  generation_id STRING, persona_id STRING, playbook_id STRING,
  action STRING,                 -- none|reminder|pct_10|pct_15|pct_20|flat_30|flat_50|...
  p_convert FLOAT64, p_optout FLOAT64
);
CREATE TABLE IF NOT EXISTS `${PROJECT}.engage_sim.response_ledger` (
  sim_run_id STRING, message_id STRING, decision_id STRING, user_id STRING, drawn_at TIMESTAMP,
  drew_open BOOL, drew_convert BOOL, true_p0 FLOAT64, true_p1 FLOAT64
) PARTITION BY DATE(drawn_at);
