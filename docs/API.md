# HireMe AI Engagement Engine: API Specification

| | |
|---|---|
| Status | Draft for client review (API version v1) |
| Date | 2026-11-02 |
| Author | AI (Fable 5.1) |
| Spec | Sections 7, 8.1-8.4, 9, 10 |
| Machine-readable | Cross-team interfaces (M0.1, done): `contracts/openapi/engage-ingest.v1.yaml` (§3-4), `rider-api.v1.yaml` (§5), `promo-api.v1.yaml` (§6.1). Admin API (§2): `engage-admin.v1.yaml` exported from the FastAPI app in M1.5 (D-073). If this document and `contracts/` disagree, `contracts/` wins. |

Contents:
1. Conventions (auth, roles, errors, pagination, idempotency)
2. Engine admin APIs (spec 8.4 and additions)
3. Inbound webhooks the engine exposes now (promo redeemed, delivery status, unsubscribe)
4. Inbound, future: backend event webhook `POST /engage/v1/events`
5. Backend APIs the HireMe backend must provide at handoff (Rider Profile, consent)
6. Outbound adapter contracts and mock behaviour (Promo API, FCM, SMS, email, WhatsApp)

---

## 1. Conventions

### 1.1 Base URL and versioning

`https://{engage-api-host}/engage/v1`. The spec paths (`/engage/playbooks`, `/engage/events`, …) map to `/engage/v1/playbooks`, `/engage/v1/events`; the unversioned spec paths are served as aliases of v1 for the backend team's convenience. Breaking changes create `/engage/v2` (D-005).

### 1.2 Authentication

| Caller | Mechanism | Header |
|---|---|---|
| Admin console users | Firebase Authentication ID token (JWT) with custom claims `role`, `city_ids` | `Authorization: Bearer <id_token>` |
| HireMe backend → engine webhooks | HMAC-SHA256 over `"{timestamp}.{raw_body}"` with a shared secret; reject if `|now − timestamp| > 300 s` | `X-HireMe-Signature: t=1792412412,v1=<hex>`; `X-HireMe-Key-Id: k2026a` (rotation) |
| Promo API / channel providers → engine | Same HMAC scheme (per-provider secret) or provider-native signature where it exists | as above |
| Engine services ↔ engine services, Cloud Scheduler | Google-signed OIDC token (Cloud Run IAM) | `Authorization: Bearer <oidc>` |

### 1.3 Roles (spec 2, 7)

| Role | Scope | Can |
|---|---|---|
| `super` | All cities | Everything; global budgets, settings, autonomy, kill switch, models, compliance settings, DLQ replay |
| `marketing` | All cities (or `city_ids` if set) | Playbooks (except autonomy > settings max), templates, campaigns, approvals, Ask AI, reports, segments preview |
| `city_admin` | Only `city_ids` in claims | Campaigns, approvals, reports, Ask AI, and playbook *city overrides* for their cities; read-only playbooks/templates; cannot change global settings, budgets beyond their city allocation, autonomy or kill switch (may request a city pause) |
| `system` | n/a | Webhooks, jobs |

Permission matrix (✔ = allowed, R = read only, C = own cities only):

| Resource | super | marketing | city_admin |
|---|---|---|---|
| playbooks | ✔ | ✔ (autonomy ≤ max) | R + C overrides |
| templates | ✔ | ✔ | R |
| approvals | ✔ | ✔ | C |
| campaigns | ✔ | ✔ | C |
| ask | ✔ | ✔ | C (answers filtered to their cities) |
| reports | ✔ | ✔ | C |
| budgets | ✔ | R | R (C) |
| settings, kill switch | ✔ | R | R; `POST /kill-switch` with `scope.city_ids` = own cities only |
| segments | ✔ | ✔ | C |
| decisions / users engagement | ✔ | ✔ (PII masked) | C (PII masked) |
| audit log | ✔ | R | C |
| models | ✔ | R | — |
| DLQ | ✔ | R | — |
| simulator (dev only) | ✔ | ✔ | — |

### 1.4 Errors (RFC 9457 problem+json)

```json
{
  "type": "https://errors.hireme.engage/validation",
  "title": "Playbook validation failed",
  "status": 422,
  "code": "PLAYBOOK_INVALID",
  "detail": "promo.max_discount_inr (150) exceeds settings.user_promo_caps.max_discount_per_ride_inr (100)",
  "errors": [{ "path": "/promo/max_discount_inr", "message": "must be <= 100" }],
  "request_id": "req_01JBX3..."
}
```

