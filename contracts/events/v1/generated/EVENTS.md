# HireMe engagement events: reference

Contract `hireme.engage.event` v1.0 (document version 1.0.0-rc1).
**GENERATED from `contracts/events/v1/catalog.yaml`. Do not edit.**

Machine-readable schema: `generated/envelope.schema.json`. GA4 mapping: `generated/ga4_mapping.json`. Examples: `generated/examples/`. Conventions and context: `docs/DATA_MODEL.md` §1-2.

Every event is sent as an envelope with `contract_version`, `event_uuid` (UUIDv7), `event_name`, `event_ts`, `user_id`, `user_pseudo_id`, `platform`, `app_version`, `city_id`, `origin` and `params`. In GA4, `event_uuid`, `contract_version`, `origin` and `city_id` are also written as event parameters. Every event may carry the optional param `engage_message_id` (deep-link attribution).

Origins: `client` = rider app, `server` = HireMe backend (server-authoritative after handoff), `auto` = Firebase automatic. Delivery after handoff: `ga4` = Firebase Analytics BigQuery export, `webhook` = `POST /engage/v1/events`.

| Event | Group | In spec | Origins | Delivery | GA4 params (incl. common) |
|---|---|---|---|---|---|
| `app_open` | onboarding | yes | client | ga4, webhook | 7 |
| `sign_up_started` | onboarding | yes | client | ga4, webhook | 6 |
| `sign_up` | onboarding | yes | client, server | ga4, webhook | 9 |
| `profile_completed` | onboarding | yes | client | ga4, webhook | 6 |
| `location_permission` | onboarding | yes | client | ga4, webhook | 7 |
| `fare_check` | booking_funnel | yes | client | ga4, webhook | 14 |
| `vehicle_selected` | booking_funnel | yes | client | ga4, webhook | 8 |
| `booking_started` | booking_funnel | yes | client | ga4, webhook | 10 |
| `booking_abandoned` | booking_funnel | yes | client | ga4, webhook | 14 |
| `ride_booked` | booking_funnel | yes | server | webhook | 15 |
| `no_driver_found` | booking_funnel | yes | server | webhook | 9 |
| `payment_failed` | booking_funnel | yes | server | webhook | 9 |
| `ride_scheduled` | scheduled_rides | yes | server | webhook | 11 |
| `scheduled_ride_cancelled` | scheduled_rides | yes | server | webhook | 7 |
| `ride_cancelled` | ride_lifecycle | yes | server | webhook | 9 |
| `ride_started` | ride_lifecycle | yes | server | webhook | 6 |
| `ride_completed` | ride_lifecycle | yes | server | webhook | 16 |
| `ride_rated` | ride_lifecycle | yes | client | ga4, webhook | 8 |
| `promo_viewed` | promo_and_engagement | yes | client | ga4, webhook | 8 |
| `promo_applied` | promo_and_engagement | yes | client | ga4, webhook | 8 |
| `referral_shared` | promo_and_engagement | yes | client | ga4, webhook | 6 |
| `wallet_topup` | promo_and_engagement | yes | server | webhook | 7 |
| `support_ticket_opened` | promo_and_engagement | yes | server | webhook | 7 |
| `notification_opened` | promo_and_engagement | yes | client, server | ga4, webhook | 8 |
| `app_remove` | additions | added | auto | ga4 | 5 |
| `consent_changed` | additions | added | server | webhook | 8 |
| `promo_redeemed` | additions | added | server | webhook | 9 |

## Onboarding

### `app_open` (user_id may be null)

App launched. Logged as a custom event (Firebase automatic events cannot carry custom params). Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `source` | enum | yes | organic / push / deeplink / email / sms / whatsapp | `"push"` | string_value | yes |  |
| `app_version` | string | yes |  | `"5.4.1"` | string_value | yes |  |

### `sign_up_started` (user_id may be null)

Rider entered a phone number (pre-login, user_id is null; D-047). Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `method` | enum | yes | phone / google / apple | `"phone"` | string_value | yes |  |

### `sign_up`

OTP verified, account created. Emitted after setUserId. Server-authored after handoff. Origins: client, server. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `method` | enum | yes | phone / google / apple | `"phone"` | string_value | yes |  |
| `referral_code` | promo_code | no | `^[A-Z0-9][A-Z0-9-]{2,19}$` | `"NEHA50"` | string_value | yes |  |
| `city` | area_name | yes |  | `"Noida"` | string_value | yes |  |
| `device_id_hash` | hash32 | yes | `^[0-9a-f]{32}$` | `"9b1f6c0e2d4a8b7c3e5f1a9d0c2b4e6f"` | string_value | added | SHA-256 of the device id, first 32 hex chars; multi-account fraud check (spec 9). |

