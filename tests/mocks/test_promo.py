"""Mock Promo API: contract shapes, idempotency, promo rules, redemption webhook (M0.4, D-091)."""
from engage.contract import openapi
from mocks.promo import Rejected, evaluate

from .conftest import AUTH, START

SPEC = "promo-api.v1.yaml"


def body(**kw):
    b = {"code": "GO15-7KQ2", "type": "percent", "value": 15, "max_discount": 75, "min_fare": 100,
         "user_id": "u_10042", "usage_limit": 1, "city_ids": [3], "vehicle_types": ["mini", "sedan"],
         "valid_from": "2026-11-10T11:30:00+05:30", "valid_to": "2026-11-10T13:30:00+05:30",
         "meta": {"campaign_id": "pb_B2_abandoned_booking", "playbook_id": "B2_abandoned_booking",
                  "created_by": "ai", "decision_id": "dec_8f3a91c2e0d4b7a6",
                  "engage_promo_ref": "prm_8f3a91c2e0d4b7a6"}}
    b.update(kw)
    return b


def ride(**kw):
    r = {"user_id": "u_10042", "fare_inr": 464.5, "vehicle_type": "sedan", "city_id": 3}
    r.update(kw)
    return r


def create(env, b=None, key="dec_8f3a91c2e0d4b7a6"):
    return env.c.post("/api/admin/promocodes", json=b or body(), headers={**AUTH, "Idempotency-Key": key})


def test_create_and_idempotency(env):
    r = create(env)
    assert r.status_code == 201
    assert openapi.errors(SPEC, "PromoCreated", r.json()) == []
    pid = r.json()["promo_id"]
    again = create(env)
    assert again.status_code == 200 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["promo_id"] == pid
    assert create(env, body(value=20)).json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    clash = create(env, key="dec_other000000001")
    assert clash.status_code == 409 and clash.json()["code"] == "CODE_EXISTS"
    assert create(env, body(code="GO15-AAAA"), key="dec_other000000001").status_code == 201


def test_create_rejects_invalid_and_unauthenticated(env):
    for bad in (body(value=150), body(type="bogus"), body(user_id="riya"), body(valid_to="2026-11-10T11:00:00+05:30")):
        r = env.c.post("/api/admin/promocodes", json=bad, headers=AUTH)
        assert r.status_code == 422 and r.json()["code"] == "INVALID_RESTRICTION", bad
        assert r.headers["content-type"].startswith("application/problem+json")
    assert env.c.post("/api/admin/promocodes", json=body()).status_code == 401


def test_apply_rules(env):
    create(env)
    apply = lambda **kw: env.c.post("/mock/promocodes/GO15-7KQ2/apply", json=ride(**kw))
    ok = apply()
    assert ok.status_code == 200 and ok.json()["discount_inr"] == 69.68      # 15% of 464.5, under the 75 cap
    assert apply(fare_inr=900).json()["discount_inr"] == 75                    # capped
    for kw, code in [({"user_id": "u_10043"}, "WRONG_USER"), ({"fare_inr": 80}, "BELOW_MIN_FARE"),
                     ({"vehicle_type": "suv"}, "VEHICLE_NOT_ELIGIBLE"), ({"city_id": 1}, "CITY_NOT_ELIGIBLE"),
                     ({"at": "2026-11-10T14:00:00+05:30"}, "PROMO_EXPIRED"),
                     ({"at": "2026-11-10T11:00:00+05:30"}, "NOT_YET_VALID")]:
        r = apply(**kw)
        assert (r.status_code, r.json()["code"]) == (422, code), kw
    assert env.c.post("/mock/promocodes/NOPE/apply", json=ride()).status_code == 404


def test_redeem_sends_webhook_once_and_usage(env):
    pid = create(env).json()["promo_id"]
    env.c.post("/mock/promocodes/GO15-7KQ2/apply", json=ride(ride_id="r_4821"))
    r = env.c.post("/mock/promocodes/GO15-7KQ2/redeem", json=ride(ride_id="r_4821", fare_inr=480.0))
    assert r.json()["status"] == "redeemed" and r.json()["discount_inr"] == 69.68   # price locked at booking
    dup = env.c.post("/mock/promocodes/GO15-7KQ2/redeem", json=ride(ride_id="r_4821"))
    assert dup.json()["status"] == "duplicate" and dup.json()["event_id"] == r.json()["event_id"]
    assert env.drain() == 1
    got = env.received("promo_redeemed")
    assert len(got) == 1 and got[0]["status"] == "applied"
    assert got[0]["body"]["meta"]["decision_id"] == "dec_8f3a91c2e0d4b7a6"
    assert got[0]["body"]["gross_fare_inr"] == 480.0
    usage = env.c.get(f"/api/admin/promocodes/{pid}/usage", headers=AUTH).json()
    assert usage["uses"] == 1 and openapi.errors(SPEC, "PromoUsage", usage) == []
    second = env.c.post("/mock/promocodes/GO15-7KQ2/redeem", json=ride(ride_id="r_4822"))
    assert second.json()["code"] == "USAGE_LIMIT_REACHED"


def test_deactivate(env):
    pid = create(env).json()["promo_id"]
    bad = env.c.patch(f"/api/admin/promocodes/{pid}", json={"status": "inactive", "reason": "bored"}, headers=AUTH)
    assert bad.status_code == 422
    r = env.c.patch(f"/api/admin/promocodes/{pid}", json={"status": "inactive", "reason": "kill_switch"},
                    headers=AUTH)
    assert r.status_code == 200
    assert env.c.post("/mock/promocodes/GO15-7KQ2/apply", json=ride()).json()["code"] == "PROMO_INACTIVE"
    assert env.c.patch("/api/admin/promocodes/1", json={"status": "inactive", "reason": "admin"},
                       headers=AUTH).status_code == 404


def test_offer_types():
    base = body(user_id=None, usage_limit=10, vehicle_types=[], min_fare=None)
    p = lambda **kw: {**base, **kw, "status": "active", "uses": 0}
    at = START
    assert evaluate(p(type="flat", value=50, max_discount=None), ride(fare_inr=40), at)["discount_inr"] == 40
    assert evaluate(p(type="free_ride", value=150, max_discount=None), ride(fare_inr=200), at)["net_fare_inr"] == 50
    cb = evaluate(p(type="cashback", value=60, max_discount=50), ride(), at)
    assert (cb["discount_inr"], cb["cashback_inr"]) == (0, 50)
    up = evaluate(p(type="upgrade", value="prime", max_discount=80), ride(vehicle_type="sedan", upgrade_fare_inr=600), at)
    assert up["discount_inr"] == 80
    try:
        evaluate(p(type="upgrade", value="sedan"), ride(vehicle_type="suv"), at)
        raise AssertionError("downgrade accepted")
    except Rejected as e:
        assert e.code == "VEHICLE_NOT_ELIGIBLE"
    try:
        evaluate(p(first_ride_only=True), ride(), at)
        raise AssertionError("first_ride_only ignored")
    except Rejected as e:
        assert e.code == "NOT_FIRST_RIDE"
