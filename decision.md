# Decision Log (ADR style)

Every design decision for the HireMe AI Engagement Engine is recorded here. **Rule (see CLAUDE.md): any new or changed design decision gets a new entry with the next D- id; entries are never renumbered; superseded entries only get their Status line changed.**

Common fields for all entries below unless stated: **Date** 2026-11-02 · **Status** Proposed — pending client review · **Decided by** AI (Fable 5.1).

Spec = "HireMe AI Engagement Engine: Specification", @Vinay, Oct 21 2026. OQ-xx = [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md).

## Index

| ID | Title | Area |
|---|---|---|
| D-001 | No dual logging yet; webhook deferred to backend handoff, still recommended for production | Data freshness |
| D-002 | Source adapters converge on one Firestore Event Inbox keyed by `event_uuid` | Ingestion |
| D-003 | Raw events in BigQuery mirror the GA4 export schema exactly | Data |
| D-004 | Canonical event envelope v1 with mandatory `event_uuid` | Contract |
| D-005 | Contract versioning policy (SemVer, N and N-1 majors) | Contract |
| D-006 | Firestore is the engine's operational store (not MySQL + Redis) for v1 | Storage |
| D-007 | BigQuery is the analytical store; engine ops mirrored append-only to `engage_ops` | Storage |
| D-008 | Timers and work queues as Firestore collections with leases | Trigger engine |
| D-009 | Python 3.12 for engine, jobs, simulator and mocks; React + TS console | Runtime |
| D-010 | Deterministic services use SDKs; MCP is for LLM agents and dev tooling | Access |
| D-011 | Dummy data: bulk via load jobs / Admin SDK; MCP for config seeding and verification | Dummy data |
| D-012 | Isolated dev project; synthetic markers; ground truth hidden from the engine | Dummy data |
| D-013 | Rider DB stand-in `hireme_riders` shaped like the future Rider Profile API | Adapters |
| D-014 | Mock external services as contract-faithful HTTP services with fault injection | Adapters |
| D-015 | Closed-loop rider simulator driven by a ground-truth response model | Dummy data |
| D-016 | Injectable clock with virtual time for simulation | Runtime |
| D-017 | Time zone and money conventions (UTC storage, IST logic, INR, paise counters) | Conventions |
| D-018 | Holdout by deterministic hash per playbook, after user-level eligibility; ghost decisions; ITT | Experimentation |
| D-019 | Offer exploration arm (10 %) in promo playbooks | Experimentation |
| D-020 | Budget ledger semantics: committed / redeemed / released | Guardrails |
| D-021 | Budget scopes and enforcement in one Firestore transaction | Guardrails |
| D-022 | Frequency caps: 1/IST day, 3/rolling 7 days (marketing); service 2/day | Guardrails |
| D-023 | Message classes transactional / service / marketing aligned to DLT | Guardrails |
| D-024 | Quiet hours: defer within `max_defer_minutes`, else skip | Guardrails |
| D-025 | Deterministic ids and idempotency keys | Reliability |
| D-026 | Retries with backoff, DLQ, send-time revalidation | Reliability |
| D-027 | Kill switch semantics | Guardrails |
| D-028 | Autonomy = min(global, city, playbook); approval granularity | Autonomy |
| D-029 | Scoring provider: heuristic in Phase 1, LightGBM uplift (ONNX) in Phase 2 | AI |
| D-030 | Exact uplift offer rule and value basis | AI |
| D-031 | Attribution windows and method | Measurement |
| D-032 | LLM model assignment per runtime agent | AI |
| D-033 | No LLM text on SMS/WhatsApp; pre-registered templates filled by code | Compliance |
| D-034 | LLM output contract: placeholders only, content check, deterministic fallback | AI safety |
| D-035 | PII minimisation and Ask-AI data access via approved views | Privacy |
| D-036 | The 12 Rules MVP playbooks | Scope |
| D-037 | Pilot geography and reference ids | Conventions |
| D-038 | Promo code formats and creation | Promo |
| D-039 | Admin console as standalone embeddable React module with Firebase Auth roles | Console |
| D-040 | API authentication and RBAC | Security |
| D-041 | Future event webhook contract (batch, 202, HMAC, idempotent) | Contract |
| D-042 | Server-authoritative events | Contract |
| D-043 | Feature store split: BigQuery daily, Firestore profile snapshot, real-time counters | Data |
| D-044 | Versioned SQL files run by `engage-jobs` (no dbt in v1) | Data |
| D-045 | Model artifacts in Cloud Storage for Firebase with a BigQuery registry | AI |
| D-046 | Fraud and discount-trained rules deterministic in Phase 1 | Guardrails |
| D-047 | Identity conventions; A1 deferred | Contract / scope |
| D-048 | Synthetic data scale and time range | Dummy data |
| D-049 | Channel selection and fallback | Delivery |
| D-050 | Late and out-of-order event policy | Trigger engine |
| D-051 | Hosting and region | Deployment |
| D-052 | Secrets and configuration management | Security |
| D-053 | Consent: read-through at send time, instant unsubscribe, write-back | Compliance |
| D-054 | Documentation governance (decision.md, flow.md) | Process |
| D-055 | Batch (scheduled) playbooks cadence | Trigger engine |
| D-056 | Independent per-playbook holdouts; optional global holdout off by default | Experimentation |
| D-057 | GA4 type mapping conventions | Contract |
| D-058 | Immutable playbook versions referenced by decisions | Config |
| D-059 | Dataset names are configuration (switch to real GA4 export by config) | Data |
| D-060 | Reporting statistics: ITT, Newcombe CI, minimum sample, auto-pause rule | Measurement |
| D-061 | Anomaly detection in code, LLM only explains | AI |
| D-062 | Engine-computed user properties (price sensitivity, home/work zone) | Data |
| D-063 | Deep link contract | Contract |
| D-064 | Exclusive groups and priority for conflicting playbooks | Trigger engine |
| D-065 | D2 credit as a user-locked flat promo code until a wallet credit API exists | Scope |
| D-066 | Proposed neutral channel gateway contract for Grepix SMS/email/WhatsApp | Adapters |
| D-067 | Event catalogue YAML is the single source; schemas, examples, GA4 mapping and EVENTS.md are generated | Contract |
| D-068 | Self-contained envelope JSON Schema; strict for senders, tolerant at ingest | Contract |
| D-069 | Server-origin events: platform SERVER, user_pseudo_id optional | Contract |
| D-070 | All user properties are strings; `marketing_opt_in_whatsapp` renamed `marketing_opt_in_wa` | Contract |
| D-071 | Playbook schema: `trigger.type` defaults to `event_delay`; additions for D2 and A3 | Contract |
| D-072 | Senders generate UUIDv7; engine synthesises UUIDv5 for Firebase automatic events | Contract |
| D-073 | Hand-written OpenAPI only for cross-team interfaces; admin API spec generated from code | Contract |
| D-074 | `hireme_riders` stub document shape equals the Rider Profile API `RiderProfile` schema | Adapters |
| D-075 | BigQuery tables partition by UTC date; IST days are filtered by timestamp range | Data |
| D-076 | Contract validator doubles as the backend conformance kit | Contract |
| D-077 | GA4 export schema: core columns now, verified against a real export at M0.2 | Data |

