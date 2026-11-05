# HireMe AI Engagement Engine: Implementation Plan

| | |
|---|---|
| Status | Proposed, pending client review |
| Date | 2026-11-02 |
| Author | AI (Fable 5.1) |
| Spec | Section 11 rollout (16 weeks, 4 phases, 3 gates) |
| Related | [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md), [DUMMY_DATA_PLAN.md](DUMMY_DATA_PLAN.md), [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) |

## 1. Re-sequencing the spec rollout

The spec's Phase 0 ("finalise event names, dual log to backend, enable BigQuery export, map the promo API") assumes the backend and the real Firebase project are available. They are not. Our Phase 0 instead produces the **data contract, the synthetic data, the simulator and the mock adapters**, so Phases 1 and 2 can be built and *proven* without the backend. The backend work moves into a parallel **Backend Handoff track** that starts when the contract freezes.

| Spec phase (weeks) | Spec content | Our phase (weeks, dates) | Our content | Spec gate → our gate |
|---|---|---|---|---|
| — | — | Week 0 (2-6 Nov 2026) | Plan review, answers to blocking open questions | Plan approved |
| Phase 0 Foundations (1-2) | Event names, dual log, BQ export, promo API mapping | **Phase 0 Foundations (W1-W3, 9-27 Nov)** | Data contract v1.0, dev project, DDL, generator, loaders, simulator, mocks, engine skeleton | "Events verified" → **G0 Contract and synthetic data verified** |
| Phase 1 Rules MVP (3-6) | 12 core playbooks, push/SMS/email, console v1, suggest-only | **Phase 1 Rules MVP (W4-W7, 30 Nov-25 Dec)** | 12 playbooks, guardrails, mocks for push/SMS/email, console v1, autonomy 0→1→2 on the simulator, holdout reporting | "Pilot city live" → **G1 Simulated Noida pilot live** (+ real pilot readiness depends on track HB) |
| Phase 2 AI layer (7-10) | Uplift & churn models, LLM writing, Ask AI & digests, auto within budget | **Phase 2 AI layer (W8-W11, 28 Dec-22 Jan)** | Uplift and churn models, LLM writer, Ask AI, digest, anomaly, campaign suggestions | "Uplift beats holdout" → **G2 Uplift beats holdout (synthetic) and beats rules policy** |
| Phase 3 Scale (11-16) | All 45 playbooks, driver nudges, WhatsApp, white label | **Phase 3 Real pilot and scale (W12-W16, 25 Jan-26 Feb 2027)** | Real Noida pilot on backend data, remaining playbooks, WhatsApp, driver nudges design, white label | **G3 Real pilot uplift beats holdout** |
| — | — | **Track HB Backend handoff (W4-W11, parallel)** | Backend implements contract, webhook, Rider API, Promo API changes; conformance tests; shadow mode | **HB gates** (§5) |

Calendar risk: W7-W9 include Christmas and New Year; Phase 1 exit and HB2 avoid depending on client availability in that window (R-10).

## 2. Phase 0 Foundations (W1-W3)

**Progress (2026-11-04):** M0.1 delivered as release candidate 1.0.0-rc1 in `contracts/` (validator green, 71 contract tests). The client review meeting, which is part of M0.1's acceptance, is still open. Changes from the drafts: `contracts/CHANGELOG.md`, D-067 to D-077.

