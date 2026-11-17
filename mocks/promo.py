"""Mock HireMe Promo API (contracts/openapi/promo-api.v1.yaml, docs/API.md §6.1).

Contract endpoints: create, usage, deactivate. Simulator-only endpoints emulate the HireMe backend applying a
code at booking (`apply`) and recording it on ride completion (`redeem`, which calls the engine's
promo-redeemed webhook).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from engage.contract import openapi
from mocks.clock import iso_ist, parse_ts
from mocks.common import Ctx, canonical_hash, has_bearer, json_body, problem
from mocks.faults import FaultError

SPEC = "promo-api.v1.yaml"
DEACTIVATE_REASONS = {"campaign_cancelled", "kill_switch", "user_unsubscribed", "fraud", "admin"}
VEHICLES = ("mini", "sedan", "prime", "suv")


def inr(x) -> float:
    """Round money half-up to the paisa (binary floats would turn 69.675 into 69.67)."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class Rejected(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code, self.detail = code, detail


def evaluate(promo: dict, ride: dict, at: datetime) -> dict:
    """The backend's promo rules at booking time. Returns discount and cashback, or raises Rejected."""
    if promo["status"] != "active":
        raise Rejected("PROMO_INACTIVE", promo.get("deactivated_reason") or "")
    if at < parse_ts(promo["valid_from"]):
        raise Rejected("NOT_YET_VALID", promo["valid_from"])
    if at > parse_ts(promo["valid_to"]):
        raise Rejected("PROMO_EXPIRED", promo["valid_to"])
    if promo.get("user_id") and promo["user_id"] != ride["user_id"]:
        raise Rejected("WRONG_USER", "code is locked to another rider")
    if ride["city_id"] not in promo["city_ids"]:
        raise Rejected("CITY_NOT_ELIGIBLE", str(ride["city_id"]))
    if promo.get("vehicle_types") and ride["vehicle_type"] not in promo["vehicle_types"]:
        raise Rejected("VEHICLE_NOT_ELIGIBLE", ride["vehicle_type"])
    fare = float(ride["fare_inr"])
    if promo.get("min_fare") is not None and fare < promo["min_fare"]:
        raise Rejected("BELOW_MIN_FARE", f"{fare} < {promo['min_fare']}")
    if promo.get("first_ride_only") and not ride.get("first_ride"):
        raise Rejected("NOT_FIRST_RIDE")
    if promo["uses"] >= promo["usage_limit"]:
        raise Rejected("USAGE_LIMIT_REACHED")
    cap = promo.get("max_discount")
    cap = float("inf") if cap is None else float(cap)
    t, v = promo["type"], promo["value"]
    discount = cashback = 0.0
    if t == "percent":
        discount = min(Decimal(str(fare)) * Decimal(str(v)) / 100, Decimal(str(cap)))
    elif t in ("flat", "free_ride"):
        discount = min(float(v), fare, cap)
    elif t == "cashback":
        cashback = min(float(v), cap)
    elif t == "upgrade":
        if VEHICLES.index(v) <= VEHICLES.index(ride["vehicle_type"]):
            raise Rejected("VEHICLE_NOT_ELIGIBLE", f"upgrade to {v} from {ride['vehicle_type']}")
        discount = min(max(float(ride.get("upgrade_fare_inr") or fare) - fare, 0.0), cap)
    discount, cashback = inr(discount), inr(cashback)
    return {"discount_inr": discount, "cashback_inr": cashback, "net_fare_inr": inr(Decimal(str(fare)) - Decimal(str(discount)))}


RIDE_FIELDS = {"user_id": str, "fare_inr": (int, float), "vehicle_type": str, "city_id": int}


def _ride(body) -> dict:
    if not isinstance(body, dict):
        raise Rejected("INVALID_REQUEST", "JSON object expected")
    for k, typ in RIDE_FIELDS.items():
        if not isinstance(body.get(k), typ) or isinstance(body.get(k), bool):
            raise Rejected("INVALID_REQUEST", f"{k} is required")
    if body["vehicle_type"] not in VEHICLES:
        raise Rejected("INVALID_REQUEST", f"vehicle_type must be one of {VEHICLES}")
    return body


