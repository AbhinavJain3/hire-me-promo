---
name: ga4-sql
description: Reference idioms for querying GA4-export-shaped BigQuery tables (analytics_* events_YYYYMMDD and events_intraday_YYYYMMDD) in the HireMe project. Load before writing any SQL against raw events.
---
# GA4 SQL idioms

- **Parameter access:** `(SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'step')`. Integers are in `int_value` (booleans are 0/1), decimals in `double_value`.
- **User properties:** same pattern with `UNNEST(user_properties)`.
- **Prune shards:** `WHERE _TABLE_SUFFIX BETWEEN '20261001' AND '20261031'`. Intraday tables have the suffix `intraday_YYYYMMDD`.
- **Daily + intraday union with dedupe:** query `events_*` and add
  `QUALIFY ROW_NUMBER() OVER (PARTITION BY event_key ORDER BY table_suffix) = 1` on `engage_features.v_events_flat`
  (`event_key` = the `event_uuid` param, or a hash for Firebase automatic events such as `app_remove` that have none).
- **Time:** `TIMESTAMP_MICROS(event_timestamp)`. The IST day is `event_date` (property time zone Asia/Kolkata) or `DATE(TIMESTAMP_MICROS(event_timestamp), 'Asia/Kolkata')`.
- **Prefer the flattened view** `engage_features.v_events_flat` for downstream work instead of unnesting repeatedly.
- **Cost:** always dry-run; never `SELECT *` on raw shards.
- **Privacy:** never return rider-level rows in answers for humans; aggregate with k >= 20.