---

## D-001 No dual logging yet; webhook deferred to backend handoff, still recommended for production
- **Context:** Spec §3 "Data freshness" recommends the app also send events to a HireMe backend endpoint for sub-15-minute triggers (B1, B2), and lists it as a decision to confirm (§11). The client states there is no webhook now; only Firebase (via MCP) and BigQuery exist.
- **Options:** (a) Wait for the webhook before building triggers. (b) Use only GA4 BigQuery export (minutes of latency, possibly more). (c) Build the engine on an internal Event Inbox fed now by a simulator, later by the webhook, with GA4 polling as fallback.
- **Decision:** (c). The webhook contract is defined now (API.md §4) and implemented on the engine side behind a flag; the backend implements its client in track HB. For production we still recommend dual logging because GA4 export latency cannot reliably meet 10-15 minute windows.
- **Consequences:** Engine development is unblocked. Until the webhook exists in production, B1/B2 on real data would run on `Ga4BigQueryPoll` with degraded timeliness; A3, D2 and E-series are unaffected. Links: OQ-01, OQ-03.

## D-002 Source adapters converge on one Firestore Event Inbox keyed by `event_uuid`
- **Context:** Three possible sources over time (simulator, webhook, GA4 export). The trigger engine must not change when sources change (client constraint 4).
- **Options:** (a) Trigger engine reads each source directly. (b) Pub/Sub topic as the inbox. (c) Firestore collection `engage_events_live` as the inbox; adapters write canonical envelopes with doc id = `event_uuid`.
- **Decision:** (c), with an `EventSource`/`InboxWriter` interface. `create()` on the doc id gives free dedupe across sources. Consumer uses a real-time listener plus a 30 s catch-up query. 7-day TTL.
- **Consequences:** Switching sources is configuration (`ENGAGE_SOURCES`). Pub/Sub can replace the inbox in Phase 3 behind the same interface if volume requires (R-05). Firestore cost per event is small at pilot volume (≈ 33 k events/day).

## D-003 Raw events in BigQuery mirror the GA4 export schema exactly
- **Context:** Client constraint 4 suggests the dummy events table mirror the GA4 BigQuery export so switching to the real export is a config change.
- **Options:** (a) Our own flat events table. (b) Exact GA4 shape (`events_YYYYMMDD`, `events_intraday_YYYYMMDD`, `event_params` repeated key/value, `user_properties`, `event_timestamp` micros). (c) Both.
- **Decision:** (b) for raw data, plus a flattening view `engage_features.v_events_flat` that all downstream SQL uses. Synthetic shards use the full official column list (unpopulated columns NULL).
- **Consequences:** All feature/mart SQL runs unchanged on real export. Slightly more complex SQL (UNNEST), handled by the view and the `ga4-sql` skill. Server-side events (ride_booked etc.) only appear in real GA4 data if the backend sends them via Measurement Protocol (OQ-06); otherwise the engine joins `engage_events_live`/webhook data instead.

## D-004 Canonical event envelope v1 with mandatory `event_uuid`
- **Context:** Same event may arrive via Firebase and webhook; GA4 has no unique event id.
- **Options:** (a) Dedupe on (user, name, timestamp) heuristics. (b) Require a UUID generated at the source and carried in both paths.
- **Decision:** (b) `event_uuid` (UUIDv7) plus `contract_version` and `origin` as common params; envelope fields in DATA_MODEL §2.1.
- **Consequences:** App and backend must generate and propagate the UUID (handoff obligation). Enables exact parity checks (HB2 exit criterion).

## D-005 Contract versioning policy (SemVer, N and N-1 majors)
- **Context:** The contract is a deliverable the backend implements against; it will evolve.
- **Options:** (a) Unversioned. (b) SemVer with `contract_version` per event and compatibility window.
- **Decision:** (b): additive = minor, breaking = major; engine supports N and N-1 majors for 90 days; unknown params/events are ignored.
- **Consequences:** Backend can upgrade independently; adapters carry mapping code during transitions.

## D-006 Firestore is the engine's operational store (not MySQL + Redis) for v1
- **Context:** Spec §8 suggests MySQL (config, logs) + Redis (queues, cooldowns). Client constraint 6: only Firebase + BigQuery exist now.
- **Options:** (a) Provision Cloud SQL MySQL + Memorystore Redis. (b) Firestore for config, state, queues, ledgers; BigQuery for analytics. (c) BigQuery for everything.
- **Decision:** (b). Firestore gives transactions (budget/cap reservation), TTL, real-time listeners (inbox, config invalidation) and no servers. BigQuery is unsuitable for low-latency transactional state (c).
- **Consequences:** Data access is behind repository interfaces so MySQL/Redis can be introduced later if HireMe ops prefer. Hot-document limits (≈ 1 sustained write/s per doc) handled by caching and later sharded counters (R-05). Spec §8.5 tables map to collections (DATA_MODEL §4.10).

## D-007 BigQuery is the analytical store; engine ops mirrored append-only to `engage_ops`
- **Context:** Reports, attribution and training need joins between engine actions and events.
- **Options:** (a) Firebase extension "Stream Firestore to BigQuery" (JSON changelog). (b) Engine-side log shipper writing typed rows via the Storage Write API. (c) Nightly export of Firestore.
- **Decision:** (b) typed append-only tables (`engage_ops.decisions`, `messages`, `promos`, `budget_ledger_entries`, `audit_log`, …), latest state via `QUALIFY` on `updated_at`; nightly reconciliation job.
- **Consequences:** Clean schemas for marts and ML; small engine complexity; (a) remains a fallback.

## D-008 Timers and work queues as Firestore collections with leases
- **Context:** Trigger delays (10 min to 48 h), `cancel_if`, outbox retries need durable scheduling without Redis.
- **Options:** (a) In-memory timers (lost on restart). (b) Cloud Tasks per timer (GCP service outside constraint; cancellation awkward). (c) Firestore `engage_timers` with a sweeper that leases due timers; outbox in `engage_messages`.
- **Decision:** (c), behind `TimerStore` and `Outbox` interfaces; fire-time recheck against the inbox; leases expire after 60 s.
- **Consequences:** Durable, crash-safe, multi-instance. Sweeper granularity 5 s (fine for minute-level triggers). Can swap to Cloud Tasks/Redis later.