| ID | Milestone | Tasks | Acceptance criteria | Owner |
|---|---|---|---|---|
| M0.1 | **Data contract v1.0-rc** | JSON Schemas for envelope and all 27 events (`contracts/events/v1`); GA4 mapping spec; user properties; playbook schema; OpenAPI drafts (admin, ingest, rider, promo); review with HireMe app/backend leads | Schemas validate all examples in DATA_MODEL; client review meeting held; open contract questions logged (OQ-07, OQ-11, OQ-12) | Architect + contract-steward agent |
| M0.2 | **Dev environment** | Dev Firebase/GCP project `hireme-engage-dev` (Blaze, asia-south1); Firestore Native; BigQuery datasets (DATA_MODEL §3); IAM service accounts; Firestore indexes, rules, TTL; `.mcp.json` with Firebase + BigQuery MCP servers verified (tool list recorded); repo skeleton per ARCHITECTURE §14; CI (lint, type check, unit tests, schema validation) | All datasets/collections exist; MCP servers answer a read query each; CI green on skeleton; `decision.md` entries for any deviations | Dev |
| M0.3 | **Generator and loaders** | `sim/generator` with personas, geography, organic process, GA4 mapping; loaders for BigQuery and Firestore; ground truth; `sql/checks` V1-V10, V13-V14 | `medium` history loaded; all checks pass; generation reproducible with seed; load runbook documented | synthetic-data-engineer |
| M0.4 | **Mocks** | `engage-mocks`: Promo API (create, usage, deactivate, apply/redeem, webhook), FCM v1, SMS (DLT validation), email, fault injection API | Contract tests: requests/responses match OpenAPI; fault modes work; redemption webhook reaches a stub endpoint | Dev |
| M0.5 | **Engine skeleton + simulator live mode** | `engage/core` (config, virtual clock, ids), Event Inbox writer/consumer, `SimulatorDirect`, `Ga4BigQueryPoll` (read path), log shipper, `sim/replayer` with virtual clock, `sim/responder` stub; feature job v1 (`user_features_daily`, segments, base rates); profile sync | Simulator at 60× writes events; consumer lag p95 < 2 s; poller reads intraday rows and dedupes against inbox; features computed for backfill window; profile docs in Firestore | Dev |

**Gate G0 – Contract and synthetic data verified** (end of W3, target 27 Nov): (1) contract v1.0 frozen (any later change follows the versioning policy); (2) validation checks V1-V10, V13, V14 green on `medium`; (3) one simulated day runs end to end through the inbox with no engine decisions yet; (4) mocks pass contract tests; (5) client signs off the contract (starts track HB).

## 3. Phase 1 Rules MVP (W4-W7)

### 3.1 The 12 core playbooks (D-036)

| # | Playbook | Why it is in the MVP |
|---|---|---|
| 1 | `B2_abandoned_booking` | Spec flagship example (section 4 and 7); highest intent; client named it |
| 2 | `B1_fare_check_no_booking` | Riya's story (spec 1); largest trigger volume; tests price-sensitivity gating |
| 3 | `B3_abandoned_payment_step` | Shares B2's trigger; tests `where` filters and exclusive groups; no promo cost |
| 4 | `B5_no_driver_found` | Service recovery with a small flat credit; tests flat codes |
| 5 | `B8_payment_failed` | Transactional class; tests cap and quiet-hours exemption; direct revenue recovery |
| 6 | `A2_welcome_offer` | Activation goal (spec 1 metric); tests first-ride-only codes and fraud blocks |
| 7 | `A3_no_first_ride_48h` | Long timer (48 h) with `cancel_if`; reuses A2's code (no new spend) |
| 8 | `C2_pickup_reminder` | `relative_time` triggers, per-ride timers, cancellation by `ride_id`, transactional at 04:30 |
| 9 | `D2_bad_experience` | Client named it; tests 48 h marketing suppression across playbooks |
| 10 | `E2_lapsing_7_14d` | Retention goal; batch (scheduled) path; light offer |
| 11 | `E3_lapsed_30d` | Stronger offer ladder; email + SMS; cohort-batch approvals |
| 12 | `E4_dormant_90d` | Final contact then stop-marketing flag; email only |

Not in the MVP, and why:

| Playbook(s) | Reason | When |
|---|---|---|
| A1 | Pre-login identity (no `user_id` at `sign_up_started`; OQ-11) | Phase 3 if backend can resolve app-instance push tokens |
| A4, A5, D1, D5, C1, C4 | Low risk/low value nudges, no promo; easy adds once the pipeline exists | Phase 3 (first batch) |
| A6, D3, D4, D6 | Need backend wallet/referral/tier logic | Phase 3 |
| B4, G1, G2 | Need zone-level surge/supply signals (zone_hour_stats is built in Phase 2) | Phase 3 |
| B6, B7, C3, C5, E1 | Pattern triggers (`window_count`, route repetition) | Phase 3 |
| E5 | Requires churn model | Phase 2 |
| E6 | `app_remove` only via GA4 export (Android) | Phase 3 |
| F1-F6 | External data (weather, calendar, venues, DOB) | Phase 3 (F2 Diwali as a manual campaign demo in Phase 1) |
| G3 | Driver app | Phase 3 design only |
| H1-H4 | LLM layer | Phase 2 |
| H5 | Budget pacing is part of the guardrail service in Phase 1 (alerts + throttling), not a playbook | Phase 1 (as guardrail) |

