# Open Questions for HireMe / Grepix

| | |
|---|---|
| Date | 2026-11-02 |
| Author | AI (Fable 5.1) |
| How to use | Each question has our **default assumption** (the decision we have taken so work can proceed) and what it **blocks**. Answers update the linked decision in [../decision.md](../decision.md) (Status → Accepted, or a superseding entry). |

Priority: **P1** = blocks Phase 0/1 or the backend handoff; **P2** = needed before the real pilot; **P3** = needed for Phase 3.

## A. Data sources and access

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-01 | Will the HireMe backend build the dual-logging webhook (`POST /engage/v1/events`, spec §3 "data freshness", §11)? When? | Yes, during track HB (W5-W8); until then real-data B1/B2 would run on GA4 polling with minutes of delay | Real pilot of B1/B2 | P1 | D-001 |
| OQ-02 | Besides the Firebase MCP server, may engine services access the Firebase/GCP project directly with service accounts (Firestore Admin SDK, BigQuery client)? | Yes | Everything | P1 | D-010 |
| OQ-03 | Is Firebase Analytics → BigQuery export enabled for the real app? Daily, streaming, or both? Property id and reporting time zone? | Not yet; will be enabled with streaming; time zone Asia/Kolkata | Real history, GA4 poller | P1 | D-003, D-059 |
| OQ-04 | Who creates and pays for the dev project `hireme-engage-dev` (Blaze plan needed for volumes and BigQuery linking)? Region asia-south1 OK? | Client creates it, grants us access; asia-south1 | M0.2 | P1 | D-012, D-051 |
| OQ-05 | Can HireMe share aggregate statistics (rides per rider, fare-check conversion, abandon rate by step, rating distribution, promo share, payment mix, city split) to calibrate the synthetic data? | Yes, aggregates only | Data realism (R-02) | P2 | D-048 |
| OQ-06 | Will server-side events also be sent to GA4 via the Measurement Protocol, or only via the webhook? | Only via webhook; GA4 holds client events | Real-data SQL joins | P2 | D-003, D-042 |

## B. Contract and backend handoff

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-07 | Is `app_open` logged as a custom event with params today? Are current event names exactly as in spec §3? | We will treat all spec events as custom events with our params | M0.1 | P1 | D-004 |
| OQ-08 | Promo API: actual base path, auth, request fields, `city_ids` values, idempotency key support, code uniqueness rules, usage endpoint, deactivate, redemption webhook payload, shared campaign codes with per-user limits? | Spec §8.2 sample + our additions (API.md §6.1) | M1.3, HB3 | P1 | D-014, D-025, D-038 |
| OQ-09 | Grepix channel APIs (push, SMS, email, WhatsApp, in-app): contracts, delivery receipts, costs, rate limits? Can we call FCM directly? | Our neutral gateway contract; FCM HTTP v1 native | HB4 | P1 | D-066 |
| OQ-10 | Can the backend provide a Rider Profile API (contact, consent, push tokens, wallet, device hash, payment fingerprints) and consent write-back? Auth method? | Yes, as in API.md §5 with OIDC or API key + mTLS | HB3 | P1 | D-013, D-053 |
| OQ-11 | Pre-login identity for A1: can the backend map an app instance / FCM token or phone number to an incomplete sign-up? | No; A1 deferred | A1 | P3 | D-047 |
| OQ-12 | Is there (or will there be) a `payment_succeeded` / payment-recovered event for B8? | Use `ride_completed` with the same `ride_id` as interim | B8 attribution | P2 | DATA_MODEL §5.4 |
| OQ-13 | Wallet credit API for D2 ("₹75 added to your wallet") and B5? | Not available; use flat user-locked promo codes | D2 wording | P2 | D-065 |
| OQ-14 | Can the app support the deep link contract (auto-apply code, open booking with quote, attach `engage_message_id`)? | Yes, at handoff | Attribution precision, spec §4 step 7 | P2 | D-063 |
| OQ-15 | Real city ids and zone taxonomy used by HireMe (is Noida `city_id 3`)? | Our reference table; mapping at handoff | HB2 | P2 | D-037 |

