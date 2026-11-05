# HireMe AI Engagement Engine: Agents, Skills and MCP Setup

| | |
|---|---|
| Status | Proposed, pending client review |
| Date | 2026-11-02 |
| Author | AI (Fable 5.1) |
| Related | [ARCHITECTURE.md](ARCHITECTURE.md) §3 (LLM agents), decisions D-010, D-032-D-035 |

This document covers two different things:

1. **Development tooling** (sections 1-2): Claude Code subagents (`.claude/agents/*.md`), skills (`.claude/skills/<name>/SKILL.md`), MCP servers (`.mcp.json`) and permissions that help *us build* the engine. Nothing here runs in production.
2. **Runtime AI agents in the product** (section 3): the LLM components inside the engine (message writer, Ask AI, digest, campaign suggestions, anomaly explainer, playbook tuner). These call the Anthropic API from engine code.

**Status (2026-11-04):** the 10 subagents (section 2.1) and 10 skills (section 2.2) are created in `.claude/agents/` and `.claude/skills/`, expanded from the drafts below; the files are the source of truth from now on. `.mcp.json` and `.claude/settings.json` (section 1) are **not** created yet: MCP package versions and tool names must be verified at milestone M0.2 first.

---

## 1. MCP servers and permissions (development)

### 1.1 Servers

| Server | Purpose | Package (verify and pin at M0.2) | Scope |
|---|---|---|---|
| `firebase` | Read/seed Firestore config docs, inspect collections, check Auth users, read Remote Config | Firebase CLI MCP server: `npx -y firebase-tools@<pinned> mcp` | Dev project `hireme-engage-dev` only (set via `firebase use` / `--dir`) |
| `bigquery` | Explore datasets, run validation and analysis SQL, check table schemas | Google MCP Toolbox for Databases, prebuilt BigQuery config: `npx -y @toolbox-sdk/server@<pinned> --prebuilt bigquery --stdio` | Dev project, `asia-south1` |

Draft `.mcp.json`:

```json
{
  "mcpServers": {
    "firebase": {
      "command": "npx",
      "args": ["-y", "firebase-tools@<pinned-version>", "mcp", "--dir", "."],
      "env": {}
    },
    "bigquery": {
      "command": "npx",
      "args": ["-y", "@toolbox-sdk/server@<pinned-version>", "--prebuilt", "bigquery", "--stdio"],
      "env": {
        "BIGQUERY_PROJECT": "hireme-engage-dev",
        "BIGQUERY_LOCATION": "asia-south1"
      }
    }
  }
}
```

Authentication uses the developer's Application Default Credentials (`gcloud auth application-default login`) scoped to the dev project; never a production service account key. Tool names below follow the current published tool sets (`firestore_get_documents`, `firestore_list_collections`, `firestore_query_collection`, `firestore_delete_document`, …; BigQuery `list_dataset_ids`, `list_table_ids`, `get_table_info`, `execute_sql`). At M0.2 we run `/mcp`, record the actual tool list in `docs/reference/mcp_tools.md`, and adjust permissions and agent `tools:` lists.

### 1.2 Permissions (`.claude/settings.json`, draft)

Principles: reads are free, writes ask, destructive operations and production are denied, package installs are denied (use the existing `.venv`).

```json
{
  "permissions": {
    "allow": [
      "Read", "Grep", "Glob",
      "mcp__firebase__firebase_get_project",
      "mcp__firebase__firestore_list_collections",
      "mcp__firebase__firestore_get_documents",
      "mcp__firebase__firestore_query_collection",
      "mcp__bigquery__list_dataset_ids",
      "mcp__bigquery__list_table_ids",
      "mcp__bigquery__get_table_info",
      "Bash(.venv/bin/python -m pytest:*)",
      "Bash(.venv/bin/python -m sim.validate:*)",
      "Bash(.venv/bin/python -m engage.tools.validate_contract:*)",
      "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)"
    ],
    "ask": [
      "Edit", "Write",
      "mcp__bigquery__execute_sql",
      "Bash(.venv/bin/python -m sim.generator:*)",
      "Bash(.venv/bin/python -m sim.loaders:*)",
      "Bash(.venv/bin/python -m sim.replayer:*)",
      "Bash(.venv/bin/python -m engage.jobs:*)"
    ],
    "deny": [
      "mcp__firebase__firestore_delete_document",
      "mcp__firebase__messaging_send_message",
      "mcp__firebase__auth_update_user",
      "Bash(pip install:*)", "Bash(.venv/bin/pip install:*)", "Bash(npm install:*)",
      "Bash(gcloud projects delete:*)", "Bash(bq rm:*)", "Bash(firebase firestore:delete:*)",
      "Bash(*hireme-engage-prod*)",
      "Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)"
    ]
  }
}
```

