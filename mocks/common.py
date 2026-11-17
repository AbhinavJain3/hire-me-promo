"""Shared context and helpers for the mock routers."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from engage.contract.catalog import CONTRACTS_DIR, REPO_ROOT
from mocks.clock import Clock
from mocks.dlt import DltRegistry
from mocks.faults import Faults
from mocks.riders import RiderDirectory

DEV_WEBHOOK_SECRET = "dev-only-not-a-secret"


@dataclass
class MockConfig:
    project_id: str = "hireme-engage-dev"     # used in FCM message names only
    engine_url: str | None = None             # where receipts and redemption webhooks go
    webhook_secret: str = DEV_WEBHOOK_SECRET
    webhook_key_id: str = "dev-1"
    profile: str = "default"                  # faults.PROFILES / DELIVERY_RATES
    seed: int = 0
    require_auth: bool = True                 # Bearer token present (any value), as the real APIs need one
    dlt_dirs: list[Path] = field(default_factory=lambda: [CONTRACTS_DIR / "examples" / "templates",
                                                          REPO_ROOT / "templates"])


# Baseline provider behaviour that is not a request error (API.md §6.3, §6.4). Deterministic per message.
DELIVERY_RATES = {
    "default": {"sms_failed": 0.01, "email_bounce": 0.02, "email_complaint": 0.001, "whatsapp_read": 0.6,
                "fcm_failed": 0.0},
    "none": {"sms_failed": 0.0, "email_bounce": 0.0, "email_complaint": 0.0, "whatsapp_read": 1.0,
             "fcm_failed": 0.0},
}


@dataclass
class Ctx:
    cfg: MockConfig
    clock: Clock
    faults: Faults
    store: object
    riders: RiderDirectory
    dlt: DltRegistry
    webhooks: object

    def now_utc_iso(self) -> str:
        return self.clock.now().astimezone(timezone.utc).isoformat()

    def stable_u(self, *keys) -> float:
        """Uniform [0,1) that depends only on the seed and the keys (reproducible per message)."""
        h = hashlib.sha256(":".join(map(str, (self.cfg.seed, *keys))).encode()).digest()
        return int.from_bytes(h[:8], "big") / 2 ** 64

    @property
    def rates(self) -> dict:
        return DELIVERY_RATES[self.cfg.profile]


def problem(status: int, code: str, detail: str = "", **extra) -> JSONResponse:
    """RFC 9457 problem+json (docs/API.md §1.4)."""
    body = {"type": f"https://hireme.app/problems/{code.lower()}", "title": code, "status": status, "code": code,
            "detail": detail, **extra}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def has_bearer(request: Request) -> bool:
    return request.headers.get("authorization", "").lower().startswith("bearer ")


async def json_body(request: Request):
    try:
        return await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
