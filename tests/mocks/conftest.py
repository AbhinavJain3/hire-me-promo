from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from mocks.app import create_app
from mocks.clock import IST, Clock
from mocks.common import MockConfig
from mocks.riders import RiderDirectory
from mocks.sink import create_sink

SECRET = "test-secret"
ENGINE = "http://engine.test"
AUTH = {"Authorization": "Bearer test"}
START = datetime(2026, 11, 10, 12, 0, tzinfo=IST)


def rider(n: int, *, dnd=False, stale=False, verified=True, wa=True, token=True) -> dict:
    t = "2026-05-01T10:00:00+05:30"
    return {"user_id": f"u_{n}", "city_id": 3, "first_name": "Test", "language": "en", "signup_ts": t,
            "contact": {"phone_e164": f"+91999{n:07d}", "email": f"rider.{n}@example.test", "phone_dnd": dnd,
                        "email_verified": verified},
            "push_tokens": [{"token": f"fcm_tok_synthetic_{n}", "platform": "ANDROID", "updated_at": t,
                             "stale": stale}] if token else [],
            "consent": {c: {"opted_in": (wa if c == "whatsapp" else True), "updated_at": t, "source": "signup"}
                        for c in ("push", "email", "sms", "whatsapp")},
            "status": "active", "is_synthetic": True}


class Env:
    def __init__(self, profile="none", engine_url=ENGINE, sleep=lambda s: None):
        self.sink_app = create_sink({"dev-1": SECRET})
        self.sink = TestClient(self.sink_app)
        self.posts: list[tuple[str, int]] = []
        self.status_override: list[int] = []

        def poster(url, body, headers):
            if self.status_override:
                code = self.status_override.pop(0)
            else:
                code = self.sink.post(url.removeprefix(ENGINE), content=body, headers=headers).status_code
            self.posts.append((url, code))
            return code
        riders = RiderDirectory()
        for doc in [rider(10042), rider(10043, dnd=True), rider(10044, stale=True), rider(10045, verified=False),
                    rider(10046, wa=False)]:
            riders.upsert(doc)
        # the contract examples address u_10042 by these values
        doc = rider(10042)
        doc["contact"].update(phone_e164="+919990012345", email="riya.10042@example.test")
        riders.upsert(doc)
        self.clock = Clock(START, scale=1.0)
        self.app = create_app(MockConfig(engine_url=engine_url, webhook_secret=SECRET, profile=profile),
                              riders=riders, clock=self.clock, poster=poster, autostart=False, sleep=sleep)
        self.ctx = self.app.state.ctx
        self.c = TestClient(self.app)

    def drain(self) -> int:
        return self.ctx.webhooks.drain()

    def received(self, kind=None) -> list[dict]:
        return self.sink.get("/received", params={"kind": kind} if kind else None).json()["received"]


@pytest.fixture
def env():
    return Env()