Notes:
- `execute_sql` stays on *ask* because a mistyped query can scan many GB; the `bigquery-analyst` agent always dry-runs first.
- Firestore writes through MCP (if the installed version exposes them) stay on *ask*; bulk writes go through the loaders (D-011).
- Recommended hooks (added with the `update-config` skill at M0.2): (a) `PostToolUse` on `Edit|Write` for paths under `contracts/` or `playbooks/` → run `engage.tools.validate_contract`; (b) `Stop` hook that warns if files under `engage/`, `contracts/` or `sim/` changed in the session but `decision.md` and `flow.md` did not (reminder only, not blocking).

---

## 2. Claude Code subagents and skills (development)

### 2.1 Subagents (`.claude/agents/*.md`)

Model aliases map to the current models: `haiku` → `claude-haiku-5-5`, `sonnet` → `claude-sonnet-5-5`, `opus` → `claude-opus-5-5` (D-032). Fable 5.1 is reserved for architecture work run by a human-driven main session, not delegated agents (cost).

| Agent | Purpose | Triggers when | Tools / MCP | Model |
|---|---|---|---|---|
| `contract-steward` | Guards the data contract: schemas, GA4 mapping, versioning, DATA_MODEL consistency | Any change under `contracts/`, event/param additions, backend questions about the contract | Read, Grep, Glob, Edit, Write, Bash (validators) | sonnet |
| `synthetic-data-engineer` | Personas, generator, loaders, validation checks, simulator scenarios | Changing `sim/`, generating or loading data, data realism questions | Read, Grep, Glob, Edit, Write, Bash; firebase (read), bigquery (read, `execute_sql` ask) | sonnet |
| `bigquery-analyst` | Writes and reviews SQL (features, marts, checks, holdout lift), dry-runs, cost checks, answers data questions | SQL work, report numbers, "how many…" questions in development | Read, Grep, Glob, Edit, Write; bigquery (all read tools + `execute_sql`) | sonnet |
| `firestore-operator` | Inspects and seeds Firestore config (playbooks, templates, settings, budgets), indexes, rules, TTL | Seeding config, debugging engine state for a user/decision | Read, Grep, Glob, Edit; firebase (read + write tools if present) | haiku |
| `playbook-author` | Turns a spec use case (A1-H5) into playbook JSON + templates (en/hi) + scenario test | Adding or changing a playbook | Read, Grep, Glob, Edit, Write, Bash (validators) | sonnet |
| `guardrail-auditor` | Reviews diffs touching decision, guardrails, dispatch, messaging for invariants (budget, caps, consent, quiet hours, holdout integrity, idempotency, LLM never writes prices/codes) | Before merging changes under `engage/decision`, `engage/guardrails`, `engage/dispatch`, `engage/messaging` | Read, Grep, Glob, Bash (tests) | opus |
| `scenario-runner` | Runs simulator scenarios and summarises pass/fail with evidence | After engine changes; before gates | Read, Bash; firebase (read), bigquery (read) | haiku |
| `compliance-reviewer` | DPDP, TRAI DLT, GDPR/TCPA/CAN-SPAM, PII minimisation review of templates, prompts, data flows, logs | New templates/channels, LLM prompt changes, new data fields | Read, Grep, Glob | opus |
| `docs-keeper` | Keeps README, decision.md, flow.md, OPEN_QUESTIONS.md consistent; assigns next D-/OQ- ids | End of any task that changed design or flow | Read, Grep, Glob, Edit | haiku |
| `uplift-modeler` (Phase 2) | Builds training sets, trains/evaluates uplift and churn models, compares policies against ground truth | Phase 2 modelling | Read, Grep, Glob, Edit, Write, Bash; bigquery (read + `execute_sql`) | opus |

Drafts (frontmatter + instructions):

**`.claude/agents/contract-steward.md`**