### `profile_completed`

Name, email and photo saved. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `has_email` | bool | yes |  | `true` | int_value | yes |  |

### `location_permission`

Location permission granted or denied. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `status` | enum | yes | granted / denied | `"denied"` | string_value | yes |  |
| `precision` | enum | no | precise / approximate | `"approximate"` | string_value | added |  |

## Booking funnel

### `fare_check`

Pickup and drop entered, fare shown. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `pickup_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"NOI-S62"` | string_value | yes |  |
| `drop_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"DEL-CP"` | string_value | yes |  |
| `distance_km` | double | yes | >= 0 | `18.4` | double_value | yes |  |
| `fare_estimate` | inr | yes | >= 0 | `420.0` | double_value | yes | Price of the displayed/default vehicle. |
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"mini"` | string_value | yes |  |
| `surge_multiplier` | double | yes | >= 1 | `1.0` | double_value | yes | 1.0 = no surge. |
| `fare_quote_id` | fare_quote_id | yes | `^fq_[0-9]{1,12}$` | `"fq_7781203"` | string_value | added | Links fare_check -> booking -> ride. |
| `drop_area_name` | area_name | yes |  | `"Connaught Place"` | string_value | added | Fills {drop_area} in templates without a geo lookup. |
| `pickup_area_name` | area_name | no |  | `"Sector 62"` | string_value | added |  |

### `vehicle_selected`

Rider picked a vehicle category. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"sedan"` | string_value | yes |  |
| `fare_estimate` | inr | yes | >= 0 | `512.0` | double_value | yes |  |
| `fare_quote_id` | fare_quote_id | yes | `^fq_[0-9]{1,12}$` | `"fq_7781203"` | string_value | added |  |

### `booking_started`

Rider tapped Book / Confirm. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"mini"` | string_value | yes |  |
| `payment_method` | payment_method | yes | cash / upi / card / wallet | `"upi"` | string_value | yes |  |
| `fare_estimate` | inr | yes | >= 0 | `420.0` | double_value | yes |  |
| `fare_quote_id` | fare_quote_id | yes | `^fq_[0-9]{1,12}$` | `"fq_7781203"` | string_value | added |  |
| `booking_attempt_id` | booking_attempt_id | yes | `^ba_[0-9]{1,12}$` | `"ba_550192"` | string_value | added |  |

### `booking_abandoned`

Rider left the booking screen without confirming. B3 handles step=payment; B2 handles the other steps. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `step` | enum | yes | fare / vehicle / payment / confirm | `"confirm"` | string_value | yes |  |
| `fare_estimate` | inr | yes | >= 0 | `420.0` | double_value | yes |  |
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"mini"` | string_value | added |  |
| `payment_method` | payment_method | no | cash / upi / card / wallet | `"card"` | string_value | added | Needed by B3. |
| `pickup_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"NOI-S62"` | string_value | added |  |
| `drop_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"DEL-CP"` | string_value | added |  |
| `drop_area_name` | area_name | yes |  | `"Connaught Place"` | string_value | added |  |
| `fare_quote_id` | fare_quote_id | yes | `^fq_[0-9]{1,12}$` | `"fq_7781203"` | string_value | added |  |
| `booking_attempt_id` | booking_attempt_id | no | `^ba_[0-9]{1,12}$` | `"ba_550192"` | string_value | added | Absent if abandoned before booking_started. |

### `ride_booked` (server-authoritative)

Booking created on the server. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | yes |  |
| `fare_estimate` | inr | yes | >= 0 | `420.0` | double_value | yes |  |
| `promo_code` | promo_code | no | `^[A-Z0-9][A-Z0-9-]{2,19}$` | `"GO15-7KQ2"` | string_value | yes |  |
| `is_scheduled` | bool | yes |  | `false` | int_value | yes |  |
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"mini"` | string_value | added |  |
| `payment_method` | payment_method | yes | cash / upi / card / wallet | `"upi"` | string_value | added |  |
| `pickup_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"NOI-S62"` | string_value | added |  |
| `drop_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"DEL-CP"` | string_value | added |  |
| `fare_quote_id` | fare_quote_id | no | `^fq_[0-9]{1,12}$` | `"fq_7781203"` | string_value | added |  |
| `booking_attempt_id` | booking_attempt_id | no | `^ba_[0-9]{1,12}$` | `"ba_550192"` | string_value | added |  |

### `no_driver_found`

Driver search timed out. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `pickup_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"NOI-S18"` | string_value | yes |  |
| `wait_seconds` | int | yes | >= 0 | `240` | int_value | yes |  |
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"mini"` | string_value | added |  |
| `booking_attempt_id` | booking_attempt_id | yes | `^ba_[0-9]{1,12}$` | `"ba_550301"` | string_value | added |  |

