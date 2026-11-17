"""Fault injection, webhook retries and signing, and contract examples against the mocks (M0.4, D-091)."""
import json
from datetime import datetime, timedelta

import pytest
import yaml

from engage.contract import openapi
from engage.contract.openapi import OPENAPI_DIR
from engage.core.signing import SignatureError, sign_headers, verify
from mocks.clock import IST

from .conftest import AUTH, START, Env
from .test_channels import FCM, push

SPEC = "channels.v1.yaml"


def test_outage_and_reset(env):
    env.c.post("/mock/admin/faults", json={"target": "fcm", "mode": "outage", "error": "UNAVAILABLE"})
    r = env.c.post(FCM, json=push(), headers=AUTH)
    assert r.status_code == 503 and openapi.errors(SPEC, "FcmError", r.json()) == []
    promo = env.c.post("/mock/admin/faults", json={"target": "promo", "mode": "outage", "error": "RATE_LIMITED"})
    assert set(promo.json()["faults"]) == {"fcm", "promo"}
    assert env.c.get("/api/admin/promocodes/1/usage", headers=AUTH).status_code == 429
    env.c.post("/mock/admin/faults", json={"mode": "reset"})
    assert env.c.post(FCM, json=push(), headers=AUTH).status_code == 200
    stats = env.c.get("/mock/admin/stats").json()["targets"]["fcm"]
    assert stats["requests"] == 2 and stats["errors"] == {"UNAVAILABLE": 1}


def test_error_rate_and_expiry(env):
    until = (START + timedelta(minutes=5)).isoformat()
    env.c.post("/mock/admin/faults", json={"target": "fcm", "mode": "error_rate", "rate": 0.3,
                                           "error": "QUOTA_EXCEEDED", "until": until})
    codes = [env.c.post(FCM, json=push(mid=f"msg_{i:012x}_1"), headers=AUTH).status_code for i in range(300)]
    assert set(codes) == {200, 429} and 60 < codes.count(429) < 120
    env.clock.advance(600)
    assert env.c.get("/mock/admin/faults").json()["faults"] == {}
    assert all(env.c.post(FCM, json=push(mid=f"msg_{i:012x}_2"), headers=AUTH).status_code == 200 for i in range(50))


def test_latency_injection():
    slept = []
    e = Env(sleep=slept.append)
    e.c.post("/mock/admin/faults", json={"target": "promo", "mode": "latency", "p50_ms": 120, "p99_ms": 360})
    for _ in range(200):
        e.c.get("/api/admin/promocodes/1/usage", headers=AUTH)
    slept.sort()
    assert 0.09 < slept[100] < 0.15 and slept[-1] < 0.6


@pytest.mark.parametrize("spec", [{"target": "fax", "mode": "outage"}, {"target": "fcm", "mode": "explode"},
                                  {"target": "fcm", "mode": "error_rate", "rate": 2},
                                  {"target": "sms", "mode": "outage", "error": "QUOTA_EXCEEDED"}])
def test_invalid_fault_specs(env, spec):
    assert env.c.post("/mock/admin/faults", json=spec).status_code == 422


def test_default_profile_matches_api_md():
    e = Env(profile="default")
    f = e.c.get("/mock/admin/faults").json()["faults"]
    assert f["promo"]["error"]["rate"] == 0.005 and f["promo"]["latency"]["p50_ms"] == 120
    assert f["fcm"]["error"]["error"] == "UNAVAILABLE"


def test_webhook_retries_then_succeeds(env):
    env.status_override[:] = [503, 503]
    env.c.post(FCM, json=push(), headers=AUTH)
    env.drain()
    [rec] = env.ctx.webhooks.sent
    assert rec["attempts"] == 3 and rec["status"] == 200
    assert [code for _, code in env.posts] == [503, 503, 200]


def test_no_engine_url_still_updates_state():
    e = Env(engine_url=None)
    e.c.post(FCM, json=push(), headers=AUTH)
    e.drain()
    assert e.ctx.webhooks.sent[0]["status"] == "not_sent"
    assert e.c.get("/mock/deliveries").json()["deliveries"][0]["status"] == "delivered"