```markdown
---
name: contract-steward
description: Owns the HireMe engagement data contract (events, GA4 mapping, Firestore/BigQuery schemas, OpenAPI, playbook schema). Use proactively for any change under contracts/ or docs/DATA_MODEL.md, and when someone asks what the backend must send.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---
You maintain the data contract that the HireMe backend will implement.
Rules:
1. docs/DATA_MODEL.md is the human source; contracts/ is the machine source. Keep them identical in names, types, required flags and examples.
2. Apply the versioning policy in DATA_MODEL §2.5: additive = minor, breaking = major. Never make a silent breaking change.
3. Every new param must state type, required/optional, example, client or server origin, and NOW/→WEBHOOK/→GA4/→RIDER-API marker.
4. Respect Firebase limits: names <= 40 chars, <= 25 params per event, string values <= 100 chars; booleans as int in GA4.
5. After edits run: .venv/bin/python -m engage.tools.validate_contract. Report failures, do not hide them.
6. Every design choice gets a decision.md entry (next free D- id) and, if unresolved, an OPEN_QUESTIONS.md entry. Mention both in your report.
Output: list of changed files, version bump, compatibility impact for backend, decision ids added.
```

**`.claude/agents/synthetic-data-engineer.md`**

```markdown
---
name: synthetic-data-engineer
description: Builds and runs the synthetic data generator, loaders and simulator for HireMe (personas, GA4-shaped events, Firestore rider stub, ground truth). Use for any task in sim/ or about dummy data volumes, realism or loading.
tools: Read, Grep, Glob, Edit, Write, Bash, mcp__firebase__firestore_list_collections, mcp__firebase__firestore_query_collection, mcp__firebase__firestore_get_documents, mcp__bigquery__list_table_ids, mcp__bigquery__get_table_info, mcp__bigquery__execute_sql
model: sonnet
---
Follow docs/DUMMY_DATA_PLAN.md exactly (personas, shares, response model, geography, time range).
Rules:
- Only ever target project hireme-engage-dev. Refuse if a command or config mentions a production project.
- Use .venv/bin/python. Never install packages.
- Bulk data goes through sim.loaders (BigQuery load jobs, Firestore BulkWriter). Use MCP only to verify (counts, samples) or to seed small config docs.
- Synthetic PII only: phones +91999001xxxx, emails @example.test.
- Ground truth goes to engage_sim only. Never write truth into datasets the engine reads.
- After any load, run the checks in sql/checks and report each V-check result.
Output: what was generated/loaded (counts, seed, generation_id), check results, anomalies.
```

**`.claude/agents/bigquery-analyst.md`**

```markdown
---
name: bigquery-analyst
description: Writes, reviews and runs BigQuery SQL for HireMe (GA4-shaped events, features, segments, marts, holdout lift). Use for SQL changes and data questions during development.
tools: Read, Grep, Glob, Edit, Write, mcp__bigquery__list_dataset_ids, mcp__bigquery__list_table_ids, mcp__bigquery__get_table_info, mcp__bigquery__execute_sql
model: sonnet
---
- Read docs/DATA_MODEL.md §3 before writing SQL. Use the ga4-sql skill idioms (UNNEST(event_params), _TABLE_SUFFIX pruning, event_uuid dedupe).
- Always filter partitions or _TABLE_SUFFIX; estimate bytes with a dry run first and stop if > 5 GB unless the user agreed.
- Dates and days are IST (Asia/Kolkata). Money is INR.
- Never query engage_sim unless the task is explicitly ground-truth validation.
- For lift numbers report n per arm, rates, lift, 95% CI and whether the minimum sample (400 per arm) is met.
Output: the SQL, bytes scanned, results table, caveats.
```

**`.claude/agents/firestore-operator.md`**

```markdown
---
name: firestore-operator
description: Inspects and seeds HireMe engine configuration and state in Firestore (engage_* collections, hireme_riders stub) through the Firebase MCP server. Use to seed playbooks/templates/settings or to debug a user's timers, decisions and caps.
tools: Read, Grep, Glob, Edit, mcp__firebase__firebase_get_project, mcp__firebase__firestore_list_collections, mcp__firebase__firestore_get_documents, mcp__firebase__firestore_query_collection
model: haiku
---
- Confirm the active project is hireme-engage-dev before anything else; stop otherwise.
- Collection and field names are defined in docs/DATA_MODEL.md §4; do not invent fields.
- Config docs must validate against contracts/playbook.schema.json (playbooks) before seeding.
- Never delete documents. Never print phone_e164, email or push tokens; mask them.
Output: documents read/written with ids, and any schema mismatches found.
```

**`.claude/agents/playbook-author.md`**

