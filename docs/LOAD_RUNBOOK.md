# Load runbook: synthetic data into the dev project (free tier)

How to (re)fill `hireme-engage-dev` with synthetic data and prove it is correct. Decisions: D-082/D-083 (free tier, `demo` scale), D-084 (`--history-end`), D-087 (Firestore without TTL), D-089 (loaders), D-090 (SQL checks).

## Prerequisites (once per machine)

- `.venv` with `requirements-dev.txt`; Google Cloud CLI in `.venv/google-cloud-sdk`; Firebase CLI in `.venv/node` (README "Local tooling").
- Logged in as the project owner: `firebase login`, `gcloud auth login`, `gcloud auth application-default login`, and `gcloud auth application-default set-quota-project hireme-engage-dev`.
- Repo scripts use the gcloud configuration `hireme-engage-dev` (`CLOUDSDK_ACTIVE_CONFIG_NAME=hireme-engage-dev`), never your default one.

## When to reload

The BigQuery sandbox drops partitions older than 60 days and deletes unpartitioned tables 60 days after creation. With 45 days of history, ride, redemption and snapshot partitions start to disappear about 15 days after the load. Check `W01_window_and_retention`: its detail line prints the date ride partitions start to drop. Reload before that date, or before any demo.

## Steps

```bash
# 1. Generate (about 1 minute for demo; reproducible: same seed + same history end = same files)
.venv/bin/python -m sim.generator --scale demo --seed 42 --history-end yesterday --force
.venv/bin/python -m sim.validate data/gen/demo_s42            # local checks incl. V3 round trip

# 2. Datasets and tables (idempotent)
.venv/bin/python -m sim.loaders.bq_ddl --project hireme-engage-dev

# 3. Load BigQuery (WRITE_TRUNCATE per table; row counts checked against manifest.json)
.venv/bin/python -m sim.loaders.bq_load --project hireme-engage-dev --dir data/gen/demo_s42
.venv/bin/python -m sim.loaders.bq_ddl --project hireme-engage-dev --views

# 4. Load the rider stub into Firestore (3,000 writes of the ~20 k/day Spark quota)
.venv/bin/python -m sim.loaders.fs_riders --project hireme-engage-dev --dir data/gen/demo_s42

# 5. Validate in BigQuery + Firestore (dry-runs every query; ~320 MB scanned for demo)
.venv/bin/python -m sim.validate.bq --project hireme-engage-dev
```

A reload with a new `--history-end` writes new `events_YYYYMMDD` shards; shards from the previous window stay until they expire. Delete old shards first if the checks must see only the new window (`bq rm` is denied to agents; a person runs it).

## Firestore rules and indexes (after contract changes)

```bash
.venv/bin/python scripts/firestore_free_tier.py
.venv/bin/firebase deploy --only firestore --config firebase.free-tier.json --project hireme-engage-dev
```

## Expected result (demo, seed 42, history 2026-09-25 to 2026-11-08)

338,598 events in 45 shards, 34,123 rides, 1,664 redemptions, 3,000 riders; `sim.validate.bq`: 12 passed, 0 failed, 3 not run (V3 local only, V11 needs the engine service account, V12 needs a simulated run).
