"""Mock channel providers (contracts/openapi/channels.v1.yaml, docs/API.md §6.2-§6.5).

Each accepted message becomes a mock_deliveries document (what the rider's phone "received"; the responder
reads these) and a delivery receipt later posted to /engage/v1/webhooks/delivery/{provider}.
Provider-side rules the mocks enforce, so engine mistakes show up as errors, not silent sends:
stale/unknown push tokens -> UNREGISTERED; SMS body must match the DLT template; promotional SMS only
09:00-21:00 IST (TRAI) and never delivered to DND numbers; marketing email needs List-Unsubscribe;
WhatsApp needs the rider's WhatsApp opt-in.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from engage.contract import openapi
from mocks.clock import IST, iso_ist
from mocks.common import Ctx, has_bearer, json_body, problem
from mocks.faults import FaultError

SPEC = "channels.v1.yaml"
SMS_COST_INR = {"promotional": 0.20}
SMS_COST_DEFAULT_INR = 0.15
PROMO_SMS_HOURS = (9, 21)          # TRAI window for promotional SMS, IST; the engine's own window is stricter
CALLBACK_DELAY_S = {"fcm": (0.5, 3), "sms": (2, 20), "email": (1, 10), "whatsapp": (1, 5)}
CHANNEL = {"fcm": "push", "sms": "sms", "email": "email", "whatsapp": "whatsapp"}


def fcm_error(status: int, fcm_status: str, error_code: str, message: str = "") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": status, "message": message or error_code, "status": fcm_status,
        "details": [{"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": error_code}]}})


FCM_STATUS = {"UNAVAILABLE": "UNAVAILABLE", "QUOTA_EXCEEDED": "RESOURCE_EXHAUSTED", "INTERNAL": "INTERNAL",
              "SENDER_ID_MISMATCH": "PERMISSION_DENIED", "THIRD_PARTY_AUTH_ERROR": "UNAUTHENTICATED"}


def gateway_error(status: int, code: str, message: str = "") -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


def router(ctx: Ctx) -> APIRouter:
    r = APIRouter()

    def delay(provider: str, client_ref: str, step: str = "") -> float:
        lo, hi = CALLBACK_DELAY_S[provider]
        return ctx.clock.real_seconds(lo + (hi - lo) * ctx.stable_u("delay", provider, step, client_ref))

    def accept(provider: str, provider_message_id: str, message_id: str, user_id: str | None, to: str,
               content: dict, cost_inr: float, outcome: list[tuple[float, str, str | None]]) -> None:
        """Record the delivery and schedule its receipts: outcome = [(real delay s, status, error_code), ...]."""
        doc_id = f"{provider}_{provider_message_id.rsplit('/', 1)[-1]}".replace("/", "_")
        now = ctx.now_utc_iso()
        ctx.store.add_delivery({
            "doc_id": doc_id, "provider": f"mock_{provider}", "channel": CHANNEL[provider],
            "provider_message_id": provider_message_id, "message_id": message_id, "user_id": user_id,
            "to": to, "content": content, "status": "accepted", "error_code": None, "cost_inr": cost_inr,
            "accepted_at": now, "history": [{"status": "accepted", "at": now}], "is_synthetic": True})
        t = 0.0
        for d, status, err in outcome:
            t += d

            def effect(status=status, err=err):
                at = ctx.clock.now()

                def upd(doc):
                    doc["status"], doc["error_code"] = status, err
                    doc["history"].append({"status": status, "at": at.astimezone(timezone.utc).isoformat()})
                ctx.store.update_delivery(doc_id, upd)
                return (f"/engage/v1/webhooks/delivery/{provider}",
                        {"provider_message_id": provider_message_id, "message_id": message_id,
                         "status": status, "at": iso_ist(at), "error_code": err})
            ctx.webhooks.schedule(t, effect)

    def pre(provider: str, request: Request, err_fn):
        try:
            ctx.faults.gate(provider)
        except FaultError as e:
            return err_fn(e)
        if ctx.cfg.require_auth and not has_bearer(request):
            ctx.faults.count_error(provider, "UNAUTHENTICATED")
            return err_fn(None)
        return None

    # ---- push: FCM HTTP v1 ------------------------------------------------------------------------------
    @r.post("/mock/fcm/v1/projects/{project_id}/messages:send")
    async def fcm_send(project_id: str, request: Request):
        def err(e):
            if e is None:
                return fcm_error(401, "UNAUTHENTICATED", "THIRD_PARTY_AUTH_ERROR", "missing OAuth2 token")
            return fcm_error(e.status, FCM_STATUS[e.error], e.error, "injected fault")
        if (resp := pre("fcm", request, err)) is not None:
            return resp
        body = await json_body(request)
        errs = openapi.errors(SPEC, "FcmSendRequest", body) if body is not None else ["invalid JSON"]
        if errs:
            ctx.faults.count_error("fcm", "INVALID_ARGUMENT")
            return fcm_error(400, "INVALID_ARGUMENT", "INVALID_ARGUMENT", "; ".join(errs[:3]))
        msg = body["message"]
        rider, registered = ctx.riders.token(msg["token"])
        if not registered:
            ctx.faults.count_error("fcm", "UNREGISTERED")
            return fcm_error(404, "NOT_FOUND", "UNREGISTERED", "Requested entity was not found.")
        name = f"projects/{project_id}/messages/0:{int(ctx.clock.now().timestamp())}%{secrets.token_hex(4)}"
        if body.get("validate_only"):
            return {"name": name}
        mid = msg["data"]["message_id"]
        failed = ctx.stable_u("fcm_failed", mid) < ctx.rates["fcm_failed"]
        accept("fcm", name, mid, rider["user_id"] if rider else None, msg["token"],
               {"title": (msg.get("notification") or {}).get("title"),
                "body": (msg.get("notification") or {}).get("body"), "data": msg["data"],
                "ttl": (msg.get("android") or {}).get("ttl")},
               0.0, [(delay("fcm", mid), "failed" if failed else "delivered", "INTERNAL" if failed else None)])
        return {"name": name}

    # ---- gateway (SMS, email, WhatsApp) -------------------------------------------------------------------
    def gw_err(e):
        if e is None:
            return gateway_error(401, "INVALID_REQUEST", "Bearer token required")
        return gateway_error(e.status, e.error, "injected fault")

    def gw_validate(provider: str, schema: str, body):
        errs = openapi.errors(SPEC, schema, body) if body is not None else ["invalid JSON"]
        if errs:
            ctx.faults.count_error(provider, "INVALID_REQUEST")
            return gateway_error(400, "INVALID_REQUEST", "; ".join(errs[:3]))
        return None

    def gw_id(prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(6)}"

    @r.post("/mock/sms/v1/sms", status_code=202)
    async def sms_send(request: Request):
        if (resp := pre("sms", request, gw_err)) is not None:
            return resp
        body = await json_body(request)
        if (resp := gw_validate("sms", "SmsSendRequest", body)) is not None:
            return resp
        if (why := ctx.dlt.check(body)) is not None:
            ctx.faults.count_error("sms", "DLT_TEMPLATE_MISMATCH")
            return gateway_error(400, "DLT_TEMPLATE_MISMATCH", why)
        category = body["dlt"]["category"]
        hour = ctx.clock.now().astimezone(IST).hour
        if category == "promotional" and not PROMO_SMS_HOURS[0] <= hour < PROMO_SMS_HOURS[1]:
            ctx.faults.count_error("sms", "OUTSIDE_PROMOTIONAL_WINDOW")
            return gateway_error(400, "OUTSIDE_PROMOTIONAL_WINDOW", f"{hour:02d}h IST")
        rider, ref = ctx.riders.phone(body["to"]), body["client_ref"]
        if category == "promotional" and rider and rider["phone_dnd"]:
            final, err = "dnd_blocked", "DND"
        elif ctx.stable_u("sms_failed", ref) < ctx.rates["sms_failed"]:
            final, err = "failed", "CARRIER_ERROR"
        else:
            final, err = "delivered", None
        pmid = gw_id("sms")
        accept("sms", pmid, ref, rider["user_id"] if rider else None, body["to"],
               {"body": body["body"], "sender_id": body["sender_id"], "dlt": body["dlt"]},
               SMS_COST_INR.get(category, SMS_COST_DEFAULT_INR), [(delay("sms", ref), final, err)])
        return JSONResponse({"provider_message_id": pmid, "status": "queued"}, status_code=202)

    @r.post("/mock/email/v1/email", status_code=202)
    async def email_send(request: Request):
        if (resp := pre("email", request, gw_err)) is not None:
            return resp
        body = await json_body(request)
        if (resp := gw_validate("email", "EmailSendRequest", body)) is not None:
            return resp
        rider, ref = ctx.riders.email(body["to"]), body["client_ref"]
        if not rider or not rider["email_verified"] or ctx.stable_u("bounce", ref) < ctx.rates["email_bounce"]:
            outcome = [(delay("email", ref), "bounced", "HARD_BOUNCE")]
        else:
            outcome = [(delay("email", ref), "delivered", None)]
            if ctx.stable_u("complaint", ref) < ctx.rates["email_complaint"]:
                outcome.append((delay("email", ref, "complaint") * 10, "complained", None))
        pmid = gw_id("em")
        accept("email", pmid, ref, rider["user_id"] if rider else None, body["to"],
               {k: body.get(k) for k in ("subject", "text", "html", "headers", "category")}, 0.0, outcome)
        return JSONResponse({"provider_message_id": pmid, "status": "queued"}, status_code=202)

    @r.post("/mock/whatsapp/v1/whatsapp", status_code=202)
    async def whatsapp_send(request: Request):
        if (resp := pre("whatsapp", request, gw_err)) is not None:
            return resp
        body = await json_body(request)
        if (resp := gw_validate("whatsapp", "WhatsappSendRequest", body)) is not None:
            return resp
        rider, ref = ctx.riders.phone(body["to"]), body["client_ref"]
        if not rider or not rider["whatsapp_opt_in"]:
            ctx.faults.count_error("whatsapp", "NO_WHATSAPP_CONSENT")
            return gateway_error(400, "NO_WHATSAPP_CONSENT", "recipient has not opted in to WhatsApp")
        outcome = [(delay("whatsapp", ref), "delivered", None)]
        if ctx.stable_u("wa_read", ref) < ctx.rates["whatsapp_read"]:
            outcome.append((delay("whatsapp", ref, "read") * 60, "read", None))
        pmid = gw_id("wa")
        accept("whatsapp", pmid, ref, rider["user_id"], body["to"], {"template": body["template"]}, 0.0, outcome)
        return JSONResponse({"provider_message_id": pmid, "status": "queued"}, status_code=202)

    # ---- what riders received (responder, scenario asserts) ---------------------------------------------
    @r.get("/mock/deliveries")
    def deliveries(user_id: str | None = None, since: str | None = None, limit: int = 100):
        if since:
            since = datetime.fromisoformat(since.replace(" ", "+").replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        return {"deliveries": ctx.store.list_deliveries(user_id=user_id, since=since, limit=min(limit, 1000))}

    return r