```markdown
---
name: playbook-author
description: Converts a spec use case (A1-H5) into a validated playbook JSON, en/hi templates and a simulator scenario test. Use when adding or changing a playbook.
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---
Inputs: playbook id from the spec (docs/reference/spec_extracted.txt §5) and any admin overrides.
Steps:
1. Draft playbooks/<id>.json against contracts/playbook.schema.json; take defaults from DATA_MODEL §5.4 when the playbook is listed there.
2. Classify message_class (transactional | service | marketing) per D-023; set exclusive_group and priority per D-064.
3. Write templates/<id>_<channel>_<lang>.yaml with only approved variables; prices and codes are placeholders, never literal numbers. SMS needs dlt fields (placeholder ids until registered).
4. Add a scenario in sim/scenarios and an assertion in tests/scenario.
5. Run the validators and the scenario at tiny scale.
Output: files, validation results, open questions (append to OPEN_QUESTIONS.md if business input is needed).
```

**`.claude/agents/guardrail-auditor.md`**

```markdown
---
name: guardrail-auditor
description: Reviews code changes in the decision, guardrail, dispatch and messaging paths for violations of HireMe engine invariants. Use proactively before merging such changes.
tools: Read, Grep, Glob, Bash
model: opus
---
Check the diff against these invariants (ARCHITECTURE §7, §10):
- Budget: committed_outstanding + redeemed + new_liability <= limit, enforced inside one Firestore transaction; compensation on failure.
- Frequency caps, cooldowns, quiet hours (IST), consent at decision AND send time, suppression after bad experience.
- Holdout users can never receive the playbook message; holdout assignment happens after user-level eligibility.
- Deterministic ids; one decision = one message per channel ordinal; idempotency keys on every provider call.
- Kill switch checked at decision start and before every provider call.
- LLM output never contains prices or codes; code inserts them; content check before send; deterministic fallback.
- No PII (phone, email, payment, tokens) in logs or LLM prompts.
Run the related unit, property and scenario tests. Report each invariant as PASS/FAIL/NOT AFFECTED with file:line evidence. Do not edit code.
```

**`.claude/agents/scenario-runner.md`**

```markdown
---
name: scenario-runner
description: Runs HireMe simulator scenarios (riya_b1, riya_b2, budget_exhaustion_b2, kill_switch_midflight, ...) and reports pass/fail with evidence. Use after engine changes and before gate reviews.
tools: Read, Bash, mcp__firebase__firestore_query_collection, mcp__firebase__firestore_get_documents, mcp__bigquery__execute_sql
model: haiku
---
Run scenarios with .venv/bin/python -m sim.replayer --mode scenario --name <name> --speed 120 (dev project only), then the matching tests in tests/scenario.
For failures, fetch the decision, timer and message documents involved and quote the guardrail trace.
Output: table of scenario | result | decision ids | notes.
```

**`.claude/agents/compliance-reviewer.md`**

```markdown
---
name: compliance-reviewer
description: Reviews templates, LLM prompts, data fields and flows for DPDP Act 2023, TRAI DLT, GDPR/TCPA/CAN-SPAM and PII minimisation issues. Use for new channels, templates, prompts or personal data fields.
tools: Read, Grep, Glob
model: opus
---
Checklist: consent per channel and purpose; instant unsubscribe; DLT template id + header for every SMS; promotional SMS windows and DND; WhatsApp template-only for business-initiated; unsubscribe link in marketing email; data minimisation for the LLM (pseudonymous id, first name, area names only); retention per collection; data subject rights path; no synthetic data in production and no production data in dev.
Output: findings with severity (blocker/major/minor), file references, and suggested fixes. Do not edit files.
```

**`.claude/agents/docs-keeper.md`**

```markdown
---
name: docs-keeper
description: Keeps decision.md, flow.md, README.md and docs/OPEN_QUESTIONS.md consistent with the current design. Use at the end of any task that changed design decisions or the runtime flow.
tools: Read, Grep, Glob, Edit
model: haiku
---
- New design decision → append to decision.md with the next D- id and the standard fields (date, title, context, options, decision, consequences, status, decided by). Never renumber.
- Flow change → update flow.md (current flow section) and its mermaid diagram; keep the "Future flow" section separate.
- Unresolved business question → OPEN_QUESTIONS.md with next OQ- id and the decision id holding our default.
- Check cross-references (D-xxx, OQ-xx, file links) resolve.
Output: list of edits and any inconsistencies found.
```

**`.claude/agents/uplift-modeler.md`** (Phase 2)

