---
name: playbook-author
description: Converts a spec use case (A1-H5) into a validated HireMe playbook JSON, English and Hindi message templates, and a simulator scenario with a test. Use when adding or changing a playbook.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---
Inputs: the playbook id from the spec (docs/reference/spec_extracted.txt section 5) and any admin overrides.

Steps:
1. Draft playbooks/<id>.json against contracts/playbook.schema.json. Use the defaults in docs/DATA_MODEL.md §5.4 when the playbook is listed there; otherwise use the spec's defaults and log each non-obvious choice.
2. Set message_class (transactional | service | marketing), exclusive_group and priority according to decision.md (message classes and conflict resolution entries).
3. Write templates/<id>_<channel>_<lang>.yaml using only approved variables ({first_name}, {drop_area}, {fare}, {promo_code}, {expiry}, {discount_label}, {validity_minutes}). Prices and codes are always placeholders, never literal numbers. SMS templates need DLT fields (placeholder ids until registered).
4. Add a scenario under sim/scenarios and an assertion under tests/scenario.
5. Run the validators and the scenario at tiny scale.

Report: files created or changed, validation and scenario results, and open questions (add them to docs/OPEN_QUESTIONS.md if business input is needed).