## D-009 Python 3.12 for engine, jobs, simulator and mocks; React + TS console
- **Context:** Spec §8 suggests Node.js engine + Python scoring worker to match the HireMe stack. We also need a data generator, SQL orchestration and ML; a `.venv` exists.
- **Options:** (a) Node.js engine + Python worker (spec). (b) All Python (FastAPI). (c) All TypeScript.
- **Decision:** (b) for v1; console in React + TypeScript (spec §7). Contracts are HTTP/JSON, so the backend handoff does not depend on the engine language; scoring runs in-process (ONNX) instead of a separate worker.
- **Consequences:** One language, faster delivery and fewer moving parts. Deviation from the spec needs client acceptance (OQ-34, R-12).

## D-010 Deterministic services use SDKs; MCP is for LLM agents and dev tooling
- **Context:** Spec §8.1 says the AI reads Firebase "through the MCP server". The hot path (timers, guardrail transactions) needs transactions, listeners and low latency.
- **Options:** (a) Everything via MCP. (b) Engine services via Firebase Admin SDK and BigQuery client on the same project; MCP servers used by Claude Code during development and optionally behind LLM tool wrappers.
- **Decision:** (b). Runtime LLM agents get engine-implemented tools (BigQuery `engage_views`, Firestore read-only config); the Firebase MCP server may back the Firestore-read tool in Phase 2 if hosted in the client project.
- **Consequences:** Requires service-account access to the Firebase project (OQ-02). Firebase Analytics data itself is not exposed by MCP; it is read from the BigQuery export.

## D-011 Dummy data: bulk via load jobs / Admin SDK; MCP for config seeding and verification
- **Context:** Client wants dummy data generated into Firebase via the MCP server and into BigQuery. Volume: 20 k riders, ≈ 6 M events.
- **Options:** (a) Everything through MCP tool calls. (b) Bulk via BigQuery load jobs and Firestore BulkWriter; MCP for config docs (~70) and verification. (c) Firestore emulator only.
- **Decision:** (b). If the installed Firebase MCP lacks document-write tools, config seeding uses the Admin SDK script and MCP verifies.
- **Consequences:** Fast, cheap, reproducible loads; MCP still central for inspection and seeding (skills `seed-firestore`, `load-bigquery`). Risk R-04.

## D-012 Isolated dev project; synthetic markers; ground truth hidden from the engine
- **Context:** Synthetic data must never mix with real data; uplift validation needs ground truth the engine must not see.
- **Options:** (a) Synthetic data in the production project with flags. (b) Separate project `hireme-engage-dev`; `is_synthetic`; truth in `engage_sim` with IAM isolation.
- **Decision:** (b). Synthetic PII uses reserved ranges (`+91999001xxxx`, `@example.test`).
- **Consequences:** Two projects to manage; strong guarantee against leakage and accidental sends.

## D-013 Rider DB stand-in `hireme_riders` shaped like the future Rider Profile API
- **Context:** Spec §8.1 rider DB read API (consent, phone, email, wallet) does not exist.
- **Options:** (a) Put contact/consent into GA4 user properties. (b) Firestore stub whose documents equal the future API response, behind `RiderDirectory`.
- **Decision:** (b); API contract in API.md §5.
- **Consequences:** Switching to the real API is an adapter change; the same JSON fixtures test both.

## D-014 Mock external services as contract-faithful HTTP services with fault injection
- **Context:** Promo API, FCM, SMS, email, WhatsApp unavailable (client constraint 5).
- **Options:** (a) In-process fakes. (b) HTTP mock service with real request/response shapes and a fault API.
- **Decision:** (b) `engage-mocks`, using the spec §8.2 Promo API sample and FCM HTTP v1 shapes; SMS/email via a proposed gateway contract (D-066).
- **Consequences:** Real adapters are exercised end to end (serialisation, retries, timeouts); switching = base URL + credentials.

## D-015 Closed-loop rider simulator driven by a ground-truth response model
- **Context:** Uplift vs holdout, budgets and caps can only be demonstrated if synthetic riders react to messages.
- **Options:** (a) Static history only. (b) Responder that reacts to delivered messages using known p0/p1 per persona and action.
- **Decision:** (b) (DUMMY_DATA_PLAN §5, §9), including fatigue, quiet-hours annoyance and discount-trained "would book anyway" behaviour.
- **Consequences:** Measured lift can be checked against truth (V12); models can be validated; generator realism is a risk (R-02).

## D-016 Injectable clock with virtual time for simulation
- **Context:** A 30-day pilot or 48 h timers must run in hours, not weeks.
- **Options:** (a) Real time only. (b) `Clock` interface; virtual clock in dev (shared via `sim_runs/{run_id}`), speed 1-120×.
- **Decision:** (b); production always `ENGAGE_CLOCK=real`.
- **Consequences:** All time logic must use the clock (lint rule against direct `datetime.now()` in `engage/`).

## D-017 Time zone and money conventions (UTC storage, IST logic, INR, paise counters)
- **Context:** Spec uses IST examples and INR; GA4 `event_date` follows the property time zone.
- **Options:** Store local times vs UTC; floats vs integers for money.
- **Decision:** Store UTC; all business days, caps, budgets, reports and quiet hours in Asia/Kolkata; GA4 property TZ Asia/Kolkata; JSON times ISO-8601 with offset; money INR decimals in APIs/BigQuery (`NUMERIC(12,2)`), integer paise in atomically incremented Firestore counters.
- **Consequences:** White-label markets later need per-city time zones (already a city setting).

## D-018 Holdout by deterministic hash per playbook, after user-level eligibility; ghost decisions; ITT
- **Context:** Spec §6.5: 10 % holdout per playbook; spec §6.1 lists "not in a holdout group" under eligibility.
- **Options:** (a) Random draw per decision. (b) Stored assignment table. (c) `sha256(salt:playbook_id:user_id) mod 10000 < pct×100`.
- **Decision:** (c), evaluated after audience/consent/cooldown/cap/suppression/fraud filters and before scoring, so both arms come from the same eligible population; holdout users get a ghost decision (`status: holdout`) with scores; analysis is intention-to-treat on the assigned arm. Salt `hm-2026q4`, changed only by an explicit new-experiment action.
- **Consequences:** Stable, stateless, reproducible assignment; budget-blocked treatment decisions remain in the treatment arm (conservative lift).

## D-019 Offer exploration arm (10 %) in promo playbooks
- **Context:** Uplift models (Phase 2) need randomised variation of offers, not only treated vs holdout.
- **Options:** (a) No exploration (models learn confounded policy data). (b) Small uniform-random rung assignment within treatment.
- **Decision:** (b) 10 % of treatment in B1, B2, E2, E3 get a random ladder rung; logged `arm: exploration`.
- **Consequences:** Small short-term cost for valid training data; exploration share configurable per playbook.