### `payment_failed` (server-authoritative)

Payment declined. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | yes |  |
| `method` | payment_method | yes | cash / upi / card / wallet | `"card"` | string_value | yes |  |
| `error_code` | string | yes | `^[A-Z0-9_]{2,40}$` | `"CARD_DECLINED"` | string_value | yes |  |
| `amount_inr` | inr | yes | >= 0 | `318.0` | double_value | added | B8 message 'Tap to pay ₹318'. |

## Scheduled rides

### `ride_scheduled`

Scheduled ride added. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_9012"` | string_value | yes |  |
| `scheduled_time` | timestamp | yes | `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z\|[+-][0-9]{2}:[0-9]{2})$` | `"2026-11-03T05:30:00+05:30"` | string_value | yes |  |
| `pickup_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"NOI-S137"` | string_value | yes |  |
| `drop_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"DEL-IGI-T3"` | string_value | yes |  |
| `drop_area_name` | area_name | yes |  | `"IGI Airport T3"` | string_value | added |  |
| `pickup_landmark` | area_name | no |  | `"Gate 2"` | string_value | added | Used in the C2 message. |

### `scheduled_ride_cancelled`

Rider cancelled a scheduled ride. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_9012"` | string_value | yes |  |
| `hours_before` | double | yes | >= 0 | `6.5` | double_value | yes |  |

## Ride lifecycle

### `ride_cancelled`

Rider, driver or system cancelled a ride. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | yes |  |
| `cancelled_by` | enum | yes | rider / driver / system | `"driver"` | string_value | yes |  |
| `reason` | enum | yes | driver_far / changed_plans / wait_too_long / price / other | `"wait_too_long"` | string_value | yes |  |
| `wait_seconds` | int | yes | >= 0 | `540` | int_value | yes |  |

### `ride_started`

Trip began. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | yes |  |

### `ride_completed` (server-authoritative)

Trip ended. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | yes |  |
| `final_fare` | inr | yes | >= 0 | `401.5` | double_value | yes | After discount. |
| `distance_km` | double | yes | >= 0 | `18.9` | double_value | yes |  |
| `payment_method` | payment_method | yes | cash / upi / card / wallet | `"upi"` | string_value | yes |  |
| `promo_used` | bool | yes |  | `true` | int_value | yes |  |
| `promo_code` | promo_code | no | `^[A-Z0-9][A-Z0-9-]{2,19}$` | `"GO15-7KQ2"` | string_value | added |  |
| `discount_inr` | inr | no | >= 0 | `63.0` | double_value | added | Actual discount applied. |
| `gross_fare` | inr | yes | >= 0 | `464.5` | double_value | added | Pre-discount fare; needed for incremental fare value. |
| `vehicle_type` | vehicle_type | yes | mini / sedan / prime / suv | `"mini"` | string_value | added |  |
| `pickup_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"NOI-S62"` | string_value | added |  |
| `drop_zone` | zone_id | yes | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | `"DEL-CP"` | string_value | added |  |

### `ride_rated`

Rating submitted. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | yes |  |
| `rating` | int | yes | >= 1; <= 5 | `2` | int_value | yes |  |
| `has_comment` | bool | yes |  | `true` | int_value | yes |  |

## Promo and engagement

### `promo_viewed`

Promo code seen. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `promo_code` | promo_code | yes | `^[A-Z0-9][A-Z0-9-]{2,19}$` | `"GO15-7KQ2"` | string_value | yes |  |
| `campaign_id` | campaign_id | yes | `^(cmp_[a-z0-9]{1,24}\|pb_[A-H][0-9]_[a-z0-9_]{3,40})$` | `"cmp_1042"` | string_value | yes |  |
| `playbook_id` | playbook_id | no | `^[A-H][0-9]_[a-z0-9_]{3,40}$` | `"B2_abandoned_booking"` | string_value | added |  |

### `promo_applied`

Promo code applied at booking. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `promo_code` | promo_code | yes | `^[A-Z0-9][A-Z0-9-]{2,19}$` | `"GO15-7KQ2"` | string_value | yes |  |
| `campaign_id` | campaign_id | yes | `^(cmp_[a-z0-9]{1,24}\|pb_[A-H][0-9]_[a-z0-9_]{3,40})$` | `"cmp_1042"` | string_value | yes |  |
| `playbook_id` | playbook_id | no | `^[A-H][0-9]_[a-z0-9_]{3,40}$` | `"B2_abandoned_booking"` | string_value | added |  |

### `referral_shared`

Invite link shared. Origins: client. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `channel` | enum | yes | whatsapp / sms / copy_link / other | `"whatsapp"` | string_value | yes |  |

