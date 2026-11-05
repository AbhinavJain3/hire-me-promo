# CLAUDE.md — HireMe AI Engagement Engine

## Purpose
Build the HireMe AI Engagement Engine: read rider events (Firebase Analytics / BigQuery), decide who to nudge (rules + uplift scoring), create promo codes via the HireMe Promo API, send by push/SMS/email/WhatsApp, enforce guardrails in code, and measure incremental lift against holdouts. Source spec: `docs/reference/spec_extracted.txt` (+ two PNG diagrams). Start with `README.md`.

## Mandatory documentation rules
- **Every design decision gets a new entry in `decision.md`** (next D-### id, ADR fields: date, title, context, options, decision, consequences, status, decided by). Never renumber; mark superseded entries by changing only their Status line. Use the `log-decision` skill.
- **Whenever the runtime flow changes, update `flow.md`** (current flow steps and the mermaid diagram) in the same change. Planned behaviour goes only in its "Future flow" section. Use the `update-flow` skill.
- Unresolved business questions go to `docs/OPEN_QUESTIONS.md` (next OQ-## id, with our default assumption and the linked D- id).
- Keep names identical across docs and code (collections, tables, events, params, playbook ids like `B2_abandoned_booking`). `docs/DATA_MODEL.md` and `contracts/` are the contract the HireMe backend implements: follow its versioning policy.

## Constraints (current)
- Data sources: **only the Firebase project (Firestore; Firebase MCP server for agents/tooling) and BigQuery.** No HireMe backend webhook, no Rider DB API, no real Promo/FCM/SMS/email access. Use the simulator, the `hireme_riders` stub and the mocks.
- Work only in the dev project `hireme-engage-dev` with synthetic data. Never touch a production project; never put real personal data in dev.
- Python: use the existing virtualenv `.venv` (`.venv/bin/python`). Do not install packages or create new environments without the user's approval.
- Time: store UTC, business logic in Asia/Kolkata (IST). Money: INR.
- Guardrails are enforced in code, never by the LLM. The LLM never writes prices or codes; SMS/WhatsApp never use LLM text.
- Bulk data loads go through loaders (BigQuery load jobs, Firestore Admin SDK); use MCP for config seeding and verification. Dry-run BigQuery queries before running large scans.

## Contract commands
- After editing `contracts/events/v1/catalog.yaml`: `.venv/bin/python -m engage.tools.gen_contract`, then `.venv/bin/python -m engage.tools.validate_contract --all` and `.venv/bin/python -m pytest tests/contract`. Never edit `contracts/events/v1/generated/` by hand.
- `contracts/` wins over `docs/DATA_MODEL.md` / `docs/API.md` on any conflict; fix the doc in the same change.

## Where things live
- Docs: `docs/` (ARCHITECTURE, DATA_MODEL, API, DUMMY_DATA_PLAN, IMPLEMENTATION_PLAN, AGENTS_AND_SKILLS, OPEN_QUESTIONS); root: `decision.md`, `flow.md`, `README.md`.
- Planned code layout: see `docs/ARCHITECTURE.md` §14 (`contracts/`, `engage/`, `sql/`, `playbooks/`, `templates/`, `sim/`, `mocks/`, `console/`, `tests/`).
- Claude Code subagents: `.claude/agents/` (contract-steward, synthetic-data-engineer, bigquery-analyst, firestore-operator, playbook-author, guardrail-auditor, scenario-runner, compliance-reviewer, docs-keeper, uplift-modeler). Skills: `.claude/skills/` (log-decision, update-flow, generate-dummy-data, load-bigquery, seed-firestore, run-scenario, holdout-report, new-playbook, validate-contract, ga4-sql). Design rationale: `docs/AGENTS_AND_SKILLS.md`.
- Not yet created: `.mcp.json` and `.claude/settings.json` (MCP package versions and tool names must be verified first, milestone M0.2). Agent `tools:` lists use the expected MCP tool names; correct them once `/mcp` shows the real ones.
- Client deliverable: `docs/client/HireMe_AI_Engagement_Engine_Architecture_and_Flow.docx`.
