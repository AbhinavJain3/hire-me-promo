"""Stand-in for the engine's inbound webhooks until engage/api exists (M0.5/M1).

Verifies the HMAC signature, validates the body against engage-ingest.v1.yaml, dedupes promo redemptions on
event_id and records everything for inspection at GET /received. Mount it in the mock process with --sink.
"""
from __future__ import annotations

import json
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from engage.contract import openapi
from engage.core.signing import SignatureError, verify

SPEC = "engage-ingest.v1.yaml"
PROVIDERS = {"fcm", "sms", "email", "whatsapp"}


def create_sink(secrets: dict[str, str]) -> FastAPI:
    app = FastAPI(title="engage webhook sink (dev)", docs_url=None, redoc_url=None)
    lock = threading.Lock()
    received: list[dict] = []
    seen_events: set[str] = set()
    app.state.received = received

    def problem(status, code, detail):
        return JSONResponse({"type": f"https://hireme.app/problems/{code.lower()}", "title": code,
                             "status": status, "code": code, "detail": detail},
                            status_code=status, media_type="application/problem+json")

    async def checked(request: Request, schema: str):
        raw = await request.body()
        try:
            verify(raw, request.headers, secrets)
        except SignatureError as e:
            return None, problem(401, e.code, str(e))
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return None, problem(422, "INVALID_JSON", "")
        errs = openapi.errors(SPEC, schema, body)
        if errs:
            return None, problem(422, "SCHEMA_VIOLATION", "; ".join(errs[:3]))
        return body, None

    @app.post("/engage/v1/webhooks/promo-redeemed")
    async def promo_redeemed(request: Request):
        body, err = await checked(request, "PromoRedeemedWebhook")
        if err:
            return err
        with lock:
            status = "duplicate" if body["event_id"] in seen_events else "applied"
            seen_events.add(body["event_id"])
            received.append({"kind": "promo_redeemed", "status": status, "body": body})
        return {"status": status}

    @app.post("/engage/v1/webhooks/delivery/{provider}")
    async def delivery(provider: str, request: Request):
        if provider not in PROVIDERS:
            return problem(404, "UNKNOWN_PROVIDER", provider)
        body, err = await checked(request, "DeliveryStatusWebhook")
        if err:
            return err
        with lock:
            received.append({"kind": "delivery", "provider": provider, "body": body})
        return {"status": "recorded"}

    @app.get("/received")
    def get_received(kind: str | None = None):
        with lock:
            return {"received": [r for r in received if kind is None or r["kind"] == kind]}

    return app
