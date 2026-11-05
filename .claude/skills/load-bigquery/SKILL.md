---
name: load-bigquery
description: Load generated HireMe synthetic data into BigQuery (GA4-shaped events_YYYYMMDD shards, hireme_ref, hireme_backend_stub, engage_sim ground truth) and run the V1-V14 validation checks. Use after generate-dummy-data.
---
# Load data into BigQuery

1. Confirm the project is hireme-engage-dev.
2. Create or update tables from the contract DDL:
   `.venv/bin/python -m sim.loaders.bq_ddl --project hireme-engage-dev`
3. Load the generation:
   `.venv/bin/python -m sim.loaders.bq_load --what ref,events,stubs,truth --dir <generation dir>`
4. Run every file in sql/checks through the BigQuery MCP `execute_sql` tool, dry run first, and record V1-V14 status.
5. Stop and report at the first failed check. Do not fix data by hand.

Report: tables loaded with row counts, bytes loaded, and the check results table.
