"""engage-mocks FastAPI app: Promo API, FCM, SMS, email, WhatsApp, and the /mock/admin control API."""
from __future__ import annotations

import itertools
import re
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from mocks import channels, promo
from mocks.callbacks import Poster, Webhooks
from mocks.clock import Clock, parse_ts
from mocks.common import Ctx, MockConfig, json_body, problem
from mocks.dataview import DataView
from mocks.dlt import DltRegistry
from mocks.faults import PROFILES, Faults
from mocks.riders import RiderDirectory
from mocks.store import MemoryStore

DEMO_PAGE = Path(__file__).parent / "demo" / "riya.html"
DATA_PAGE = Path(__file__).parent / "demo" / "data.html"

# API activity feed for the demo page: (pattern, caller, service, action). Admin and polling calls are not shown.
ACTIVITY = [
    (r"^POST /api/admin/promocodes$", "Engine", "Promo API", "create promo code"),
    (r"^GET /api/admin/promocodes/\d+/usage$", "Engine", "Promo API", "read usage"),
    (r"^PATCH /api/admin/promocodes/\d+$", "Engine", "Promo API", "deactivate code"),
    (r"^POST /mock/fcm/", "Engine", "FCM", "send push"),
    (r"^POST /mock/sms/", "Engine", "SMS gateway", "send SMS"),
    (r"^POST /mock/email/", "Engine", "Email gateway", "send email"),
    (r"^POST /mock/whatsapp/", "Engine", "WhatsApp", "send WhatsApp"),
    (r"^POST /mock/promocodes/[^/]+/apply$", "HireMe app", "Promo API", "apply code at booking"),
    (r"^POST /mock/promocodes/[^/]+/redeem$", "HireMe backend", "Promo API", "redeem on ride completion"),
    (r"^POST /sink/engage/v1/webhooks/promo-redeemed$", "Promo API", "Engine", "redemption webhook"),
    (r"^POST /sink/engage/v1/webhooks/delivery/(\w+)$", "{0}", "Engine", "delivery receipt"),
]
ACTIVITY_RE = [(re.compile(p), *rest) for p, *rest in ACTIVITY]
PROVIDER_NAME = {"fcm": "FCM", "sms": "SMS gateway", "email": "Email gateway", "whatsapp": "WhatsApp"}


