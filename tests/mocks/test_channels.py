"""Mock channel providers: provider-side rules, deliveries, signed receipts (M0.4, D-091)."""
from datetime import datetime

import pytest

from engage.contract import openapi
from mocks.clock import IST

from .conftest import AUTH, Env

SPEC = "channels.v1.yaml"
FCM = "/mock/fcm/v1/projects/hireme-engage-dev/messages:send"
B2_SMS = "HireMe: Complete your ride in the next 30 min and save 15% with code GO15-7KQ2. T&C apply."


def push(token="fcm_tok_synthetic_10042", mid="msg_8f3a91c2e0d4_1", **extra):
    return {"message": {"token": token, "notification": {"title": "Still heading?", "body": "15% off"},
                        "data": {"message_id": mid, "campaign_id": "pb_B2_abandoned_booking"}, **extra}}


def sms(to="+919990010042", body=B2_SMS, ref="msg_8f3a91c2e0d4_2", template="PENDING_DLT_B2_EN"):
    return {"to": to, "sender_id": "HIREME", "body": body, "client_ref": ref,
            "dlt": {"pe_id": "PENDING_PE_ID", "template_id": template, "category": "promotional"},
            "template_vars": {"validity_minutes": "30", "discount_label": "15%", "promo_code": "GO15-7KQ2"}}


