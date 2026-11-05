# HireMe AI Engagement Engine: Synthetic (Dummy) Data Plan

| | |
|---|---|
| Status | Proposed, pending client review |
| Date | 2026-11-02 |
| Author | AI (Fable 5.1) |
| Related | [DATA_MODEL.md](DATA_MODEL.md) (schemas), [ARCHITECTURE.md](ARCHITECTURE.md), decisions D-011, D-012, D-015, D-016, D-048 |

## 1. Goals

The synthetic data must let us run **every v1 use case end to end** with no HireMe backend, and must be rich enough to *demonstrate* (not just exercise) the hard parts:

| Must demonstrate | How the data enables it |
|---|---|
| Riya's story (spec 1): fare check → 15 min → promo → booking | Scripted scenario `riya_b1` plus organic price-sensitive persona behaviour |
| B2 abandoned booking with timer and `cancel_if` | Abandon events where ~45 % of riders book on their own within 10 min (timer cancelled) and the rest do not |
| A2/A3 activation | Daily stream of new sign-ups; a share never ride without a nudge |
| E2-E5 lapse | Riders in each recency band at history end, plus a churn hazard that moves riders into lapse during the live run |
| D2 bad experience | Low ratings and support tickets that depend on ride quality (wait time, driver cancellations), and a retention effect of the apology credit |
| Uplift vs holdout | A **known ground-truth response model**: we know each persona's p0 and p1 per action, so the measured lift must match the truth within its confidence interval |
| "Don't discount riders who'd book anyway" | Personas with high p0 and little offer sensitivity (commuters) and personas who game discounts (discount-trained) |
| Budgets, caps, quiet hours, cooldowns | Enough volume to hit a deliberately small budget; users who trigger several playbooks per day; triggers at night |
| Fraud | A ring of multi-account users sharing devices and payment instruments |
| Model training (Phase 2) | Randomised exploration and holdout outcomes; features correlated with latent traits but not equal to them |

## 2. Where data goes

| Data | Destination | Loader | Volume (medium scale) |
|---|---|---|---|
| Reference (cities, zones, vehicles, calendar) | BigQuery `hireme_ref.*` | BigQuery load job from CSV | ~60 rows |
| 180 days of raw events, GA4 shape | BigQuery `analytics_999999999.events_YYYYMMDD` (one shard per IST day) | BigQuery load jobs from NDJSON (one file per day) | ≈ 6 M events, ≈ 8 GB |
| Backend stand-ins (rides, riders snapshot, redemptions) | BigQuery `hireme_backend_stub.*` | Load jobs | ≈ 520 k rides |
| Rider DB stand-in (contact, consent, tokens, wallet) | Firestore `hireme_riders` | Firestore Admin SDK `BulkWriter` | 20,000 docs |
| Engine config: settings, 12 playbooks, ~40 templates, budgets, segments | Firestore `engage_*` | **Firebase MCP server** (via Claude Code skill `seed-firestore`), with Admin SDK script as fallback | ~70 docs |
| Ground truth (personas, latent traits, true effects) | BigQuery `engage_sim.*` | Load jobs | 20,000 + ~200 rows |
| Feature snapshots, segments, base rates | BigQuery `engage_features.*` | Engine's own jobs run over the loaded history (not generated) | — |
| Profile snapshot for the engine | Firestore `engage_user_profile` | Engine's `profile-sync` job | 20,000 docs |
| Live events during a simulated run | Firestore `engage_events_live` + BigQuery `events_intraday_YYYYMMDD` | Simulator (Admin SDK + BigQuery streaming) | ≈ 33 k events per simulated day |

Why bulk loads do not go through MCP (D-011): MCP tools write one document or run one query per call; loading 20,000 rider documents or 6 M events one call at a time is slow and costly in tokens. MCP is used where it adds value: seeding and inspecting configuration documents, verifying loads (`firestore_query_collection`, BigQuery `execute_sql`), and answering ad-hoc questions during development. The exact Firebase MCP tool set (and whether it supports document writes in the installed version) is verified at M0.2; if it does not, configuration seeding uses the same Admin SDK script and MCP is used for verification only (risk R-04).

