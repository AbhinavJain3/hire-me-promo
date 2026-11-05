# HireMe AI Engagement Engine: Data Model and Data Contract

| | |
|---|---|
| Status | Draft for client review (contract version **1.0.0-rc1**) |
| Date | 2026-11-02 |
| Author | AI (Fable 5.1), lead architect |
| Spec | "HireMe AI Engagement Engine: Specification", @Vinay, Oct 21 2026 (sections 3, 6, 7, 8.5, 9, 10) |
| Related | [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](API.md), [DUMMY_DATA_PLAN.md](DUMMY_DATA_PLAN.md), [../decision.md](../decision.md) |

> **Machine-readable contract (since 2026-11-04, M0.1):** `contracts/` (see `contracts/README.md`). The event catalogue `contracts/events/v1/catalog.yaml` is the single source for events, params and user properties (D-067); `contracts/events/v1/generated/EVENTS.md` is its generated reference. If this document and `contracts/` disagree, `contracts/` wins and this document must be corrected. Validate with `.venv/bin/python -m engage.tools.validate_contract --all`.

This document is the **data contract** that the HireMe backend and app teams will implement once the engine is proven on our synthetic data (D-001, D-005). Every section marks where the data lives **now** (synthetic, written by us into Firebase and BigQuery) and where it moves **after the backend handoff**.

Legend used in every table:

| Marker | Meaning |
|---|---|
| **NOW** | Exists today in our dev Firebase project or BigQuery, populated by the generator or simulator |
| **→WEBHOOK** | After handoff, arrives in real time via `POST /engage/v1/events` from the HireMe backend |
| **→GA4** | After handoff, arrives via the real Firebase Analytics → BigQuery export (same schema, config switch) |
| **→RIDER-API** | After handoff, read from the HireMe Rider Profile API (source of truth) instead of our stub |
| **ENGINE** | Owned by the engine for good (never moves) |

---

## 1. Conventions (apply to everything below)

| Topic | Rule | Decision |
|---|---|---|
| Time storage | All timestamps are stored in UTC (BigQuery `TIMESTAMP`, Firestore `Timestamp`, GA4 `event_timestamp` in microseconds). | D-017 |
| Time display and business logic | `Asia/Kolkata` (IST, UTC+05:30). "Day" means IST calendar day for budgets, caps, reports and GA4 `event_date`. | D-017 |
| Timestamps in JSON | ISO-8601 with offset, e.g. `2026-10-21T18:25:00+05:30`. | D-017 |
| Money | INR. APIs and BigQuery use decimal rupees (`*_inr`, BigQuery `NUMERIC(12,2)`). Firestore counters that are incremented atomically use integer paise (`*_paise`, `int64`) to avoid float drift. | D-017 |
| Booleans in GA4 | GA4 has no boolean type: send `int` 0/1. In the webhook envelope booleans are JSON booleans. | D-057 |
| IDs | `user_id` = `u_<digits>` (e.g. `u_88213`), set via `setUserId` after login. `ride_id` = `r_<digits>`. `event_uuid` = UUIDv7 string. Engine IDs are prefixed (`dec_`, `msg_`, `prm_`, `tmr_`, `apr_`, `cmp_`, `aud_`). | D-004, D-025 |
| Names | Event and parameter names: lowercase snake_case, ≤ 40 chars, ≤ 25 params per event (Firebase rule, spec section 3). String values ≤ 100 chars (GA4 limit). User property values ≤ 36 chars. | D-057 |
| Cities | `city_id` 1 = Delhi, 2 = Gurgaon, 3 = Noida (pilot). Matches the spec Promo API sample `city_ids: [3]`. | D-037 |
| Zones | `zone_id` = `<CITY3>-<CODE>`, e.g. `NOI-S62`, `DEL-CP`, `DEL-IGI-T3`. Reference table `hireme_ref.zones`. | D-037 |
| Vehicle types | `mini`, `sedan`, `prime`, `suv`. | D-037 |
| Payment methods | `cash`, `upi`, `card`, `wallet`. | — |
| Contract version | Every event carries `contract_version` (`"1.0"`). SemVer policy in section 2.4. | D-005 |
| Synthetic marker | Every synthetic user has user property `is_synthetic = "1"` and lives only in the dev project. | D-012 |

---

## 2. Analytics event contract (spec section 3)

### 2.1 Canonical event envelope (contract `hireme.engage.event` v1)