```markdown
---
name: uplift-modeler
description: Builds training sets, trains and evaluates uplift (p0/p1) and churn models for HireMe, and compares policies against synthetic ground truth. Use in Phase 2 modelling tasks.
tools: Read, Grep, Glob, Edit, Write, Bash, mcp__bigquery__get_table_info, mcp__bigquery__execute_sql
model: opus
---
- Features as of the day before the decision (no leakage); time-based splits only.
- Train only on holdout/treatment/exploration rows from engage_ops; engage_sim is for evaluation only and must never be a feature.
- Report Qini/AUUC, calibration, Spearman vs true uplift, and the policy simulation result (incremental rides per INR) vs heuristic_v1.
- Export to ONNX, register in engage_ml.model_registry as candidate; never promote to active (humans do).
```

### 2.2 Skills (`.claude/skills/<name>/SKILL.md`)

| Skill | Purpose | Triggers | Tools / MCP | Model note |
|---|---|---|---|---|
| `log-decision` | Append an ADR entry to `decision.md` with the next id | "record this decision", any design choice made in a session | Read, Edit | any |
| `update-flow` | Update `flow.md` current flow + diagram after a flow change | flow changes (sources, steps, adapters, jobs) | Read, Edit | any |
| `generate-dummy-data` | Run the generator with a scale/seed and produce a generation report | "generate data", new persona config | Bash (.venv), Read | sonnet |
| `load-bigquery` | Create DDL, load generated NDJSON into GA4-shaped shards and stubs, run checks | after generation | Bash, bigquery MCP | sonnet |
| `seed-firestore` | Seed settings, playbooks, templates, budgets, segments into Firestore via MCP and read back | after config changes | firebase MCP, Read | haiku |
| `run-scenario` | Run one or all simulator scenarios and summarise | after engine changes | Bash, firebase/bigquery MCP | haiku |
| `holdout-report` | Compute lift vs holdout for a playbook/city/period with CI and ROI; optionally compare with ground truth | "did B2 work?", gate evidence | bigquery MCP | sonnet |
| `new-playbook` | Scaffold playbook JSON, templates, scenario from a spec id | "add playbook X" | Read, Write, Bash | sonnet |
| `validate-contract` | Validate events/playbooks/OpenAPI against `contracts/` | contract edits, before handoff | Bash | any |
| `ga4-sql` | Reference: idioms for querying GA4-shaped tables (UNNEST params, `_TABLE_SUFFIX`, intraday union, dedupe, IST dates) | any SQL on `analytics_*` | none (knowledge) | any |

Drafts:

**`.claude/skills/log-decision/SKILL.md`**

```markdown
---
name: log-decision
description: Append a new architecture/design decision to decision.md in this repo using the project ADR format. Use whenever a design choice is made or changed, even small ones.
---
1. Read decision.md; find the highest D-### id; the new id is +1 (never reuse or renumber).
2. Append:
   ## D-### <title>
   - Date: <today, YYYY-MM-DD>
   - Status: Proposed — pending client review (or Accepted / Superseded by D-### when told)
   - Decided by: <who>
   - Context: <why a decision is needed; cite spec section / constraint>
   - Options considered: <2-4 options, one line each>
   - Decision: <what we chose>
   - Consequences: <trade-offs, follow-ups, what changes later>
3. If it supersedes an older decision, edit only the old entry's Status line to "Superseded by D-###".
4. If business input is still needed, add an OPEN_QUESTIONS.md entry referencing the D- id.
```

**`.claude/skills/update-flow/SKILL.md`**

```markdown
---
name: update-flow
description: Update flow.md whenever the runtime flow of the project changes (data sources, steps, adapters, jobs, mocks, reporting). Keeps the current-flow section and mermaid sequence accurate.
---
1. Read flow.md and the change made in this session.
2. Edit the numbered "Current flow" steps and the mermaid sequence so they describe what runs today, not what is planned.
3. Planned changes go only in "Future flow (after backend handoff)".
4. Update the "Last updated" line with today's date and a one-line summary of the change.
5. If the change reflects a design decision, also run the log-decision skill.
```

**`.claude/skills/generate-dummy-data/SKILL.md`**

```markdown
---
name: generate-dummy-data
description: Generate HireMe synthetic history (personas, GA4-shaped events, rider stub, ground truth) with a given scale and seed. Use when data must be (re)generated.
---
Preconditions: project hireme-engage-dev; .venv exists; sim/personas.yaml reviewed.
Run: .venv/bin/python -m sim.generator --scale <tiny|small|medium> --seed <int> --out data/gen/<date>/
Then report: generation_id, riders by persona and city, events by name, date range, file sizes.
Do not load anything; loading is the load-bigquery and seed-firestore skills.
```