## 3. Geography and calendar

| City | city_id | Riders (medium) | Zones (examples, `zone_id` → type) |
|---|---|---|---|
| Noida (pilot) | 3 | 10,000 (50 %) | `NOI-S62` Sector 62 (business), `NOI-S18` Sector 18 (mall), `NOI-S15` (residential), `NOI-S137` (residential), `NOI-S76` (residential), `NOI-CC` City Centre (business), `NOI-S128` (residential), `NOI-GNW` Greater Noida West (residential), `NOI-BOT` Botanical Garden (railway/metro) |
| Delhi | 1 | 7,000 (35 %) | `DEL-CP` Connaught Place (business), `DEL-IGI-T3` IGI Airport T3 (airport), `DEL-IGI-T1` (airport), `DEL-NDLS` New Delhi Railway Station (railway), `DEL-SAKET` (mall), `DEL-HKV` Hauz Khas (nightlife), `DEL-LAJ` Lajpat Nagar (mall), `DEL-NP` Nehru Place (business), `DEL-KB` Karol Bagh (residential), `DEL-DWK` Dwarka (residential) |
| Gurgaon | 2 | 3,000 (15 %) | `GGN-CYBERHUB` Cyber Hub (business), `GGN-GCR` Golf Course Road (residential), `GGN-S29` Sector 29 (nightlife), `GGN-MGR` MG Road (mall), `GGN-UV` Udyog Vihar (business), `GGN-S56` (residential) |

Cross-city trips are allowed (Noida → Connaught Place, Gurgaon → IGI Airport), as in the spec's examples.

Fares: `fare = max(base, base + per_km × km + per_min × minutes) × surge`, with vehicle rates (INR): mini 50 + 12/km + 1/min; sedan 70 + 15/km + 1.5/min; prime 90 + 18/km + 2/min; suv 120 + 22/km + 2.5/min. Sector 62 → Connaught Place (≈ 18 km, 45 min) gives a mini fare of about ₹311-₹420 depending on surge, consistent with Riya's ₹420. Surge: 1.0 most of the time; 1.2-1.8 during 08:00-10:30 and 18:00-21:00 weekdays in business zones, rain days and festival evenings.

Time range: history **2026-05-05 00:00 IST to 2026-10-31 23:59 IST** (180 days) so 90-day dormant riders have prior rides. Live simulation starts at **2026-11-01 00:00 IST** (virtual clock) and covers Diwali (2026-11-08) for the F2 demo. Calendar events in `hireme_ref.calendar_events`: Independence Day, Raksha Bandhan, Ganesh Chaturthi, Dussehra (2026-10-20), Diwali (2026-11-08), plus 12 synthetic rain days (monsoon July-September) with demand × 1.3 and surge.

Diurnal pattern (weekday rides per hour share): peaks 08:00-10:00 and 18:00-21:00; weekend peak 12:00-14:00 and 19:00-23:00; ~6 % of rides between 22:00 and 05:00 (F4 and quiet-hours tests).

## 4. Personas

Each rider gets one persona and **latent traits** drawn from the persona's distributions. Behaviour (and therefore all features the engine sees) is generated from the latent traits; the engine never sees the persona or the traits (D-012).

Latent traits per rider: `ride_rate` (rides/week), `price_elasticity` e ∈ [0,1], `promo_affinity`, `fare_check_propensity` (checks per intended trip), `abandon_propensity`, `push_open_rate`, `email_open_rate`, `churn_hazard` (weekly), `service_tolerance` (how bad experience affects churn), `preferred_hour`, `home_zone`, `work_zone`, `weekend_bias`, `airport_rate`, `language`.