### 3.2 Milestones

| ID | Milestone | Tasks | Acceptance criteria |
|---|---|---|---|
| M1.1 | **Trigger engine** | Matcher, `event_delay` and `relative_time` timers, `cancel_if` with `match_params`, `on_retrigger`, sweeper with leases, fire-time recheck, late-event policy, batch scheduler for `schedule` triggers | Scenarios `b2_cancelled_by_booking`, `b2_double_abandon`, `b2_late_cancel_event`, `c2_airport_reminder`, `c2_cancelled`, `duplicate_events` pass; 10 k timers/hour at 60× with no missed or double fires |
| M1.2 | **Decision pipeline + guardrails** | Eligibility, holdout hash, exploration, `heuristic_v1` scorer, offer rule and sizing, channel/time selection, reservation transaction, budgets (D/M, scopes), caps, cooldowns, quiet hours, suppression, consent, fraud and discount-trained rules, kill switch, content check (deterministic) | Unit tests for every guardrail; property tests: budget never exceeded under 50 concurrent reservations; scenarios `quiet_hours_b2`, `budget_exhaustion_b2`, `freq_cap`, `kill_switch_midflight`, `consent_revoked_midtimer`, `discount_trained_user`, `holdout_user`, `a2_fraud_repeat_device` pass |
| M1.3 | **Executor, dispatcher, adapters** | Promo adapter (idempotent), outbox, retries/backoff, DLQ, fallback channels, delivery webhooks, tracked links/unsubscribe, deep links; push/SMS/email adapters (mock targets) | Scenarios `promo_api_outage`, `fcm_unregistered` pass; zero duplicate sends or codes under injected faults (1,000-message chaos test) |
| M1.4 | **Outcomes, attribution, reporting** | Outcome tracker, ledger redeem/release, promo-expiry job, `engage_ops` mirror, marts (`playbook_daily`, `holdout_lift`, `channel_daily`, `promo_daily`, `budget_pacing_daily`, `funnel_daily`, `ai_activity_daily`), reconciliation job | Ledger invariants hold nightly; mart numbers reconcile with Firestore counts (±0); V12 ground-truth recovery passes for B2, A2, D2 on a 30-day simulated run |
| M1.5 | **Admin API + console v1** | API (spec 8.4 + budgets, settings, kill switch, decisions explain, simulator controls); console screens: Playbooks, Templates, Budgets, Frequency & quiet hours, AI settings (autonomy), Approval queue, Campaigns (manual), Reports, Audit log, Kill switch, Decision explorer; Firebase Auth roles | RBAC tests for every endpoint × role; a marketing admin can change B2 wait time, see the approval, approve, and observe the new version in decisions; kill switch effective < 5 s |
| M1.6 | **12 playbooks + templates** | Playbook JSON (validated), en + hi templates, DLT placeholders for SMS; dry-run endpoint | All 12 enabled on the simulator in Noida; dry-run predictions within ±20 % of actuals on a replayed week |
| M1.7 | **Simulated pilot** | 30-day simulated Noida pilot (Delhi/Gurgaon as untouched comparison): week 1 at autonomy 0 (shadow), week 2 at 1, weeks 3-4 at 2 | Runbook, dashboards, pilot report generated from marts |

**Gate G1 – Simulated Noida pilot live** (end of W7, target 24 Dec): (1) all scenario tests green; (2) 30-day simulated pilot completed with no guardrail violation (budget, caps, quiet hours, consent, holdout integrity) found by the nightly invariant checks; (3) B2 measured lift has 95 % CI lower bound > 0 and contains the ground-truth lift; (4) console v1 accepted by a client marketing user in a demo; (5) contract conformance kit delivered to backend (HB1 done).

