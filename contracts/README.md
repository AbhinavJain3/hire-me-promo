# HireMe Engagement Engine: data contract

**Version 1.0.0-rc1** (event `contract_version` `"1.0"`), 2026-11-04. Status: release candidate for HireMe review (milestone M0.1).
It freezes as 1.0.0 at gate G0, when HireMe signs it off.

This folder is what the HireMe app and backend teams implement against (backend handoff, IMPLEMENTATION_PLAN §5),
and what the engine, simulator and loaders are built on. The background and reasoning are in
`docs/DATA_MODEL.md` and `docs/API.md`. **If those documents and this folder disagree, this folder wins.**

## What is here

| Path | What | Who implements it |
|---|---|---|
| `events/v1/catalog.yaml` | **Single source** for all 27 events, their params, types, examples, origins and delivery, plus the 16 user properties (D-067) | Edited by us; read by everyone |
| `events/v1/generated/EVENTS.md` | Readable event reference (generated) | App + backend teams |
| `events/v1/generated/envelope.schema.json` | Self-contained JSON Schema for one event envelope (generated, D-068) | App + backend (validate before sending); engine ingest |
| `events/v1/generated/examples/*.json` | One valid envelope per event (generated) | Test fixtures |
| `events/v1/generated/ga4_mapping.json` | Envelope ↔ GA4 BigQuery export mapping (generated) | Engine, simulator, GA4 poller |
| `openapi/engage-ingest.v1.yaml` | `POST /engage/v1/events` (future webhook), promo-redeemed and delivery webhooks, tracked links, unsubscribe | Backend calls it; engine serves it |
| `openapi/rider-api.v1.yaml` | Rider Profile API + consent write-back; also the shape of the `hireme_riders` stub (D-074) | **Backend provides it** |
| `openapi/promo-api.v1.yaml` | Promo API create/usage/deactivate + redemption webhook (to be matched to the real API, OQ-08) | **Backend provides it**; mock now |
| `playbook.schema.json` | Playbook configuration (D-071) | Engine, console, playbook-author agent |
| `template.schema.json` | Message template | Engine, console |
| `bigquery/ga4_events_schema.json` | GA4 export table schema, core columns (D-077) | Loaders (synthetic shards) |
| `bigquery/ddl/*.sql` | All other BigQuery datasets and tables, `${PROJECT}` / `${GA4_DATASET}` placeholders | Loaders (M0.2) |
| `firestore/firestore.indexes.json` | Composite indexes and TTL policies (`expire_at`) | `firebase deploy` (M0.2) |
| `firestore/firestore.rules` | Deny all client access | `firebase deploy` |
| `firestore/collections.md` | Which Firestore documents have a schema here | — |
| `examples/` | Hand-written examples: the B2 playbook, the spec section 7 sample (regression test), B2 templates | Tests |

## Commands

```bash
# after editing catalog.yaml: regenerate, then validate everything
.venv/bin/python -m engage.tools.gen_contract
.venv/bin/python -m engage.tools.validate_contract --all
.venv/bin/python -m pytest tests/contract

# conformance check for payloads (backend/app teams, D-076): one envelope, an array,
# a webhook body {"events": [...]}, or NDJSON
.venv/bin/python -m engage.tools.validate_contract --events my_events.ndjson
```

`--all` checks Firebase naming and size limits (names ≤ 40 chars, ≤ 25 params per event, user property names ≤ 24 chars),
that generated files are current, that schemas compile, that the doc examples in DATA_MODEL.md and API.md validate,
that the GA4 round trip is lossless, the OpenAPI files and every example in them, playbooks (schema plus cross-checks
against the event catalogue), templates (placeholders declared, no literal prices), Firestore indexes and rules, and the DDL.

## Rules for senders (summary)

1. Every event carries `contract_version` ("1.0") and a **UUIDv7** `event_uuid` generated once at the source. Send the same id to Firebase Analytics and to the webhook; the engine deduplicates on it.
2. `origin: client` events need `user_pseudo_id` (Firebase app instance id), `app_version`, and `platform` ANDROID or IOS. `origin: server` events use `platform: SERVER` (D-069).
3. `user_id` (`u_<digits>`, set with `setUserId` after login) is required except for `sign_up_started` and pre-login `app_open`.
4. Timestamps are ISO-8601 with an offset. Money is INR in decimal rupees. Booleans are JSON booleans in the envelope and 0/1 integers in GA4.
5. Server-authoritative events (`ride_booked`, `ride_completed`, `payment_failed`, and the other `origin: server` events) come from the backend, not the app.
6. Unknown params are rejected by the schema (catch typos before sending). The engine itself drops unknown params and logs them rather than failing.

## Versioning (D-005)

New optional param or new event → minor (1.0 → 1.1). New required param, rename, removal, type change, or removed enum value → major (2.0); the engine supports N and N-1 majors for 90 days. Every change gets a `CHANGELOG.md` entry and a `decision.md` entry.

## Known gaps (to close at M0.2 / handoff)

- `bigquery/ga4_events_schema.json` holds the core columns only; diff it against a real export (D-077, OQ-03).
- MCP tool names and the actual Promo API (OQ-08) and Grepix channel APIs (OQ-09) are not verified yet.
- The admin API OpenAPI is generated from code in M1.5 (D-073).
