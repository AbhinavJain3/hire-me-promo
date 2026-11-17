"""/demo/data and /mock/admin/data from a tiny local generation (no cloud access in tests)."""
import gzip
import json

from fastapi.testclient import TestClient

from mocks.app import create_app
from mocks.dataview import DataView, mask_email, mask_phone

from .conftest import rider


def _write(path, rows, gz=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r) + "\n" for r in rows)
    if gz:
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        path.write_text(text)


def make_generation(d):
    riders = [rider(10042), rider(10043, dnd=True, wa=False)]
    _write(d / "firestore/hireme_riders.ndjson", riders)
    _write(d / "bigquery/hireme_ref/cities.ndjson", [{"city_id": 3, "city_name": "Noida", "is_pilot": True}])
    _write(d / "bigquery/hireme_backend_stub/rides.ndjson", [
        {"status": "completed", "gross_fare_inr": 400.0, "promo_code": "SAVE20"},
        {"status": "completed", "gross_fare_inr": 200.0, "promo_code": None},
        {"status": "cancelled", "gross_fare_inr": None, "promo_code": None}])
    _write(d / "bigquery/hireme_backend_stub/promo_redemptions.ndjson", [{"code": "SAVE20", "discount_inr": 80.0}])
    _write(d / "bigquery/engage_sim/personas.ndjson", [{"user_id": "u_10042", "persona_id": "P01"}])
    ev = {"event_name": "booking_abandoned", "event_timestamp": "1762614000000000", "event_date": "20261108",
          "user_id": "u_10042", "user_pseudo_id": "abc", "platform": "ANDROID",
          "event_params": [{"key": "fare_estimate", "value": {"int_value": 420}},
                           {"key": "city_id", "value": {"int_value": 3}}]}
    _write(d / "bigquery/analytics_999999999/events_20261108.ndjson.gz", [ev], gz=True)
    (d / "manifest.json").write_text(json.dumps({
        "generation_id": "gen-test", "scale": "tiny", "seed": 1, "riders": 2, "contract_document_version": "1.0.0-rc1",
        "window": {"start_ist": "2026-11-08", "end_ist": "2026-11-08", "days": 1},
        "counts": {"events_total": 1, "events_by_name": {"booking_abandoned": 1},
                   "riders_by_persona": {"P01_price_sensitive_explorer": 1}},
        "files": [{"path": "bigquery/analytics_999999999/events_20261108.ndjson.gz", "rows": 1}]}))


def test_masking():
    assert mask_phone("+919990012345") == "+9199••••••45"
    assert mask_email("riya.10042@example.test") == "ri•••@example.test"


def test_data_page_and_local_summary(tmp_path):
    make_generation(tmp_path)
    c = TestClient(create_app(dataview=DataView(None, tmp_path), autostart=False))
    assert c.get("/demo/data").status_code == 200
    d = c.get("/mock/admin/data").json()
    assert d["source"] == "local" and d["error"] is None and d["generation"]["id"] == "gen-test"
    fs, bq = d["firestore"], d["bigquery"]
    assert fs["riders_total"] == 2 and fs["by_city"] == [{"city": "Noida", "pilot": True, "n": 2}]
    assert fs["reach"] == {"push_opt_in": 2, "whatsapp_opt_in": 1, "email_opt_in": 2, "phone_dnd": 1}
    sample = fs["sample"][0]
    assert sample["contact"]["phone_e164"] == "+9199••••••42" and "@" in sample["contact"]["email"]
    assert "10042@" not in json.dumps(d) and "fcm_tok_synthetic" not in json.dumps(d)    # contact never leaves unmasked
    assert bq["rides"][0] == {"status": "completed", "n": 2, "avg_fare": 300, "with_promo": 1}
    assert bq["promos"] == [{"code": "SAVE20", "n": 1, "discount": 80.0}]
    assert bq["personas"] == [{"id": "P01", "n": 1, "label": "price sensitive explorer"}]
    assert bq["sample_event"]["event_params"] == [{"key": "city_id", "value": "3"}, {"key": "fare_estimate", "value": "420"}]
    assert bq["daily"] == [{"d": "2026-11-08", "n": 1}]
    assert c.get("/mock/admin/data").json()["cached"] is True


def test_cloud_failure_falls_back_to_local(tmp_path, monkeypatch):
    make_generation(tmp_path)
    dv = DataView("hireme-engage-dev", tmp_path)
    monkeypatch.setattr(dv, "_cloud", lambda: (_ for _ in ()).throw(RuntimeError("no credentials")))
    d = dv.summary()
    assert d["source"] == "local" and "no credentials" in d["error"]


def test_no_data_view(tmp_path):
    c = TestClient(create_app(autostart=False))
    assert c.get("/mock/admin/data").status_code == 404