All sources (simulator now, backend webhook later, GA4 export poller) are normalised to this envelope before the trigger engine sees them (D-002, D-004). It is also the exact body item of the future `POST /engage/v1/events` webhook ([API.md §4](API.md#4-inbound-future-backend-webhook-post-engagev1events)).

```json
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
  "source": "simulator",
  "params": {
    "step": "confirm",
    "fare_estimate": 420.0,
    "vehicle_type": "mini",
    "pickup_zone": "NOI-S62",
    "drop_zone": "DEL-CP",
    "drop_area_name": "Connaught Place",
    "fare_quote_id": "fq_7781203",
    "booking_attempt_id": "ba_550192"
  },
  "user_properties": { "language": "en" },
  "received_at": "2026-10-21T18:10:13.002+05:30"
}
```

| Field | Type | Req | Notes | GA4 export column |
|---|---|---|---|---|
| `contract_version` | string | yes | `"1.0"` | `event_params.contract_version` |
| `event_uuid` | string (UUIDv7) | yes | Generated on device (client events) or server (server events). **Dedupe key** across GA4 and webhook. | `event_params.event_uuid` |
| `event_name` | string | yes | From the tables below | `event_name` |
| `event_ts` | ISO-8601 | yes | Device time for client events, server time for server events | `event_timestamp` (µs UTC) |
| `user_id` | string | yes\* | \*Null only for `sign_up_started` and pre-login `app_open` | `user_id` |
| `user_pseudo_id` | string | client and auto events | Firebase app instance id. Optional for server events (D-069) | `user_pseudo_id` |
| `platform` | enum `ANDROID`,`IOS`,`SERVER` | yes | `SERVER` exactly when `origin = server` (D-069) | `platform` (server events: rider's device platform) |
| `app_version` | string | client events | | `app_info.version` |
| `city_id` | int | when known | | `event_params.city_id` |
| `origin` | enum `client`,`server` | yes | Which system authored the event (D-042) | `event_params.origin` |
| `source` | enum `simulator`,`webhook`,`ga4_export`,`replay` | yes | Set by the engine adapter, not by the sender | (not in GA4) |
| `params` | object | yes | Event-specific parameters below; values are string, number or boolean | `event_params[]` |
| `user_properties` | object | no | Only properties that changed | `user_properties[]` |
| `received_at` | ISO-8601 | engine | Stamped by the engine on ingest | (not in GA4) |

### 2.2 Common parameters (every custom event)

| Param | Type | Req | Example | Notes |
|---|---|---|---|---|
| `event_uuid` | string | yes | `01936f2e-6b1a-…` | New in contract (not in spec). Required for dedupe (D-004). |
| `contract_version` | string | yes | `1.0` | D-005 |
| `origin` | string enum | yes | `client` | D-042 |
| `city_id` | int | if known | `3` | Rider's current city |
| `engage_message_id` | string | no | `msg_8f3a91c2e0d4b7a65c1e2f90_1` | Present when the screen was reached from an engine deep link (attribution). App reads it from the deep link `mid` parameter and attaches it to every event in that session for 30 min. |

Firebase automatically adds `ga_session_id`, `ga_session_number`, `engagement_time_msec`, etc. The engine does not depend on them.

### 2.3 Event catalogue

`Spec` = listed in spec section 3. `Added` = new in this contract (why given). Source: `C` = app (client), `S` = HireMe backend (server). **Server-authoritative events** (D-042) must be emitted by the backend after handoff, because the server is the only system that knows they really happened.

Location now/later applies to all events: **NOW** synthetic in `analytics_999999999.events_*` and `engage_events_live`; **→WEBHOOK** for real-time delivery and **→GA4** for history.

#### Onboarding

**`app_open`** (Spec; C) – App launched. Must be logged as a custom event (Firebase auto-events cannot carry custom params).

| Param | Type | Req | Example |
|---|---|---|---|
| `source` | enum `organic`,`push`,`deeplink`,`email`,`sms`,`whatsapp` | yes | `push` |
| `app_version` | string | yes | `5.4.1` |

**`sign_up_started`** (Spec; C) – Rider enters phone number. `user_id` is null (pre-login), see D-047.

| Param | Type | Req | Example |
|---|---|---|---|
| `method` | enum `phone`,`google`,`apple` | yes | `phone` |

**`sign_up`** (Spec, Firebase recommended; S after handoff, C now) – OTP verified, account created. Emitted after `setUserId`.

| Param | Type | Req | Example |
|---|---|---|---|
| `method` | enum `phone`,`google`,`apple` | yes | `phone` |
| `referral_code` | string | no | `NEHA50` |
| `city` | string | yes | `Noida` |
| `device_id_hash` | string (SHA-256 hex, first 32 chars) | yes | `9b1f…` | Added: needed for multi-account fraud check (spec 9). |

**`profile_completed`** (Spec; C)

| Param | Type | Req | Example |
|---|---|---|---|
| `has_email` | bool(int) | yes | `1` |

**`location_permission`** (Spec; C)

| Param | Type | Req | Example |
|---|---|---|---|
| `status` | enum `granted`,`denied` | yes | `denied` |
| `precision` | enum `precise`,`approximate` | no | `approximate` | Added (optional) |

#### Booking funnel

**`fare_check`** (Spec; C) – Pickup and drop entered, fare shown.

| Param | Type | Req | Example | Notes |
|---|---|---|---|---|
| `pickup_zone` | string zone_id | yes | `NOI-S62` | |
| `drop_zone` | string zone_id | yes | `DEL-CP` | |
| `distance_km` | double | yes | `18.4` | |
| `fare_estimate` | double INR | yes | `420.0` | Price of the displayed/default vehicle |
| `vehicle_type` | enum | yes | `mini` | |
| `surge_multiplier` | double | yes | `1.0` | 1.0 = no surge |
| `fare_quote_id` | string | yes | `fq_7781203` | Added: links fare_check → booking → ride |
| `drop_area_name` | string | yes | `Connaught Place` | Added: fills `{drop_area}` in templates without a geo lookup |
| `pickup_area_name` | string | no | `Sector 62` | Added |

**`vehicle_selected`** (Spec; C)

| Param | Type | Req | Example |
|---|---|---|---|
| `vehicle_type` | enum | yes | `sedan` |
| `fare_estimate` | double | yes | `512.0` |
| `fare_quote_id` | string | yes | `fq_7781203` |

**`booking_started`** (Spec; C) – Rider taps Book / Confirm.

| Param | Type | Req | Example |
|---|---|---|---|
| `vehicle_type` | enum | yes | `mini` |
| `payment_method` | enum | yes | `upi` |
| `fare_estimate` | double | yes | `420.0` |
| `fare_quote_id` | string | yes | `fq_7781203` |
| `booking_attempt_id` | string | yes | `ba_550192` | Added |

**`booking_abandoned`** (Spec; C) – Rider leaves booking screen without confirming.

| Param | Type | Req | Example | Notes |
|---|---|---|---|---|
| `step` | enum `fare`,`vehicle`,`payment`,`confirm` | yes | `confirm` | B3 handles `payment`; B2 handles the rest |
| `fare_estimate` | double | yes | `420.0` | |
| `vehicle_type` | enum | yes | `mini` | Added |
| `payment_method` | enum | no | `card` | Added (needed by B3) |
| `pickup_zone` | string | yes | `NOI-S62` | Added |
| `drop_zone` | string | yes | `DEL-CP` | Added |
| `drop_area_name` | string | yes | `Connaught Place` | Added |
| `fare_quote_id` | string | yes | `fq_7781203` | Added |
| `booking_attempt_id` | string | no | `ba_550192` | Added (absent if abandoned before booking_started) |

**`ride_booked`** (Spec; **S**, server-authoritative) – Booking created on server.

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_4821` |
| `fare_estimate` | double | yes | `420.0` |
| `promo_code` | string | no | `GO15-7KQ2` |
| `is_scheduled` | bool(int) | yes | `0` |
| `vehicle_type` | enum | yes | `mini` | Added |
| `payment_method` | enum | yes | `upi` | Added |
| `pickup_zone` / `drop_zone` | string | yes | `NOI-S62` / `DEL-CP` | Added |
| `fare_quote_id` | string | no | `fq_7781203` | Added |
| `booking_attempt_id` | string | no | `ba_550192` | Added |

**`no_driver_found`** (Spec; S)

| Param | Type | Req | Example |
|---|---|---|---|
| `pickup_zone` | string | yes | `NOI-S18` |
| `wait_seconds` | int | yes | `240` |
| `vehicle_type` | enum | yes | `mini` | Added |
| `booking_attempt_id` | string | yes | `ba_550301` | Added |

**`payment_failed`** (Spec; **S**)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_4821` |
| `method` | enum | yes | `card` |
| `error_code` | string | yes | `CARD_DECLINED` |
| `amount_inr` | double | yes | `318.0` | Added (B8 message "Tap to pay ₹318") |

#### Scheduled rides

**`ride_scheduled`** (Spec; S)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_9012` |
| `scheduled_time` | string ISO-8601 with offset | yes | `2026-11-03T05:30:00+05:30` |
| `pickup_zone` | string | yes | `NOI-S137` |
| `drop_zone` | string | yes | `DEL-IGI-T3` |
| `drop_area_name` | string | yes | `IGI Airport T3` | Added |
| `pickup_landmark` | string | no | `Gate 2` | Added (C2 message) |

**`scheduled_ride_cancelled`** (Spec; S)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_9012` |
| `hours_before` | double | yes | `6.5` |

#### Ride lifecycle

**`ride_cancelled`** (Spec; S)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_4821` |
| `cancelled_by` | enum `rider`,`driver`,`system` | yes | `driver` |
| `reason` | string enum (`driver_far`,`changed_plans`,`wait_too_long`,`price`,`other`) | yes | `wait_too_long` |
| `wait_seconds` | int | yes | `540` |

**`ride_started`** (Spec; S)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_4821` |

**`ride_completed`** (Spec; **S**)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_4821` |
| `final_fare` | double | yes | `401.5` (after discount) |
| `distance_km` | double | yes | `18.9` |
| `payment_method` | enum | yes | `upi` |
| `promo_used` | bool(int) | yes | `1` |
| `promo_code` | string | no | `GO15-7KQ2` | Added |
| `discount_inr` | double | no | `63.0` | Added (actual discount) |
| `gross_fare` | double | yes | `464.5` | Added (pre-discount; needed for incremental fare value) |
| `vehicle_type` | enum | yes | `mini` | Added |
| `pickup_zone` / `drop_zone` | string | yes | | Added |

**`ride_rated`** (Spec; C)

| Param | Type | Req | Example |
|---|---|---|---|
| `ride_id` | string | yes | `r_4821` |
| `rating` | int 1-5 | yes | `2` |
| `has_comment` | bool(int) | yes | `1` |

#### Promo, referral, wallet, support, notifications

**`promo_viewed`** and **`promo_applied`** (Spec; C)

| Param | Type | Req | Example |
|---|---|---|---|
| `promo_code` | string | yes | `GO15-7KQ2` |
| `campaign_id` | string | yes | `cmp_1042` |
| `playbook_id` | string | no | `B2_abandoned_booking` | Added |

**`referral_shared`** (Spec; C): `channel` enum `whatsapp`,`sms`,`copy_link`,`other` (yes).

**`wallet_topup`** (Spec; S): `amount` double (yes), `balance_after` double (no, Added).

**`support_ticket_opened`** (Spec; S): `category` enum `ride_issue`,`driver_behaviour`,`payment`,`safety`,`lost_item`,`other` (yes); `ride_id` string (no, Added).

**`notification_opened`** (Spec; C) – Push tapped or email/SMS/WhatsApp link opened (link opens go through the engine redirect, which emits this event server-side).

| Param | Type | Req | Example |
|---|---|---|---|
| `campaign_id` | string | yes | `cmp_1042` or `pb_B2_abandoned_booking` |
| `message_id` | string | yes | `msg_8f3a91c2e0d4b7a65c1e2f90_1` |
| `channel` | enum `push`,`sms`,`email`,`whatsapp`,`in_app` | yes | `push` | Added |

#### Additions (not in spec section 3)

| Event | Source | Params | Why |
|---|---|---|---|
| `app_remove` | Firebase automatic (Android only) | none | E6 uninstall signal (spec 5.5). Arrives via GA4 export only, never via webhook. |
| `consent_changed` | S | `channel` enum `push`,`email`,`sms`,`whatsapp` (yes); `opted_in` bool (yes); `change_source` enum `app_settings`,`unsubscribe_link`,`stop_sms`,`support`,`engine` (yes) | Spec 9 "honour unsubscribe instantly"; lets the engine invalidate consent cache in real time (D-053). |
| `promo_redeemed` | S (from Promo API redemption hook) | `promo_id` int, `promo_code` string, `ride_id` string, `discount_inr` double (all yes) | Budget ledger "redeemed" leg (D-020). Now produced by the mock Promo API. |

### 2.4 User properties (spec section 3)

GA4 allows 25 user properties per project; we use 16. **All values are strings** (Firebase `setUserProperty` only accepts strings; numeric ones such as `total_rides` follow a digits-only pattern), names are at most 24 characters and values at most 36 (D-070). The "Type" column below describes the content of the string.

| Property | Type (GA4 value) | Owner | Example | Now / later |
|---|---|---|---|---|
| `city` | string | app | `Noida` | NOW → GA4 |
| `signup_date` | string `YYYY-MM-DD` | backend | `2026-06-14` | NOW → GA4 |
| `total_rides` | int | backend | `37` | NOW → GA4 |
| `last_ride_date` | string `YYYY-MM-DD` | backend | `2026-10-19` | NOW → GA4 |
| `preferred_vehicle` | string | engine-computed, mirrored | `mini` | ENGINE |
| `preferred_payment` | string | engine-computed, mirrored | `upi` | ENGINE |
| `price_sensitivity` | string `low`/`medium`/`high` | **engine-computed only** (app must not set) | `high` | ENGINE (D-062) |
| `home_zone` | string | engine-computed | `NOI-S62` | ENGINE (D-062) |
| `work_zone` | string | engine-computed | `DEL-CP` | ENGINE (D-062) |
| `lifetime_value_band` | string `low`/`mid`/`high`/`top` | engine-computed | `mid` | ENGINE |
| `marketing_opt_in_push` | string `0`/`1` | backend | `1` | NOW → GA4 (segmentation only; **consent truth is RIDER-API**, D-053) |
| `marketing_opt_in_email` | string `0`/`1` | backend | `0` | as above |
| `marketing_opt_in_sms` | string `0`/`1` | backend | `1` | as above |
| `language` | string `en`/`hi`/`ar`… | app | `hi` | NOW → GA4 |
| `is_synthetic` | string `0`/`1` | generator | `1` | Dev project only (D-012) |
| `marketing_opt_in_wa` | string `0`/`1` | backend | `0` | Added (spec 2 lists WhatsApp channel). Short name because GA4 user property names are max 24 chars (D-070) |

### 2.5 Contract versioning (D-005)

| Change | Version bump | Rule |
|---|---|---|
| New optional param, new event | minor (1.0 → 1.1) | Engine must ignore unknown params/events. |
| New required param, renamed/removed param, type change, enum value removed | major (1.x → 2.0) | Engine supports N and N-1 majors for 90 days; adapters map old → new. |
| Clarification only | patch | Docs only. |

Machine-readable schemas live in `contracts/events/v1/generated/`: one self-contained `envelope.schema.json` with a `$defs` entry per event (D-068), generated from `catalog.yaml` (D-067). The contract test suite validates every generated and every received event against it; senders validate strictly, and the engine's ingest is tolerant (unknown params dropped and logged, unknown events stored but never triggering). Senders can self-check payloads with `validate_contract --events FILE` (D-076).

### 2.6 Deep link contract (D-063)

`hireme://book?quote={fare_quote_id}&drop={drop_zone}&promo={promo_code}&mid={message_id}&cid={campaign_id}` (universal link equivalent `https://hireme.app/l/book?...`). The app must: apply `promo` if valid for the user, open the booking screen with the quote if not expired, and attach `engage_message_id = mid` to subsequent events (section 2.2). → backend/app team at handoff.

---

## 3. BigQuery

All datasets in the dev project live in `asia-south1` (Mumbai) (D-051). Dataset names are configuration (`ENGAGE_BQ_*`), so a dataset can be replaced by the real one by changing config (D-059).

| Dataset | Purpose | Written by | Now / later |
|---|---|---|---|
| `analytics_999999999` | Raw events, **exact GA4 export shape** (`events_YYYYMMDD`, `events_intraday_YYYYMMDD`) | Generator (load jobs), simulator (streaming) | NOW → GA4 (replace with `analytics_<real_property_id>`) |
| `hireme_ref` | Cities, zones, vehicle types, festival calendar | Seed SQL | ENGINE (kept) |
| `hireme_backend_stub` | Stand-in for HireMe backend tables: riders snapshot, rides, promo redemptions | Generator + mock Promo API | NOW → RIDER-API / backend export |
| `engage_features` | Daily user features, segments, base rates, fraud flags | `engage-jobs` SQL | ENGINE |
| `engage_ops` | Append-only mirror of engine operational records (decisions, messages, promos, ledger entries, audit, approvals, playbook versions) | Engine log shipper | ENGINE |
| `engage_ml` | Training sets, score log, model registry | `engage-jobs` | ENGINE |
| `engage_mart` | Reporting marts (spec section 10) | `engage-jobs` SQL | ENGINE |
| `engage_views` | Read-only, aggregated, PII-free views; the only dataset the Ask-AI agent may query | DDL | ENGINE (D-035) |
| `engage_sim` | Ground truth (personas, true uplift). **Never readable by engine or models.** | Generator | Dev only (D-012) |

### 3.1 Raw events: `analytics_999999999.events_YYYYMMDD` (GA4 export shape, D-003)

Daily sharded tables, `event_date` in the property time zone (set to Asia/Kolkata), plus `events_intraday_YYYYMMDD` for "today" (streamed). `contracts/bigquery/ga4_events_schema.json` holds the GA4 export schema's core columns now and is diffed against a real export at M0.2 (D-077); the columns below are the ones we populate (all other GA4 columns are created and left NULL so real-export queries run unchanged). All DDL is in `contracts/bigquery/ddl/`. Timestamp-partitioned tables partition by UTC date, because BigQuery partition expressions cannot take a time zone (D-075); the `contracts/` files are authoritative.

```sql
-- Template; the loader creates one shard per IST day: events_20261021, ...
CREATE TABLE IF NOT EXISTS `hireme-engage-dev.analytics_999999999.events_${YYYYMMDD}` (
  event_date STRING,                       -- 'YYYYMMDD' in Asia/Kolkata
  event_timestamp INT64,                   -- microseconds since epoch, UTC
  event_name STRING,
  event_params ARRAY<STRUCT<
    key STRING,
    value STRUCT<string_value STRING, int_value INT64, float_value FLOAT64, double_value FLOAT64>>>,
  event_previous_timestamp INT64,
  event_value_in_usd FLOAT64,
  event_bundle_sequence_id INT64,
  event_server_timestamp_offset INT64,
  user_id STRING,
  user_pseudo_id STRING,
  privacy_info STRUCT<analytics_storage STRING, ads_storage STRING, uses_transient_token STRING>,
  user_properties ARRAY<STRUCT<
    key STRING,
    value STRUCT<string_value STRING, int_value INT64, float_value FLOAT64, double_value FLOAT64,
                 set_timestamp_micros INT64>>>,
  user_first_touch_timestamp INT64,
  user_ltv STRUCT<revenue FLOAT64, currency STRING>,
  device STRUCT<
    category STRING, mobile_brand_name STRING, mobile_model_name STRING, mobile_marketing_name STRING,
    mobile_os_hardware_model STRING, operating_system STRING, operating_system_version STRING,
    vendor_id STRING, advertising_id STRING, language STRING, is_limited_ad_tracking STRING,
    time_zone_offset_seconds INT64>,
  geo STRUCT<city STRING, country STRING, continent STRING, region STRING, sub_continent STRING, metro STRING>,
  app_info STRUCT<id STRING, version STRING, install_store STRING, firebase_app_id STRING, install_source STRING>,
  traffic_source STRUCT<name STRING, medium STRING, source STRING>,
  stream_id STRING,
  platform STRING,                         -- 'ANDROID' | 'IOS'
  is_active_user BOOL,
  batch_event_index INT64,
  batch_ordering_id INT64,
  batch_page_id INT64
  -- + remaining official GA4 columns (ecommerce, items, collected_traffic_source, session_traffic_source_last_click, ...) as NULLable
);
```

Mapping rules (D-057): string params → `string_value`; int/bool → `int_value`; double → `double_value`. `event_uuid` and `contract_version` are ordinary params. Server-origin events in the synthetic data use `platform = 'ANDROID'|'IOS'` of the user's device and `origin = 'server'` (in the real world server events are not in GA4 unless the backend uses the Measurement Protocol; see OQ-06).

Canonical extraction view used by every downstream job (works on both synthetic and real export):

```sql
CREATE OR REPLACE VIEW `hireme-engage-dev.engage_features.v_events_flat` AS
SELECT
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'event_uuid') AS event_uuid,
  event_name,
  TIMESTAMP_MICROS(event_timestamp) AS event_ts,
  PARSE_DATE('%Y%m%d', event_date) AS event_date_ist,
  user_id, user_pseudo_id, platform,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'city_id') AS city_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'origin') AS origin,
  event_params, user_properties, _TABLE_SUFFIX AS table_suffix
FROM `hireme-engage-dev.analytics_999999999.events_*`;   -- matches events_YYYYMMDD and events_intraday_YYYYMMDD
```

Dedupe rule: `QUALIFY ROW_NUMBER() OVER (PARTITION BY event_key ORDER BY table_suffix) = 1` (the daily table wins over intraday). The authoritative view (`contracts/bigquery/ddl/70_views.sql`) adds `event_key` = `event_uuid`, or a hash for Firebase automatic events such as `app_remove` that carry no `event_uuid` (D-072).

### 3.2 Reference: `hireme_ref`

```sql
CREATE TABLE hireme_ref.cities (
  city_id INT64 NOT NULL, city_name STRING NOT NULL, state STRING, country STRING,
  timezone STRING NOT NULL,            -- 'Asia/Kolkata'
  currency STRING NOT NULL,            -- 'INR'
  is_pilot BOOL NOT NULL
);
CREATE TABLE hireme_ref.zones (
  zone_id STRING NOT NULL, city_id INT64 NOT NULL, zone_name STRING NOT NULL,
  zone_type STRING NOT NULL,           -- residential|business|airport|railway|mall|nightlife|education
  lat FLOAT64, lng FLOAT64, base_demand_weight FLOAT64
);
CREATE TABLE hireme_ref.vehicle_types (vehicle_type STRING, display_name STRING, base_fare_inr NUMERIC(12,2), per_km_inr NUMERIC(12,2), per_min_inr NUMERIC(12,2));
CREATE TABLE hireme_ref.calendar_events (event_date DATE, city_id INT64, kind STRING, name STRING, demand_multiplier FLOAT64); -- Diwali 2026-11-08, etc.
```

### 3.3 Backend stand-ins: `hireme_backend_stub` (NOW → RIDER-API / backend)

```sql
CREATE TABLE hireme_backend_stub.riders_snapshot (      -- daily copy of Firestore hireme_riders (PII-free columns only)
  snapshot_date DATE, user_id STRING, city_id INT64, signup_ts TIMESTAMP, language STRING,
  has_email BOOL, has_push_token BOOL, push_platform STRING,
  consent_push BOOL, consent_email BOOL, consent_sms BOOL, consent_whatsapp BOOL,
  wallet_balance_inr NUMERIC(12,2), device_id_hash STRING, payment_fingerprints ARRAY<STRING>,
  referral_code_used STRING, referred_by_user_id STRING, birth_month_day STRING, is_synthetic BOOL
) PARTITION BY snapshot_date CLUSTER BY city_id, user_id;

CREATE TABLE hireme_backend_stub.rides (                 -- source of truth for fares after handoff
  ride_id STRING, user_id STRING, city_id INT64, status STRING,  -- completed|cancelled|no_driver
  booked_ts TIMESTAMP, started_ts TIMESTAMP, completed_ts TIMESTAMP, is_scheduled BOOL, scheduled_ts TIMESTAMP,
  pickup_zone STRING, drop_zone STRING, distance_km FLOAT64, vehicle_type STRING, payment_method STRING,
  gross_fare_inr NUMERIC(12,2), discount_inr NUMERIC(12,2), final_fare_inr NUMERIC(12,2),
  promo_code STRING, promo_id INT64, surge_multiplier FLOAT64, driver_id STRING, rating INT64
) PARTITION BY DATE(booked_ts) CLUSTER BY city_id, user_id;

CREATE TABLE hireme_backend_stub.promo_redemptions (
  promo_id INT64, code STRING, user_id STRING, ride_id STRING, redeemed_ts TIMESTAMP, discount_inr NUMERIC(12,2)
) PARTITION BY DATE(redeemed_ts);
```

### 3.4 Features: `engage_features` (ENGINE)

```sql
CREATE TABLE engage_features.user_features_daily (
  snapshot_date DATE NOT NULL,                 -- IST day the snapshot describes (as of 23:59:59 IST)
  user_id STRING NOT NULL, city_id INT64, feature_version STRING NOT NULL,   -- 'fv1'
  signup_date DATE, days_since_signup INT64,
  total_rides INT64, rides_7d INT64, rides_30d INT64, rides_90d INT64,
  last_ride_date DATE, days_since_last_ride INT64, avg_weekly_rides_prior_8w FLOAT64,
  weekday_ride_share_90d FLOAT64, weekend_ride_share_90d FLOAT64, airport_rides_90d INT64,
  commute_regularity_score FLOAT64, commute_hour_mode INT64, home_zone STRING, work_zone STRING,
  fare_checks_7d INT64, fare_checks_30d INT64, fare_checks_per_ride_30d FLOAT64, fare_checks_no_book_7d INT64,
  abandons_30d INT64, surge_abandon_rate_30d FLOAT64,
  promo_ride_share_90d FLOAT64, promo_redemptions_30d INT64,
  avg_fare_90d NUMERIC(12,2), spend_30d NUMERIC(12,2), spend_90d NUMERIC(12,2),
  preferred_vehicle STRING, preferred_payment STRING, long_trip_mini_share_90d FLOAT64,
  low_rating_7d BOOL, support_ticket_7d BOOL,
  notif_sent_30d INT64, notif_open_rate_30d FLOAT64, best_open_hour_ist INT64,
  price_sensitivity_score FLOAT64, price_sensitivity_band STRING,   -- low|medium|high (D-062)
  churn_score FLOAT64,                                              -- NULL in Phase 1; model output in Phase 2
  discount_trained_flag BOOL, fraud_flag BOOL, fraud_reasons ARRAY<STRING>,
  ltv_band STRING, language STRING, segments ARRAY<STRING>
) PARTITION BY snapshot_date CLUSTER BY city_id, user_id
OPTIONS (partition_expiration_days = 400);

CREATE TABLE engage_features.segment_membership_daily (
  snapshot_date DATE, segment_id STRING, user_id STRING, city_id INT64
) PARTITION BY snapshot_date CLUSTER BY segment_id, city_id;

CREATE TABLE engage_features.playbook_base_rates (     -- feeds the Phase 1 heuristic scorer (D-029)
  computed_date DATE, playbook_id STRING, city_id INT64, price_sensitivity_band STRING, recency_band STRING,
  n_triggers INT64, p0_conversion FLOAT64, p0_ci_low FLOAT64, p0_ci_high FLOAT64, source STRING  -- 'history_no_msg'|'holdout'
);

CREATE TABLE engage_features.fraud_flags_daily (
  snapshot_date DATE, user_id STRING, reason STRING,  -- multi_account_device|shared_payment|repeat_welcome|code_only_booker
  evidence JSON
) PARTITION BY snapshot_date;

CREATE TABLE engage_features.zone_hour_stats (
  stat_hour TIMESTAMP, zone_id STRING, fare_checks INT64, bookings INT64, no_driver_found INT64,
  avg_surge FLOAT64, conversion_rate FLOAT64
) PARTITION BY DATE(stat_hour) CLUSTER BY zone_id;
```

Segment definitions (spec 6.2), versioned SQL in `sql/features/segments.sql`:

| segment_id | Rule (fv1) |
|---|---|
| `new_not_activated` | `total_rides = 0` |
| `commuters` | ≥ 3 weekday rides in last 14 days with `commute_regularity_score ≥ 0.6` (same zone pair, start hour ±1 h) |
| `weekend_riders` | `weekend_ride_share_90d ≥ 0.7` and `rides_90d ≥ 3` (Fri–Sun) |
| `airport_travellers` | `airport_rides_90d ≥ 2` |
| `price_sensitive` | `price_sensitivity_band = 'high'` |
| `high_value` | top 10 % by `spend_90d` within city |
| `at_risk` | `churn_score > 0.7` (Phase 2) |
| `lapsing_7_14` | `days_since_last_ride BETWEEN 7 AND 14` and `avg_weekly_rides_prior_8w ≥ 1` |
| `lapsed_30` | `days_since_last_ride BETWEEN 30 AND 89` |
| `dormant_90` | `days_since_last_ride ≥ 90` |
| `unhappy` | `low_rating_7d OR support_ticket_7d` |
| `discount_trained` | `discount_trained_flag` (D-046) |
| `fraud_flagged` | `fraud_flag` (D-046) |

Price sensitivity v1 (rules, D-062): `score = 0.4·min(fare_checks_per_ride_30d/5,1) + 0.3·promo_ride_share_90d + 0.2·surge_abandon_rate_30d + 0.1·min(fare_checks_no_book_7d/3,1)`; bands: high ≥ 0.6, medium ≥ 0.3, else low. Riya (two fare checks without booking, frequent promo use) lands in high.

### 3.5 Engine operations mirror: `engage_ops` (ENGINE, append-only, D-007)

Each Firestore write to an operational collection also appends a row here (status changes append a new row; `QUALIFY` the latest by `updated_at`). These tables implement the spec 8.5 core tables for analytics.

```sql
CREATE TABLE engage_ops.decisions (
  decision_id STRING, updated_at TIMESTAMP, user_id STRING, city_id INT64,
  playbook_id STRING, playbook_version INT64, campaign_id STRING,
  trigger_event_uuid STRING, trigger_event_name STRING, trigger_event_ts TIMESTAMP, timer_id STRING,
  arm STRING,                               -- treatment|holdout|exploration
  status STRING,                            -- see §4.6 status machine
  reason_code STRING, reason_detail STRING,
  scores JSON,                              -- {"p0":0.22,"p1":{"0":0.27,"10":0.41,"15":0.48},"price_sensitivity":0.71,"churn":null,"scorer":"heuristic_v1"}
  offer JSON,                               -- {"rung":15,"type":"percent","value":15,"max_discount_inr":75,"expected_cost_inr":30.2,"liability_inr":75}
  channel STRING, send_at TIMESTAMP, template_id STRING, autonomy_effective INT64, approval_id STRING,
  guardrails JSON,                          -- [{"check":"budget","result":"pass"},...]
  attribution_window_hours INT64, clock_mode STRING, sim_run_id STRING
) PARTITION BY DATE(updated_at) CLUSTER BY playbook_id, city_id, user_id;

CREATE TABLE engage_ops.messages (
  message_id STRING, updated_at TIMESTAMP, decision_id STRING, user_id STRING, channel STRING, provider STRING,
  provider_message_id STRING, template_id STRING, language STRING, llm_used BOOL, llm_model STRING,
  status STRING,                            -- queued|sending|sent|delivered|failed|undeliverable|dlq|cancelled
  attempt INT64, error_code STRING, sent_at TIMESTAMP, delivered_at TIMESTAMP, opened_at TIMESTAMP,
  cost_inr NUMERIC(12,4)                    -- per-message channel cost (SMS/WhatsApp) for channel report
) PARTITION BY DATE(updated_at) CLUSTER BY channel, decision_id;

CREATE TABLE engage_ops.promos (
  promo_ref STRING, updated_at TIMESTAMP, promo_id INT64, code STRING, decision_id STRING, campaign_id STRING,
  playbook_id STRING, user_id STRING, city_id INT64, type STRING, value NUMERIC(12,2), max_discount_inr NUMERIC(12,2),
  liability_inr NUMERIC(12,2), valid_from TIMESTAMP, valid_to TIMESTAMP,
  status STRING,                            -- creating|active|redeemed|expired|deactivated|failed
  redeemed_at TIMESTAMP, ride_id STRING, cost_inr NUMERIC(12,2), created_by STRING   -- ai|admin
) PARTITION BY DATE(updated_at) CLUSTER BY playbook_id, user_id;

CREATE TABLE engage_ops.budget_ledger_entries (
  entry_id STRING, created_at TIMESTAMP, ledger_date DATE, city_id INT64, playbook_id STRING,
  kind STRING,                              -- commit|redeem|release
  amount_inr NUMERIC(12,2), promo_ref STRING, decision_id STRING
) PARTITION BY ledger_date CLUSTER BY city_id, playbook_id;

CREATE TABLE engage_ops.audit_log (
  audit_id STRING, created_at TIMESTAMP, actor_type STRING, actor_id STRING, actor_role STRING,
  action STRING, target_type STRING, target_id STRING, before_json JSON, after_json JSON, reason STRING, request_id STRING
) PARTITION BY DATE(created_at);

CREATE TABLE engage_ops.playbook_versions (playbook_id STRING, version INT64, created_at TIMESTAMP, created_by STRING, config JSON, approved_by STRING, approved_at TIMESTAMP);
CREATE TABLE engage_ops.approvals (approval_id STRING, updated_at TIMESTAMP, kind STRING, status STRING, payload JSON, decided_by STRING, decided_at TIMESTAMP);
CREATE TABLE engage_ops.timers_log (timer_id STRING, updated_at TIMESTAMP, playbook_id STRING, user_id STRING, status STRING, fire_at TIMESTAMP, reason STRING) PARTITION BY DATE(updated_at);
```

### 3.6 ML: `engage_ml` (ENGINE)

```sql
CREATE TABLE engage_ml.uplift_training_examples (
  decision_id STRING, playbook_id STRING, user_id STRING, city_id INT64, decision_ts TIMESTAMP,
  arm STRING,                    -- holdout|treatment|exploration
  action STRING,                 -- none|reminder|pct_10|pct_15|pct_20|flat_30|flat_50
  features JSON,                 -- snapshot of user_features_daily (as of decision_ts - 1 day) + trigger context
  converted_window BOOL,         -- ride_booked within attribution window
  converted_24h BOOL, converted_7d BOOL,
  fare_value_inr NUMERIC(12,2), discount_cost_inr NUMERIC(12,2), sim_run_id STRING
) PARTITION BY DATE(decision_ts) CLUSTER BY playbook_id;

CREATE TABLE engage_ml.churn_training_examples (as_of_date DATE, user_id STRING, features JSON, churned_30d BOOL) PARTITION BY as_of_date;
CREATE TABLE engage_ml.score_log (scored_at TIMESTAMP, decision_id STRING, model_id STRING, p0 FLOAT64, p1 JSON, churn FLOAT64, latency_ms INT64) PARTITION BY DATE(scored_at);
CREATE TABLE engage_ml.model_registry (model_id STRING, kind STRING, playbook_scope ARRAY<STRING>, trained_at TIMESTAMP, train_from DATE, train_to DATE, metrics JSON, artifact_uri STRING, status STRING); -- candidate|shadow|active|retired
```

### 3.7 Reporting marts: `engage_mart` (spec section 10)

| Table | Grain | Key columns | Spec report |
|---|---|---|---|
| `funnel_daily` | IST date × city × platform | sign_ups, fare_checks, bookings_started, booked, completed | Funnel |
| `playbook_daily` | IST date × city × playbook × arm | eligible, holdout, sent, delivered, opened, converted, conv_rate, promo_cost_inr, fare_value_inr | Playbook performance |
| `holdout_lift` | period × city × playbook | n_treat, n_hold, conv_treat, conv_hold, lift_pp, ci_low, ci_high, incremental_rides, incremental_fare_inr, promo_cost_inr, roi, significant | Playbook performance (incremental) |
| `channel_daily` | date × city × channel | sent, delivered, opened, converted, channel_cost_inr, cost_per_conversion_inr | Channel performance |
| `promo_daily` | date × city × playbook | codes_created, codes_redeemed, value_given_inr, top_codes, abuse_flags | Promo report |
| `budget_pacing_daily` | date × city × playbook | budget_month_inr, committed_outstanding_inr, redeemed_mtd_inr, forecast_month_end_inr, pct_used | Budget pacing |
| `cohort_retention_weekly` | signup_week × touched flag | w1, w4, w12 retention | Cohort retention |
| `ai_activity_daily` | date × playbook | decisions, sent, skipped_by_reason (JSON), approvals_pending, model_auc, calibration_error | AI activity |

`holdout_lift` is intention-to-treat on the assigned arm (D-018, D-060):

```sql
-- sql/marts/holdout_lift.sql (abridged)
WITH d AS (
  SELECT decision_id, user_id, city_id, playbook_id, arm, created_ts, window_h,
         IF(arm = 'holdout', 'hold', 'treat') AS grp
  FROM engage_mart.v_decisions_latest
  WHERE created_ts BETWEEN @from AND @to AND status != 'cancelled_by_event'
), conv AS (
  SELECT d.decision_id, LOGICAL_OR(e.event_name = 'ride_booked') AS converted,
         SUM(IF(e.event_name = 'ride_completed', e.gross_fare, 0)) AS fare_value
  FROM d LEFT JOIN engage_features.v_ride_events e
    ON e.user_id = d.user_id AND e.event_ts > d.created_ts
   AND e.event_ts <= TIMESTAMP_ADD(d.created_ts, INTERVAL d.window_h HOUR)
  GROUP BY d.decision_id
)
SELECT playbook_id, city_id,
  COUNTIF(grp='treat') n_treat, COUNTIF(grp='hold') n_hold,
  SAFE_DIVIDE(COUNTIF(grp='treat' AND converted), COUNTIF(grp='treat')) conv_treat,
  SAFE_DIVIDE(COUNTIF(grp='hold' AND converted), COUNTIF(grp='hold')) conv_hold
  -- lift, 95% CI (Newcombe), incremental rides = lift × n_treat, ROI computed in the next CTE
FROM d JOIN conv USING (decision_id) GROUP BY 1, 2;
```

### 3.8 Approved views for Ask-AI: `engage_views` (D-035)

`v_funnel_daily`, `v_playbook_performance`, `v_channel_performance`, `v_promo_summary`, `v_budget_pacing`, `v_segment_sizes`, `v_zone_hour_demand`, `v_scheduled_rides_daily`. Rules: no `user_id`, phone, email or code columns; every grouped row with fewer than 20 users is suppressed (k-anonymity, k = 20).

### 3.9 Ground truth: `engage_sim` (dev only, D-012)

`personas(user_id, persona_id, latent JSON)`, `true_effects(persona_id, playbook_id, action, p_convert, p_optout)`, `response_ledger(sim_run_id, message_id, user_id, drew_open BOOL, drew_convert BOOL, true_p0, true_p1)`. IAM: readable only by the `sim-validator` service account and humans; the engine service account has no access.

---

## 4. Firestore (engine operational state, D-006)

Firestore (Native mode, `asia-south1`) in the dev Firebase project `hireme-engage-dev`. Access from services via Admin SDK; from Claude Code and LLM agents via the Firebase MCP server (D-010). All documents carry `created_at`, `updated_at` (server timestamps) and, where noted, `expire_at` (Firestore TTL policy).

### 4.1 Collection map

| Collection | Doc id | Purpose | Spec 8.5 table | Now / later | TTL |
|---|---|---|---|---|---|
| `engage_settings` | `global`, `city_{city_id}` | Kill switch, autonomy caps, freq caps, quiet hours, holdout salt | — | ENGINE | — |
| `engage_playbooks` | `{playbook_id}` | Current config; subcollection `versions/{n}` immutable | `engage_playbook` | ENGINE | — |
| `engage_templates` | `{template_id}` | Message templates per channel/language | `engage_template` | ENGINE | — |
| `engage_budgets` | `{budget_id}` | Budget limits by scope | (`budget` of `engage_playbook`) | ENGINE | — |
| `engage_budget_ledger` | `{ledger_id}` | Running counters; subcollection `entries/{entry_id}` | `engage_budget_ledger` | ENGINE | entries 400 d |
| `engage_decisions` | `{decision_id}` | One per candidate (incl. holdout/skipped) | `engage_decision` | ENGINE | 180 d (BQ keeps all) |
| `engage_messages` | `{message_id}` | Message + dispatch outbox | `engage_message` | ENGINE | 180 d |
| `engage_promos` | `{promo_ref}` | Promo codes created via Promo API | `engage_promo` | ENGINE | 180 d |
| `engage_timers` | `{timer_id}` | Pending triggers (delays, cancel_if) | — | ENGINE | 30 d after terminal |
| `engage_user_state` | `{user_id}` | Caps, cooldowns, suppressions, promo-per-month | — | ENGINE | — |
| `engage_user_profile` | `{user_id}` | Feature snapshot synced from BigQuery | — | ENGINE | — |
| `engage_events_live` | `{event_uuid}` | **Event Inbox** (all sources converge here) | — | NOW (sim) → written by webhook / GA4 poller | 7 d |
| `engage_source_checkpoints` | `{source_id}` | Poller watermarks | — | ENGINE | — |
| `engage_approvals` | `{approval_id}` | Approval queue | — | ENGINE | — |
| `engage_campaigns` | `{campaign_id}` | Manual broadcasts and AI-drafted campaigns | — | ENGINE | — |
| `engage_segments` | `{segment_id}` | Segment definitions + latest counts | — | ENGINE | — |
| `engage_audit_log` | `{audit_id}` | Who/what/when/why | `engage_audit_log` | ENGINE | 400 d (BQ forever) |
| `engage_dlq` | `{message_id}` or `{job_id}` | Dead letters | — | ENGINE | 30 d |
| `engage_idempotency` | `{key_hash}` | API idempotency records | — | ENGINE | 24 h |
| `engage_ask_sessions` | `{session_id}` | Ask-AI Q&A history | — | ENGINE | 90 d |
| `engage_digests` | `{yyyymmdd}_{city_id}` | H1 daily digests | — | ENGINE | — |
| `engage_alerts` | `{alert_id}` | H2/H5 alerts | — | ENGINE | — |
| `engage_models` | `{model_id}` | Active model pointers | — | ENGINE | — |
| `hireme_riders` | `{user_id}` | **Rider DB stand-in** (contact, consent, wallet, device) | — | NOW → **RIDER-API** (D-013) | — |
| `mock_promo_codes` | `{promo_id}` | State of the mock Promo API | — | NOW → real Promo API | — |
| `mock_deliveries` | `{provider_message_id}` | Everything the mock channels "sent" | — | NOW → real providers | 30 d |
| `sim_runs` | `{run_id}` | Simulator run config/state/clock | — | Dev only | — |

### 4.2 Configuration documents

**`engage_settings/global`**

| Field | Type | Example | Notes |
|---|---|---|---|
| `kill_switch` | map `{active: bool, scope: "marketing_and_service"\|"all", reason: string, set_by: string, set_at: ts}` | `{active:false,...}` | D-027 |
| `autonomy_max` | int 0-3 | `1` | Global ceiling (D-028) |
| `freq_caps` | map `{marketing_per_day: 1, marketing_per_7d: 3, service_per_day: 2}` | | Spec 7/9 (D-022) |
| `quiet_hours` | map `{start: "22:00", end: "08:00", applies_to: ["marketing","service"]}` | | Spec 7 (D-024) |
| `holdout_salt` | string | `hm-2026q4` | Read-only via API (D-018) |
| `global_holdout_percent` | number | `0` | D-056 |
| `user_promo_caps` | map `{max_value_inr_per_month: 300, max_codes_per_month: 4, max_discount_per_ride_inr: 100}` | | Spec 7/9 |
| `llm` | map `{enabled: false, writer_model: "claude-haiku-5-5", ...}` | | D-032 |
| `scoring` | map `{provider: "heuristic_v1", min_uplift: 0.02, value_basis: "fare"}` | | D-029, D-030 |
| `source_mode` | string `firestore_inbox`\|`ga4_bq_poll`\|`webhook` (multi allowed as array) | `["firestore_inbox"]` | D-002 |
| `version` | int | `12` | Optimistic concurrency |

`engage_settings/city_3` overrides: `autonomy_max`, `quiet_hours`, `enabled`, `timezone`.

**`engage_playbooks/{playbook_id}`** – Current version of the config (schema in section 5). Extra fields: `version` (int), `status` (`draft`\|`pending_approval`\|`approved`\|`retired`), `approved_version` (int; the version the engine executes), `stats_cache` (map, last 7 d), `auto_paused` (map `{active, reason: "negative_roi_14d", at}`, spec 6.5). Subcollection `versions/{version}` holds immutable copies (D-058); every decision stores `playbook_version`.

**`engage_templates/{template_id}`**

| Field | Type | Example |
|---|---|---|
| `template_id` | string | `tpl_B2_push_en_v1` |
| `playbook_id` | string | `B2_abandoned_booking` |
| `channel` | enum `push`,`sms`,`email`,`whatsapp`,`in_app` | `push` |
| `language` | string | `en` |
| `message_class` | enum `transactional`,`service`,`marketing` | `marketing` |
| `title` | string | `Still heading to {drop_area}?` |
| `body` | string | `Complete your ride in the next {validity_minutes} min and save {discount_label} with {promo_code}.` |
| `variables` | array<string> | `["first_name","drop_area","fare","promo_code","expiry","discount_label","validity_minutes"]` |
| `llm_personalisable` | bool | `true` (always `false` for sms/whatsapp, D-033) |
| `variants` | array<map> | LLM-approved phrasing variants (Phase 2) |
| `dlt` | map `{template_id, sender_id, pe_id, category}` | SMS only |
| `wa_template` | map `{name, namespace, language}` | WhatsApp only |
| `approved_by` / `approved_at` | string / ts | `uid_marketing_7` |
| `status` | enum `draft`,`approved`,`retired` | `approved` |

**`engage_budgets/{budget_id}`**

| Field | Type | Example |
|---|---|---|
| `scope` | enum `global`,`city`,`playbook`,`city_playbook` | `city_playbook` |
| `city_id` | int\|null | `3` |
| `playbook_id` | string\|null | `B2_abandoned_booking` |
| `daily_inr` / `monthly_inr` | number\|null | `5000` / `100000` |
| `alert_threshold_pct` | int | `80` |
| `hard_stop` | bool | `true` |
| `throttle_policy` | enum `none`,`low_roi_first` | `low_roi_first` (H5) |

**`engage_segments/{segment_id}`**: `name`, `definition_sql_ref` (path in repo), `feature_version`, `latest_counts` (map city→int), `computed_at`.

### 4.3 Event Inbox: `engage_events_live/{event_uuid}`

Canonical envelope (section 2.1) plus engine fields. Writing with `create()` makes duplicates fail, which gives dedupe for free (D-002).

| Field | Type | Notes |
|---|---|---|
| envelope fields | as §2.1 | `params` and `user_properties` are maps |
| `event_ts` | Timestamp | Converted from ISO string |
| `received_at` | Timestamp | |
| `processed` | map `{state: "new"\|"done"\|"error", at, attempts, error}` | Set by inbox consumer |
| `sim_run_id` | string | Simulator only |
| `expire_at` | Timestamp | `received_at + 7 d` (TTL) |

### 4.4 Timers: `engage_timers/{timer_id}` (D-008)

`timer_id = "tmr_" + sha256(playbook_id | user_id | dedupe_key)[:24]`, where `dedupe_key` is the trigger `event_uuid` for `event_delay`, `ride_id|offset` for `relative_time`, and `IST date` for batch.

| Field | Type | Example |
|---|---|---|
| `playbook_id`, `playbook_version` | string, int | `B2_abandoned_booking`, `3` |
| `user_id`, `city_id` | string, int | `u_88213`, `3` |
| `trigger` | map `{event_uuid, event_name, event_ts, params}` | context copied from the event |
| `fire_at` | Timestamp | `event_ts + wait_minutes` |
| `cancel_if` | array<map `{event, match_params: [..]}`> | `[{event:"ride_booked", match_params: []}]` |
| `status` | enum `pending`,`leased`,`fired`,`cancelled`,`superseded`,`expired`,`error` | |
| `lease_owner`, `lease_until` | string, Timestamp | sweeper lease |
| `cancelled_by` | map `{event_uuid, event_name}` | |
| `attempts` | int | |
| `clock` | enum `real`,`virtual` | D-016 |
| `expire_at` | Timestamp | terminal + 30 d |

### 4.5 User engagement state: `engage_user_state/{user_id}`

Updated only inside the guardrail reservation transaction (section 4.7) or by outcome handlers.

| Field | Type | Example / notes |
|---|---|---|
| `mkt_sends` | array<Timestamp> (last 10) | rolling 7-day cap (D-022) |
| `mkt_sends_by_day` | map `yyyy-mm-dd(IST)` → int (last 8 days) | daily cap |
| `service_sends_by_day` | map | service cap |
| `cooldowns` | map `playbook_id` → Timestamp (until) | `{ "B2_abandoned_booking": 2026-10-22T18:25+05:30 }` |
| `suppress_marketing_until` | Timestamp\|null | D2 48 h pause |
| `suppress_reason` | string | `bad_experience` |
| `promo_month` | map `yyyy-mm` → `{committed_paise, redeemed_paise, codes}` | user caps |
| `active_codes` | array<string promo_ref> | |
| `last_open_at`, `open_hour_hist` | Timestamp, array<int>[24] | channel/time selection |
| `counters_rt` | map `{fare_checks_today, abandons_today, last_event_at}` | real-time counters from inbox |
| `holdout_cache` | map `playbook_id` → bool | cached hash result (re-derivable) |
| `exclusive_group_last` | map `group` → `{decision_id, at}` | conflict resolution (D-064) |

### 4.6 Decisions, messages, promos

**`engage_decisions/{decision_id}`** – `decision_id = "dec_" + sha256(playbook_id | user_id | dedupe_key)[:24]` (deterministic, D-025).

| Field | Type | Notes |
|---|---|---|
| `user_id`, `city_id`, `playbook_id`, `playbook_version`, `campaign_id` | | `campaign_id` = `pb_{playbook_id}` for playbook sends |
| `trigger` | map | event or batch context |
| `timer_id` | string | |
| `arm` | enum `treatment`,`holdout`,`exploration` | D-018, D-019 |
| `status` | enum (below) | |
| `reason_code`, `reason_detail` | string | enumerated list below |
| `scores` | map `{p0, p1: {rung: p}, churn, price_sensitivity, scorer, model_id}` | spec 6.1 step 2 |
| `offer` | map `{rung, type, value, max_discount_inr, expected_cost_inr, liability_inr, rationale}` | spec 6.1 steps 3-4 |
| `channel`, `fallback_channels` | string, array | spec 6.1 step 5 |
| `send_at` | Timestamp | quiet-hours deferral |
| `template_id`, `message_ids`, `promo_ref` | | |
| `guardrails` | array<map `{check, result, detail}`> | full trace for "why" in audit/explain |
| `autonomy_effective`, `approval_id` | int, string | D-028 |
| `attribution` | map `{window_hours, converted: bool, converted_at, ride_id}` | filled by outcome tracker |
| `clock_mode`, `sim_run_id` | | |

Decision status machine: `evaluating → holdout` (terminal, ghost), `→ skipped` (terminal, with reason), `→ queued_approval → approved → scheduled → sent` / `rejected` / `expired`, `→ scheduled → sent` (auto), `→ sent → converted|not_converted` (via attribution fields), `→ failed`, `cancelled_by_event` (timer-time recheck found a cancel event). Spec values `sent, skipped, holdout, queued` are a subset (queued = `queued_approval`).

Reason codes: `audience_mismatch`, `no_consent`, `no_reachable_channel`, `cooldown`, `freq_cap_daily`, `freq_cap_weekly`, `service_cap`, `quiet_hours_skip`, `suppressed_bad_experience`, `fraud_flag`, `discount_trained_downgrade` (not a skip), `likely_to_book_anyway_downgrade` (not a skip), `no_uplift`, `budget_exhausted`, `user_promo_cap`, `kill_switch`, `holdout`, `superseded_exclusive_group`, `cancelled_by_event`, `late_event`, `approval_expired`, `approval_rejected`, `content_check_fallback`, `promo_api_error`, `playbook_disabled`, `playbook_auto_paused`.

**`engage_messages/{message_id}`** – `message_id = "msg_" + decision_id_suffix + "_" + channel_ordinal` (1 = primary, 2 = first fallback). Doubles as the dispatch outbox (D-026).

| Field | Type | Notes |
|---|---|---|
| `decision_id`, `user_id`, `channel`, `channel_ordinal`, `message_class` | | |
| `provider` | string | `mock_fcm`, `fcm`, `mock_sms`, `msg91`… |
| `rendered` | map `{title, body, deep_link, html_ref}` | final text after code insertion |
| `render` | map `{template_id, variant_id, llm_model, llm_latency_ms, content_check: "pass"\|"fallback"}` | |
| `status` | enum `queued`,`sending`,`sent`,`delivered`,`failed`,`undeliverable`,`dlq`,`cancelled` | |
| `next_attempt_at`, `attempt`, `lease_until`, `last_error` | | retry/backoff |
| `provider_message_id`, `sent_at`, `delivered_at`, `opened_at` | | spec 8.5 |
| `cost_inr` | number | channel unit cost |

**`engage_promos/{promo_ref}`** – `promo_ref = "prm_" + decision_id_suffix` (one promo per decision, D-025).

| Field | Type | Notes |
|---|---|---|
| `promo_id` | int | Promo API id (e.g. 55120) |
| `code` | string | `GO15-7KQ2` |
| `decision_id`, `campaign_id`, `playbook_id`, `user_id`, `city_id` | | |
| `type`, `value`, `max_discount_inr`, `min_fare_inr`, `vehicle_types`, `usage_limit` | | mirrors Promo API request |
| `valid_from`, `valid_to` | Timestamp | |
| `liability_paise` | int | committed amount (D-020) |
| `status` | enum `creating`,`active`,`redeemed`,`expired`,`deactivated`,`failed` | |
| `redeemed_at`, `ride_id`, `cost_inr` | | spec `engage_promo.redeemed_at, ride_id, cost_inr` |
| `created_by` | enum `ai`,`admin` | spec 6.3 |

### 4.7 Budget ledger: `engage_budget_ledger/{ledger_id}` (D-020, D-021)

`ledger_id` examples: `D_20261021_c3_B2_abandoned_booking` (day, city × playbook), `M_202610_c3_B2_abandoned_booking` (month, city × playbook), `M_202610_c3_ALL` (city month), `M_202610_ALL_ALL` (global month).

| Field | Type | Meaning |
|---|---|---|
| `period` | enum `D`,`M` | |
| `period_key` | string | `2026-10-21` / `2026-10` (IST) |
| `city_id`, `playbook_id` | int\|`ALL`, string\|`ALL` | |
| `committed_gross_paise` | int | Sum of liabilities ever committed (spec `committed_inr`) |
| `committed_outstanding_paise` | int | Liabilities of codes still active |
| `redeemed_paise` | int | Actual discounts on redeemed codes (spec `redeemed_inr`) |
| `released_paise` | int | Liabilities released on expiry/deactivation |
| `codes_created`, `codes_redeemed` | int | |
| `limit_paise` | int | Copied from the matching `engage_budgets` doc at period start |
| `alert_sent_at` | Timestamp | |

Invariant per ledger doc: `committed_gross = committed_outstanding + released + (liabilities of redeemed codes)`. Budget check (all ledger docs in scope, one Firestore transaction): `committed_outstanding + redeemed + new_liability ≤ limit`. Subcollection `entries/{entry_id}`: `{kind: commit|redeem|release, amount_paise, promo_ref, decision_id, at}`.

**Reservation transaction** (the single choke point before any send; reads ≤ 6 docs):
read `engage_settings/global` (cached ≤ 5 s) → `engage_user_state/{user}` → applicable ledger docs → check caps, cooldown, suppression, user promo caps, budget → write user_state (+cap slot, +cooldown, +promo_month) and ledger (+commit) → write decision status `scheduled`. On send failure, a compensating transaction releases the slot and the commitment.

### 4.8 Approvals, campaigns, audit, rider stub

**`engage_approvals/{approval_id}`**: `kind` (`playbook_version`, `template`, `cohort_batch`, `campaign`, `ai_playbook`), `status` (`pending`,`approved`,`rejected`,`expired`,`edited_approved`), `city_id`, `payload` (map: proposal), `prediction` (map `{reach, cost_inr, incremental_rides, ci}`), `created_by` (`ai`\|uid), `expires_at`, `decided_by`, `decided_at`, `decision_note`.

**`engage_campaigns/{campaign_id}`**: `name`, `kind` (`manual_broadcast`,`ai_suggested`,`festival`), `city_ids`, `segment` (map: segment_id or builder JSON), `channels`, `template_ids`, `promo` (map: readable code like `DIWALI20` or personal), `schedule` (map `{send_at, send_window}`), `budget_inr`, `holdout_percent`, `status` (`draft`,`pending_approval`,`scheduled`,`running`,`completed`,`cancelled`), `stats`.

**`engage_audit_log/{audit_id}`**: `actor_type` (`ai`,`admin`,`system`), `actor_id`, `actor_role`, `action` (e.g. `playbook.update`, `approval.approve`, `kill_switch.activate`, `decision.send`), `target_type`, `target_id`, `before`, `after`, `reason`, `request_id`, `created_at`. Spec `engage_audit_log(actor, action, before_json, after_json, created_at)`.

**`hireme_riders/{user_id}`** (Rider DB stand-in, **→RIDER-API**, D-013, D-074). The document is exactly the `RiderProfile` schema in `contracts/openapi/rider-api.v1.yaml` (the future `GET /api/engage/v1/riders/{user_id}` response, [API.md §5](API.md#5-backend-apis-the-hireme-backend-must-provide-at-handoff)), plus the dev-only field `is_synthetic`. Summary:

| Field | Type | Example | PII |
|---|---|---|---|
| `user_id`, `city_id`, `signup_ts`, `language`, `status` (`active`\|`blocked`\|`deleted`) | | `u_88213`, 3, `active` | no |
| `first_name` | string | `Riya` | low (sent to LLM, D-035) |
| `contact.phone_e164` | string | `+919990012345` (synthetic range) | **yes**, never to LLM |
| `contact.email` | string | `riya.s@example.test` | **yes**, never to LLM |
| `contact.phone_dnd` | bool | TRAI DND (promotional SMS blocked) | — |
| `contact.email_verified` | bool | `true` | — |
| `push_tokens` | array<map `{token, platform, updated_at, stale}`> | | yes |
| `consent` | map `{push, email, sms, whatsapp: {opted_in: bool, updated_at, source}}` | | — |
| `wallet_balance_inr` | number | `42.0` | — |
| `device_id_hash`, `payment_fingerprints` | string, array | | pseudonymous |
| `birth_month_day` | string `MM-DD` | F6 | low |
| `referral` | map `{code, referred_by_user_id}` | A6 | — |
| `is_synthetic` | bool | `true` (dev stub only) | — |

### 4.9 Indexes (`contracts/firestore/firestore.indexes.json`)

| Collection | Fields | Query |
|---|---|---|
| `engage_timers` | `status` ASC, `fire_at` ASC | sweeper: due pending timers |
| `engage_timers` | `user_id` ASC, `status` ASC | cancel_if lookup on new event |
| `engage_events_live` | `user_id` ASC, `event_ts` ASC | fire-time recheck |
| `engage_events_live` | `processed.state` ASC, `received_at` ASC | consumer catch-up |
| `engage_decisions` | `user_id` ASC, `created_at` DESC | user timeline |
| `engage_decisions` | `playbook_id` ASC, `status` ASC, `created_at` DESC | console lists |
| `engage_decisions` | `city_id` ASC, `playbook_id` ASC, `created_at` DESC | city admin views |
| `engage_messages` | `status` ASC, `next_attempt_at` ASC | dispatcher |
| `engage_messages` | `decision_id` ASC, `channel_ordinal` ASC | fallback |
| `engage_promos` | `status` ASC, `valid_to` ASC | expiry release job |
| `engage_promos` | `user_id` ASC, `created_at` DESC | user caps |
| `engage_approvals` | `status` ASC, `expires_at` ASC | queue |
| `engage_approvals` | `city_id` ASC, `status` ASC, `created_at` DESC | city admin queue |
| `engage_audit_log` | `target_type` ASC, `target_id` ASC, `created_at` DESC | audit per object |
| `engage_audit_log` | `actor_id` ASC, `created_at` DESC | audit per actor |

Security rules: deny all client SDK access (`allow read, write: if false;`) for every collection; only service accounts (Admin SDK bypasses rules) and the admin API touch data. The console never reads Firestore directly (D-039).

### 4.10 Mapping to spec section 8.5 core tables

| Spec table | Spec key fields | Firestore (operational) | BigQuery (analytics) | Notes |
|---|---|---|---|---|
| `engage_playbook` | id, name, trigger_json, audience_json, promo_json, channels, budget, autonomy, enabled | `engage_playbooks/{id}` (+`versions`) | `engage_ops.playbook_versions` | `budget` split into `engage_budgets` for multi-scope budgets |
| `engage_template` | id, playbook_id, channel, language, body, variables, approved_by | `engage_templates/{id}` | (config export) | + DLT/WABA ids |
| `engage_decision` | id, user_id, playbook_id, scores_json, offer, channel, status, reason | `engage_decisions/{id}` | `engage_ops.decisions` | + arm, version, guardrail trace |
| `engage_message` | id, decision_id, channel, provider_id, sent_at, delivered_at, opened_at | `engage_messages/{id}` | `engage_ops.messages` | doubles as outbox |
| `engage_promo` | id, promo_id, code, user_id, value, cost_inr, redeemed_at, ride_id | `engage_promos/{ref}` | `engage_ops.promos` | + liability, status |
| `engage_budget_ledger` | city_id, playbook_id, date, committed_inr, redeemed_inr | `engage_budget_ledger/{id}` | `engage_ops.budget_ledger_entries`, `engage_mart.budget_pacing_daily` | + outstanding/released (D-020) |
| `engage_audit_log` | actor, action, before_json, after_json, created_at | `engage_audit_log/{id}` | `engage_ops.audit_log` | + target, reason, request_id |

---

## 5. Playbook configuration

### 5.1 B2 example (extends the spec section 7 example; spec fields unchanged and in bold below)

```json
{
  "playbook_id": "B2_abandoned_booking",
  "version": 1,
  "name": "Abandoned booking",
  "description": "Rider left the booking screen and did not book within 10 minutes (spec 5.2 B2).",
  "category": "B",
  "phase": 1,
  "enabled": true,
  "message_class": "marketing",
  "priority": 20,
  "exclusive_group": "intent_recovery",
  "trigger": {
    "type": "event_delay",
    "event": "booking_abandoned",
    "where": [{ "param": "step", "op": "in", "value": ["fare", "vehicle", "confirm"] }],
    "wait_minutes": 10,
    "cancel_if": ["ride_booked"],
    "on_retrigger": "restart",
    "max_lateness_minutes": 20
  },
  "audience": {
    "cities": ["Noida", "Delhi"],
    "min_total_rides": 0,
    "segments_exclude": ["fraud_flagged"]
  },
  "promo": {
    "allowed": true,
    "type": "percent",
    "ladder": [0, 10, 15, 20],
    "max_discount_inr": 75,
    "min_fare_inr": 100,
    "validity_minutes": 30,
    "single_use": true,
    "user_locked": true,
    "vehicle_types": "same_as_trigger",
    "code_prefix": "GO",
    "no_promo_if_discount_trained": true
  },
  "scoring": {
    "scorer": "heuristic_v1",
    "min_uplift": 0.02,
    "likely_to_book_p0": 0.6,
    "value_basis": "fare",
    "exploration_percent": 10
  },
  "channels": ["push", "sms"],
  "channel_policy": { "fallback_on": ["undeliverable", "no_token", "no_consent"], "fallback_after_unopened_minutes": null },
  "templates": { "push": { "en": "tpl_B2_push_en_v1", "hi": "tpl_B2_push_hi_v1" }, "sms": { "en": "tpl_B2_sms_en_v1", "hi": "tpl_B2_sms_hi_v1" } },
  "timing": { "send": "immediate", "quiet_hours": "respect", "max_defer_minutes": 0 },
  "cooldown_hours": 24,
  "attribution": { "window_hours": 24, "conversion_event": "ride_booked" },
  "budget": { "daily_inr": 5000, "monthly_inr": 100000, "alert_threshold_pct": 80, "hard_stop": true },
  "autonomy": 2,
  "holdout_percent": 10
}
```

The spec's original object (fields `playbook_id`, `enabled`, `trigger.event`, `trigger.wait_minutes`, `trigger.cancel_if`, `audience`, `promo.allowed/ladder/max_discount_inr/validity_minutes/single_use`, `channels`, `cooldown_hours`, `budget`, `autonomy`, `holdout_percent`) validates unchanged against the schema below; every new field has a default.

### 5.2 Trigger types

| `trigger.type` | Semantics | Used by |
|---|---|---|
| `event_delay` | On `event` (matching `where`), wait `wait_minutes`; cancel if any `cancel_if` event for the same user (and matching `match_params`) arrives after the trigger and before fire; fire-time recheck against the inbox. `on_retrigger`: `restart` (debounce), `ignore`, `parallel`. | A2 (0 min), A3 (2880 min), B1, B2, B3, B5, B8, D2, C4 |
| `relative_time` | Schedule at `param_time + offset` for each offset (e.g. `scheduled_time` − 60 and − 15 min); cancel on matching `ride_id`. | C2, C5 |
| `schedule` | Cron in IST (`"0 10 * * *"`) over a segment or SQL audience; one decision per user per run. | E2, E3, E4, F2, F5, H1 |
| `window_count` | N occurrences of an event within a window (e.g. 3 `fare_check` with the same route in 7 d). | B6, C3 (Phase 3) |
| `threshold` | Profile field crosses a value (`total_rides` in [5,10,25,50]). | D3, D4 (Phase 3) |
| `external` | Weather API, admin-marked venue, calendar. | F1, F3 (Phase 3) |

### 5.3 JSON Schema (`contracts/playbook.schema.json`, draft 2020-12)

The schema lives only in `contracts/playbook.schema.json` (no copy here, to avoid drift). Changes from the first draft (D-071):

| Change | Why |
|---|---|
| `trigger.type` is optional, default `event_delay` | The spec section 7 B2 example has no `type` and must validate unchanged (`contracts/examples/playbooks/spec_section7_B2.json` is a regression test) |
| `trigger.events_any` + `trigger.event_where` | D2 fires on `ride_rated` (rating ≤ 2) **or** `support_ticket_opened` |
| `promo.reuse_code_from` | A3 reminds the rider of A2's code instead of creating a new one |
| `cooldown_hours: null` | "Once per user" (A2, A3, E4) |
| `additionalProperties: false` on `trigger`; required fields for `window_count` and `threshold` | Catch typos and incomplete triggers |
| `message_class: transactional` implies `promo.allowed: false` | Rule previously enforced only in code |
| `templates` keys limited to channel names | Catch typos |

Validation beyond JSON Schema (code, `engage/playbooks/validate.py`): ladder values ≤ `settings.user_promo_caps.max_discount_per_ride_inr` when `type = flat`; `max_discount_inr ≤ max_discount_per_ride_inr`; every channel has templates for every audience language; SMS/WhatsApp templates have DLT/WABA ids; `autonomy ≤ settings.autonomy_max`; `cancel_if` events exist in the contract; transactional playbooks may not have `promo.allowed = true`.

### 5.4 Rules MVP playbook defaults (12 playbooks, D-036)

| Playbook | Class | Trigger | Wait / offsets | cancel_if | Promo | Channels | Cooldown | Window |
|---|---|---|---|---|---|---|---|---|
| `A2_welcome_offer` | marketing | `sign_up` | 0 | — | percent 50, cap ₹100, 7 d, first_ride_only | push, email | once per user | 7 d |
| `A3_no_first_ride_48h` | marketing | `sign_up` | 2880 min | `ride_booked` | reminder of A2 code (no new code) | push, sms | once | 5 d |
| `B1_fare_check_no_booking` | marketing | `fare_check` | 15 min | `booking_started`, `ride_booked` | ladder [0,10,15], cap ₹60, 120 min, only if price sensitivity high | push | 24 h | 24 h |
| `B2_abandoned_booking` | marketing | `booking_abandoned` (step ≠ payment) | 10 min | `ride_booked` | ladder [0,10,15,20], cap ₹75, 30 min | push, sms | 24 h | 24 h |
| `B3_abandoned_payment_step` | service | `booking_abandoned` (step = payment) | 5 min | `ride_booked` | none | push | 24 h | 24 h |
| `B5_no_driver_found` | service | `no_driver_found` | 2 min | `ride_booked` | flat ₹30, 7 d | push | 24 h | 7 d |
| `B8_payment_failed` | transactional | `payment_failed` | 1 min | `ride_completed` (match `ride_id`), interim | none | sms, push | none | 48 h (conversion = payment recovered, OQ-12) |
| `C2_pickup_reminder` | transactional | `ride_scheduled` (relative_time on `scheduled_time`) | −60, −15 min | `scheduled_ride_cancelled` (match `ride_id`) | none | push, sms | none | n/a |
| `D2_bad_experience` | service | `ride_rated` (rating ≤ 2) or `support_ticket_opened` | 15 min | — | flat ₹75 next-ride code (wallet credit later, D-065) | push, email | 7 d | 30 d (retention) |
| `E2_lapsing_7_14d` | marketing | schedule 10:00 IST, segment `lapsing_7_14` | — | — | ladder [0,10], cap ₹50, 7 d | push | 14 d | 7 d |
| `E3_lapsed_30d` | marketing | schedule 10:00 IST, segment `lapsed_30` | — | — | ladder [0,20,25,30], cap ₹100, 7 d | email, sms | 30 d | 7 d |
| `E4_dormant_90d` | marketing | schedule 10:00 IST Mon, segment `dormant_90` | — | — | flat ₹100 credit code, 7 d; then `stop_marketing` flag | email | once | 7 d |

B8 note: `cancel_if` uses a backend event confirming payment recovery; contract v1 uses `ride_completed` with matching `ride_id` until a `payment_succeeded` event exists (OQ-12). All 12 playbook JSON files will live in `playbooks/` and are validated in CI.