## C. Business rules and targets

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-16 | Confirm success metric targets (spec §1 "to be confirmed"): +15 % booking recovery, +20 % activation, +10 % 30-day retention, positive ROI, opt-out < 1 %/month | As in spec | Gate criteria | P1 | D-060 |
| OQ-17 | Value basis for the uplift rule: gross fare (spec wording) or HireMe margin/commission? Typical take rate? | Gross fare, configurable to margin | Offer economics | P1 | D-030 |
| OQ-18 | Pilot budgets: Noida monthly total, per playbook daily/monthly; alert threshold; global caps (₹100 per ride, ₹300 per user per month, 4 codes per user per month) | Spec examples (B2 ₹5,000/day, ₹100,000/month) | M1.6 | P1 | D-020, D-021 |
| OQ-19 | Discount ladders and validity per MVP playbook (DATA_MODEL §5.4) acceptable? | As proposed | M1.6 | P1 | D-036 |
| OQ-20 | Holdout: 10 % per playbook OK? Should we run a global holdout (2-5 %) to measure total engine lift? | 10 % per playbook; global 0 % in pilot | Measurement | P2 | D-018, D-056 |
| OQ-21 | Message classes: confirm B3, B5, D2 as "service" (not capped as marketing) and quiet hours applying to service messages | As in D-023 | Guardrails | P2 | D-023, D-024 |
| OQ-22 | Frequency cap "3 per week": rolling 7 days or calendar week? | Rolling 7 days | Guardrails | P2 | D-022 |
| OQ-23 | Kill switch: should it also stop transactional messages (payment failed, pickup reminders)? | No, unless scope "all" is chosen | Guardrails | P2 | D-027 |
| OQ-24 | Attribution windows (24 h intent, 7 d win-back, 30 d D2 retention) OK? | Yes | Reports | P2 | D-031 |
| OQ-25 | Who approves what (marketing vs super vs city admin) and expected approval turnaround for cohort batches and campaigns? | Marketing or super for all; city admins for their cities | M1.5 | P2 | D-028 |
| OQ-26 | Fraud and discount-trained thresholds; action on flags (block promos only, or manual review queue)? | D-046 thresholds; block promos, allow reminders | Guardrails | P2 | D-046 |
| OQ-27 | E4 "final email; then stop marketing": permanent stop? Does an organic return ride re-enable marketing? | Stop 180 days or until organic ride | E4 | P2 | DATA_MODEL §5.4 |
| OQ-28 | Is iOS-only absence of `app_remove` acceptable for E6 (Android only)? | Yes | E6 (Phase 3) | P3 | — |

## D. Compliance, security, AI

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-29 | TRAI DLT: registered PE id, sender header, who registers the 12 playbook templates (en/hi), lead time? | HireMe/Grepix registers; we supply texts in W5 | SMS in pilot | P1 | D-033 |
| OQ-30 | DPDP: consent notice wording and purposes for marketing personalisation; process for data-principal requests (access/erasure) reaching the engine | Backend owns consent UX; engine provides erasure job | Real pilot | P2 | D-053 |
| OQ-31 | Anthropic API usage: is sending first name, language and area names to the LLM acceptable? Any data-residency requirement for LLM calls? Enterprise data terms in place? | Acceptable with minimisation; no residency requirement for LLM | LLM features (Phase 2) | P2 | D-032, D-035 |
| OQ-32 | Retention periods for decisions, messages and audit logs | Firestore 180 d / 400 d audit, BigQuery indefinite (pseudonymised) | Compliance | P2 | DATA_MODEL §4.1 |
| OQ-33 | Hosting in the client's GCP project on Cloud Run, region asia-south1? Who operates it (Grepix ops)? | Yes; Grepix ops with our runbooks | Deployment | P2 | D-051 |

## E. Engineering and product

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-34 | Is Python acceptable for the engine instead of Node.js (spec §8)? | Yes (HTTP contracts isolate the backend) | Repo setup | P1 | D-009 |
| OQ-35 | Console embedding into the existing HireMe admin panel: route package, module federation or iframe? SSO with existing admin accounts? | Standalone now, packaged for embedding later; Firebase Auth | M1.5 | P2 | D-039 |
| OQ-36 | White label: is a `brand_id` dimension (separate from city) needed in v1 data? | Not in v1; added in Phase 3 | Phase 3 | P3 | — |
| OQ-37 | Pilot timing: real Noida pilot target date and any holiday freeze (Christmas/New Year)? | Real pilot from W12 (25 Jan 2027) | Plan | P2 | — |

## F. Raised while building contract v1.0-rc1 (2026-11-04)

| ID | Question | Default assumption | Blocks | Pri | Decision |
|---|---|---|---|---|---|
| OQ-38 | Can the backend include the rider's Firebase app instance id (`user_pseudo_id`) in server events (`ride_booked`, `ride_completed`, ...)? | Optional; joins use `user_id` | Nothing (nice to have for GA4 joins) | P3 | D-069 |
| OQ-39 | Does the HireMe app already set Firebase user properties or log events with names that clash with the contract (for example an existing `app_open`, `city`, `language`), and what does it log today? | No clashes; to be checked against the live Firebase project | HB2 instrumentation | P2 | D-067, D-070 |
| OQ-40 | Does the Promo API support campaign codes that are not user-locked (`user_id: null`, `usage_limit` > 1, several `city_ids`), as needed for F2 (DIWALI20)? | Yes | F2 campaign demo | P2 | D-038 |