## D-020 Budget ledger semantics: committed / redeemed / released
- **Context:** Spec §8.5 ledger has `committed_inr` and `redeemed_inr`; spend must never exceed budget even if all codes are redeemed.
- **Options:** (a) Count only redeemed spend (can overshoot). (b) Commit the maximum liability at code creation, convert to redeemed on use, release on expiry.
- **Decision:** (b). Liability = flat value, or `min(max_discount, ceil(pct × fare_estimate × 1.25))` for percent codes. Check: `committed_outstanding + redeemed + new_liability ≤ limit`. Ledger fields: `committed_gross`, `committed_outstanding`, `redeemed`, `released` (paise).
- **Consequences:** Hard budgets are truly hard; spend reports use redeemed; pacing uses both. Expiry job releases unused liability every 5 min.

## D-021 Budget scopes and enforcement in one Firestore transaction
- **Context:** Spec §7: monthly and daily budget per city and per playbook, alert threshold, hard stop.
- **Options:** (a) Per-playbook only. (b) Scopes global month, city month, city × playbook day and month; all checked in one transaction.
- **Decision:** (b); budgets in `engage_budgets`, counters in `engage_budget_ledger` (ids like `D_20261021_c3_B2_abandoned_booking`).
- **Consequences:** ≤ 6 document reads per reservation; sharding needed only at much higher volume (Phase 3).

## D-022 Frequency caps: 1/IST day, 3/rolling 7 days (marketing); service 2/day
- **Context:** Spec §7/§9: max 1 marketing message per day, 3 per week per user across channels; transactional exempt. "Week" is ambiguous.
- **Options:** Calendar week vs rolling 7 days.
- **Decision:** Daily = IST calendar day; weekly = rolling 7 × 24 h; service-class cap 2/day separate; transactional uncapped.
- **Consequences:** Rolling window avoids Monday bursts. OQ-22 confirms.

## D-023 Message classes transactional / service / marketing aligned to DLT
- **Context:** Spec distinguishes marketing vs transactional; some playbooks (B3, B5, D2, A1) are neither promotional nor strictly transactional. TRAI DLT has transactional, service (implicit/explicit), promotional.
- **Decision:** Every playbook has `message_class`. Transactional: B8, C1, C2, F4. Service: A1, A4, B3, B5, D1, D2. Marketing: everything with a promo or retention aim. Caps, quiet hours and kill switch rules apply per class (ARCHITECTURE §7).
- **Consequences:** Correct DLT categories; D2 apology is not blocked by marketing caps. OQ-21 confirms classification.

## D-024 Quiet hours: defer within `max_defer_minutes`, else skip
- **Context:** Spec §7: no marketing 22:00-08:00 local time.
- **Options:** Always defer to 08:00; always skip; per-playbook.
- **Decision:** Per playbook `timing.max_defer_minutes`: if 08:00 (+0-30 min jitter) is within it, defer; else skip with `quiet_hours_skip`. B1/B2 default 0 (a 30-minute code at 08:00 the next day makes no sense); E-series 720. Applies to marketing and service; transactional exempt.
- **Consequences:** No night-time marketing; intent playbooks lose some night volume (visible in reports).

## D-025 Deterministic ids and idempotency keys
- **Context:** Spec §9: one decision id = one message, idempotent sends.
- **Decision:** `timer_id`, `decision_id` = `sha256(playbook_id | user_id | dedupe_key)` (dedupe key = trigger `event_uuid`, `ride_id|offset`, or IST date for batch); `message_id = msg_<decision>_<channel_ordinal>`; `promo_ref` per decision; provider calls carry `decision_id` (Promo API `Idempotency-Key`) or `message_id`.
- **Consequences:** Replays and duplicate events are harmless; the Promo API must support idempotency keys (OQ-08) or the engine relies on its own `promo_ref` + code-uniqueness check.

## D-026 Retries with backoff, DLQ, send-time revalidation
- **Decision:** Retryable errors (429, 5xx, timeouts): 5 attempts at 5 s, 20 s, 80 s, 5 min, 20 min with full jitter; permanent errors → `undeliverable` → fallback channel; after the last attempt → `engage_dlq` and reservation released. Before every provider call re-check kill switch, consent, quiet hours, promo validity (≥ 5 min left) and decision status. Promo API failure → downgrade to reminder if allowed, else skip.
- **Options considered:** infinite retries; no fallback; DLQ only.
- **Consequences:** No stale or unsafe late sends; DLQ replay in console for super admins.

## D-027 Kill switch semantics
- **Context:** Spec §9: super admin can pause all AI sends in one click. Unclear whether transactional messages stop.
- **Decision:** Default scope `marketing_and_service` stops all marketing/service sends and promo creation; transactional (payment failed, pickup reminders) continue. Scope `all` stops everything. Optional city scope. Effective ≤ 5 s; checked at decision start and before each provider call; optional deactivation of unused codes.
- **Consequences:** Riders still get safety-critical and operational messages during incidents. OQ-23 confirms.

## D-028 Autonomy = min(global, city, playbook); approval granularity
- **Context:** Spec §6.4 levels 0-3; "admin approves each" is impossible for 10-minute real-time triggers.
- **Decision:** Effective level = min of the three settings. Approval kinds: `playbook_version` (pre-approves rule-conformant sends), `template`, `cohort_batch` (one approval per scheduled batch), `campaign`, `realtime_decision` (expires within promo validity, max 30 min). Level 0 for real-time playbooks therefore behaves as shadow mode.
- **Consequences:** Spec Phase 1 "suggest only" maps to level 0/1; approvals are workable. OQ-25 on who approves what.

## D-029 Scoring provider: heuristic in Phase 1, LightGBM uplift (ONNX) in Phase 2
- **Context:** Spec §6.1 step 2 (p0, p1, churn, price sensitivity) and §6.5 (gradient boosting on BigQuery).
- **Options:** (a) Models from day one (no randomised data yet). (b) Heuristic scorer from base rates + priors, then uplift models trained on holdout/exploration data. (c) BigQuery ML only.
- **Decision:** (b): `heuristic_v1` (base rates by playbook × city × price band × recency, configured prior lifts), then `uplift_v1` (LightGBM T-learner per playbook family, calibrated, exported to ONNX, scored in-process) and `churn_v1` (nightly batch). Promotion candidate → shadow → active by humans.
- **Consequences:** Same pipeline and offer rule across phases; Phase 2 gate compares the two policies on identical simulations.

