# Open Questions for HireMe / Grepix

| | |
|---|---|
| Date | 2026-11-02 |
| Author | AI (Fable 5.1) |
| How to use | Each question has our **default assumption** (the decision we have taken so work can proceed) and what it **blocks**. Answers update the linked decision in [../decision.md](../decision.md) (Status → Accepted, or a superseding entry). |

**Status (2026-11-09):** the client reviewed the checklist and accepted our default for every question except OQ-06, which they answered (D-086). All decisions D-001 to D-086 are Accepted. Open questions: OQ-41, OQ-42 (added 2026-11-17).

Priority: **P1** = blocks Phase 0/1 or the backend handoff; **P2** = needed before the real pilot; **P3** = needed for Phase 3.

## G. Open

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-41 | Measurement Protocol for Firebase apps needs the rider's app instance id (`app_instance_id`, our `user_pseudo_id`) for every server event sent to GA4 (D-086). How will the backend get it? | The app sends its Firebase app instance id with each booking and sign-up API call; the backend stores the latest one per rider and uses it for Measurement Protocol. Events with no known id go only to the webhook. This makes `user_pseudo_id` effectively required for server events sent to GA4 (D-069 stays as is for the webhook). | GA4 copy of server events (HB2) | P2 | D-069, D-086 |
| OQ-42 | Fast path transport: does HireMe want option G (backend → Kafka, Valkey) over option E (direct endpoint) or F (Firestore write)? Who operates Kafka/Valkey, which provider and region, and is the post-`fare_check` wait 15 min (spec) or 180 s? | Kafka accepted only as a transport into the existing inbox with durable timers (not key-expiry triggers); B1 keeps 15 min and 180 s is tested as an experiment arm; no real rider data to any new provider without approval | Fast path for B1/B2 on real riders | P2 | D-001, D-095 |

## Closed