**`.claude/skills/load-bigquery/SKILL.md`**

```markdown
---
name: load-bigquery
description: Load generated HireMe data into BigQuery (GA4-shaped events_YYYYMMDD shards, hireme_ref, hireme_backend_stub, engage_sim) and run validation checks.
---
1. .venv/bin/python -m sim.loaders.bq_ddl --project hireme-engage-dev
2. .venv/bin/python -m sim.loaders.bq_load --what ref,events,stubs,truth --dir <generation dir>
3. Run every file in sql/checks via the BigQuery MCP execute_sql tool (dry run first) and report V1-V14 status.
4. Stop and report on the first failed check; do not "fix" data by hand.
```

**`.claude/skills/seed-firestore/SKILL.md`**

```markdown
---
name: seed-firestore
description: Seed or refresh HireMe engine configuration documents (engage_settings, engage_playbooks + versions, engage_templates, engage_budgets, engage_segments) in Firestore via the Firebase MCP server, then read them back.
---
1. Verify the Firebase project is hireme-engage-dev.
2. Validate playbooks/*.json against contracts/playbook.schema.json and templates/*.yaml against the template schema.
3. Write each document with the Firebase MCP write tool if available; otherwise run .venv/bin/python -m sim.loaders.fs_config.
4. Read every document back with firestore_get_documents and diff against the source files.
Report: documents written, diffs (should be none), validation errors.
```

**`.claude/skills/run-scenario/SKILL.md`**

```markdown
---
name: run-scenario
description: Run HireMe simulator scenarios end to end (inject events on the virtual clock, let the engine act on mocks, assert outcomes). Use after engine changes or for demos.
---
Usage: run-scenario <name|all>. Names are listed in docs/DUMMY_DATA_PLAN.md §9.
Run .venv/bin/python -m sim.replayer --mode scenario --name <name> --speed 120, then .venv/bin/python -m pytest tests/scenario -k <name>.
Summarise: scenario, expected behaviour, observed decisions (ids, status, reason_code), pass/fail.
```

**`.claude/skills/holdout-report/SKILL.md`**

```markdown
---
name: holdout-report
description: Compute incremental lift vs holdout for a HireMe playbook (or campaign) by city and period, with 95% CI, incremental rides, promo cost and ROI; optionally compare with synthetic ground truth.
---
Inputs: playbook_id, city_id, from, to (IST), compare_truth (bool).
Use sql/marts/holdout_lift.sql with parameters (dry run first). Intention-to-treat on assigned arm.
Report n_treat, n_hold, conv rates, lift (pp) with Newcombe 95% CI, incremental rides, incremental fare value, promo cost, ROI, and "insufficient sample" if either arm < 400.
If compare_truth: compute true lift from engage_sim.response_ledger for the same decisions and state whether it lies inside the CI.
```

**`.claude/skills/new-playbook/SKILL.md`**

```markdown
---
name: new-playbook
description: Scaffold a new HireMe playbook from a spec use-case id (A1-H5): playbook JSON, en/hi templates, scenario and test, then validate.
---
Delegate the work to the playbook-author agent with the use-case id and any overrides. Afterwards run validate-contract and run-scenario for the new scenario. Log any non-default choice with log-decision.
```

**`.claude/skills/validate-contract/SKILL.md`**

```markdown
---
name: validate-contract
description: Validate HireMe contract artefacts (event schemas, examples in docs, playbooks, templates, OpenAPI) and report problems.
---
Run .venv/bin/python -m engage.tools.validate_contract --all. It checks: JSON Schemas compile; DATA_MODEL examples validate; every playbook validates and references existing templates/events; OpenAPI files lint; GA4 round-trip on fixtures.
Report each failure with file and path. Do not change schemas to make tests pass without the contract-steward agent.
```

**`.claude/skills/ga4-sql/SKILL.md`**

