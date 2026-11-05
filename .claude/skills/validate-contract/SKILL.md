---
name: validate-contract
description: Validate HireMe contract artefacts (event JSON Schemas, examples in docs/DATA_MODEL.md, playbooks, templates, OpenAPI files, GA4 round-trip) and report problems. Use after contract edits and before handing the contract to the backend team.
---
# Validate the data contract

Run:

```
.venv/bin/python -m engage.tools.validate_contract --all
```

It checks that:
- all JSON Schemas compile
- every example in docs/DATA_MODEL.md validates
- every playbook validates and references existing events and templates
- OpenAPI files lint cleanly
- the GA4 round-trip (envelope → GA4 row → envelope) is lossless on fixtures

Report each failure with file and JSON path. Do not change schemas just to make validation pass; route contract changes through the contract-steward agent.