### `wallet_topup`

Wallet recharged. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `amount` | inr | yes | >= 0 | `500.0` | double_value | yes |  |
| `balance_after` | inr | no | >= 0 | `542.0` | double_value | added |  |

### `support_ticket_opened`

Help request raised. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `category` | enum | yes | ride_issue / driver_behaviour / payment / safety / lost_item / other | `"ride_issue"` | string_value | yes |  |
| `ride_id` | ride_id | no | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | added |  |

### `notification_opened`

Push tapped (client), or email/SMS/WhatsApp link opened through the engine redirect (server-emitted by the engine). Origins: client, server. Delivery: ga4, webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `campaign_id` | campaign_id | yes | `^(cmp_[a-z0-9]{1,24}\|pb_[A-H][0-9]_[a-z0-9_]{3,40})$` | `"pb_B2_abandoned_booking"` | string_value | yes |  |
| `message_id` | message_id | yes | `^msg_[0-9a-f]{12,32}_[1-9][0-9]?$` | `"msg_8f3a91c2e0d4b7a65c1e2f90_1"` | string_value | yes |  |
| `channel` | enum | yes | push / sms / email / whatsapp / in_app | `"push"` | string_value | added |  |

## Additions

### `app_remove` (user_id may be null)

Firebase automatic uninstall event (Android only). Arrives via the GA4 export only; the GA4 poller synthesises a deterministic UUIDv5 event_uuid (D-072). E6 uninstall signal. Origins: auto. Delivery: ga4.

No event-specific params.

### `consent_changed`

Marketing consent changed for a channel; lets the engine invalidate its consent cache in real time (spec 9, D-053). Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `channel` | enum | yes | push / email / sms / whatsapp | `"email"` | string_value | added |  |
| `opted_in` | bool | yes |  | `false` | int_value | added |  |
| `change_source` | enum | yes | app_settings / unsubscribe_link / stop_sms / support / engine | `"unsubscribe_link"` | string_value | added |  |

### `promo_redeemed`

Promo code redeemed on a completed ride (from the Promo API redemption hook). Budget ledger "redeemed" leg (D-020). Produced by the mock Promo API in the current phase. Origins: server. Delivery: webhook.

| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |
|---|---|---|---|---|---|---|---|
| `promo_id` | int | yes | >= 1 | `55120` | int_value | added |  |
| `promo_code` | promo_code | yes | `^[A-Z0-9][A-Z0-9-]{2,19}$` | `"GO15-7KQ2"` | string_value | added |  |
| `ride_id` | ride_id | yes | `^r_[0-9]{1,12}$` | `"r_4821"` | string_value | added |  |
| `discount_inr` | inr | yes | >= 0 | `63.0` | double_value | added |  |

## User properties

All values are strings.

| Property | Allowed values | Owner | Example | Now / later |
|---|---|---|---|---|
| `city` | `^[A-Za-z ]{2,36}$` | app | `Noida` | NOW -> GA4 |
| `signup_date` | `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` | backend | `2026-06-14` | NOW -> GA4 |
| `total_rides` | `^[0-9]{1,6}$` | backend | `37` | NOW -> GA4 |
| `last_ride_date` | `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` | backend | `2026-10-19` | NOW -> GA4 |
| `preferred_vehicle` | mini / sedan / prime / suv | engine | `mini` | ENGINE |
| `preferred_payment` | cash / upi / card / wallet | engine | `upi` | ENGINE |
| `price_sensitivity` | low / medium / high | engine | `high` | ENGINE (app must not set, D-062) |
| `home_zone` | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | engine | `NOI-S62` | ENGINE |
| `work_zone` | `^[A-Z]{3}-[A-Z0-9]{1,8}(-[A-Z0-9]{1,8})?$` | engine | `DEL-CP` | ENGINE |
| `lifetime_value_band` | low / mid / high / top | engine | `mid` | ENGINE |
| `marketing_opt_in_push` | 0 / 1 | backend | `1` | NOW -> GA4 (segmentation only; consent truth is the Rider API, D-053) |
| `marketing_opt_in_email` | 0 / 1 | backend | `0` | NOW -> GA4 (segmentation only) |
| `marketing_opt_in_sms` | 0 / 1 | backend | `1` | NOW -> GA4 (segmentation only) |
| `marketing_opt_in_wa` | 0 / 1 | backend | `0` | NOW -> GA4 (segmentation only). Short name: GA4 user property names are max 24 chars |
| `language` | `^[a-z]{2}$` | app | `en` | NOW -> GA4 |
| `is_synthetic` | 0 / 1 | generator | `1` | Dev project only (D-012) |
