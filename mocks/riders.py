"""What the mock providers know about recipients, read from the hireme_riders stub (RiderProfile shape, D-074).

A real provider knows its own state (stale push tokens, DND registry, bounced addresses, WhatsApp opt-in), not
the rider database. The mocks derive that state from the stub so the synthetic world is consistent:
push tokens marked `stale` return UNREGISTERED, `contact.phone_dnd` blocks promotional SMS, unverified
emails bounce.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class RiderDirectory:
    def __init__(self):
        self._lock = threading.Lock()
        self.by_token: dict[str, dict] = {}
        self.by_phone: dict[str, dict] = {}
        self.by_email: dict[str, dict] = {}
        self.by_user: dict[str, dict] = {}

    def upsert(self, doc: dict) -> None:
        uid = doc["user_id"]
        contact = doc.get("contact") or {}
        consent = doc.get("consent") or {}
        rec = {"user_id": uid, "phone_dnd": bool(contact.get("phone_dnd")),
               "email_verified": bool(contact.get("email_verified")),
               "whatsapp_opt_in": bool((consent.get("whatsapp") or {}).get("opted_in")),
               "stale_tokens": {t["token"] for t in doc.get("push_tokens") or [] if t.get("stale")}}
        with self._lock:
            old = self.by_user.get(uid)
            if old:   # drop old keys so a changed phone/email/token no longer resolves to this rider
                for idx, key in ((self.by_phone, old.get("_phone")), (self.by_email, old.get("_email"))):
                    idx.pop(key, None)
                for t in old.get("_tokens", ()):
                    self.by_token.pop(t, None)
            rec["_phone"], rec["_email"] = contact.get("phone_e164"), contact.get("email")
            rec["_tokens"] = [t["token"] for t in doc.get("push_tokens") or []]
            self.by_user[uid] = rec
            if rec["_phone"]:
                self.by_phone[rec["_phone"]] = rec
            if rec["_email"]:
                self.by_email[rec["_email"].lower()] = rec
            for t in rec["_tokens"]:
                self.by_token[t] = rec

    def __len__(self) -> int:
        return len(self.by_user)

    def token(self, token: str) -> tuple[dict | None, bool]:
        """(rider, registered). Unknown tokens are unregistered, as with real FCM."""
        rec = self.by_token.get(token)
        return rec, bool(rec) and token not in rec["stale_tokens"]

    def phone(self, phone: str) -> dict | None:
        return self.by_phone.get(phone)

    def email(self, email: str) -> dict | None:
        return self.by_email.get(email.lower())

    @classmethod
    def from_ndjson(cls, path: Path) -> "RiderDirectory":
        d = cls()
        with open(path) as f:
            for line in f:
                if line.strip():
                    d.upsert(json.loads(line))
        return d

    @classmethod
    def from_firestore(cls, client) -> "RiderDirectory":
        d = cls()
        for snap in client.collection("hireme_riders").stream():
            d.upsert(snap.to_dict())
        return d
