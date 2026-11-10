# sql/checks: validation checks V1-V14 in BigQuery (DUMMY_DATA_PLAN §10)

Run after every load (and nightly once jobs exist):

    .venv/bin/python -m sim.validate.bq --project hireme-engage-dev

Each file returns rows `(metric STRING, value FLOAT64, lo FLOAT64, hi FLOAT64, ok BOOL, detail STRING)`;
a check fails if any row has `ok = FALSE`. Placeholders filled by the runner: `${PROJECT}`, `${GA4_DATASET}`,
`${REQUIRED_PARAMS}` (from contracts/events/v1/catalog.yaml), `${REACH_TARGETS}` (from sim/personas.yaml).
Every query is dry-run first and refused above the byte limit. Checks may read `engage_sim` (ground truth):
they are validation, not engine code (D-012).

Not in SQL: V3 GA4 round trip (local, `sim.validate`), V11 IAM (needs the engine service account),
V12 ground-truth recovery (needs a simulated run, M1.4), V13 Firestore count and sample (runner, Firestore client).