## D-030 Exact uplift offer rule and value basis
- **Context:** Spec §6.1 step 3: promo only if (p1 − p0) × average fare value exceeds discount cost; step 4: smallest discount reaching target uplift.
- **Decision:** Rung r viable if `(p1[r] − p0) × V ≥ p1[r] × E[discount_r]` and `p1[r] − p0 ≥ min_uplift` (0.02). `V` = fare estimate (or margin if `value_basis = margin`); `E[discount_r] = min(r% × fare, cap)` or flat value. Choose the smallest viable rung whose net value is within 5 % of the best. `p0 ≥ 0.6` or discount-trained → reminder only. Nothing viable → skip `no_uplift`.
- **Consequences:** Discount cost counts only on conversion (expected cost). Using gross fare favours discounts more than margin would (OQ-17).

## D-031 Attribution windows and method
- **Context:** Spec §6.5: 24 h for intent, 7 days for win-back.
- **Decision:** Window anchored at decision time for both arms (holdout has no send time); conversion = `attribution.conversion_event` (default `ride_booked`) by the same user; fare value from `ride_completed.gross_fare`; last-touch credit for per-message "converted" counts; incrementality from per-playbook ITT holdout comparison.
- **Consequences:** Symmetric, unbiased comparison; per-message conversion counts can double-count across playbooks but lift does not. OQ-24 confirms windows.

## D-032 LLM model assignment per runtime agent
- **Context:** Client: Claude via Anthropic API; current models opus-5-5, sonnet-5-5, haiku-5-5, fable-5-1. Pricing (per M tokens in/out): Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20, Fable 5.1 $10/$50.
- **Decision:** Message writer and anomaly explainer: `claude-haiku-5-5` (volume, latency). Ask AI and daily digest: `claude-sonnet-5-5` (tool use, reasoning; digest via Message Batches). Campaign suggester and playbook tuner: `claude-opus-5-5` (low volume, high stakes). Content policy reviewer: `claude-haiku-5-5`. Fable 5.1 not used at runtime (cost); used for architecture work. No LLM in the Phase 1 hot path.
- **Consequences:** Model ids pinned in `engage_settings/global.llm`; changing a model requires re-running the LLM eval set.

## D-033 No LLM text on SMS/WhatsApp; pre-registered templates filled by code
- **Context:** TRAI DLT requires SMS content to match registered templates; WhatsApp business-initiated messages must use approved templates.
- **Decision:** LLM personalisation only for push, email and in-app; SMS/WhatsApp use registered templates with variables substituted by code.
- **Consequences:** Compliance by construction; less personalisation on SMS.

## D-034 LLM output contract: placeholders only, content check, deterministic fallback
- **Context:** Spec §9: LLM never writes prices or codes; output passes a content check.
- **Decision:** Structured output with placeholders; code substitutes values; deterministic checks (placeholders, digits/currency outside placeholders, lengths, language script, banned phrases); 2 s timeout; any failure → approved template text.
- **Consequences:** Wrong prices are impossible from the LLM; fallback rate monitored.

## D-035 PII minimisation and Ask-AI data access via approved views
- **Context:** Spec §9 PII minimisation; DPDP Act.
- **Decision:** LLM inputs limited to pseudonymous id, first name, language, area names, offer label. Ask AI may only run single SELECTs on `engage_views` (aggregated, no identifiers, k ≥ 20), city-scoped for city admins, with dry-run byte caps and numeric answer verification.
- **Consequences:** Some questions (individual rider lookups) are not answerable by Ask AI by design.

## D-036 The 12 Rules MVP playbooks
- **Context:** Spec Phase 1: "12 core playbooks"; client asked to pick and justify.
- **Decision:** A2, A3, B1, B2, B3, B5, B8, C2, D2, E2, E3, E4 (justification in IMPLEMENTATION_PLAN §3.1). E5 needs the churn model (Phase 2); A1 blocked by pre-login identity (D-047).
- **Consequences:** Covers activation, intent recovery, service recovery, transactional, scheduled rides and win-back; all exercisable with synthetic data.

## D-037 Pilot geography and reference ids
- **Decision:** Pilot Noida (spec §11). Synthetic data also covers Delhi and Gurgaon (comparison and cross-city trips). `city_id` 1 Delhi, 2 Gurgaon, 3 Noida (matches spec Promo API sample `city_ids: [3]`); `zone_id` `<CITY3>-<CODE>`; vehicles mini/sedan/prime/suv.
- **Consequences:** Real HireMe city ids must be mapped at handoff (OQ-15).

## D-038 Promo code formats and creation
- **Context:** Spec §6.3: readable codes for campaigns, random codes for personal offers; codes created via the Promo API with attribution meta.
- **Decision:** Personal: `<PREFIX><VALUE>-<4 chars Crockford base32 without I,L,O,U>` (e.g. `GO15-7KQ2`), user-locked, single use; collision → regenerate (max 3). Campaign: readable (`DIWALI20`). `meta` carries `campaign_id` (`pb_<playbook_id>` for playbook sends), `playbook_id`, `created_by`, `decision_id`. Readable personal codes like the spec's `RIYA15` are not used (guessable).
- **Consequences:** Spec example text adapted; codes cannot be shared usefully.

## D-039 Admin console as standalone embeddable React module with Firebase Auth roles
- **Context:** Spec §7: module inside existing HireMe admin panel (React) with roles super/marketing/city admin. We have no access to that panel yet.
- **Decision:** Build `engage-console` (React + TS + Vite) talking only to the engine API; package for embedding later (route package or module federation, OQ-35). Auth via Firebase Authentication with custom claims; SSO with HireMe admin later.
- **Consequences:** Console usable now; integration work at handoff.

## D-040 API authentication and RBAC
- **Decision:** Admin: Firebase ID tokens + custom claims (`role`, `city_ids`), permission matrix in API.md §1.3. Webhooks: HMAC-SHA256 with timestamp, key id rotation. Service-to-service: Google OIDC (Cloud Run IAM). All mutations audited with `request_id`.
- **Consequences:** No shared static API keys for humans; backend must implement HMAC signing.

## D-041 Future event webhook contract (batch, 202, HMAC, idempotent)
- **Decision:** `POST /engage/v1/events` (alias `/engage/events`), batches of 1-500 envelopes, per-event results, 202, dedupe by `event_uuid`, sender retries with backoff up to 24 h (API.md §4).
- **Consequences:** Backend can relay client events and emit server events with one client library.

## D-042 Server-authoritative events
- **Context:** Some events can only be trusted from the server (spec: `ride_booked` "booking created on server").
- **Decision:** After handoff the backend emits: `sign_up`, `ride_booked`, `ride_scheduled`, `scheduled_ride_cancelled`, `no_driver_found`, `ride_cancelled`, `ride_started`, `ride_completed`, `payment_failed`, `wallet_topup`, `support_ticket_opened`, `promo_redeemed`, `consent_changed`. App emits UI events. `origin` param records which.
- **Consequences:** Conversions and spend are measured on server truth.