| HTTP | `code` examples | When |
|---|---|---|
| 400 | `BAD_REQUEST`, `INVALID_CURSOR` | Malformed request |
| 401 | `UNAUTHENTICATED`, `BAD_SIGNATURE`, `STALE_TIMESTAMP` | Missing/invalid token or HMAC |
| 403 | `FORBIDDEN_ROLE`, `FORBIDDEN_CITY` | RBAC |
| 404 | `NOT_FOUND` | |
| 409 | `VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `ALREADY_DECIDED` | ETag mismatch; same key with a different body; approval already decided |
| 412 | `PRECONDITION_REQUIRED` | PATCH without `If-Match` |
| 422 | `PLAYBOOK_INVALID`, `TEMPLATE_INVALID`, `DLT_TEMPLATE_MISSING`, `AUTONOMY_ABOVE_MAX`, `LADDER_OUTSIDE_CAPS` | Semantic validation |
| 423 | `KILL_SWITCH_ACTIVE` | Campaign launch while kill switch is on |
| 429 | `RATE_LIMITED` | With `Retry-After` |
| 503 | `DEPENDENCY_UNAVAILABLE` | BigQuery/Firestore outage |

### 1.5 Pagination, filtering, sorting

Cursor based: `?page_size=50&page_token=<opaque>` (max 200). Response: `{"items": [...], "next_page_token": "...", "total_estimate": 1234}`. Time filters use `from`/`to` (ISO-8601 with offset; defaults interpreted in IST). Sorting `?order_by=created_at desc` on documented fields only.

### 1.6 Concurrency and idempotency

- Config resources return `ETag: "v12"`; `PATCH`/`PUT` require `If-Match` (412 otherwise, 409 on mismatch).
- All `POST` endpoints accept `Idempotency-Key` (UUID). The engine stores `{key, request_hash, response}` for 24 h in `engage_idempotency`; replay returns the stored response with `Idempotent-Replayed: true`; same key with a different body → 409 `IDEMPOTENCY_CONFLICT`.
- Every mutation writes `engage_audit_log` with `request_id`.

---

## 2. Engine admin APIs

### 2.1 Playbooks (spec 8.4: `GET/POST/PATCH /engage/playbooks`)

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/playbooks` | all | List; filters `category`, `enabled`, `phase`, `city_id` |
| GET | `/playbooks/{playbook_id}` | all | Current config + `approved_version` + 7-day stats |
| POST | `/playbooks` | super, marketing | Create (status `draft`, version 1) |
| PATCH | `/playbooks/{playbook_id}` | super, marketing; city_admin for `city_overrides` | JSON merge patch → new immutable version; if it changes trigger/audience/promo/templates/budget/autonomy, status becomes `pending_approval` and an approval of kind `playbook_version` is created; `enabled` toggles take effect immediately |
| GET | `/playbooks/{playbook_id}/versions` | all | Version history |
| POST | `/playbooks/{playbook_id}/validate` | super, marketing | Validate a candidate body without saving |
| POST | `/playbooks/{playbook_id}/dry-run` | super, marketing | Replay the last N days of BigQuery events through the trigger + decision logic (no sends) and predict reach, cost, incremental rides |

`PATCH /playbooks/B2_abandoned_booking` (If-Match: "v1")

```json
{ "trigger": { "wait_minutes": 12 }, "promo": { "ladder": [0, 10, 15] } }
```

`200 OK`, `ETag: "v2"`

```json
{
  "playbook_id": "B2_abandoned_booking",
  "version": 2,
  "status": "pending_approval",
  "approved_version": 1,
  "approval_id": "apr_01JBX4ZK",
  "config": { "...": "full playbook JSON, see DATA_MODEL §5.1" }
}
```

`POST /playbooks/B2_abandoned_booking/dry-run`

```json
{ "from": "2026-10-01T00:00:00+05:30", "to": "2026-10-31T23:59:59+05:30", "city_ids": [3], "candidate_version": 2 }
```

```json
{
  "job_id": "dry_01JBX5",
  "status": "done",
  "result": {
    "triggers": 5120, "eligible": 4820, "holdout": 482, "would_send": 4120,
    "by_rung": { "0": 2210, "10": 1180, "15": 730 },
    "predicted_cost_inr": 18400, "predicted_incremental_rides": 300, "predicted_ci": [210, 390],
    "skips_by_reason": { "cooldown": 210, "freq_cap_daily": 120, "no_consent": 88 }
  }
}
```

### 2.2 Templates (spec 8.4: `GET/POST /engage/templates`)

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/templates` | all | Filters `playbook_id`, `channel`, `language`, `status` |
| GET | `/templates/{template_id}` | all | |
| POST | `/templates` | super, marketing | Create draft |
| PATCH | `/templates/{template_id}` | super, marketing | New draft version |
| POST | `/templates/{template_id}/preview` | all | Render with sample or real (masked) user; returns per-device preview text, length checks, content-check result |
| POST | `/templates/{template_id}/approve` | super, marketing | Approve (creates audit entry); SMS requires `dlt.template_id`, WhatsApp requires `wa_template` |

`POST /templates`

```json
{
  "template_id": "tpl_B2_push_en_v1",
  "playbook_id": "B2_abandoned_booking",
  "channel": "push",
  "language": "en",
  "message_class": "marketing",
  "title": "Still heading to {drop_area}?",
  "body": "Complete your ride in the next {validity_minutes} min and save {discount_label} with {promo_code}.",
  "variables": ["drop_area", "validity_minutes", "discount_label", "promo_code"],
  "llm_personalisable": true
}
```

`POST /templates/tpl_B2_push_en_v1/preview` → `{"user_id": "u_88213"}`

```json
{
  "rendered": { "title": "Still heading to Connaught Place?", "body": "Complete your ride in the next 30 min and save 15% with GO15-XXXX." },
  "checks": { "length_ok": true, "content_check": "pass", "unresolved_variables": [] },
  "sample_values": { "promo_code": "GO15-XXXX (placeholder in preview)" }
}
```

### 2.3 Approvals (spec 8.4: `GET /engage/approvals`, `POST /engage/approvals/{id}/approve|reject`)

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/approvals` | super, marketing, city_admin (C) | Filters `status` (default `pending`), `kind`, `city_id`; sorted by `expires_at` |
| GET | `/approvals/{approval_id}` | same | Full payload with prediction and diff (for `playbook_version`) |
| POST | `/approvals/{approval_id}/approve` | same | Optional `edits` (JSON merge patch on the payload) → status `edited_approved` |
| POST | `/approvals/{approval_id}/reject` | same | Requires `reason` |

