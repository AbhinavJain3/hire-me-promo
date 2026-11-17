"""HMAC signing for webhooks (contracts/openapi/engage-ingest.v1.yaml, docs/API.md §3).

Signature: HMAC-SHA256 over "{timestamp}.{raw_body}", sent as
    X-HireMe-Signature: t=<unix seconds>,v1=<hex>
    X-HireMe-Key-Id: <key id>
Requests more than 300 s from server time are rejected (STALE_TIMESTAMP).
Senders (mocks now, real providers later) and the engine's receiving side both use this module.
"""
from __future__ import annotations

import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-HireMe-Signature"
KEY_ID_HEADER = "X-HireMe-Key-Id"
MAX_SKEW_S = 300


class SignatureError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


def _digest(secret: str, ts: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def sign_headers(body: bytes, secret: str, key_id: str, ts: int | None = None) -> dict[str, str]:
    ts = int(time.time()) if ts is None else ts
    return {SIGNATURE_HEADER: f"t={ts},v1={_digest(secret, ts, body)}", KEY_ID_HEADER: key_id,
            "Content-Type": "application/json"}


def verify(body: bytes, headers, secrets: dict[str, str], now: float | None = None) -> str:
    """Return the key id if the signature is valid; raise SignatureError otherwise.

    `secrets` maps key id -> secret, so keys can be rotated. Uses wall-clock time, not the virtual clock:
    the signature protects the transport, which always runs in real time.
    """
    key_id = headers.get(KEY_ID_HEADER)
    raw = headers.get(SIGNATURE_HEADER) or ""
    if key_id not in secrets:
        raise SignatureError("UNKNOWN_KEY", f"key id {key_id!r}")
    parts = dict(p.split("=", 1) for p in raw.split(",") if "=" in p)
    try:
        ts = int(parts["t"])
    except (KeyError, ValueError):
        raise SignatureError("BAD_SIGNATURE", "missing or malformed t=") from None
    if abs((time.time() if now is None else now) - ts) > MAX_SKEW_S:
        raise SignatureError("STALE_TIMESTAMP", f"t={ts}")
    if not hmac.compare_digest(parts.get("v1", ""), _digest(secrets[key_id], ts, body)):
        raise SignatureError("BAD_SIGNATURE", "digest mismatch")
    return key_id