| # | Persona | Share | Riders (medium) | Behaviour summary | Primary playbooks exercised |
|---|---|---|---|---|---|
| P01 | `price_sensitive_explorer` ("Riya") | 18 % | 3,600 | 2-4 fare checks per ride, high abandon rate when surge > 1.2, 2-3 rides/month, elasticity 0.6-0.9 | B1, B2, B4, E2 |
| P02 | `daily_commuter` | 15 % | 3,000 | 8-10 rides/week, same route ±1 h on weekdays, low elasticity 0.05-0.2, high p0 | E1 (P3), C3, B2 "reminder only" |
| P03 | `weekend_leisure` | 12 % | 2,400 | 70-90 % rides Fri-Sun, malls/nightlife, medium elasticity | F5, B1, E2 |
| P04 | `airport_traveller` | 6 % | 1,200 | 2-6 airport rides per 90 days, scheduled rides early morning (05:00-07:00), sedan/prime | C1, C2, C5, B6 |
| P05 | `new_not_activated` | 10 % | 2,000 | Signed up in last 30 days of history, 0 rides; 35 % would never ride without a nudge; responds to welcome offer | A2, A3, A4, A5 |
| P06 | `casual_regular` | 14 % | 2,800 | 1-3 rides/month, mixed purposes, medium elasticity | B2, D1, D5 |
| P07 | `lapsing` | 6 % | 1,200 | Previously weekly, last ride 7-14 days before history end | E2, E5 |
| P08 | `lapsed` | 7 % | 1,400 | Last ride 30-89 days before history end | E3 |
| P09 | `dormant` | 6 % | 1,200 | Last ride ≥ 90 days before history end | E4, E6 |
| P10 | `unhappy_recent` | 3 % | 600 | A bad ride (driver cancel, long wait, rating ≤ 2 or ticket) in the last 7 days | D2 |
| P11 | `discount_trained` | 2.5 % | 500 | Books almost only with codes; abandons and waits for a nudge; true p0 without offer moderate, but offers cause **no incremental** rides (they would book later anyway) | Guardrail "no promo to discount-trained" |
| P12 | `fraud_ring` | 0.5 % | 100 | 100 accounts on 25 devices and 12 payment instruments; sign up, redeem welcome codes, few full-fare rides | Fraud rules, A2 block |
| | **Total** | 100 % | **20,000** | | |

Channel reachability (all personas, with persona tweaks):

| Attribute | Distribution |
|---|---|
| Platform | Android 78 %, iOS 22 % |
| Push token present / stale | 92 % present; 5 % of present tokens stale (`UNREGISTERED`) |
| Consent push / email / SMS / WhatsApp | 85 % / 60 % / 75 % / 40 % (email only if `has_email`, 70 %) |
| Phone on DND | 18 % |
| Language | en 70 %, hi 30 % (Noida/Delhi), en 85 % Gurgaon |
| Push open rate (latent) | Beta(2, 6) mean ≈ 0.25; price-sensitive and new users higher (0.35) |

## 5. Ground-truth response model (built-in uplift)

When the engine sends a message, the **rider responder** decides what the synthetic rider does using these probabilities (and logs the draw in `engage_sim.response_ledger`). Holdout users receive nothing, so their behaviour follows the organic process only. This makes the true effect known.

For a trigger context c (playbook family) and action a (none, reminder, 10 %, 15 %, 20 %, flat ₹30/₹50/₹100):

```
p_convert(user, c, a) = clip( p0_persona(c) × m(user)                              # organic conversion within window
                              + I[a≠none] × open(user, channel) × lift(c, a, e(user)) , 0, 0.95 )
lift(c, reminder, e)   = r_c                                                         # reminder effect
lift(c, x%, e)         = r_c + L_c × e × (1 − exp(−x / 10))                          # diminishing returns in discount x
```

`m(user)` ∈ [0.7, 1.3] is a per-user multiplier derived from latent traits (so features carry signal); `e` is the user's price elasticity. Discount-trained users: `lift = 0` for every action, but their organic p0 is raised only *after* a 6-hour delay (they book later anyway), and their `promo_ride_share` is high: the uplift model must learn to give them nothing.

