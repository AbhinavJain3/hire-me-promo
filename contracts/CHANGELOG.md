# Contract changelog

## 1.0.0-rc1 (2026-11-04)

First machine-readable release candidate (milestone M0.1), built from docs/DATA_MODEL.md and docs/API.md.

Changes from the planning drafts in those documents:

- Event catalogue `events/v1/catalog.yaml` as the single source; schemas, examples, GA4 mapping and EVENTS.md are generated (D-067, D-068).
- `user_pseudo_id` is optional for `origin: server` events, and `platform` is `SERVER` exactly when the origin is server (D-069).
- User properties are all strings; `marketing_opt_in_whatsapp` is renamed **`marketing_opt_in_wa`** (the 24-character GA4 limit) (D-070).
- Playbook schema: `trigger.type` defaults to `event_delay`, so the spec section 7 example validates unchanged; added `events_any`/`event_where`, `promo.reuse_code_from`, and `cooldown_hours: null` (D-071).
- Firebase automatic events (`app_remove`) get an engine-synthesised UUIDv5 `event_uuid`; the BigQuery view exposes `event_key` (D-072).
- OpenAPI files for ingest, Rider API and Promo API; the admin API spec will be generated from code (D-073).
- The `hireme_riders` stub uses the `RiderProfile` shape (`contact.*`, `referral.*`, `status`) (D-074).
- BigQuery tables partition by UTC date; the draft's time-zone partition expressions were invalid (D-075).
- `message_id` format is `msg_<hex>_<ordinal>`; doc examples `msg_dec_8f3a…_1` corrected.
