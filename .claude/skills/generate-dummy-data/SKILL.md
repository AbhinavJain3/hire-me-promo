---
name: generate-dummy-data
description: Generate HireMe synthetic history (personas, GA4-shaped events, rider stub records, ground truth) at a given scale and seed, without loading it anywhere. Use when dummy data must be created or regenerated.
---
# Generate synthetic data

Follow docs/DUMMY_DATA_PLAN.md. Delegate non-trivial generator changes to the synthetic-data-engineer agent.

Preconditions:
- Target is the dev project hireme-engage-dev.
- `.venv` exists; sim/personas.yaml has been reviewed.

Run:

```
.venv/bin/python -m sim.generator --scale <tiny|small|medium|large> --seed <int> --out data/gen/<YYYY-MM-DD>/
```

Then report:
- generation_id, scale and seed
- riders by persona and by city
- events by name, and the date range covered
- output files and sizes

Do not load anything. Loading is done by the load-bigquery and seed-firestore skills.