## D-043 Feature store split: BigQuery daily, Firestore profile snapshot, real-time counters
- **Decision:** `engage_features.user_features_daily` built nightly; synced to Firestore `engage_user_profile` (nightly + hourly delta); same-day signals (fare checks today, abandons) kept in `engage_user_state.counters_rt` from the inbox.
- **Consequences:** Decision-time reads are single Firestore gets; training uses as-of snapshots in BigQuery (no leakage).

## D-044 Versioned SQL files run by `engage-jobs` (no dbt in v1)
- **Options:** dbt; BigQuery scheduled queries; SQL files + Python runner.
- **Decision:** SQL files in `sql/` executed by `engage-jobs` with parameters and dry-run cost caps; tests on fixture datasets.
- **Consequences:** Simple, reviewable; revisit dbt if model count grows.

## D-045 Model artifacts in Cloud Storage for Firebase with a BigQuery registry
- **Decision:** ONNX artifacts in the project's Firebase Storage bucket (`models/`), metadata and metrics in `engage_ml.model_registry`, active pointer in Firestore `engage_models`.
- **Consequences:** Stays within the Firebase/GCP project; promotion is a pointer change.

## D-046 Fraud and discount-trained rules deterministic in Phase 1
- **Decision:** Fraud flags: device shared by ≥ 3 accounts, payment fingerprint shared by ≥ 3, repeat welcome redemption per device, code-only booker (≥ 80 % rides with codes and ≥ 10 fare checks per ride). Discount-trained: `promo_ride_share_90d ≥ 0.7` with ≥ 5 rides, or ≥ 3 abandon-then-book-with-code patterns in 60 days. Fraud-flagged → no promos (reminders allowed); discount-trained → reminder only. Phase 2 uplift model supersedes the discount-trained rule if it performs better.
- **Consequences:** Thresholds need business confirmation (OQ-26).

## D-047 Identity conventions; A1 deferred
- **Context:** `sign_up_started` happens before login, so there is no `user_id` (spec §3 requires stable user_id for joins).
- **Decision:** `user_id` = `u_<digits>` set via `setUserId` right after OTP; A1 (incomplete sign-up) deferred until the backend can map app instance (FCM token) or phone to a pre-account record.
- **Consequences:** A1 not in MVP (OQ-11).

## D-048 Synthetic data scale and time range
- **Decision:** History 2026-05-05 to 2026-10-31 (180 days, enough for 90-day dormancy); live simulation from 2026-11-01 (covers Diwali 2026-11-08). Presets tiny/small/medium/large; `medium` = 20 k riders (Noida 50 %, Delhi 35 %, Gurgaon 15 %), ≈ 6 M events, sized so B2 in Noida reaches ≈ 8,000 eligible triggers within one 30-day simulated run.
- **Consequences:** Dev project on Blaze plan (OQ-04).

## D-049 Channel selection and fallback
- **Decision:** Channels in playbook order; first with consent and reachability. Fallback on `undeliverable`, `no_token`, `no_consent`; optional `unopened` fallback after N minutes for long-window playbooks (spec: push not opened in 24 h → SMS/email). Fallback messages share the decision and count once toward caps.
- **Consequences:** Push-first keeps cost low (spec §6.1 step 5).

## D-050 Late and out-of-order event policy
- **Decision:** Timers fire at `event_ts + wait`; events older than `max_lateness_minutes` do not start timers but still cancel timers and feed features/attribution; future-dated client events (> 5 min) clamped to receipt time; fire-time recheck against the inbox; with the GA4 poller, the recheck waits for the source watermark (≤ 5 min).
- **Consequences:** Order-tolerant engine; fewer wrong nudges to riders who already booked.

## D-051 Hosting and region
- **Decision:** Cloud Run services (`engage-api`, `engage-worker`, `engage-mocks` dev only), Cloud Run jobs + Cloud Scheduler (`engage-jobs`), Firebase Hosting (console); Firestore, BigQuery and Storage in `asia-south1` (Mumbai); everything in the client's own project (spec §9).
- **Consequences:** India data residency; LLM calls leave the project to the Anthropic API (OQ-31).

## D-052 Secrets and configuration management
- **Decision:** Secret Manager in deployed environments; local `.env` (git-ignored, denied to Claude Code reads); configuration via environment variables plus Firestore settings for admin-editable values; no secrets in Firestore or repo.
- **Consequences:** Rotation of HMAC keys via key ids.

## D-053 Consent: read-through at send time, instant unsubscribe, write-back
- **Context:** Spec §9: separate opt-ins per channel; honour unsubscribe instantly; rider DB is source of truth.
- **Decision:** Consent checked at decision and send time from `RiderDirectory` (stub now, Rider API later; cache ≤ 60 s, evicted by `consent_changed`); engine-hosted unsubscribe updates the stub now and writes back to the backend later; GA4 `marketing_opt_in_*` properties used only for segmentation counts.
- **Consequences:** DPDP-aligned; backend must provide consent write-back (API.md §5.2).

## D-054 Documentation governance (decision.md, flow.md)
- **Decision:** Every design decision → new entry here; any flow change → update `flow.md`; enforced via CLAUDE.md, the `log-decision`/`update-flow` skills, `docs-keeper` agent and a reminder hook.
- **Consequences:** Reviewable history of design intent.

## D-055 Batch (scheduled) playbooks cadence
- **Decision:** E2 and E3 daily at 10:00 IST, E4 Mondays 10:00 IST, from `segment_membership_daily` built at 01:30; each batch at autonomy < 2 creates one `cohort_batch` approval; sends spread over a 2-hour window to smooth load.
- **Consequences:** Win-back avoids quiet hours and morning commute; batch approvals are practical for admins.

## D-056 Independent per-playbook holdouts; optional global holdout off by default
- **Context:** A user can be in B2's holdout and E2's treatment; overall engine lift is not measured by per-playbook holdouts.
- **Decision:** Independent hashes per playbook; `global_holdout_percent` setting (default 0 in pilot, recommended 2-5 % once volume allows) that excludes users from all marketing.
- **Consequences:** Per-playbook lift unbiased within playbook; overall lift needs the global holdout (OQ-20).

## D-057 GA4 type mapping conventions
- **Decision:** Strings → `string_value`; ints and booleans (0/1) → `int_value`; doubles → `double_value`; timestamps in params as ISO strings; user properties as strings except counters (int).
- **Consequences:** Consistent extraction SQL; the app team must follow (contract).

