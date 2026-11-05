-- HireMe Engagement Engine - BigQuery datasets (docs/DATA_MODEL.md §3).
-- Placeholders: ${PROJECT} (hireme-engage-dev), ${GA4_DATASET} (analytics_999999999 now; analytics_<real id> after handoff, D-059).
-- Location asia-south1 (D-051). Applied by sim.loaders.bq_ddl at M0.2.
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.${GA4_DATASET}`  OPTIONS (location = 'asia-south1', description = 'Raw events in the exact GA4 export shape (synthetic in dev, D-003)');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.hireme_ref`          OPTIONS (location = 'asia-south1', description = 'Cities, zones, vehicle types, calendar');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.hireme_backend_stub` OPTIONS (location = 'asia-south1', description = 'Stand-ins for HireMe backend tables (-> Rider API / backend export)');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.engage_features`     OPTIONS (location = 'asia-south1', description = 'Daily user features, segments, base rates, fraud flags');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.engage_ops`          OPTIONS (location = 'asia-south1', description = 'Append-only mirror of engine operational records (D-007)');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.engage_ml`           OPTIONS (location = 'asia-south1', description = 'Training sets, score log, model registry');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.engage_mart`         OPTIONS (location = 'asia-south1', description = 'Reporting marts (spec 10); built by engage-jobs SQL in Phase 1');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.engage_views`        OPTIONS (location = 'asia-south1', description = 'Aggregated, PII-free views for Ask AI (D-035)');
CREATE SCHEMA IF NOT EXISTS `${PROJECT}.engage_sim`          OPTIONS (location = 'asia-south1', description = 'Synthetic ground truth. Never readable by the engine (D-012)');
-- Raw event shards events_YYYYMMDD / events_intraday_YYYYMMDD are created by the loader from
-- contracts/bigquery/ga4_events_schema.json, one shard per IST day.