## 4. Phase 2 AI layer (W8-W11)

| ID | Milestone | Tasks | Acceptance criteria |
|---|---|---|---|
| M2.1 | **Uplift models** | Training set builder from `engage_ops` + features (as-of joins); LightGBM T-learner per family (intent: B1/B2; win-back: E2/E3; activation: A2/A3); calibration; ONNX export; registry; shadow scoring | On a time-split test set: Qini coefficient > heuristic's; calibration error < 0.03; ranking Spearman vs ground-truth uplift ≥ 0.5; scoring p95 < 10 ms |
| M2.2 | **Churn model and E5** | `churn_training_examples`, LightGBM, nightly batch scores in features; E5 playbook (`churn_score > 0.7`, cheapest offer that works) | AUC ≥ 0.75 on synthetic; E5 runs in simulator with holdout |
| M2.3 | **Policy comparison** | Run two 30-day simulated pilots with the same seed: rules (`heuristic_v1`) vs `uplift_v1` | `uplift_v1` delivers ≥ 15 % more incremental rides per ₹ of promo spend than rules, with CI excluding 0 |
| M2.4 | **LLM message writer** | Template variants, structured output, content check, fallback, latency budget, prompt caching; push + email only | 0 content-check escapes on a 5,000-message adversarial eval set; fallback rate < 2 %; p95 < 1.5 s; no PII beyond allowed fields in prompts (log audit) |
| M2.5 | **Ask AI (H4)** | `engage_views`, SQL tool with guardrails, city scoping, answer verification, to-campaign | 50-question eval set: ≥ 90 % numerically correct, 0 PII leaks, 0 queries outside `engage_views` |
| M2.6 | **Digest (H1), anomaly (H2), campaign suggestions (H3), pacing narrative (H5)** | Jobs + agents + alert channels (email now; WhatsApp in Phase 3) | Injected anomalies (payment failures ×4, bookings −40 %) detected within 30 min with correct explanation in ≥ 8/10 cases; H3 drafts land in approval queue with code-computed predictions |
| M2.7 | **Best-time sending and fallback on unopened** | `open_hour_hist`, `best_time` timing | Open rate +10 % relative vs fixed time in simulation (responder has hour-of-day open propensity) |

**Gate G2 – Uplift beats holdout** (end of W11, target 22 Jan): (1) M2.3 criterion met; (2) every active playbook's lift CI lower bound > 0 or the playbook is auto-paused; (3) LLM evals pass; (4) super admin approves autonomy level 2 for B1/B2/E2 in the dev project; (5) if HB3 shadow data exists, `uplift_v1` scores on real traffic show calibration error < 0.05 against holdout outcomes (otherwise the real pilot starts on `heuristic_v1`).

## 5. Track HB – Backend handoff (parallel, W4-W11)

This is the explicit milestone in which the HireMe backend is moulded to our contract.

| ID | Milestone | HireMe backend/app team must do | Engine team provides | Exit criterion |
|---|---|---|---|---|
| HB1 | **Contract handoff** (W4) | Review and accept contract v1.0; nominate owners | Contract pack: event JSON Schemas, GA4 mapping, OpenAPI for ingest/rider/promo, deep-link spec, example payloads, **conformance test kit** (CLI that validates a sample of events or a webhook endpoint), synthetic sample data | Signed acceptance; implementation plan from HireMe |
| HB2 | **Instrumentation** (W5-W8) | App: emit all events with `event_uuid`/`contract_version`, set user properties, deep-link handling. Backend: server-authoritative events (`ride_booked`, `ride_completed`, `payment_failed`, `promo_redeemed`, `consent_changed`, `ride_scheduled`, `scheduled_ride_cancelled`, `no_driver_found`, `ride_cancelled`, `ride_started`, `wallet_topup`, `support_ticket_opened`, `sign_up`); `POST /engage/v1/events` client with retries; enable Firebase → BigQuery export (daily + streaming) in prod and grant the engine service account read access | Staging endpoint, HMAC keys, conformance runs, help desk | Conformance kit: ≥ 99.5 % of staging events valid; webhook p95 latency < 5 s; event parity Firebase vs webhook ≥ 99 % by `event_uuid` |
| HB3 | **Rider Profile API, consent write-back, Promo API changes** (W6-W9) | Implement API.md §5 and Promo API idempotency + redemption webhook + usage + deactivate | Adapter switch (`RiderDirectory`, `PromoAdapter`), contract tests | Contract tests green against HireMe staging |
| HB4 | **Channels** (W6-W9) | Grepix gateway credentials and contracts for push/SMS/email (and WhatsApp later); DLT registrations (PE id, header, templates for the 12 playbooks in en/hi) | Template list with DLT text, channel adapters | Test sends to internal devices; DLT approvals received (lead time risk R-03) |
| HB5 | **Shadow mode on real traffic** (W10-W11) | Production events flowing to the engine in Noida | Engine in prod project at autonomy 0 (suggest-only; nothing sent to riders) | 2 weeks of shadow: trigger volumes within ±15 % of BigQuery counts; no data-quality alerts open; approval queue reviewed by marketing |