```markdown
---
name: ga4-sql
description: Reference idioms for querying GA4-export-shaped BigQuery tables (analytics_* events_YYYYMMDD / events_intraday_YYYYMMDD) in this project. Load before writing SQL against raw events.
---
- Param access: (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'step'); ints in int_value (booleans are 0/1); doubles in double_value.
- Prune shards: WHERE _TABLE_SUFFIX BETWEEN '20261001' AND '20261031' (intraday tables have suffix 'intraday_YYYYMMDD').
- Union daily + intraday via events_* and dedupe: QUALIFY ROW_NUMBER() OVER (PARTITION BY event_uuid ORDER BY _TABLE_SUFFIX) = 1.
- Time: TIMESTAMP_MICROS(event_timestamp); IST day = event_date (property TZ is Asia/Kolkata) or DATE(ts, 'Asia/Kolkata').
- Prefer engage_features.v_events_flat for downstream work.
- Never select user_id-level rows into answers for humans; aggregate with k >= 20.
```

---

## 3. Runtime AI agents in the product

All runtime agents share these rules (spec 6.1 step 6, 9; D-032-D-035):

| Rule | Implementation |
|---|---|
| LLM never writes prices, discounts or codes | Prompts and outputs use placeholders (`{promo_code}`, `{fare}`, `{discount_label}`, `{expiry}`); code substitutes values after the LLM; content check rejects digits/currency outside placeholders |
| PII minimisation | Inputs: pseudonymous `user_id` (only where needed), `first_name`, `language`, area names, playbook intent. Never phone, email, tokens, payment data, exact addresses |
| Structured outputs | `output_config.format` JSON Schema on every call; forced `tool_choice` is not used (not supported on current Opus/Sonnet; `auto` + instructions + `strict: true` tools) |
| Refusals and errors | Always check `stop_reason`; Sonnet/Opus calls enable the server-side refusal fallback (`fallbacks: "default"`); any failure → deterministic fallback (template text, rule-based digest, "could not answer") |
| Caching | Stable system prompt + tool definitions + template catalogue first, with prompt caching; per-request data last |
| Observability | Log model, tokens, latency, cache hit, fallback reason in `engage_ops.messages` / `engage_ask_sessions`; never log prompts containing first names beyond 30 days |
| Kill switch | `settings.llm.enabled` and the global kill switch disable all LLM calls instantly (fallbacks take over) |
| Data access | Agents never use raw MCP access in production. Their tools are engine-implemented wrappers over BigQuery (`engage_views` only) and Firestore (read-only config). The Firebase MCP server may back the Firestore-read tool in Phase 2 if it is hosted inside the client project (D-010) |

Model price/latency tiers (Anthropic first-party rates, per million tokens input/output): Haiku 5.5 $0.10/$0.50; Sonnet 5.5 $2/$10; Opus 5.5 $4/$20; Fable 5.1 $10/$50 (not used at runtime).

### 3.1 Agent catalogue

| Agent | Use case | Phase | Model (effort) | Mode | Latency budget |
|---|---|---|---|---|---|
| R1 Message writer | Spec 6.1 step 6 | 2 | `claude-haiku-5-5` (low) | Per message (push, email, in-app only) | 1.5 s p95, 2 s timeout |
| R2 Content policy reviewer | Spec 9 content check (semantic part) | 2 | `claude-haiku-5-5` (medium) | Offline, on template/variant creation | n/a |
| R3 Ask AI | H4 | 2 | `claude-sonnet-5-5` (medium) | Interactive, tool use | 20 s p95 |
| R4 Insight digest | H1 | 2 | `claude-sonnet-5-5` (medium) | Daily batch (Message Batches API) | by 09:00 IST |
| R5 Campaign suggester | H3 | 2 | `claude-opus-5-5` (high) | Weekly + on demand | minutes |
| R6 Anomaly explainer | H2 | 2 | `claude-haiku-5-5` (low) | On detected anomaly | 10 s |
| R7 Playbook tuner | Autonomy level 3 | 3 | `claude-opus-5-5` (high) | Weekly | minutes |

### 3.2 R1 Message writer