def email(to="rider.10043@example.test", ref="msg_1c77e0a9b3f2_1", unsubscribe=True):
    e = {"to": to, "from": {"email": "offers@mail.hireme.app"}, "subject": "25% off", "text": "hi",
         "client_ref": ref, "category": "marketing"}
    if unsubscribe:
        e["headers"] = {"List-Unsubscribe": "<https://x.test/u/t>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    return e


def test_push_delivered_with_signed_receipt(env):
    r = env.c.post(FCM, json=push(), headers=AUTH)
    assert r.status_code == 200 and openapi.errors(SPEC, "FcmSendResponse", r.json()) == []
    [d] = env.c.get("/mock/deliveries", params={"user_id": "u_10042"}).json()["deliveries"]
    assert d["status"] == "accepted" and d["content"]["data"]["message_id"] == "msg_8f3a91c2e0d4_1"
    assert env.drain() == 1
    [got] = env.received("delivery")
    assert got["provider"] == "fcm" and got["body"]["status"] == "delivered"
    assert got["body"]["provider_message_id"] == r.json()["name"]
    [d] = env.c.get("/mock/deliveries", params={"user_id": "u_10042"}).json()["deliveries"]
    assert [h["status"] for h in d["history"]] == ["accepted", "delivered"]


@pytest.mark.parametrize("token", ["fcm_tok_synthetic_10044", "fcm_tok_never_issued"])
def test_push_unregistered(env, token):
    r = env.c.post(FCM, json=push(token=token), headers=AUTH)
    assert r.status_code == 404 and openapi.errors(SPEC, "FcmError", r.json()) == []
    assert r.json()["error"]["details"][0]["errorCode"] == "UNREGISTERED"
    assert env.c.get("/mock/deliveries").json()["deliveries"] == []


def test_push_invalid_and_validate_only(env):
    bad = push()
    del bad["message"]["data"]["message_id"]
    assert env.c.post(FCM, json=bad, headers=AUTH).json()["error"]["status"] == "INVALID_ARGUMENT"
    assert env.c.post(FCM, json=push(), headers={}).status_code == 401
    assert env.c.post(FCM, json={**push(), "validate_only": True}, headers=AUTH).status_code == 200
    assert env.c.get("/mock/deliveries").json()["deliveries"] == []


def test_sms_dlt_dnd_and_window(env):
    ok = env.c.post("/mock/sms/v1/sms", json=sms(), headers=AUTH)
    assert ok.status_code == 202 and openapi.errors(SPEC, "GatewayAccepted", ok.json()) == []
    dnd = env.c.post("/mock/sms/v1/sms", json=sms(to="+919990010043", ref="msg_8f3a91c2e0d4_3"), headers=AUTH)
    assert dnd.status_code == 202                       # gateways accept, then report DND
    env.drain()
    statuses = {r["body"]["message_id"]: r["body"]["status"] for r in env.received("delivery")}
    assert statuses == {"msg_8f3a91c2e0d4_2": "delivered", "msg_8f3a91c2e0d4_3": "dnd_blocked"}
    costs = {d["message_id"]: d["cost_inr"] for d in env.c.get("/mock/deliveries").json()["deliveries"]}
    assert costs["msg_8f3a91c2e0d4_2"] == 0.20

    edited = env.c.post("/mock/sms/v1/sms", json=sms(body=B2_SMS.replace("T&C apply.", "Hurry!")), headers=AUTH)
    assert edited.status_code == 400 and edited.json()["code"] == "DLT_TEMPLATE_MISMATCH"
    wrong_var = sms()
    wrong_var["template_vars"]["promo_code"] = "OTHER-CODE"
    assert env.c.post("/mock/sms/v1/sms", json=wrong_var, headers=AUTH).json()["code"] == "DLT_TEMPLATE_MISMATCH"
    assert env.c.post("/mock/sms/v1/sms", json=sms(template="UNREGISTERED"), headers=AUTH).status_code == 400

    env.clock.set(datetime(2026, 11, 10, 21, 30, tzinfo=IST))
    late = env.c.post("/mock/sms/v1/sms", json=sms(ref="msg_8f3a91c2e0d4_4"), headers=AUTH)
    assert late.json()["code"] == "OUTSIDE_PROMOTIONAL_WINDOW"
    env.c.post("/mock/admin/dlt", json={"template_id": "TXN_1", "body": "HireMe: your ride {ride_ref} is confirmed.",
                                        "sender_id": "HIREME", "category": "transactional"})
    txn = sms(body="HireMe: your ride R-4821 is confirmed.", template="TXN_1", ref="msg_8f3a91c2e0d4_5")
    txn["dlt"]["category"], txn["template_vars"] = "transactional", {}
    assert env.c.post("/mock/sms/v1/sms", json=txn, headers=AUTH).status_code == 202


def test_email_rules(env):
    assert env.c.post("/mock/email/v1/email", json=email(unsubscribe=False), headers=AUTH).status_code == 400
    for to, ref in [("rider.10043@example.test", "msg_1c77e0a9b3f2_1"), ("rider.10045@example.test", "msg_1c77e0a9b3f2_2"),
                    ("nobody@example.test", "msg_1c77e0a9b3f2_3")]:
        assert env.c.post("/mock/email/v1/email", json=email(to, ref), headers=AUTH).status_code == 202
    env.drain()
    statuses = {r["body"]["message_id"]: r["body"]["status"] for r in env.received("delivery")}
    assert statuses == {"msg_1c77e0a9b3f2_1": "delivered", "msg_1c77e0a9b3f2_2": "bounced",
                        "msg_1c77e0a9b3f2_3": "bounced"}


def test_whatsapp_consent_and_read(env):
    wa = lambda to, ref: {"to": to, "template": {"name": "hm_winback_25", "language": "en"}, "client_ref": ref}
    no = env.c.post("/mock/whatsapp/v1/whatsapp", json=wa("+919990010046", "msg_1c77e0a9b3f2_4"), headers=AUTH)
    assert no.json()["code"] == "NO_WHATSAPP_CONSENT"
    assert env.c.post("/mock/whatsapp/v1/whatsapp", json=wa("+919990010043", "msg_1c77e0a9b3f2_5"),
                      headers=AUTH).status_code == 202
    env.drain()
    assert [r["body"]["status"] for r in env.received("delivery")] == ["delivered", "read"]


def test_default_profile_rates_are_deterministic():
    """Baseline 1 % SMS failure: same seed, same messages -> same outcome per message; rate is roughly right."""
    def run():
        e = Env(profile="default", engine_url=None)
        e.ctx.faults.apply({"mode": "reset"})          # isolate delivery outcomes from request faults
        for i in range(400):
            e.c.post("/mock/sms/v1/sms", json=sms(ref=f"msg_{i:012x}_1"), headers=AUTH)
        e.drain()
        return {d["message_id"]: d["status"] for d in e.c.get("/mock/deliveries", params={"limit": 1000}).json()["deliveries"]}
    a, b = run(), run()
    assert len(a) == 400 and a == b and 0 < list(a.values()).count("failed") < 15
