# Client demo (Phase 0)

What can be shown today, and how. The engine itself is built in Phase 1; this demo shows the foundations and the B2 story running against the live mock services (D-093).

## Before the meeting

- The `demo` data in BigQuery starts to expire around 2026-11-23 (sandbox, D-089). Reload with [LOAD_RUNBOOK.md](LOAD_RUNBOOK.md) if the meeting is later.
- Be logged in with `gcloud auth application-default login` so the data page can read the dev project (otherwise it falls back to the local files and says so).
- Start the mock services. They read the dev project once at startup (about 20 s); wait for the log line `data page ready: source cloud`. The story page works offline:

```bash
.venv/bin/python -m mocks --riders data/gen/demo_s42/firestore/hireme_riders.ndjson --sink
# then open http://127.0.0.1:8090/demo/data and http://127.0.0.1:8090/demo   (API docs: /docs)
```

## Agenda (about 25 minutes)

1. **Data contract (3 min).** `.venv/bin/python -m engage.tools.validate_contract --all` (12/12). Show `contracts/events/v1/generated/EVENTS.md`. The HireMe team can self-check payloads with `--events FILE`.
2. **Synthetic data in their project (7 min).** Open `/demo/data`: riders in Firestore by city and consent (click a sample document), events per day and by type in BigQuery, the B2 funnel with one raw `booking_abandoned` event, rides and promo codes, personas, every table with its row count. The badge says "Live from hireme-engage-dev". Its **Riya's story →** button leads into point 3. Optional deeper look: BigQuery console, project `hireme-engage-dev`: 45 daily GA4-shaped shards, 3,000 synthetic riders; Firestore console: `hireme_riders`. Run `.venv/bin/python -m sim.validate.bq --project hireme-engage-dev` (12 passed). All data is synthetic.
3. **Riya's story at `/demo` (10 min).** Left: Riya's phone; right: the engine's steps; top: every API call between the services.
   - Tap **Not now** → the engine runs B2 (10-minute timer fast-forwarded), creates a code on the Promo API, sends the push. *Live API* steps are real calls; *scripted* steps show the Phase 1 engine logic with the design's numbers (ARCHITECTURE §4.1).
   - Tap the notification → the code is pre-filled → **Apply** (₹420 → −₹63 → ₹357) → **Book** → **Complete ride** → redemption webhook → ledger: ₹75 reserved, ₹63 redeemed, ₹12 released.
   - Variations: type a wrong code to see the rejection; **Restart story** with **Promo API outage** on to see retries with the same Idempotency-Key; tap **Confirm** instead of Not now to show the engine stays quiet when Riya books.
4. **Status and asks (5 min).** M0.1-M0.4 done (M0.2 without CI); next M0.5, gate G0 on 27 Nov. Needed from HireMe: OQ-41 (`app_instance_id`), OQ-08 (real Promo API), OQ-09 (Grepix gateway API; our proposal is `channels.v1.yaml`), review of D-091 to D-093, contract sign-off.

Do not show `docs/reference/`, `docs/client/` or any `.env` files.
