---
name: run-scenario
description: Run HireMe simulator scenarios end to end (inject events on the virtual clock, let the engine act on the mock services, assert outcomes). Use after engine changes, before gate reviews, or for demos. Usage - run-scenario <name|all>.
---
# Run simulator scenarios

Scenario names and expected behaviour are listed in docs/DUMMY_DATA_PLAN.md §9. For a single scenario you can run it directly; for `all` or for failure investigation, delegate to the scenario-runner agent.

```
.venv/bin/python -m sim.replayer --mode scenario --name <name> --speed 120
.venv/bin/python -m pytest tests/scenario -k <name>
```

Summarise as a table: scenario | expected behaviour | observed decisions (ids, status, reason_code) | pass/fail.
Do not change code or data to make a scenario pass.
