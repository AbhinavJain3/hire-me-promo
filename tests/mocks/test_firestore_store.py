"""FirestoreStore against the Firestore emulator (skipped unless FIRESTORE_EMULATOR_HOST is set).

    scripts/firebase.sh emulators:start --only firestore --project demo-hireme-engage-dev
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python -m pytest tests/mocks/test_firestore_store.py
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from mocks.app import create_app
from mocks.common import MockConfig

from .conftest import AUTH, Env
from .test_channels import FCM, push
from .test_promo import body, ride

pytestmark = pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="needs the Firestore emulator")


@pytest.fixture
def fs_env():
    from google.cloud import firestore
    from mocks.store import FirestoreStore
    client = firestore.Client(project=f"demo-mocks-{uuid.uuid4().hex[:8]}")    # fresh, isolated database
    e = Env()
    e.app = create_app(MockConfig(engine_url="http://engine.test", webhook_secret="test-secret", profile="none"),
                       store=FirestoreStore(client), riders=e.ctx.riders, clock=e.clock,
                       poster=e.ctx.webhooks.poster, autostart=False)
    e.ctx, e.c = e.app.state.ctx, TestClient(e.app)
    return e


def test_promo_lifecycle_in_firestore(fs_env):
    e = fs_env
    r = e.c.post("/api/admin/promocodes", json=body(), headers={**AUTH, "Idempotency-Key": "dec_1"})
    assert r.status_code == 201 and r.json()["promo_id"] == 55001
    assert e.c.post("/api/admin/promocodes", json=body(), headers={**AUTH, "Idempotency-Key": "dec_1"}).status_code == 200
    assert e.c.post("/api/admin/promocodes", json=body(), headers={**AUTH, "Idempotency-Key": "dec_2"}).status_code == 409
    assert e.c.post("/api/admin/promocodes", json=body(code="GO15-BBBB"), headers=AUTH).json()["promo_id"] == 55002
    assert e.c.post("/mock/promocodes/GO15-7KQ2/redeem", json=ride(ride_id="r_1")).json()["status"] == "redeemed"
    assert e.c.post("/mock/promocodes/GO15-7KQ2/redeem", json=ride(ride_id="r_1")).json()["status"] == "duplicate"
    assert e.c.get("/api/admin/promocodes/55001/usage", headers=AUTH).json()["uses"] == 1
    e.drain()
    assert len(e.received("promo_redeemed")) == 1


def test_deliveries_in_firestore(fs_env):
    e = fs_env
    assert e.c.post(FCM, json=push(), headers=AUTH).status_code == 200
    e.drain()
    [d] = e.c.get("/mock/deliveries", params={"user_id": "u_10042"}).json()["deliveries"]
    assert d["status"] == "delivered" and len(d["history"]) == 2
    assert len(e.c.get("/mock/deliveries", params={"since": "2026-11-10T00:00:00+05:30"}).json()["deliveries"]) == 1