def create_app(cfg: MockConfig | None = None, *, store=None, riders: RiderDirectory | None = None,
               clock: Clock | None = None, poster: Poster | None = None, autostart: bool = True,
               sleep=time.sleep, dataview: DataView | None = None) -> FastAPI:
    cfg = cfg or MockConfig()
    if cfg.profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    clock = clock or Clock()
    dlt = DltRegistry()
    dlt.load_dirs(cfg.dlt_dirs)
    ctx = Ctx(cfg=cfg, clock=clock, faults=Faults(clock, seed=cfg.seed, profile=cfg.profile, sleep=sleep),
              store=store or MemoryStore(), riders=riders or RiderDirectory(), dlt=dlt,
              webhooks=Webhooks(cfg.engine_url, cfg.webhook_secret, cfg.webhook_key_id, poster, autostart))

    app = FastAPI(title="engage-mocks (dev only)", version="0.1.0",
                  description="Mock HireMe Promo API and channel providers (D-014, D-091).")
    app.state.ctx = ctx
    app.include_router(promo.router(ctx))
    app.include_router(channels.router(ctx))

    activity: deque = deque(maxlen=500)
    seq = itertools.count(1)
    act_lock = threading.Lock()

    @app.middleware("http")
    async def record_activity(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        key = f"{request.method} {request.url.path}"
        for rx, caller, service, action in ACTIVITY_RE:
            m = rx.match(key)
            if m:
                if caller == "{0}":
                    caller = PROVIDER_NAME.get(m.group(1), m.group(1))
                with act_lock:
                    activity.append({"seq": next(seq), "at": ctx.clock.now().isoformat(), "caller": caller,
                                     "service": service, "action": action, "method": request.method,
                                     "path": request.url.path, "status": response.status_code,
                                     "ms": round((time.perf_counter() - t0) * 1000)})
                break
        return response

    @app.get("/mock/admin/activity")
    def get_activity(after: int = 0):
        """API calls between the services, for the demo page (newest last)."""
        with act_lock:
            return {"activity": [a for a in activity if a["seq"] > after]}

    @app.get("/demo", include_in_schema=False)
    def demo_page():
        """Riya's B2 story, split screen (D-093). Dev only."""
        return FileResponse(DEMO_PAGE, media_type="text/html")

    @app.get("/demo/data", include_in_schema=False)
    def data_page():
        """The synthetic data in Firestore and BigQuery, for the client demo (D-094). Dev only."""
        return FileResponse(DATA_PAGE, media_type="text/html")

    @app.get("/mock/admin/data")
    def data_summary(refresh: bool = False):
        """Read-only summary of the synthetic data (live dev project, or local files as fallback)."""
        if dataview is None:
            return problem(404, "NO_DATA_VIEW", "start the mocks with --riders or --data-dir")
        try:
            return dataview.summary(refresh)
        except FileNotFoundError as e:
            return problem(404, "NO_DATA_VIEW", str(e))

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "riders": len(ctx.riders), "dlt_templates": len(ctx.dlt), "profile": cfg.profile,
                "engine_url": ctx.webhooks.engine_url}

    @app.get("/mock/admin/faults")
    def get_faults():
        return {"faults": ctx.faults.active()}

    @app.post("/mock/admin/faults")
    async def set_faults(request: Request):
        """One spec or a list: {target, mode: error_rate|outage|latency|reset, rate, error, p50_ms, p99_ms, until}."""
        body = await json_body(request)
        specs = body if isinstance(body, list) else [body]
        try:
            for spec in specs:
                if not isinstance(spec, dict):
                    raise ValueError("fault spec must be an object")
                active = ctx.faults.apply(spec)
        except (ValueError, KeyError) as e:
            return problem(422, "INVALID_FAULT", str(e))
        return {"faults": active}

    @app.get("/mock/admin/stats")
    def stats():
        return {"targets": ctx.faults.summary(), "webhooks": {
            "pending": ctx.webhooks.pending(), "sent": len(ctx.webhooks.sent),
            "failed": sum(1 for s in ctx.webhooks.sent if not (isinstance(s["status"], int) and s["status"] < 300))}}

    @app.get("/mock/admin/clock")
    def get_clock():
        return ctx.clock.state()

    @app.post("/mock/admin/clock")
    async def set_clock(request: Request):
        """{now?: ISO timestamp, scale?: virtual seconds per real second, advance_s?: jump forward}."""
        body = await json_body(request) or {}
        try:
            if "now" in body or "scale" in body:
                ctx.clock.set(parse_ts(body["now"]) if body.get("now") else ctx.clock.now(), body.get("scale"))
            if body.get("advance_s"):
                ctx.clock.advance(float(body["advance_s"]))
        except (ValueError, TypeError) as e:
            return problem(422, "INVALID_CLOCK", str(e))
        return ctx.clock.state()

    @app.post("/mock/admin/riders")
    async def upsert_riders(request: Request):
        """RiderProfile docs (one or a list), e.g. to mark a push token stale mid-scenario."""
        body = await json_body(request)
        docs = body if isinstance(body, list) else [body]
        if not all(isinstance(d, dict) and str(d.get("user_id", "")).startswith("u_") for d in docs):
            return problem(422, "INVALID_RIDER", "RiderProfile documents with user_id expected")
        for d in docs:
            ctx.riders.upsert(d)
        return {"riders": len(ctx.riders)}

    @app.post("/mock/admin/dlt")
    async def register_dlt(request: Request):
        """{template_id, body (with {placeholders}), sender_id, category}."""
        b = await json_body(request) or {}
        try:
            ctx.dlt.register(b["template_id"], b["body"], b["sender_id"], b["category"])
        except (KeyError, TypeError) as e:
            return problem(422, "INVALID_DLT", f"missing {e}")
        return {"dlt_templates": len(ctx.dlt)}

    @app.post("/mock/admin/drain")
    def drain():
        """Send all scheduled receipts and webhooks now, regardless of their delay."""
        return {"ran": ctx.webhooks.drain()}

    return app