| ID | Question | Answer | Date | By | Decision |
|---|---|---|---|---|---|
| OQ-01 | Will the HireMe backend build the dual-logging webhook (`POST /engage/v1/events`, spec §3 "data freshness", §11)? When? | Default accepted: Yes, during track HB (W5-W8); until then real-data B1/B2 would run on GA4 polling with minutes of delay | 2026-11-09 | Client | D-001 |
| OQ-02 | Besides the Firebase MCP server, may engine services access the Firebase/GCP project directly with service accounts (Firestore Admin SDK, BigQuery client)? | Default accepted: Yes | 2026-11-09 | Client | D-010 |
| OQ-03 | Is Firebase Analytics → BigQuery export enabled for the real app? Daily, streaming, or both? Property id and reporting time zone? | Default accepted: Not yet; will be enabled with streaming; time zone Asia/Kolkata | 2026-11-09 | Client | D-003, D-059 |
| OQ-04 | Who creates and pays for the dev project, and is the Blaze plan needed? | Start on the free tier (Firebase Spark + BigQuery sandbox), created by us, in asia-south1. Move to a client-paid Blaze project once the client signs and the service works, at the latest before full-scale data and the pilot. | 2026-11-09 | Project lead | D-082, D-083 |
| OQ-05 | Can HireMe share aggregate statistics to calibrate the synthetic data? | Not needed for now: we generate the dummy data ourselves at a free-tier scale (`demo`: 3,000 riders, 45 days) sized to exercise every MVP playbook and show holdout lift. Persona parameters stay as calibrated from the spec; real aggregates can refine them at the Blaze switch. | 2026-11-09 | Project lead | D-083 |
| OQ-06 | Will server-side events also be sent to GA4 via the Measurement Protocol, or only via the webhook? | Both: server events go to GA4 via the Measurement Protocol (free export keeps all data) and to the engine webhook for real-time playbooks; deduped by `event_uuid`. | 2026-11-09 | Client | D-003, D-042, D-086 |
| OQ-07 | Is `app_open` logged as a custom event with params today? Are current event names exactly as in spec §3? | Default accepted: We will treat all spec events as custom events with our params | 2026-11-09 | Client | D-004 |
| OQ-08 | Promo API: actual base path, auth, request fields, `city_ids` values, idempotency key support, code uniqueness rules, usage endpoint, deactivate, redemption webhook payload, shared campaign codes with per-user limits? | Default accepted: Spec §8.2 sample + our additions (API.md §6.1) | 2026-11-09 | Client | D-014, D-025, D-038 |
| OQ-09 | Grepix channel APIs (push, SMS, email, WhatsApp, in-app): contracts, delivery receipts, costs, rate limits? Can we call FCM directly? | Default accepted: Our neutral gateway contract; FCM HTTP v1 native | 2026-11-09 | Client | D-066 |
| OQ-10 | Can the backend provide a Rider Profile API (contact, consent, push tokens, wallet, device hash, payment fingerprints) and consent write-back? Auth method? | Default accepted: Yes, as in API.md §5 with OIDC or API key + mTLS | 2026-11-09 | Client | D-013, D-053 |
| OQ-11 | Pre-login identity for A1: can the backend map an app instance / FCM token or phone number to an incomplete sign-up? | Default accepted: No; A1 deferred | 2026-11-09 | Client | D-047 |
| OQ-12 | Is there (or will there be) a `payment_succeeded` / payment-recovered event for B8? | Default accepted: Use `ride_completed` with the same `ride_id` as interim | 2026-11-09 | Client | DATA_MODEL §5.4 |
| OQ-13 | Wallet credit API for D2 ("₹75 added to your wallet") and B5? | Default accepted: Not available; use flat user-locked promo codes | 2026-11-09 | Client | D-065 |
| OQ-14 | Can the app support the deep link contract (auto-apply code, open booking with quote, attach `engage_message_id`)? | Default accepted: Yes, at handoff | 2026-11-09 | Client | D-063 |
| OQ-15 | Real city ids and zone taxonomy used by HireMe (is Noida `city_id 3`)? | Default accepted: Our reference table; mapping at handoff | 2026-11-09 | Client | D-037 |
| OQ-16 | Confirm success metric targets (spec §1 "to be confirmed"): +15 % booking recovery, +20 % activation, +10 % 30-day retention, positive ROI, opt-out < 1 %/month | Default accepted: As in spec | 2026-11-09 | Client | D-060 |
| OQ-17 | Value basis for the uplift rule: gross fare (spec wording) or HireMe margin/commission? Typical take rate? | Default accepted: Gross fare, configurable to margin | 2026-11-09 | Client | D-030 |
| OQ-18 | Pilot budgets: Noida monthly total, per playbook daily/monthly; alert threshold; global caps (₹100 per ride, ₹300 per user per month, 4 codes per user per month) | Default accepted: Spec examples (B2 ₹5,000/day, ₹100,000/month) | 2026-11-09 | Client | D-020, D-021 |
| OQ-19 | Discount ladders and validity per MVP playbook (DATA_MODEL §5.4) acceptable? | Default accepted: As proposed | 2026-11-09 | Client | D-036 |
| OQ-20 | Holdout: 10 % per playbook OK? Should we run a global holdout (2-5 %) to measure total engine lift? | Default accepted: 10 % per playbook; global 0 % in pilot | 2026-11-09 | Client | D-018, D-056 |
| OQ-21 | Message classes: confirm B3, B5, D2 as "service" (not capped as marketing) and quiet hours applying to service messages | Default accepted: As in D-023 | 2026-11-09 | Client | D-023, D-024 |
| OQ-22 | Frequency cap "3 per week": rolling 7 days or calendar week? | Default accepted: Rolling 7 days | 2026-11-09 | Client | D-022 |
| OQ-23 | Kill switch: should it also stop transactional messages (payment failed, pickup reminders)? | Default accepted: No, unless scope "all" is chosen | 2026-11-09 | Client | D-027 |
| OQ-24 | Attribution windows (24 h intent, 7 d win-back, 30 d D2 retention) OK? | Default accepted: Yes | 2026-11-09 | Client | D-031 |
| OQ-25 | Who approves what (marketing vs super vs city admin) and expected approval turnaround for cohort batches and campaigns? | Default accepted: Marketing or super for all; city admins for their cities | 2026-11-09 | Client | D-028 |
| OQ-26 | Fraud and discount-trained thresholds; action on flags (block promos only, or manual review queue)? | Default accepted: D-046 thresholds; block promos, allow reminders | 2026-11-09 | Client | D-046 |
| OQ-27 | E4 "final email; then stop marketing": permanent stop? Does an organic return ride re-enable marketing? | Default accepted: Stop 180 days or until organic ride | 2026-11-09 | Client | DATA_MODEL §5.4 |
| OQ-28 | Is iOS-only absence of `app_remove` acceptable for E6 (Android only)? | Default accepted: Yes | 2026-11-09 | Client | — |
| OQ-29 | TRAI DLT: registered PE id, sender header, who registers the 12 playbook templates (en/hi), lead time? | Default accepted: HireMe/Grepix registers; we supply texts in W5 | 2026-11-09 | Client | D-033 |
| OQ-30 | DPDP: consent notice wording and purposes for marketing personalisation; process for data-principal requests (access/erasure) reaching the engine | Default accepted: Backend owns consent UX; engine provides erasure job | 2026-11-09 | Client | D-053 |
| OQ-31 | Anthropic API usage: is sending first name, language and area names to the LLM acceptable? Any data-residency requirement for LLM calls? Enterprise data terms in place? | Default accepted: Acceptable with minimisation; no residency requirement for LLM | 2026-11-09 | Client | D-032, D-035 |
| OQ-32 | Retention periods for decisions, messages and audit logs | Default accepted: Firestore 180 d / 400 d audit, BigQuery indefinite (pseudonymised) | 2026-11-09 | Client | DATA_MODEL §4.1 |
| OQ-33 | Hosting in the client's GCP project on Cloud Run, region asia-south1? Who operates it (Grepix ops)? | Default accepted: Yes; Grepix ops with our runbooks | 2026-11-09 | Client | D-051 |
| OQ-34 | Is Python acceptable for the engine instead of Node.js (spec §8)? | Default accepted: Yes (HTTP contracts isolate the backend) | 2026-11-09 | Client | D-009 |
| OQ-35 | Console embedding into the existing HireMe admin panel: route package, module federation or iframe? SSO with existing admin accounts? | Default accepted: Standalone now, packaged for embedding later; Firebase Auth | 2026-11-09 | Client | D-039 |
| OQ-36 | White label: is a `brand_id` dimension (separate from city) needed in v1 data? | Default accepted: Not in v1; added in Phase 3 | 2026-11-09 | Client | — |
| OQ-37 | Pilot timing: real Noida pilot target date and any holiday freeze (Christmas/New Year)? | Default accepted: Real pilot from W12 (25 Jan 2027) | 2026-11-09 | Client | — |
| OQ-38 | Can the backend include the rider's Firebase app instance id (`user_pseudo_id`) in server events (`ride_booked`, `ride_completed`, ...)? | Default accepted: Optional; joins use `user_id` | 2026-11-09 | Client | D-069 |
| OQ-39 | Does the HireMe app already set Firebase user properties or log events with names that clash with the contract (for example an existing `app_open`, `city`, `language`), and what does it log today? | Default accepted: No clashes; to be checked against the live Firebase project | 2026-11-09 | Client | D-067, D-070 |
| OQ-40 | Does the Promo API support campaign codes that are not user-locked (`user_id: null`, `usage_limit` > 1, several `city_ids`), as needed for F2 (DIWALI20)? | Default accepted: Yes | 2026-11-09 | Client | D-038 |