Switching steps (config only, no code change): `ENGAGE_SOURCES=["webhook","ga4_bq_poll"]`, `ENGAGE_BQ_GA4_DATASET=analytics_<real_id>`, `ENGAGE_RIDER_DIRECTORY=hireme_api`, `ENGAGE_PROMO_BASE_URL=…`, channel base URLs, `ENGAGE_CLOCK=real`, and a new production project id. Each switch has its own feature flag so they can be flipped one at a time.

## 6. Phase 3 Real pilot and scale (W12-W16)

| ID | Milestone | Content | Acceptance |
|---|---|---|---|
| M3.1 | **Real Noida pilot** (W12-W14) | 12 playbooks at autonomy 1 (week 12), level 2 for B1/B2/E2 after 2 weeks if lift positive | G3: B2 lift CI lower bound > 0 on real data (expected after ~4-7 weeks, see ARCHITECTURE §9); opt-out rate < 1 %/month; zero guardrail violations |
| M3.2 | **Remaining rider playbooks** | A1 (if OQ-11 resolved), A4, A5, A6, B4, B6, B7, C1, C3, C4, C5, D1, D3-D6, E1, E6, F1-F6, H-series refinements | Each new playbook: JSON validated, scenario test, holdout ≥ 10 % for the first 4 weeks |
| M3.3 | **WhatsApp channel** | WABA templates, adapter, consent | Test sends, template approvals |
| M3.4 | **Driver nudges (G1-G3) design** | Driver event contract (`driver_online`, `driver_offline`, `trip_offer_*`), driver consent, separate budgets | Design approved; implementation is post-W16 |
| M3.5 | **White label** | `brand_id` dimension, per-market policy packs (GDPR, TCPA, CAN-SPAM), languages (ar), time zones | Second brand configurable in dev |
| M3.6 | **Scale hardening** | Sharded ledger counters, Pub/Sub inbox option, `large` load test (100 k riders, 120×) | p95 decision latency < 2 s at 5× pilot load |
| M3.7 | **Expansion** | Delhi, Gurgaon | City-level gates as G3 |

## 7. Testing strategy

| Layer | What | Tooling | When |
|---|---|---|---|
| Contract | Every event (generated, simulated, webhook) validated against `contracts/events/v1`; OpenAPI request/response validation for API and mocks; GA4 round-trip | jsonschema, schemathesis-style tests | CI on every PR |
| Unit | Pure logic: matcher, offer rule, sizing, holdout hash, cap arithmetic, quiet hours (IST edges, midnight, DST-free), id derivation | pytest | CI |
| Property | Invariants: budget never exceeded; one message per decision ordinal; holdout users never messaged; caps never exceeded; idempotency under retries | Hypothesis (added to dev requirements in M0.2) | CI |
| Integration | Firestore transactions, listeners, TTL fields, indexes | Firestore emulator | CI |
| SQL | Feature, segment, mart SQL on fixture data with expected outputs | `engage_test_*` datasets, dry runs | CI nightly (cost-capped) |
| Scenario | All scripted scenarios in DUMMY_DATA_PLAN §9 | simulator `--mode scenario` + assertions | CI (tiny scale) + nightly |
| Statistical acceptance | Ground-truth recovery (V12), policy comparison (M2.3), model metrics | simulator `medium`, 30-day runs | Gate evidence |
| Chaos | Mock fault injection (promo outage, FCM 503, SMS DLT reject, worker kill mid-transaction) | mocks fault API | Weekly |
| LLM evals | Content check escapes, numeric hallucination, tone, language, PII in prompts; Ask AI correctness | eval sets in `tests/evals/` | Before enabling any LLM feature, and on every prompt/model change |
| Security | RBAC matrix, HMAC verification, PII masking in logs, IAM (no engine access to `engage_sim`) | pytest + IAM checks | CI + pre-gate |
| Load | `large` scale at 120× | simulator | M3.6 |