Calibrated values for the main contexts (persona means; "open" already folded in at the persona's mean open rate):

| Context (playbook) | Persona | p0 (no message) | Reminder | 10 % | 15 % | 20 % | Notes |
|---|---|---|---|---|---|---|---|
| B2 abandoned booking, 24 h | P01 price-sensitive | 0.08 | 0.11 | 0.17 | 0.20 | 0.21 | Spec example: 9 % holdout → 16 % treated |
| | P02 commuter | 0.45 | 0.49 | 0.50 | 0.50 | 0.51 | Reminder is enough |
| | P06 casual | 0.14 | 0.17 | 0.20 | 0.22 | 0.22 | |
| | P11 discount-trained | 0.30 | 0.30 | 0.30 | 0.30 | 0.30 | Zero uplift ("would book anyway") |
| B1 fare check no booking, 24 h | P01 | 0.10 | 0.12 | 0.18 | 0.21 | 0.22 | Riya |
| | P03 weekend | 0.18 | 0.21 | 0.24 | 0.25 | 0.25 | |
| A2 + A3 activation, 7 d | P05 | 0.38 | 0.45 | — | — | — | 50 % welcome code → 0.58 |
| E2 lapsing, 7 d | P07 | 0.22 | 0.27 | 0.33 | — | — | |
| E3 lapsed, 7 d | P08 | 0.05 | 0.06 | — | — | 0.10 | 25 % → 0.12, 30 % → 0.13 |
| E4 dormant, 7 d | P09 | 0.01 | 0.015 | — | — | — | ₹100 credit → 0.04 |
| D2 bad experience, 30-day retention | P10 | 0.40 (active again in 30 d) | 0.44 (apology only) | — | — | — | Apology + ₹75 credit → 0.55 |
| B5 no driver found, 7 d | all | 0.30 | 0.32 | — | — | — | ₹30 flat → 0.38 |

Side effects (so guardrails matter):

| Effect | Rule |
|---|---|
| Fatigue | Each marketing message beyond 1/day or 3/week multiplies that user's subsequent open rate by 0.8 for 7 days and adds 0.5 % opt-out probability per extra message (so turning off caps visibly raises the opt-out rate in reports). |
| Quiet-hours annoyance | Marketing between 22:00 and 08:00: open rate × 0.3 and opt-out probability + 2 %. |
| Bad-experience sensitivity | Marketing to P10 within 48 h of a bad ride: churn hazard × 1.5. |
| Code expiry | Conversion with a code only counts if the simulated booking time is before `valid_to`; otherwise the rider books at full price with probability p0 only. |

Conversion timing: given a conversion, the delay after the message is drawn from a log-normal with median 9 min for intent playbooks (B1/B2) and 26 h for win-back (E), matching the attribution windows.

## 6. Volumes and sizing check

Medium scale (default for demos), per simulated 30 days in Noida only:

| Trigger | Expected triggers / 30 d (Noida) | Needed for a 3-point lift at 80 % power (10 % holdout) |
|---|---|---|
| `booking_abandoned` (B2) | ≈ 9,500 | ≈ 8,000 eligible → reached in ~26 days |
| `fare_check` without booking in 15 min (B1) | ≈ 14,000 | reached |
| `sign_up` (A2/A3) | ≈ 1,800 | Detects the ~13-point activation lift easily (needs ≈ 600) |
| Lapsing/lapsed/dormant batch candidates | ≈ 600 / 700 / 600 | E2 5-point lift detectable; E3/E4 effects reported with wide CI (honest result) |
| `ride_rated ≤ 2` or ticket (D2) | ≈ 450 | 15-point retention lift detectable (needs ≈ 350) |

Scale presets (`--scale`):

| Preset | Riders | History days | Events (approx.) | Use |
|---|---|---|---|---|
| `tiny` | 500 | 30 | 25 k | Unit/scenario tests, CI, Firestore emulator |
| `small` | 2,000 | 180 | 600 k | Developer laptops |
| `medium` | 20,000 | 180 | 6 M | Demos, gate evidence, model training |
| `large` | 100,000 | 180 | 30 M | Load test (Phase 3) |

Cost guard: medium history ≈ 8 GB in BigQuery; daily feature jobs scan only the last 90 days of partitions (≈ 4 GB/day, ≈ 120 GB/month, inside the 1 TB free query tier). The dev Firebase project must be on the Blaze plan because Spark limits (20 k Firestore writes/day) are far below the bulk load (OQ-04).

## 7. Generator design (`sim/generator`)

1. **Config**: `sim/personas.yaml` (shares, latent distributions, response model), `sim/geo.yaml` (cities, zones, fare rates), `sim/calendar.yaml`; `--seed` makes runs reproducible.
2. **Population**: create riders (ids `u_10000`…), assign persona, latent traits, home/work zones, device hash (fraud ring shares), payment fingerprints, consent, tokens, language; first names from a curated list of common Indian first names (no real people), phones in a reserved synthetic range (`+91999001xxxx`), emails `@example.test` (RFC 2606 reserved domain, can never be delivered).
3. **Organic process** (day by day, per rider): a non-homogeneous Poisson process for "trip intents" from `ride_rate`, weekday/hour patterns, calendar multipliers. Each intent produces a session: `app_open` → 1+ `fare_check` (count from `fare_check_propensity`, more under surge) → maybe `vehicle_selected` → `booking_started` → either `booking_abandoned` (step drawn) or `ride_booked` → (`no_driver_found` with zone/hour supply probability → retry or give up) → `ride_started` → `ride_completed` (or `ride_cancelled`) → `ride_rated` (55 %) and occasionally `support_ticket_opened`; `payment_failed` (2 % card/UPI) → retry. Scheduled rides for P04. `wallet_topup`, `referral_shared`, `profile_completed`, `location_permission` at plausible rates. Riders lapse according to `churn_hazard`; organic returns occur with persona-specific probability.
4. **Historical engine absence**: in history, no engine messages exist (the engine did not exist), except an optional `--prepilot-experiment` flag that simulates a randomised manual campaign in Sept-Oct (B2 and E2 with random rungs and a 20 % holdout) to bootstrap Phase 2 model training. Default: off; Phase 2 trains on logs produced by Phase 1 simulated runs (realistic, D-019).
5. **Emit**: each event as a canonical envelope → converted to the GA4 row (`ga4_mapping.py`, shared with the engine's `Ga4BigQueryPoll`, so a round-trip test proves both directions) → NDJSON per IST day. Backend stubs (`rides`, `riders_snapshot`) written from the same state.
6. **Ground truth**: `engage_sim.personas`, `engage_sim.true_effects`.

GA4 fidelity details: `event_date` in Asia/Kolkata; `event_timestamp` microseconds; `user_pseudo_id` stable per install (a reinstall creates a new pseudo id for 3 % of users); `device.operating_system` `Android`/`iOS`; `app_info.version` drifts across versions over time; `geo.city` from the rider's city (GA4 derives it from IP; ours is clean); `privacy_info.analytics_storage = "Yes"`; client events have small device-clock skew (±30 s) and 2 % arrive late (batched up to 2 h, visible as `event_server_timestamp_offset`), so late-event handling is exercised.

## 8. Loading

| Step | Tool | Command (to be implemented in M0.3) | Verification |
|---|---|---|---|
| 1 Create datasets/tables | `bq`-equivalent via Python client, DDL from `contracts/bigquery` | `python -m sim.loaders.bq_ddl --project hireme-engage-dev` | BigQuery MCP: list tables |
| 2 Load reference | BigQuery load job | `python -m sim.loaders.bq_load --what ref` | row counts |
| 3 Generate history | generator | `python -m sim.generator --scale medium --seed 42 --out data/gen/2026-11-02/` | file counts, size |
| 4 Load events | BigQuery load jobs (NDJSON → `events_YYYYMMDD`) | `python -m sim.loaders.bq_load --what events --dir …` | `sql/checks/*.sql` (section 10) |
| 5 Load stubs and truth | load jobs | `--what stubs,truth` | counts |
| 6 Load rider stub | Admin SDK `BulkWriter` | `python -m sim.loaders.fs_riders` | Firebase MCP: `firestore_query_collection hireme_riders limit 5`; count |
| 7 Seed engine config | Firebase MCP (skill `seed-firestore`) | playbooks/*.json, templates/*.yaml, settings, budgets | MCP read-back + JSON Schema validation |
| 8 Build features | engine jobs | `python -m engage.jobs features-daily --backfill 2026-08-01..2026-10-31` | feature sanity checks |
| 9 Profile sync | engine job | `python -m engage.jobs profile-sync` | Firestore count = riders |

All loader scripts are idempotent (`WRITE_TRUNCATE` per shard; Firestore `set` with merge) and tag rows with `generation_id`.

## 9. Live simulator (`sim/replayer`, `sim/responder`)

| Feature | Design |
|---|---|
| Virtual clock | `sim_runs/{run_id}.clock = {virtual_now, speed, state}`; the engine reads the same clock in `ENGAGE_CLOCK=virtual` mode (D-016). Speed 1× (real time) to 120×. At 60×, a 10-minute B2 timer fires after 10 real seconds; a simulated day takes 24 minutes; a 30-day pilot ≈ 12 hours. |
| Event emission | The same organic process as the generator, run forward from the history end state; each event is written to `engage_events_live` (Admin SDK `create`) and streamed to `events_intraday_YYYYMMDD`; at virtual midnight the intraday table is copied into `events_YYYYMMDD` (mimicking GA4's daily export). |
| Rider responder (closed loop) | Polls `mock_deliveries` (and push/email/SMS delivery callbacks) → for each delivered message, draws open/convert from the ground-truth model (§5) → emits `notification_opened`, `promo_viewed`, `promo_applied`, `ride_booked` with the deep-link `engage_message_id`, calls mock Promo API `apply`/`redeem`; also emits opt-outs (`consent_changed`) from fatigue. The responder only reads what a real phone would see (the delivered message), never engine internals. |
| Scenario injection | Scripted, deterministic event sequences for tests and demos (below), injected at a virtual time with a fixed user. |
| Modes | `--mode organic` (population runs), `--mode scenario --name riya_b2`, `--mode mixed`. |
| Safety | Simulator refuses to run unless the project id ends with `-dev` and `ENGAGE_ENV=dev`. |

Scripted scenarios (each has an automated assertion in `tests/scenario/`):

| Scenario | Script | Expected engine behaviour |
|---|---|---|
| `riya_b1` | 18:10 `fare_check` NOI-S62 → DEL-CP ₹420 by a high price-sensitivity user; no booking | 18:25 B1 decision: 15 % code, push; message text contains Connaught Place; code inserted by code |
| `riya_b2` | 18:10 `booking_abandoned` step=confirm; no booking | 18:20 B2: offer 10-20 %, push, promo valid 30 min; spec numbers p0≈0.22, p1≈0.48 (heuristic) |
| `b2_cancelled_by_booking` | abandon, then `ride_booked` at +6 min | Timer `cancelled`, no decision |
| `b2_late_cancel_event` | abandon; `ride_booked` with `event_ts` +6 min but delivered +12 min | Fire-time recheck or post-send attribution; documented outcome: decision `cancelled_by_event` if recheck sees it, else sent and flagged |
| `b2_double_abandon` | two abandons 4 min apart | First timer `superseded`, one decision |
| `quiet_hours_b2` | abandon at 23:10 | Marketing B2 skipped `quiet_hours_skip` (max_defer 0) |
| `c2_airport_reminder` | `ride_scheduled` at 21:00 for 05:30 next day | Reminders at 04:30 and 05:15, sent despite quiet hours (transactional) |
| `c2_cancelled` | schedule, then `scheduled_ride_cancelled` | Both reminder timers cancelled; C4 path (Phase 3) |
| `a2_a3_activation` | `sign_up`; no ride for 48 h | A2 welcome code at once; A3 reminder at +48 h referencing the same code |
| `a2_fraud_repeat_device` | `sign_up` from a device already used by 3 accounts | A2 skipped `fraud_flag` |
| `d2_bad_rating` | `ride_rated` = 1 | D2 apology + ₹75 code; marketing suppressed 48 h (a B2 trigger 2 h later is skipped `suppressed_bad_experience`) |
| `budget_exhaustion_b2` | set B2 Noida daily budget to ₹500; burst of 40 abandons | Sends stop once committed + redeemed reaches ₹500; later decisions `budget_exhausted`; alert at 80 % |
| `freq_cap` | same user triggers B1, B2, E2 on one day | One marketing send; others `freq_cap_daily` or `superseded_exclusive_group` |
| `kill_switch_midflight` | activate kill switch while 20 messages are queued | No marketing sent after activation; transactional C2 still sent |
| `consent_revoked_midtimer` | `consent_changed push=false` during a B2 timer | Fallback to SMS if consented, else `no_consent` |
| `duplicate_events` | same `event_uuid` written 3 times | One timer, one decision |
| `promo_api_outage` | mock Promo API 100 % 503 for 5 min | Retries, then downgrade to reminder or skip per playbook; no duplicate codes after recovery |
| `fcm_unregistered` | user with stale token | Push permanent failure → SMS fallback (B2 channels push, sms) |
| `discount_trained_user` | P11 user abandons | Reminder only (`discount_trained_downgrade`) |
| `holdout_user` | user whose hash falls in holdout | Ghost decision `holdout`, nothing delivered (assert `mock_deliveries` empty) |

## 10. Validation checks (`sql/checks/`, run after every load and nightly)

| # | Check | Pass criterion |
|---|---|---|
| V1 | Every event has `event_uuid`, `contract_version`, required params per event schema | 100 % (sample 1 % for JSON Schema; SQL null checks on all) |
| V2 | `event_uuid` unique per table | 0 duplicates |
| V3 | GA4 round trip: envelope → GA4 row → envelope | byte-identical params on 10 k sample |
| V4 | Funnel ratios | fare_check → booked 30-45 %; booked → completed 85-92 %; abandon share of booking_started 20-30 % |
| V5 | Persona sanity | commuters' weekday share > 0.8; weekend riders' Fri-Sun share > 0.7; dormant riders have no rides in the last 90 days |
| V6 | Recency bands at history end | lapsing/lapsed/dormant counts within ±5 % of target |
| V7 | Fares | ₹ distribution by vehicle/distance within configured bounds; Sector 62 → CP mini median ₹330-₹430 |
| V8 | Time zones | `event_date` equals the IST date of `event_timestamp` for 100 % of rows |
| V9 | Consent and reachability shares | within ±2 points of config |
| V10 | Fraud ring | 25 devices with ≥ 3 accounts; flagged by `fraud_flags_daily` |
| V11 | No leakage | Engine service account cannot read `engage_sim` (IAM test) |
| V12 | Ground-truth recovery (after a simulated run) | Measured B2 lift in Noida within the 95 % CI of the true lift computed from `engage_sim.response_ledger`; same for A2, D2 |
| V13 | Firestore loads | `hireme_riders` count = riders; random 100 docs match BigQuery `riders_snapshot` |
| V14 | PII hygiene | All phones in synthetic range, all emails `@example.test` |

## 11. Calibration with real data (when available)

We ask HireMe for aggregate statistics only (OQ-05): rides per active rider per month, fare check → booking conversion, abandon rate by step, rating distribution, share of rides with promo, payment method mix, city split. These update `personas.yaml` without moving any personal data. When the real GA4 export is linked, the same `sql/checks` run on real data and highlight gaps between synthetic and real distributions.