def test_signing():
    body = b'{"a":1}'
    h = sign_headers(body, "s3cret", "k1")
    assert verify(body, h, {"k1": "s3cret"}) == "k1"
    for bad_body, secrets, now, code in [(b'{"a":2}', {"k1": "s3cret"}, None, "BAD_SIGNATURE"),
                                         (body, {"k2": "s3cret"}, None, "UNKNOWN_KEY"),
                                         (body, {"k1": "s3cret"}, 10 ** 10, "STALE_TIMESTAMP")]:
        with pytest.raises(SignatureError) as exc:
            verify(bad_body, h, secrets, now=now)
        assert exc.value.code == code


def test_sink_rejects_unsigned_and_invalid(env):
    assert env.sink.post("/engage/v1/webhooks/delivery/fcm", json={}).status_code == 401
    body = json.dumps({"message_id": "nope"}).encode()
    r = env.sink.post("/engage/v1/webhooks/delivery/fcm", content=body, headers=sign_headers(body, "test-secret", "dev-1"))
    assert r.status_code == 422


def _examples(path_key: str):
    spec = yaml.safe_load((OPENAPI_DIR / SPEC).read_text())
    media = spec["paths"][path_key]["post"]["requestBody"]["content"]["application/json"]
    return [ex["value"] for ex in media["examples"].values()]


@pytest.mark.parametrize("path_key,url,ok", [
    ("/v1/projects/{project_id}/messages:send", FCM, 200),
    ("/v1/sms", "/mock/sms/v1/sms", 202),
    ("/v1/email", "/mock/email/v1/email", 202),
    ("/v1/whatsapp", "/mock/whatsapp/v1/whatsapp", 202),
])
def test_contract_examples_accepted(env, path_key, url, ok):
    """Every request example in channels.v1.yaml is accepted by the mock, and receipts match the ingest contract."""
    env.c.post("/mock/admin/dlt", json={
        "template_id": "1207166000000000001", "sender_id": "HIREME", "category": "promotional",
        "body": "HireMe: Complete your ride in the next {validity_minutes} min and save {discount_label} with code {promo_code}. T&C apply."})
    for ex in _examples(path_key):
        r = env.c.post(url, json=ex, headers=AUTH)
        assert r.status_code == ok, r.text
        schema = "FcmSendResponse" if ok == 200 else "GatewayAccepted"
        assert openapi.errors(SPEC, schema, r.json()) == []
    env.drain()
    got = env.received("delivery")
    assert got and all(openapi.errors("engage-ingest.v1.yaml", "DeliveryStatusWebhook", g["body"]) == [] for g in got)


def test_promo_contract_examples_accepted(env):
    spec = yaml.safe_load((OPENAPI_DIR / "promo-api.v1.yaml").read_text())
    exs = spec["paths"]["/api/admin/promocodes"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    for ex in exs.values():
        r = env.c.post("/api/admin/promocodes", json=ex["value"], headers=AUTH)
        assert r.status_code == 201, r.text
        assert openapi.errors("promo-api.v1.yaml", "PromoCreated", r.json()) == []


def test_clock_admin(env):
    r = env.c.post("/mock/admin/clock", json={"now": "2026-11-11T09:00:00+05:30", "scale": 60})
    assert r.json()["scale"] == 60 and r.json()["now_ist"].startswith("2026-11-11T09:00")
    assert env.c.post("/mock/admin/clock", json={"scale": 0}).status_code == 422
    assert datetime.fromisoformat(env.c.get("/mock/admin/clock").json()["now"]).astimezone(IST).day == 11


def test_demo_page_and_activity_feed(env):
    page = env.c.get("/demo")
    assert page.status_code == 200 and "Riya" in page.text
    env.c.post(FCM, json=push(), headers=AUTH)
    env.c.get("/mock/deliveries")                                  # polling is not shown
    env.c.post("/mock/promocodes/NOPE/apply", json={"user_id": "u_1", "fare_inr": 1, "vehicle_type": "mini", "city_id": 3})
    feed = env.c.get("/mock/admin/activity").json()["activity"]
    assert [(a["caller"], a["service"], a["status"]) for a in feed] == [("Engine", "FCM", 200), ("HireMe app", "Promo API", 404)]
    assert env.c.get("/mock/admin/activity", params={"after": feed[0]["seq"]}).json()["activity"] == feed[1:]
