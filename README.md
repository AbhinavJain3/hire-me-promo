# HireMe AI Engagement Engine

The engine reads rider behaviour (Firebase Analytics events and user properties), decides who needs a nudge (rules plus AI uplift scoring), creates promo codes through the HireMe Promo API, sends them by push, SMS, email or WhatsApp, enforces guardrails in code (budgets, frequency caps, quiet hours, consent, cooldowns, holdouts, fraud), and reports incremental lift against a holdout group.

**Status (2026-11-04):** plan pending client review. Phase 0 has started: the data contract v1.0.0-rc1 is in [contracts/](contracts/README.md) (milestone M0.1). No engine runtime yet.

**Constraint that shapes this plan:** today the only data sources are the Firebase project (via the Firebase MCP server) and BigQuery. There is no HireMe backend webhook, no Rider DB API, and no Promo or messaging APIs we can reach. We first define the data contract, generate realistic synthetic data into Firebase and BigQuery, and prove the engine end to end on mocks. After that, the HireMe backend is changed to emit data in our format.

## Documents

| Document | What it contains |
|---|---|
| [contracts/](contracts/README.md) | **Machine-readable data contract** (v1.0.0-rc1): event catalogue and generated schemas, OpenAPI for ingest, Rider API and Promo API, playbook and template schemas, BigQuery DDL, Firestore indexes and rules, and the validator. Wins over the docs on any conflict |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, diagrams, one event end to end (now and after the webhook), trigger engine, decision pipeline, guardrails, autonomy, learning loop, reliability, security and compliance, deployment, tech stack, repo layout |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | The data contract: event and user-property schemas, BigQuery DDL (GA4-shaped raw events, features, ops, ML, marts), Firestore collections and indexes, mapping to the spec's core tables, playbook JSON schema and the B2 example |
| [docs/API.md](docs/API.md) | Admin APIs (spec 8.4 and additions), roles, errors, pagination, idempotency; future backend webhook; Rider Profile API the backend must provide; Promo API, FCM, SMS, email and WhatsApp adapters with mock behaviour |
| [docs/DUMMY_DATA_PLAN.md](docs/DUMMY_DATA_PLAN.md) | Personas, volumes, geography, ground-truth uplift model, loading into BigQuery and Firebase, live simulator and scripted scenarios, validation checks |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phases, milestones, acceptance criteria, gates, the 12 MVP playbooks, backend handoff track, testing strategy, risks |
| [docs/AGENTS_AND_SKILLS.md](docs/AGENTS_AND_SKILLS.md) | Claude Code subagents, skills, MCP servers and permissions for development; runtime AI agents in the product |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | Questions for HireMe/Grepix, each with our default assumption and what it blocks |
| [decision.md](decision.md) | ADR log of every design decision (D-001 to D-077) |
| [flow.md](flow.md) | How the project works right now, step by step, plus the future flow after backend handoff |
| [CLAUDE.md](CLAUDE.md) | Instructions for future Claude Code sessions |
| `docs/reference/`, `docs/client/` | Source spec (extracted text, diagrams) and the client Word document. **Kept locally only, not in this public repository** (client material); ask the project owner for access |

## How to review this plan

1. **Spec context (10 min):** skim `docs/reference/spec_extracted.txt` sections 1, 4 and 6, and the two diagrams.
2. **[flow.md](flow.md) (5 min):** what will actually run now, without the backend.
3. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §1 and §4 (15 min):** what we changed from the spec and why; one event end to end.
4. **[docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) P1 rows (10 min):** answers here unblock Phase 0.
5. **[decision.md](decision.md) index (10 min):** read in full the entries you disagree with. Highest impact: D-001, D-002, D-003, D-006, D-009, D-018, D-020, D-028, D-030, D-036.
6. **[contracts/README.md](contracts/README.md) and `contracts/events/v1/generated/EVENTS.md` (backend and app teams):** the event contract you will implement; background in [docs/DATA_MODEL.md](docs/DATA_MODEL.md) §2.
7. **[docs/API.md](docs/API.md) §4-§6 (backend team):** webhook, Rider Profile API, Promo API changes.
8. **[docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md):** timeline, gates, backend handoff track.
9. **[docs/DUMMY_DATA_PLAN.md](docs/DUMMY_DATA_PLAN.md):** how uplift will be proven before real riders are involved.
10. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §6-§11 and [docs/AGENTS_AND_SKILLS.md](docs/AGENTS_AND_SKILLS.md):** detail for engineers.

## Conventions

Time zone Asia/Kolkata (IST) for all business logic, UTC for storage; currency INR; pilot city Noida (`city_id` 3). Names (collections, tables, events, playbook ids such as `B2_abandoned_booking`) are identical across all documents.
