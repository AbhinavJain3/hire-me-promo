# Firestore collections (contract summary)

Field-level definitions: `docs/DATA_MODEL.md` §4. Indexes and TTL policies: `firestore.indexes.json`
(`expire_at` is the TTL field on every collection that has one). Security rules: `firestore.rules` (deny all clients).

Document shapes that are part of a cross-team contract have machine-readable schemas:

| Collection | Schema |
|---|---|
| `engage_events_live/{event_uuid}` (Event Inbox) | `contracts/events/v1/generated/envelope.schema.json` plus engine fields `processed`, `sim_run_id`, `expire_at` (DATA_MODEL §4.3) |
| `hireme_riders/{user_id}` (Rider DB stand-in) | `RiderProfile` in `contracts/openapi/rider-api.v1.yaml` (D-013, D-074) |
| `engage_playbooks/{playbook_id}` | `contracts/playbook.schema.json` plus engine fields `status`, `approved_version`, `stats_cache`, `auto_paused` |
| `engage_templates/{template_id}` | `contracts/template.schema.json` |
| `mock_promo_codes/{promo_id}` | `PromoCreate` in `contracts/openapi/promo-api.v1.yaml` plus mock state |

Engine-internal collections (`engage_settings`, `engage_timers`, `engage_user_state`, `engage_decisions`,
`engage_messages`, `engage_promos`, `engage_budget_ledger`, ...) are defined in DATA_MODEL §4 and get Pydantic
models in `engage/core/models.py` in Phase 0 (M0.5); they are not part of the backend contract.