| Item | Spec |
|---|---|
| Inputs | Approved template (title, body, variables, channel limits), language, `first_name`, `drop_area`, playbook intent (e.g. "abandoned booking recovery"), time of day bucket, offer *label placeholder* (not value), tone setting, up to 3 approved style variants |
| Tools | none |
| Guardrails | Output must keep every required placeholder exactly once, add no new placeholders, contain no digits or currency symbols outside placeholders, stay within length (push title 50, body 150 chars; email subject 70), be in the requested language (script check), avoid banned phrases (`contracts/content_policy.yaml`: "guaranteed", "free" unless type free_ride, urgency claims beyond validity). Any failure → deterministic template, reason `content_check_fallback`. SMS and WhatsApp never use R1 (D-033) |
| Output schema | below |

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["title", "body", "language", "placeholders_used"],
  "properties": {
    "title": { "type": "string", "maxLength": 80 },
    "body": { "type": "string", "maxLength": 300 },
    "language": { "type": "string", "enum": ["en", "hi", "ar"] },
    "placeholders_used": { "type": "array", "items": { "type": "string", "enum": ["first_name", "drop_area", "fare", "promo_code", "expiry", "discount_label", "validity_minutes"] } },
    "style_note": { "type": "string", "maxLength": 120 }
  }
}
```

Example output: `{"title": "{first_name}, still heading to {drop_area}?", "body": "Book in the next {validity_minutes} min and save {discount_label} with code {promo_code}.", "language": "en", "placeholders_used": ["first_name","drop_area","validity_minutes","discount_label","promo_code"]}` → code fills `Riya`, `Connaught Place`, `30`, `15%`, `GO15-7KQ2`.

### 3.3 R2 Content policy reviewer

Inputs: new template or LLM variant set, playbook, channel, market policy pack. Output: `{verdict: "approve"|"revise"|"reject", issues: [{type: "claim"|"tone"|"pii"|"regulatory"|"language", text, suggestion}]}`. It only advises the human approver; it never approves on its own.

### 3.4 R3 Ask AI (H4)

| Item | Spec |
|---|---|
| Inputs | Question, admin role + `city_ids`, session history (last 5 turns), catalogue of `engage_views` with column descriptions (cached) |
| Tools | `list_views()`, `describe_view(name)`, `run_sql(sql)` (single SELECT over `engage_views`, auto city filter for city_admin, dry run ≤ 2 GB, 10 k row cap, k ≥ 20 suppression), `get_playbook(playbook_id)` (Firestore read), `segment_preview(definition)` (counts only), `draft_campaign(spec)` (returns a draft; predictions computed by code) |
| Guardrails | Max 8 tool calls; every number in the answer must match a tool result (post-check); no user-level data; answers cite views and SQL; questions outside scope get a polite refusal |
| Output schema | `{answer: string, numbers: [{value: number, unit: string, source_call_id: string}], evidence: [{view, sql, bytes_processed}], campaign_draft: object|null, confidence: "high"|"medium"|"low", follow_ups: [string]}` |

### 3.5 R4 Insight digest (H1)

Inputs: metrics JSON computed by SQL for yesterday vs trailing 7-day and same weekday last week, per city: funnel, abandonment by hour/zone, playbook performance with lift CI, budget pacing, alerts. Tools: none (data is precomputed). Output: `{date, city_id, headline, bullets: [{text, metric_refs: [string]}], watch_items: [string], suggested_actions: [{kind: "review_playbook"|"campaign_idea"|"budget", ref, text}]}`; numbers verified against input; delivered by email and in the console at 09:00 IST (spec H1 example: "Yesterday: 1,240 fare checks, 38% converted; abandonment rose 6% in Noida after 8 pm").

### 3.6 R5 Campaign suggester (H3)

Inputs: segments with poor conversion (e.g. "820 riders checked airport fares and did not book"), playbook catalogue, remaining budgets, allowed ladders, recent experiment results. Tools: `segment_preview`, `estimate_campaign` (code computes reach, cost, predicted incremental rides with CI using the active scorer), `list_recent_campaigns`. Guardrails: offers only from allowed ladders; draft only; at most 3 drafts per week per city. Output: `{drafts: [{name, rationale, segment, channels, template_suggestion (placeholders only), offer: {type, rung}, schedule, estimate_ref}]}` → `engage_approvals` kind `campaign`.

### 3.7 R6 Anomaly explainer (H2)

Detection is statistical code (seasonal baseline per city × hour, robust z-score > 4 or ratio > 3×, minimum volume); the LLM only explains. Inputs: anomaly record + top breakdowns (payment method, gateway error codes, zone, app version, platform). Output: `{title, severity: "info"|"warning"|"critical", explanation, likely_causes: [string], suggested_checks: [string]}` (spec example: "Payment failures up 4x in the last hour, mostly UPI. Check gateway."). Fallback: rule-based template text.

### 3.8 R7 Playbook tuner (Phase 3, autonomy level 3)

Inputs: per-playbook experiment history (lift by rung, by wait time, by channel), current config, guardrail limits. Output: JSON merge patch on the playbook with rationale and expected effect; applied only as a new version with a capped trial budget and holdout, and reported in the daily digest; humans can roll back with one click.
