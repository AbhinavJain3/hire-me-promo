---
name: seed-firestore
description: Seed or refresh HireMe engine configuration documents in Firestore (engage_settings, engage_playbooks and versions, engage_templates, engage_budgets, engage_segments) via the Firebase MCP server, then read them back and diff. Use after config files change.
---
# Seed Firestore configuration

1. Verify the active Firebase project is hireme-engage-dev; stop otherwise.
2. Validate playbooks/*.json against contracts/playbook.schema.json and templates/*.yaml against the template schema. Stop on any error.
3. Write each document with the Firebase MCP write tool if the installed server provides one; otherwise run `.venv/bin/python -m sim.loaders.fs_config --project hireme-engage-dev`.
4. Read every document back with the Firebase MCP read tool and diff against the source files.
5. Never delete documents. Bulk rider data (hireme_riders) is not seeded here; it goes through the loaders.

Report: documents written, diffs (expected: none), validation errors.