`GET /approvals?status=pending&kind=cohort_batch`

```json
{
  "items": [{
    "approval_id": "apr_01JBX9QH",
    "kind": "cohort_batch",
    "city_id": 3,
    "playbook_id": "E3_lapsed_30d",
    "created_by": "ai",
    "created_at": "2026-11-02T10:00:04+05:30",
    "expires_at": "2026-11-03T10:00:00+05:30",
    "summary": "E3 lapsed riders, Noida: 412 riders, offers 20%-30%",
    "prediction": { "reach": 412, "cost_inr": 9800, "incremental_rides": 37, "ci": [18, 56], "roi": 1.9 },
    "payload": { "batch_id": "bat_E3_20261102_c3", "by_rung": { "20": 260, "25": 120, "30": 32 }, "channels": { "email": 301, "sms": 111 } }
  }],
  "next_page_token": null
}
```

`POST /approvals/apr_01JBX9QH/approve`

```json
{ "note": "OK but cap at 25%", "edits": { "payload": { "max_rung": 25 } } }
```

```json
{ "approval_id": "apr_01JBX9QH", "status": "edited_approved", "decided_by": "uid_marketing_7", "decided_at": "2026-11-02T11:12:40+05:30" }
```

Errors: 409 `ALREADY_DECIDED`, 410 `APPROVAL_EXPIRED`.

### 2.4 Campaigns (spec 8.4: `POST /engage/campaigns`, manual broadcast)

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/campaigns` | super, marketing, city_admin (C) | Create; `dry_run: true` returns an estimate only |
| GET | `/campaigns` / `/campaigns/{id}` | same | |
| POST | `/campaigns/{id}/submit` | same | → approval (kind `campaign`) |
| POST | `/campaigns/{id}/cancel` | same | Stops unsent messages, deactivates unused personal codes |

`POST /campaigns` (Idempotency-Key required)

```json
{
  "name": "Diwali 2026 Noida",
  "kind": "festival",
  "city_ids": [3],
  "segment": { "include": ["weekend_riders", "commuters"], "exclude": ["unhappy", "fraud_flagged"], "min_rides_90d": 1 },
  "channels": ["push", "email"],
  "templates": { "push": { "en": "tpl_F2_push_en_v1", "hi": "tpl_F2_push_hi_v1" } },
  "promo": { "mode": "shared_code", "code": "DIWALI20", "type": "percent", "value": 20, "max_discount_inr": 80, "valid_to": "2026-11-10T23:59:59+05:30", "usage_limit_per_user": 1 },
  "schedule": { "send_at": "2026-11-07T10:00:00+05:30", "send_window_minutes": 120 },
  "budget_inr": 60000,
  "holdout_percent": 10,
  "dry_run": false
}
```

```json
{ "campaign_id": "cmp_1042", "status": "draft", "estimate": { "audience": 6120, "after_guardrails": 5380, "holdout": 612, "predicted_cost_inr": 41200 } }
```

Campaign sends pass through the same decision pipeline (eligibility, holdout keyed by `campaign_id`, guardrails); the shared readable code is created once via the Promo API with `user_id: null` and `usage_limit_per_user` (OQ-08).

### 2.5 Ask AI (spec 8.4: `POST /engage/ask`; H4)

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/ask` | super, marketing, city_admin (C) | Natural-language question → answer + evidence + optional campaign draft |
| GET | `/ask/{session_id}` | same | Session history |
| POST | `/ask/{session_id}/to-campaign` | same | Turn the suggested draft into a `draft` campaign |

`POST /ask`

```json
{ "question": "How many riders in Delhi booked a scheduled ride last week?", "session_id": null, "allow_campaign_draft": true }
```