def router(ctx: Ctx) -> APIRouter:
    r = APIRouter()

    def gate(request: Request):
        try:
            ctx.faults.gate("promo")
        except FaultError as e:
            return problem(e.status, e.error, "injected fault")
        if ctx.cfg.require_auth and not has_bearer(request):
            ctx.faults.count_error("promo", "UNAUTHENTICATED")
            return problem(401, "UNAUTHENTICATED", "Bearer service token required")
        return None

    @r.post("/api/admin/promocodes")
    async def create(request: Request):
        if (resp := gate(request)) is not None:
            return resp
        body = await json_body(request)
        errs = openapi.errors(SPEC, "PromoCreate", body) if body is not None else ["invalid JSON"]
        if not errs and parse_ts(body["valid_to"]) <= parse_ts(body["valid_from"]):
            errs = ["valid_to must be after valid_from"]
        if errs:
            ctx.faults.count_error("promo", "INVALID_RESTRICTION")
            return problem(422, "INVALID_RESTRICTION", "; ".join(errs[:5]), errors=errs)
        key = request.headers.get("idempotency-key")
        if key is not None and not 0 < len(key) <= 64:
            return problem(422, "INVALID_RESTRICTION", "Idempotency-Key must be 1-64 characters")
        now = ctx.clock.now()
        doc = {**body, "status": "active", "uses": 0, "redemptions": [], "applications": {},
               "idempotency_key": key, "request_hash": canonical_hash(body), "created_at": now.isoformat(),
               "deactivated_reason": None}
        result, saved = ctx.store.create_promo(doc, key, doc["request_hash"], now)
        if result == "code_exists":
            ctx.faults.count_error("promo", "CODE_EXISTS")
            return problem(409, "CODE_EXISTS", f"code {body['code']} already exists")
        if result == "key_reused":
            return problem(422, "IDEMPOTENCY_KEY_REUSED", "same Idempotency-Key with a different body")
        out = {"promo_id": saved["promo_id"], "code": saved["code"], "status": saved["status"]}
        if result == "replayed":
            return JSONResponse(out, status_code=200, headers={"Idempotent-Replayed": "true"})
        return JSONResponse(out, status_code=201)

    @r.get("/api/admin/promocodes/{promo_id}/usage")
    def usage(promo_id: int, request: Request):
        if (resp := gate(request)) is not None:
            return resp
        p = ctx.store.get_promo(promo_id)
        if not p:
            return problem(404, "NOT_FOUND", f"promo {promo_id}")
        return {"promo_id": promo_id, "uses": p["uses"],
                "redemptions": [{k: x[k] for k in ("ride_id", "user_id", "discount_inr", "redeemed_at")}
                                for x in p["redemptions"]]}

    @r.patch("/api/admin/promocodes/{promo_id}")
    async def deactivate(promo_id: int, request: Request):
        if (resp := gate(request)) is not None:
            return resp
        body = await json_body(request)
        if not (isinstance(body, dict) and set(body) == {"status", "reason"} and body["status"] == "inactive"
                and body["reason"] in DEACTIVATE_REASONS):
            return problem(422, "INVALID_REQUEST",
                           f"body must be {{status: inactive, reason: one of {sorted(DEACTIVATE_REASONS)}}}")
        now = ctx.now_utc_iso()

        def off(p):
            p.update(status="inactive", deactivated_reason=body["reason"], deactivated_at=now)
        try:
            ctx.store.update_promo(("id", promo_id), off)
        except KeyError:
            return problem(404, "NOT_FOUND", f"promo {promo_id}")
        return {"promo_id": promo_id, "status": "inactive", "reason": body["reason"]}

    # ---- simulator-only: the HireMe backend's side of a booking ---------------------------------------
    @r.get("/mock/promocodes/{code}")
    def inspect(code: str):
        p = ctx.store.get_promo_by_code(code)
        return p if p else problem(404, "NOT_FOUND", code)

    @r.post("/mock/promocodes/{code}/apply")
    async def apply(code: str, request: Request):
        """Body: user_id, fare_inr, vehicle_type, city_id, [ride_id, first_ride, upgrade_fare_inr, at].
        With ride_id the result is remembered and honoured at redeem, as a backend locks the price at booking."""
        try:
            ride = _ride(await json_body(request))
            at = parse_ts(ride["at"]) if ride.get("at") else ctx.clock.now()

            def do(p):
                res = evaluate(p, ride, at)
                if ride.get("ride_id"):
                    p["applications"][ride["ride_id"]] = {**res, "user_id": ride["user_id"],
                                                          "applied_at": at.isoformat()}
                return {"promo_id": p["promo_id"], "code": p["code"], "applicable": True, **res}
            return ctx.store.update_promo(("code", code), do)
        except KeyError:
            return problem(404, "NOT_FOUND", code)
        except Rejected as e:
            return problem(422, e.code, e.detail, applicable=False)

    @r.post("/mock/promocodes/{code}/redeem")
    async def redeem(code: str, request: Request):
        """Body: user_id, ride_id, fare_inr (gross), vehicle_type, city_id, [first_ride, upgrade_fare_inr, at].
        Idempotent on ride_id. Sends the promo-redeemed webhook (API.md §3.1)."""
        try:
            ride = _ride(await json_body(request))
            if not str(ride.get("ride_id", "")).startswith("r_"):
                raise Rejected("INVALID_REQUEST", "ride_id (r_<digits>) is required")
            at = parse_ts(ride["at"]) if ride.get("at") else ctx.clock.now()

            def do(p):
                for x in p["redemptions"]:
                    if x["ride_id"] == ride["ride_id"]:
                        return {"status": "duplicate", **x}, None
                applied = p["applications"].get(ride["ride_id"])
                if applied and applied["user_id"] == ride["user_id"]:
                    if p["uses"] >= p["usage_limit"]:
                        raise Rejected("USAGE_LIMIT_REACHED")
                    res = applied
                else:
                    res = evaluate(p, ride, at)
                cost = inr(Decimal(str(res["discount_inr"])) + Decimal(str(res["cashback_inr"])))
                event_id = "prx_" + hashlib.sha1(f"{p['promo_id']}:{ride['ride_id']}".encode()).hexdigest()[:12]
                rec = {"event_id": event_id, "ride_id": ride["ride_id"], "user_id": ride["user_id"],
                       "discount_inr": cost, "gross_fare_inr": float(ride["fare_inr"]), "redeemed_at": iso_ist(at)}
                p["redemptions"].append(rec)
                p["uses"] += 1
                hook = {"event_id": event_id, "promo_id": p["promo_id"], "code": p["code"],
                        "user_id": ride["user_id"], "ride_id": ride["ride_id"], "discount_inr": cost,
                        "gross_fare_inr": float(ride["fare_inr"]), "redeemed_at": iso_ist(at),
                        "meta": {k: v for k, v in p["meta"].items()}}
                return {"status": "redeemed", **rec}, hook
            out, hook = ctx.store.update_promo(("code", code), do)
        except KeyError:
            return problem(404, "NOT_FOUND", code)
        except Rejected as e:
            return problem(422, e.code, e.detail)
        if hook:
            ctx.webhooks.schedule(0, lambda: ("/engage/v1/webhooks/promo-redeemed", hook))
        return out

    return r