Definition of done for any change: tests green, docs updated, `decision.md` entry for every design decision, `flow.md` updated if the flow changed (CLAUDE.md rule).

## 8. Risks

| ID | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R-01 | Backend handoff slips (track HB) | High / High | Engine proven on synthetic data independently; GA4 poller as interim real-data source (minutes latency) for non-urgent playbooks (A3, D2, E-series) |
| R-02 | Synthetic data not realistic; models overfit the generator | Medium / High | Truth hidden from engine; vary seeds and persona mixes; calibrate with HireMe aggregates (OQ-05); real pilot starts on heuristic scorer; shadow mode before autonomy |
| R-03 | DLT registration lead time for SMS templates | High / Medium | Submit 12 playbook templates in W5; push/email-first for marketing; transactional SMS templates first |
| R-04 | Firebase MCP tool limits (write support, throughput) | Medium / Low | Bulk via Admin SDK (D-011); MCP for config and verification; tool list verified in M0.2 |
| R-05 | Firestore hot documents (ledger, settings) at scale | Low (pilot) / Medium | Settings cached; ledger sharded counters in M3.6; Pub/Sub option |
| R-06 | GA4 export latency or gaps if webhook is never built | Medium / High for B1/B2 | Recommend webhook (D-001); poller + fire-time watermark wait; B1/B2 windows extended if needed |
| R-07 | Promo API differs from the spec sample | High / Medium | Adapter isolates mapping; contract tests; OQ-08 early |
| R-08 | LLM produces wrong prices or claims | Low / High | Prices/codes inserted by code; content check; deterministic fallback; LLM off for SMS/WhatsApp |
| R-09 | Consent mismatch between app, backend and engine (DPDP exposure) | Medium / High | Rider API as truth, 60 s cache, `consent_changed` events, send-time check, unsubscribe write-back |
| R-10 | Holiday season (W7-W9) delays reviews | High / Medium | Schedule G1 demo before 24 Dec; HB work tracked by HireMe leads |
| R-11 | Small real pilot volume makes lift inconclusive | Medium / Medium | Sample-size table shared up front; run B1/B2 longer; pool Noida weeks; do not expand on noise |
| R-12 | Python runtime not accepted by HireMe ops (spec says Node.js) | Medium / Medium | HTTP contracts make the engine replaceable; containerised; ops runbooks; decision D-009 open for review |
| R-13 | Cost overrun (BigQuery scans, LLM tokens) | Low / Medium | Partition pruning, dry-run caps, Haiku for volume, prompt caching, Batch API for digests, budget alerts |
| R-14 | Interaction between overlapping playbook holdouts biases lift | Medium / Low | Independent hashes, exclusive groups, report overlap share; optional global holdout (D-056) |

## 9. Team and working agreements (proposed)

| Role | Count | Notes |
|---|---|---|
| Lead architect / tech lead | 1 | Owns contract and `decision.md` |
| Backend/data engineers (Python) | 2 | Engine, jobs, simulator |
| Frontend engineer (React) | 1 | Console from W4 |
| Data scientist | 1 | From W6 (models, experiment analysis) |
| HireMe backend + app engineers | 2-3 | Track HB |
| Claude Code subagents and skills | — | See AGENTS_AND_SKILLS.md; every agent output is reviewed by a human before merge |

Rituals: weekly demo on the simulator (Fridays), gate reviews with the client, `OPEN_QUESTIONS.md` triage twice a week until all blocking questions are closed.