## D-058 Immutable playbook versions referenced by decisions
- **Decision:** Every material change creates a new version in `engage_playbooks/{id}/versions/{n}` and `engage_ops.playbook_versions`; the engine runs `approved_version`; decisions store `playbook_version`.
- **Consequences:** Reports can be sliced by version; rollback = re-approve an old version.

## D-059 Dataset names are configuration (switch to real GA4 export by config)
- **Decision:** `ENGAGE_BQ_GA4_DATASET` (dummy `analytics_999999999`), plus dataset env vars for all engine datasets.
- **Consequences:** Real export = change config + IAM grant; validation checks run on both.

## D-060 Reporting statistics: ITT, Newcombe CI, minimum sample, auto-pause rule
- **Decision:** Lift = conv_treat − conv_hold on assigned arms; 95 % CI by Newcombe hybrid score; incremental rides = lift × n_treat; ROI = (incremental fare − promo cost) / promo cost; "insufficient data" below 400 per arm; auto-pause when the ROI CI upper bound < 0 for 14 consecutive days (spec §6.5 "ROI stays negative for 14 days").
- **Consequences:** Conservative auto-pause avoids pausing on noise.

## D-061 Anomaly detection in code, LLM only explains
- **Decision:** Seasonal baseline per city × hour with robust z-score (> 4) or ratio (> 3×) and minimum volume; the LLM (Haiku) writes the explanation from breakdowns.
- **Consequences:** Deterministic alerting; LLM failure only loses the narrative.

## D-062 Engine-computed user properties (price sensitivity, home/work zone)
- **Context:** Spec §3 lists `price_sensitivity` (computed), `home_zone`, `work_zone` as user properties.
- **Decision:** The engine computes them (rules in DATA_MODEL §3.4); the app must not set them; optional mirroring to Firebase user properties via backend later for Firebase audiences.
- **Consequences:** One definition, versioned with `feature_version`.

## D-063 Deep link contract
- **Decision:** `hireme://book?quote=&drop=&promo=&mid=&cid=` (+ universal link); app applies the code, opens booking with the quote, and attaches `engage_message_id` to events for 30 minutes.
- **Consequences:** Required for "deep link that opens booking with the code applied" (spec §4 step 7) and precise attribution (OQ-14).

## D-064 Exclusive groups and priority for conflicting playbooks
- **Context:** A single session can trigger B1, B2, B3 (and B4); spec caps help but do not define precedence.
- **Decision:** `exclusive_group` + `priority` per playbook; at most one message per user per group per cooldown window; higher priority wins; B3 (payment step) takes `step = payment`, B2 the other steps.
- **Consequences:** Predictable behaviour; skipped candidates logged `superseded_exclusive_group`.

## D-065 D2 credit as a user-locked flat promo code until a wallet credit API exists
- **Context:** Spec D2 says "₹75 has been added to your wallet"; no wallet API is available.
- **Decision:** MVP issues a ₹75 flat, user-locked, 14-day code via the Promo API; message wording adapted ("₹75 off your next ride"); switch to wallet credit when `POST /api/admin/wallet/credits` exists.
- **Consequences:** Slightly different rider experience; OQ-13.

## D-066 Proposed neutral channel gateway contract for Grepix SMS/email/WhatsApp
- **Context:** Spec §8.3: "Grepix provides an API" for each channel; contracts unknown.
- **Decision:** Adapters target a proposed neutral contract (API.md §6.3-6.5) and mocks implement it; FCM uses native HTTP v1 shape. Mapping to the real Grepix APIs happens in HB4.
- **Consequences:** Possible adapter rework once Grepix shares its APIs (OQ-09).

## D-067 Event catalogue YAML is the single source; schemas, examples, GA4 mapping and EVENTS.md are generated
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** M0.1 needs JSON Schemas for 27 events, a GA4 mapping, examples and a readable reference. Writing each by hand means five copies of the same facts drifting apart (DATA_MODEL §2.5 asked for one schema file per event).
- **Options considered:** (a) hand-written JSON Schema per event; (b) one YAML catalogue that generates everything; (c) Pydantic models as the source and export schemas from them.
- **Decision:** (b). `contracts/events/v1/catalog.yaml` holds names, types, required flags, examples, origins and delivery. `engage.tools.gen_contract` writes `contracts/events/v1/generated/` (envelope schema, `ga4_mapping.json`, 27 examples, `EVENTS.md`). `validate_contract` fails if the generated files are stale.
- **Consequences:** The backend team reads `EVENTS.md` and validates against `envelope.schema.json`. Contract changes are one YAML edit plus regeneration. DATA_MODEL §2.3 stays as the narrative, and the catalogue wins on any conflict. Engine Pydantic models (M0.5) are generated or checked against the same catalogue.

## D-068 Self-contained envelope JSON Schema; strict for senders, tolerant at ingest
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** Schemas with cross-file `$ref`s are awkward for other teams' validators (Node ajv, Java), and DATA_MODEL §2.5 says the engine must ignore unknown params and events.
- **Options considered:** (a) one file per event with external refs; (b) one bundled schema with internal `$defs`; (c) lenient schemas that allow extra params.
- **Decision:** (b), strict: `additionalProperties: false` on the envelope and on every event's params, `event_name` an enum, and conditional rules per event (allowed origins, nullable `user_id`). Senders validate strictly, so typos are caught at the source. At runtime the ingest adapter is tolerant: unknown params are dropped and logged, and unknown events are stored in the inbox but never trigger playbooks.
- **Consequences:** A new minor contract version must be deployed to the engine before senders use new params, or they will be dropped (they are logged, not lost silently).

## D-069 Server-origin events: platform SERVER, user_pseudo_id optional
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** DATA_MODEL §2.1 made `user_pseudo_id` (Firebase app instance id) required for every event. The backend usually does not know it for server events such as `ride_booked`. The API.md webhook example already used `platform: SERVER`.
- **Options considered:** (a) require the backend to store and forward the app instance id; (b) optional for server origin; (c) drop the field from server events.
- **Decision:** (b). `origin: client` requires `user_pseudo_id` and `app_version` with platform ANDROID or IOS. `origin: server` requires `platform: SERVER`, and `user_pseudo_id` is optional. In GA4-shaped rows a server event carries the rider's device platform; converting back to an envelope restores `SERVER` from `origin`.
- **Consequences:** Joins between server events and GA4 history use `user_id`, which is set for every non-pre-login event. OQ-38 asks the backend whether it can include the app instance id anyway.