```json
{
  "session_id": "ask_01JBXC2",
  "answer": "312 riders in Delhi booked a scheduled ride from 26 Oct to 1 Nov 2026, up 18% on the previous week (265).",
  "evidence": [{
    "view": "engage_views.v_scheduled_rides_daily",
    "sql": "SELECT SUM(riders) FROM `engage_views.v_scheduled_rides_daily` WHERE city_id = 1 AND d BETWEEN '2026-10-26' AND '2026-11-01'",
    "bytes_processed": 1048576,
    "rows": [{ "riders": 312 }]
  }],
  "campaign_draft": null,
  "model": "claude-sonnet-5-5",
  "data_freshness": "engage_mart refreshed 2026-11-02T04:12+05:30"
}
```

Guarantees (D-035): only `engage_views` is queryable; SQL is parsed and must be a single `SELECT` on allowed views; BigQuery dry-run first (max 2 GB scanned); groups < 20 users suppressed; city_admin queries are rewritten with a `city_id IN (...)` filter; numbers in the answer must appear in the tool results (post-check), otherwise the answer is returned as "could not verify".

### 2.6 Reports (spec 8.4: `GET /engage/reports?from&to&playbook&city`; spec 10)

`GET /reports?type={type}&from&to&playbook&city&channel&group_by=day|week|month&format=json|csv`

| `type` | Source mart | Columns |
|---|---|---|
| `funnel` | `funnel_daily` | sign_ups, fare_checks, bookings_started, booked, completed, by city/date/platform |
| `playbook_performance` | `playbook_daily`, `holdout_lift` | eligible, sent, delivered, opened, converted, conv_treat, conv_hold, lift_pp, ci, incremental_rides, promo_cost_inr, incremental_fare_inr, roi |
| `channel_performance` | `channel_daily` | delivery, open, conversion rates, cost per conversion |
| `promo` | `promo_daily` | codes created/redeemed, value given, top codes, abuse flags |
| `budget_pacing` | `budget_pacing_daily` | spend vs budget, forecast to month end |
| `cohort_retention` | `cohort_retention_weekly` | W1, W4, W12 retention touched vs not touched |
| `ai_activity` | `ai_activity_daily` | decisions, sent vs skipped by reason, approvals pending, model accuracy |

`GET /reports?type=playbook_performance&from=2026-10-01&to=2026-10-31&playbook=B2_abandoned_booking&city=3`

```json
{
  "type": "playbook_performance",
  "period": { "from": "2026-10-01", "to": "2026-10-31", "tz": "Asia/Kolkata" },
  "rows": [{
    "playbook_id": "B2_abandoned_booking", "city_id": 3,
    "eligible": 4820, "holdout": 482, "sent": 4338, "opened": 1302,
    "conv_treat": 0.16, "conv_hold": 0.09, "lift_pp": 7.0, "ci_pp": [4.1, 9.9],
    "incremental_rides": 300, "promo_cost_inr": 18400, "incremental_fare_inr": 89000, "roi": 3.84,
    "significant": true
  }],
  "freshness": "2026-11-01T04:10:00+05:30",
  "synthetic": true
}
```