## D-070 All user properties are strings; `marketing_opt_in_whatsapp` renamed `marketing_opt_in_wa`
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** Firebase `setUserProperty` accepts only strings, and GA4 limits user property names to 24 characters. DATA_MODEL §2.4 typed `total_rides` as int and added `marketing_opt_in_whatsapp` (25 characters), which Firebase would reject.
- **Options considered:** For the name: `mkt_opt_in_whatsapp`, `marketing_opt_in_wa`, `opt_in_whatsapp`.
- **Decision:** Every user property is a string with a pattern or enum (`total_rides` matches `^[0-9](1, 6)$`). The WhatsApp property is named `marketing_opt_in_wa`, which keeps the prefix shared with the other opt-in properties. The validator enforces the 24-character limit.
- **Consequences:** SQL casts numeric user properties (`SAFE_CAST(... AS INT64)`). Neither change affects spec section 3 names.

## D-071 Playbook schema: `trigger.type` defaults to `event_delay`; additions for D2 and A3
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** DATA_MODEL §5.1 claimed the spec section 7 B2 example validates unchanged, but the draft schema required `trigger.type`, which the spec example does not have. The MVP defaults also needed shapes the schema lacked: D2 has two trigger events (`ride_rated` with rating ≤ 2, or `support_ticket_opened`), A3 reminds the rider of A2's code, and A2/A3/E4 are "once per user".
- **Options considered:** (a) edit the spec example; (b) make `type` optional with default `event_delay`; (c) separate D2 into two playbooks.
- **Decision:** (b). Also added: `trigger.events_any` plus `trigger.event_where` (per-event conditions), `promo.reuse_code_from`, `cooldown_hours: null` meaning once per user, `additionalProperties: false` on triggers, required fields for `window_count` and `threshold`, and a rule that transactional playbooks cannot carry promos. Cross-checks in code confirm that trigger, `cancel_if` and conversion events exist in the contract, and that `where` and `match_params` name real params.
- **Consequences:** `contracts/examples/playbooks/spec_section7_B2.json` is kept as a regression test. DATA_MODEL §5.3 now points to `contracts/playbook.schema.json` instead of embedding a copy.

## D-072 Senders generate UUIDv7; engine synthesises UUIDv5 for Firebase automatic events
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** `event_uuid` is the dedupe key (D-004), but Firebase automatic events such as `app_remove` carry no custom params, so they have no `event_uuid`.
- **Options considered:** (a) let them have no id; (b) random id on ingest; (c) deterministic id from GA4 fields.
- **Decision:** (c). The GA4 poller sets `uuid5(namespace, user_pseudo_id|event_timestamp|event_name|event_bundle_sequence_id)`. The envelope schema accepts version 5 only for `origin: auto` and version 7 for everything else. The BigQuery view `v_events_flat` exposes `event_key` (the `event_uuid` param, or an MD5 of the same inputs) for SQL dedupe.
- **Consequences:** Re-polling the same GA4 row produces the same id, so it is deduplicated. The SQL `event_key` and the poller's UUIDv5 are different strings for the same automatic event; neither is ever compared with the other.

## D-073 Hand-written OpenAPI only for cross-team interfaces; admin API spec generated from code
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** M0.1 listed four OpenAPI drafts. Three describe interfaces between the engine and the HireMe backend or providers: ingest and webhooks, Rider Profile API, Promo API. The admin API is used only by our own console, and D-009 already says FastAPI generates OpenAPI from the same models.
- **Options considered:** (a) hand-write all four now; (b) hand-write the three cross-team ones now and generate the admin spec in Phase 1.
- **Decision:** (b). `contracts/openapi/engage-ingest.v1.yaml`, `rider-api.v1.yaml` and `promo-api.v1.yaml` are hand-written, validated, and every example in them is checked against its schema. `engage-admin.v1.yaml` is exported from the FastAPI app in M1.5, with docs/API.md §2 as its specification.
- **Consequences:** The admin API is not frozen at G0, which is acceptable because no other team depends on it.

## D-074 `hireme_riders` stub document shape equals the Rider Profile API `RiderProfile` schema
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** D-013 says the stub has the shape of the future Rider API response, but DATA_MODEL §4.8 listed flat fields (`phone_e164`, `email`, `dnd_registered`, `referral_code`) while API.md §5.1 nests them (`contact.*`, `referral.*`) and adds `status`.
- **Options considered:** (a) flat stub with a mapping layer; (b) the stub stores exactly `RiderProfile`.
- **Decision:** (b). `RiderProfile` in `rider-api.v1.yaml` is canonical. The stub may add only `is_synthetic`, and `RiderDirectory` returns the document unchanged.
- **Consequences:** DATA_MODEL §4.8 is updated to match. Switching to the real API needs no field mapping.

## D-075 BigQuery tables partition by UTC date; IST days are filtered by timestamp range
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** The draft DDL used `PARTITION BY DATE(ts, 'Asia/Kolkata')`. BigQuery partition expressions accept `DATE(timestamp_column)` but not a time zone argument, so that DDL would fail.
- **Options considered:** (a) UTC date partitions; (b) an extra stored `*_date_ist` column to partition on; (c) hourly partitions.
- **Decision:** (a) for timestamp-partitioned tables. Queries for an IST day filter `ts >= TIMESTAMP('YYYY-MM-DD 00:00:00', 'Asia/Kolkata') AND ts < next day`, which prunes to at most two UTC partitions. Tables that already hold an IST `DATE` column (`snapshot_date`, `ledger_date`) keep partitioning on it. The validator rejects partition expressions that include a time zone.
- **Consequences:** An IST-day query scans up to two partitions, which is negligible at pilot volume.

## D-076 Contract validator doubles as the backend conformance kit
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** Backend handoff step HB1 promises a conformance test kit. Building a separate tool would duplicate the validation logic.
- **Decision:** `.venv/bin/python -m engage.tools.validate_contract --events FILE...` validates single envelopes, arrays, webhook bodies or NDJSON against the generated schema and prints every violation. `--all` runs the repository checks (Firebase naming limits, generated files current, schemas compile, doc examples, GA4 round trip, OpenAPI and their examples, playbooks, templates, Firestore, DDL).
- **Consequences:** HB1 hands over `contracts/` plus this tool. A standalone package for the backend team can come later if they do not use Python.

## D-077 GA4 export schema: core columns now, verified against a real export at M0.2
- **Date:** 2026-11-04 · **Status:** Proposed — pending client review · **Decided by:** AI (Claude Opus 5.5)
- **Context:** DATA_MODEL §3.1 asks for the official GA4 export schema verbatim. We have no access to a real export yet, and Google adds columns over time (for example `session_traffic_source_last_click`, `publisher`).
- **Decision:** `contracts/bigquery/ga4_events_schema.json` holds the stable core columns, including `event_params`, `user_properties`, `device`, `geo`, `app_info`, `traffic_source`, `ecommerce`, `items` and `collected_traffic_source`. At M0.2 it is diffed against a real export table (OQ-03) or Google's published schema, and missing columns are added as NULLABLE.
- **Consequences:** The engine reads only columns that are present, so queries on the real export are unaffected by columns we lack.