(Values reproduce the spec's illustrative row; `synthetic: true` is set whenever the data comes from the dev project.)

### 2.7 Additional APIs (not in spec 8.4, needed for spec 7 screens and operations)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/budgets` | all (C for city_admin) | Budgets with live ledger (`committed_outstanding_inr`, `redeemed_inr`, `pct_used`) |
| PUT | `/budgets/{budget_id}` | super | Create/replace a budget (If-Match) |
| GET | `/budgets/pacing` | all | Forecast to month end (H5) |
| GET | `/settings` | all | Global + city settings |
| PATCH | `/settings` | super | Caps, quiet hours, autonomy max, LLM, scoring (If-Match); `holdout_salt` is read-only |
| GET | `/kill-switch` | all | State |
| POST | `/kill-switch` | super (city_admin: own cities only) | `{ "active": true, "scope": "marketing_and_service", "city_ids": null, "reason": "Gateway incident" }` → effective in ≤ 5 s; audited; alert to all super admins |
| GET | `/segments` | all | Definitions + counts |
| POST | `/segments/preview` | super, marketing, city_admin (C) | Segment builder → count by city/channel reachability (k ≥ 20) |
| GET | `/decisions` | all (PII masked) | Filters `user_id`, `playbook_id`, `status`, `reason_code`, `from`, `to` |
| GET | `/decisions/{decision_id}` | all | Full explain: trigger, scores, offer rationale, guardrail trace, messages, promo, attribution |
| GET | `/users/{user_id}/engagement` | super, marketing | Caps, cooldowns, suppressions, recent decisions (contact data masked: `+91******2345`) |
| GET | `/audit-log` | super, marketing (R), city_admin (C) | Filters `actor_id`, `target_type`, `target_id`, `action` |
| GET | `/digests?date=` | all | H1 digest |
| GET | `/alerts` / POST `/alerts/{id}/ack` | all | H2, H5 alerts |
| GET | `/models` / POST `/models/{model_id}/promote` | super | Model registry; promote candidate → shadow → active |
| GET | `/dlq` / POST `/dlq/{id}/replay` | super | Dead letters |
| GET | `/healthz` | none | Liveness |
| GET | `/readyz` | none | Firestore + BigQuery reachable |
| GET | `/status` | all | Source lag, inbox backlog, timer backlog, outbox backlog, DLQ size, kill switch, clock mode |

Simulator controls (only when `ENGAGE_ENV=dev`; return 404 elsewhere):

| Method | Path | Purpose |
|---|---|---|
| POST | `/sim/runs` | Start a run: `{ "scale": "medium", "start_at": "2026-11-01T00:00:00+05:30", "speed": 60, "duration_days": 30, "cities": [1,2,3], "seed": 42 }` |
| GET | `/sim/runs/{run_id}` | State, virtual clock, events emitted, responder stats |
| POST | `/sim/runs/{run_id}/pause` · `/resume` · `/stop` | Control |
| PATCH | `/sim/runs/{run_id}` | Change `speed` |
| POST | `/sim/scenarios/{name}/inject` | Inject a scripted scenario (`riya_b1`, `riya_b2`, `b2_cancelled_by_booking`, `c2_airport_reminder`, `d2_bad_rating`, `quiet_hours_b2`, `budget_exhaustion_b2`, `kill_switch_midflight`, `consent_revoked_midtimer`, `duplicate_events`, `promo_api_outage`) |
| GET | `/sim/clock` | Current virtual time |

---

## 3. Inbound webhooks the engine exposes now

### 3.1 Promo redeemed (spec 8.2 "a webhook when a code is redeemed")

`POST /engage/v1/webhooks/promo-redeemed` (HMAC)

```json
{
  "event_id": "prx_778812",
  "promo_id": 55120,
  "code": "GO15-7KQ2",
  "user_id": "u_88213",
  "ride_id": "r_4821",
  "discount_inr": 63.0,
  "gross_fare_inr": 464.5,
  "redeemed_at": "2026-10-21T18:31:40+05:30",
  "meta": { "campaign_id": "pb_B2_abandoned_booking", "playbook_id": "B2_abandoned_booking", "created_by": "ai" }
}
```

→ `200 {"status": "applied"}` or `{"status": "duplicate"}` (dedupe on `event_id`). Effect: promo `redeemed`, ledger `redeem` entry, inbox event `promo_redeemed` (origin `server`).

### 3.2 Delivery status

`POST /engage/v1/webhooks/delivery/{provider}` where provider ∈ `fcm`, `sms`, `email`, `whatsapp` (mocks call the same endpoint)

```json
{ "provider_message_id": "projects/hireme-engage-dev/messages/0:1792412415%31bd", "message_id": "msg_8f3a91c2e0d4_1", "status": "delivered", "at": "2026-10-21T18:20:16+05:30", "error_code": null }
```

Statuses: `delivered`, `failed`, `bounced`, `complained`, `read` (WhatsApp), `dnd_blocked` (SMS).

### 3.3 Unsubscribe and tracked links

| Method | Path | Purpose |
|---|---|---|
| GET | `/engage/v1/l/{token}` | Tracked redirect for SMS/email/WhatsApp links → emits `notification_opened` (origin server) → 302 to deep link / web fallback |
| GET/POST | `/engage/v1/unsubscribe/{token}` | One-click unsubscribe (email List-Unsubscribe-Post compatible) → consent withdrawn immediately in `hireme_riders` stub now; after handoff, engine calls backend `POST /api/engage/v1/riders/{user_id}/consent` and emits `consent_changed` |

Tokens are signed (HMAC) and carry `message_id`, `user_id`, `channel`, expiry 30 days.

---

## 4. Inbound, future: backend event webhook (`POST /engage/v1/events`)

The HireMe backend implements a client for this at the backend handoff milestone (IMPLEMENTATION_PLAN M-HB). The engine implements and contract-tests the endpoint in Phase 1 (disabled in config until handoff).

| Item | Value |
|---|---|
| Method / path | `POST /engage/v1/events` (alias `POST /engage/events`) |
| Auth | HMAC (§1.2) |
| Body | `{ "events": [ <envelope>, ... ] }`, 1-500 events, ≤ 1 MB, `Content-Type: application/json`, gzip allowed |
| Envelope | DATA_MODEL §2.1; `source` is set by the engine (`webhook`) and ignored if sent |
| Ordering | Not required; send as soon as possible (target p95 < 5 s from occurrence) |
| Dedupe | By `event_uuid`; retries are safe |
| Response | `202 Accepted` with per-event results |
| Retries (sender) | On 429/5xx/timeouts: exponential backoff up to 24 h, then backfill via BigQuery is acceptable |
| Throughput | Pilot: ≤ 50 events/s sustained; burst 500/s |

Request:

```json
{
  "events": [
    {
      "contract_version": "1.0",
      "event_uuid": "01936f2e-6b1a-7c3e-9a4f-2b8d1e0c5a77",
      "event_name": "booking_abandoned",
      "event_ts": "2026-10-21T18:10:12.345+05:30",
      "user_id": "u_88213",
      "user_pseudo_id": "6f1c2b9a8e7d4c3b",
      "platform": "ANDROID",
      "app_version": "5.4.1",
      "city_id": 3,
      "origin": "client",
      "params": { "step": "confirm", "fare_estimate": 420.0, "vehicle_type": "mini", "pickup_zone": "NOI-S62", "drop_zone": "DEL-CP", "drop_area_name": "Connaught Place", "fare_quote_id": "fq_7781203" }
    },
    {
      "contract_version": "1.0",
      "event_uuid": "01936f2f-0c11-7a01-8f2e-55aa10cc0e01",
      "event_name": "ride_booked",
      "event_ts": "2026-10-21T18:31:02.000+05:30",
      "user_id": "u_88213",
      "user_pseudo_id": "6f1c2b9a8e7d4c3b",
      "platform": "SERVER",
      "city_id": 3,
      "origin": "server",
      "params": { "ride_id": "r_4821", "fare_estimate": 420.0, "promo_code": "GO15-7KQ2", "is_scheduled": false, "vehicle_type": "mini", "payment_method": "upi", "pickup_zone": "NOI-S62", "drop_zone": "DEL-CP" }
    }
  ]
}
```

Response `202`:

```json
{
  "accepted": 1, "duplicates": 1, "rejected": 0,
  "results": [
    { "event_uuid": "01936f2e-6b1a-7c3e-9a4f-2b8d1e0c5a77", "status": "accepted" },
    { "event_uuid": "01936f2f-0c11-7a01-8f2e-55aa10cc0e01", "status": "duplicate" }
  ]
}
```

Per-event rejection (`status: "rejected"`, `errors: [...]`) for schema failures does not fail the batch. Whole-batch errors: 400 (not JSON / > 500 events), 401, 413, 429.

---

## 5. Backend APIs the HireMe backend must provide at handoff

The engine calls these through the `RiderDirectory` adapter. Until then, `FirestoreRiderStub` serves the same JSON from `hireme_riders` (D-013).

### 5.1 Rider profile

`GET /api/engage/v1/riders/{user_id}` (service auth: OIDC or API key + mTLS, to be agreed, OQ-10)

```json
{
  "user_id": "u_88213",
  "city_id": 3,
  "first_name": "Riya",
  "language": "en",
  "signup_ts": "2026-03-14T11:02:00+05:30",
  "contact": { "phone_e164": "+919990012345", "email": "riya.s@example.test", "phone_dnd": false, "email_verified": true },
  "push_tokens": [{ "token": "fcm_tok_…", "platform": "ANDROID", "updated_at": "2026-10-20T09:00:00+05:30" }],
  "consent": {
    "push": { "opted_in": true, "updated_at": "2026-03-14T11:02:00+05:30", "source": "app_settings" },
    "email": { "opted_in": true, "updated_at": "2026-03-14T11:02:00+05:30", "source": "signup" },
    "sms": { "opted_in": true, "updated_at": "2026-03-14T11:02:00+05:30", "source": "signup" },
    "whatsapp": { "opted_in": false, "updated_at": null, "source": null }
  },
  "wallet_balance_inr": 42.0,
  "device_id_hash": "9b1f6c0e…",
  "payment_fingerprints": ["pf_3c9e…"],
  "birth_month_day": "07-21",
  "referral": { "code": "RIYA50", "referred_by_user_id": null },
  "status": "active"
}
```

`POST /api/engage/v1/riders:batchGet` → `{ "user_ids": [...≤ 500] }` → `{ "riders": [...], "not_found": [...] }` (used by batch playbooks).

Requirements: p95 < 100 ms single, < 1 s batch of 500; 404 for unknown users; `status` ∈ `active`, `blocked`, `deleted` (engine skips non-active).

### 5.2 Consent write-back (engine-originated unsubscribe)

`POST /api/engage/v1/riders/{user_id}/consent` → `{ "channel": "email", "opted_in": false, "source": "unsubscribe_link", "at": "2026-10-22T09:12:00+05:30" }` → `204`. The backend then emits `consent_changed` via the webhook.

### 5.3 Wallet credit (Phase 3, D-065)

`POST /api/admin/wallet/credits` → `{ "user_id": "u_88213", "amount_inr": 75, "reason": "D2_bad_experience", "idempotency_key": "dec_…", "meta": {...} }` → `201 { "credit_id": 9921 }`. Until it exists, D2 uses a flat ₹75 user-locked promo code.

### 5.4 Summary of backend obligations at handoff

| # | Obligation | Contract |
|---|---|---|
| 1 | Emit every event in DATA_MODEL §2.3 with `event_uuid` and `contract_version` to Firebase Analytics (client events) | DATA_MODEL §2 |
| 2 | Post the same events (client relay + server-authoritative) to `POST /engage/v1/events` | §4 |
| 3 | Enable Firebase → BigQuery export (daily + streaming) in the production project; share the dataset with the engine service account | D-003 |
| 4 | Provide the Rider Profile API and consent write-back | §5.1, §5.2 |
| 5 | Implement Promo API endpoints: create (with `Idempotency-Key`), usage, deactivate, redemption webhook | §6.1 |
| 6 | Provide Grepix channel APIs (or allow direct FCM/MSG91/SES) with delivery receipts | §6.2-6.5 |
| 7 | Support the deep link contract (promo auto-apply, `mid` attribution) | DATA_MODEL §2.6 |

---

## 6. Outbound adapter contracts and mock behaviour

All adapters implement a common interface; the mock and the real implementation differ only in base URL and credentials (D-014).

```python
class PromoAdapter(Protocol):
    def create(self, req: PromoCreate, idempotency_key: str) -> PromoCreated: ...
    def usage(self, promo_id: int) -> PromoUsage: ...
    def deactivate(self, promo_id: int, reason: str) -> None: ...

class ChannelAdapter(Protocol):
    channel: Literal["push", "sms", "email", "whatsapp", "in_app"]
    def send(self, msg: OutboundMessage, idempotency_key: str) -> SendResult: ...   # SendResult.status: accepted | retryable_error | permanent_error
```

Mock service `engage-mocks` (dev only) exposes all providers under one host with a control API:

| Method | Path | Purpose |
|---|---|---|
| POST | `/mock/admin/faults` | `{ "target": "fcm", "mode": "error_rate", "rate": 0.2, "error": "UNAVAILABLE", "until": "…" }`; modes `error_rate`, `outage`, `latency` (`p50_ms`, `p99_ms`), `reset` |
| GET | `/mock/admin/stats` | Requests, errors, latencies per target |
| GET | `/mock/deliveries?user_id=` | What a user "received" (reads `mock_deliveries`) |

### 6.1 HireMe Promo API (spec 8.2, "existing, to confirm")

**Create** `POST /api/admin/promocodes` (spec sample, plus `Idempotency-Key` header which we ask the backend to support, OQ-08)

```json
{
  "code": "GO15-7KQ2",
  "type": "percent",
  "value": 15,
  "max_discount": 75,
  "min_fare": 100,
  "user_id": "u_88213",
  "usage_limit": 1,
  "city_ids": [3],
  "vehicle_types": ["mini", "sedan"],
  "valid_from": "2026-10-21T18:25:00+05:30",
  "valid_to": "2026-10-21T20:25:00+05:30",
  "meta": { "campaign_id": "cmp_1042", "playbook_id": "B2_abandoned_booking", "created_by": "ai" }
}
```

→ `201 {"promo_id": 55120, "code": "GO15-7KQ2", "status": "active"}`

Engine additions to `meta`: `decision_id`, `engage_promo_ref`. Types: `percent`, `flat`, `free_ride` (value = cap), `cashback`, `upgrade` (`value` = target vehicle) per spec 6.3; restriction `first_ride_only` (bool).

| Response | Meaning | Engine action |
|---|---|---|
| 201 | Created | Store `promo_id`, status `active` |
| 200 + `Idempotent-Replayed` | Same idempotency key replayed | Treat as created |
| 409 `CODE_EXISTS` | Code collision | Generate a new random suffix, retry (max 3) |
| 422 | Invalid restriction | Permanent error → `promo_api_error`, downgrade/skip |
| 429 / 5xx / timeout (3 s) | Transient | Retry ×3 with backoff, same key |

**Usage** `GET /api/admin/promocodes/{promo_id}/usage` → `{"promo_id": 55120, "uses": 1, "redemptions": [{"ride_id": "r_4821", "user_id": "u_88213", "discount_inr": 63.0, "redeemed_at": "2026-10-21T18:31:40+05:30"}]}` (used for reconciliation; the webhook in §3.1 is the primary signal).

**Deactivate** `PATCH /api/admin/promocodes/{promo_id}` → `{"status": "inactive", "reason": "campaign_cancelled"}` → `200`. Used on campaign cancel, kill switch with `deactivate_codes: true`, and user unsubscribe.

**Mock behaviour**: state in Firestore `mock_promo_codes`; validates field types and restriction values; returns 409 for duplicate `code`; honours `Idempotency-Key` for 24 h; exposes `POST /mock/promocodes/{code}/apply` used by the simulator to emulate the backend applying the code at booking (checks user lock, validity window, min fare, vehicle, usage limit, computes `discount = min(value% × fare, max_discount)`); on ride completion the simulator calls `POST /mock/promocodes/{code}/redeem`, which records usage, writes `hireme_backend_stub.promo_redemptions` (log shipper) and calls the engine webhook §3.1. Default fault profile: 0.5 % 503, p50 latency 120 ms.

### 6.2 Push: FCM HTTP v1 (spec 8.3)

Real: `POST https://fcm.googleapis.com/v1/projects/{project_id}/messages:send` (OAuth2 service account). If Grepix wraps FCM (spec: "Grepix provides an API"), the adapter targets the Grepix endpoint with the same logical payload (OQ-09).

```json
{
  "message": {
    "token": "fcm_tok_…",
    "notification": { "title": "Still heading to Connaught Place?", "body": "Complete your ride in the next 30 min and save 15% with GO15-7KQ2." },
    "data": {
      "deep_link": "hireme://book?quote=fq_7781203&drop=DEL-CP&promo=GO15-7KQ2&mid=msg_8f3a91c2e0d4_1&cid=pb_B2_abandoned_booking",
      "message_id": "msg_8f3a91c2e0d4_1",
      "campaign_id": "pb_B2_abandoned_booking"
    },
    "android": { "priority": "HIGH", "ttl": "1800s", "collapse_key": "B2" },
    "apns": { "headers": { "apns-priority": "10", "apns-expiration": "1792414212" } }
  }
}
```

→ `200 {"name": "projects/hireme-engage-dev/messages/0:1792412415%31bd"}`. TTL = promo validity so a stale push is not shown after the code expires.

| FCM error | Engine classification |
|---|---|
| `UNREGISTERED` (404), `INVALID_ARGUMENT` (400) on token | permanent → mark token stale in rider stub → fallback channel |
| `QUOTA_EXCEEDED` (429), `UNAVAILABLE` (503), `INTERNAL` (500) | retryable |
| `SENDER_ID_MISMATCH`, `THIRD_PARTY_AUTH_ERROR` | permanent, alert (config problem) |

**Mock**: `POST /mock/fcm/v1/projects/{p}/messages:send` with the same request/response shape; returns `UNREGISTERED` for tokens marked stale in `hireme_riders` (≈ 5 % synthetic), 0.5 % `UNAVAILABLE`; writes `mock_deliveries`; calls the delivery webhook after 0.5-3 s; the simulator responder sees the delivery and decides open/convert.

### 6.3 SMS (MSG91 / Twilio / local gateway, via Grepix) with TRAI DLT

Logical request the adapter sends (proposed Grepix gateway contract until the real one is shared, D-066):

```json
{
  "to": "+919990012345",
  "sender_id": "HIRMEE",
  "dlt": { "pe_id": "1201160000000000000", "template_id": "1207166000000000001", "category": "promotional" },
  "template_vars": { "var1": "15%", "var2": "GO15-7KQ2", "var3": "30" },
  "body": "HireMe: Complete your ride in the next 30 min and save 15% with GO15-7KQ2. T&C apply. -HireMe",
  "client_ref": "msg_8f3a91c2e0d4_2",
  "callback_url": "https://{engage-api-host}/engage/v1/webhooks/delivery/sms"
}
```

→ `202 {"provider_message_id": "sms_5531…", "status": "queued"}`.

Rules: body must equal the DLT template with variables substituted (adapter verifies before sending; mismatch = permanent error `DLT_TEMPLATE_MISMATCH`); `category` from `message_class` (`transactional` → transactional, `service` → service-implicit, `marketing` → promotional); promotional only to `phone_dnd = false`, 10:00-21:00 IST. Links use the tracked short link (§3.3).

**Mock**: validates DLT match against `engage_templates.dlt`; rejects promotional SMS to DND numbers (`dnd_blocked`); 1 % failure; delivery callback after 2-20 s; cost ₹0.20 (promotional) / ₹0.15 (transactional) per SMS recorded in `cost_inr`.

### 6.4 Email (Amazon SES or SendGrid, via Grepix)

```json
{
  "to": "riya.s@example.test",
  "from": { "email": "offers@mail.hireme.app", "name": "HireMe" },
  "subject": "It has been a while, Riya. 25% off to welcome you back",
  "html": "<html>…rendered template…</html>",
  "text": "…",
  "headers": { "List-Unsubscribe": "<https://{engage-api-host}/engage/v1/unsubscribe/{token}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click" },
  "client_ref": "msg_1c77e0a9b3f2_1",
  "category": "marketing"
}
```

→ `202 {"provider_message_id": "em_…"}`. **Mock**: 2 % hard bounce for addresses flagged invalid in the stub, 0.1 % complaint (treated as unsubscribe), delivery callback; email opens are emitted by the responder via the tracked link.

### 6.5 WhatsApp (wa.grepixit.com or WhatsApp Business API) – Phase 3

```json
{
  "to": "+919990012345",
  "template": { "name": "hm_winback_25", "language": "en", "components": [{ "type": "body", "parameters": [{ "type": "text", "text": "Pooja" }, { "type": "text", "text": "25%" }, { "type": "text", "text": "BACK25-H8DQ" }] }] },
  "client_ref": "msg_…_1"
}
```

Only pre-approved templates, only with `consent.whatsapp.opted_in = true`. **Mock**: same shape, `delivered` and `read` callbacks.

### 6.6 In-app (Firebase In-App Messaging) – Phase 3

Delivered as a campaign trigger via Remote Config/In-App Messaging conditions; no per-message API. Out of scope for the MVP.

### 6.7 Anthropic API (LLM)

Called only by `engage/agents/*` and `engage/messaging/llm_writer.py`; see [AGENTS_AND_SKILLS.md §3](AGENTS_AND_SKILLS.md#3-runtime-ai-agents-in-the-product) for prompts, tools, models and output schemas. Timeouts: 2 s for the message writer (fallback to deterministic template), 60 s for Ask AI, batch for digests.
