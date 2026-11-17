"""State of the mock services: promo codes (mock_promo_codes) and sent messages (mock_deliveries).

MemoryStore is the default (tests, quick runs). FirestoreStore keeps the same state in Firestore so the
responder and scenario checks can read it (docs/DATA_MODEL.md §4); use it with the emulator for live runs
(D-083). On the free tier every write counts against 20k/day.
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timedelta
from typing import Callable, TypeVar

T = TypeVar("T")
FIRST_PROMO_ID = 55001
IDEMPOTENCY_WINDOW = timedelta(hours=24)
DELIVERY_RETENTION = timedelta(days=30)


def _idem_result(doc: dict | None, req_hash: str, now: datetime) -> str | None:
    if not doc or now - datetime.fromisoformat(doc["created_at"]) > IDEMPOTENCY_WINDOW:
        return None
    return "replayed" if doc["request_hash"] == req_hash else "key_reused"


class MemoryStore:
    def __init__(self):
        self._lock = threading.RLock()
        self.promos: dict[int, dict] = {}
        self.deliveries: dict[str, dict] = {}

    # -- promo codes
    def create_promo(self, doc: dict, idem_key: str | None, req_hash: str, now: datetime):
        with self._lock:
            if idem_key:
                prior = max((p for p in self.promos.values() if p.get("idempotency_key") == idem_key),
                            key=lambda p: p["promo_id"], default=None)
                res = _idem_result(prior, req_hash, now)
                if res:
                    return res, copy.deepcopy(prior)
            if any(p["code"] == doc["code"] for p in self.promos.values()):
                return "code_exists", None
            pid = max(self.promos, default=FIRST_PROMO_ID - 1) + 1
            self.promos[pid] = new = {**copy.deepcopy(doc), "promo_id": pid}
            return "created", copy.deepcopy(new)

    def get_promo(self, promo_id: int) -> dict | None:
        with self._lock:
            return copy.deepcopy(self.promos.get(promo_id))

    def get_promo_by_code(self, code: str) -> dict | None:
        with self._lock:
            return copy.deepcopy(next((p for p in self.promos.values() if p["code"] == code), None))

    def update_promo(self, key: tuple[str, int | str], fn: Callable[[dict], T]) -> T:
        """Run fn on the promo found by ("id", promo_id) or ("code", code) atomically; fn mutates it in place.
        Raises KeyError if there is no such promo."""
        with self._lock:
            kind, val = key
            doc = self.promos.get(val) if kind == "id" else next(
                (p for p in self.promos.values() if p["code"] == val), None)
            if doc is None:
                raise KeyError(val)
            work = copy.deepcopy(doc)
            out = fn(work)
            self.promos[doc["promo_id"]] = work
            return out

    # -- deliveries
    def add_delivery(self, doc: dict) -> None:
        with self._lock:
            self.deliveries[doc["doc_id"]] = copy.deepcopy(doc)

    def update_delivery(self, doc_id: str, fn: Callable[[dict], T]) -> T:
        with self._lock:
            work = copy.deepcopy(self.deliveries[doc_id])
            out = fn(work)
            self.deliveries[doc_id] = work
            return out

    def list_deliveries(self, user_id: str | None = None, since: str | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = [d for d in self.deliveries.values()
                    if (user_id is None or d.get("user_id") == user_id)
                    and (since is None or d["accepted_at"] >= since)]
        return copy.deepcopy(sorted(rows, key=lambda d: d["accepted_at"])[:limit])


class FirestoreStore:
    def __init__(self, client):
        from google.cloud import firestore
        self._fs = firestore
        self.db = client
        self.promos = client.collection("mock_promo_codes")
        self.deliveries = client.collection("mock_deliveries")

    def create_promo(self, doc: dict, idem_key: str | None, req_hash: str, now: datetime):
        fs = self._fs

        @fs.transactional
        def tx_create(tx):
            if idem_key:
                prior = [s.to_dict() for s in tx.get(self.promos.where(
                    filter=fs.FieldFilter("idempotency_key", "==", idem_key)))]
                res = _idem_result(max(prior, key=lambda p: p["promo_id"], default=None), req_hash, now)
                if res:
                    return res, max(prior, key=lambda p: p["promo_id"])
            if list(tx.get(self.promos.where(filter=fs.FieldFilter("code", "==", doc["code"])).limit(1))):
                return "code_exists", None
            last = list(tx.get(self.promos.order_by("promo_id", direction=fs.Query.DESCENDING).limit(1)))
            pid = last[0].to_dict()["promo_id"] + 1 if last else FIRST_PROMO_ID
            new = {**doc, "promo_id": pid}
            tx.set(self.promos.document(str(pid)), new)
            return "created", new

        return tx_create(self.db.transaction())

    def get_promo(self, promo_id: int) -> dict | None:
        snap = self.promos.document(str(promo_id)).get()
        return snap.to_dict() if snap.exists else None

    def get_promo_by_code(self, code: str) -> dict | None:
        snaps = list(self.promos.where(filter=self._fs.FieldFilter("code", "==", code)).limit(1).stream())
        return snaps[0].to_dict() if snaps else None

    def update_promo(self, key, fn):
        fs = self._fs
        kind, val = key

        @fs.transactional
        def tx_update(tx):
            if kind == "id":
                snaps = [s for s in [self.promos.document(str(val)).get(transaction=tx)] if s.exists]
            else:
                snaps = list(tx.get(self.promos.where(filter=fs.FieldFilter("code", "==", val)).limit(1)))
            if not snaps:
                raise KeyError(val)
            work = snaps[0].to_dict()
            out = fn(work)
            tx.set(snaps[0].reference, work)
            return out

        return tx_update(self.db.transaction())

    def add_delivery(self, doc: dict) -> None:
        exp = datetime.fromisoformat(doc["accepted_at"]) + DELIVERY_RETENTION
        self.deliveries.document(doc["doc_id"]).set({**doc, "expire_at": exp})

    def update_delivery(self, doc_id: str, fn):
        fs = self._fs

        @fs.transactional
        def tx_update(tx):
            ref = self.deliveries.document(doc_id)
            work = ref.get(transaction=tx).to_dict()
            out = fn(work)
            tx.set(ref, work)
            return out

        return tx_update(self.db.transaction())

    def list_deliveries(self, user_id: str | None = None, since: str | None = None, limit: int = 100) -> list[dict]:
        fs = self._fs
        q = self.deliveries
        if user_id:      # equality only, sorted here: avoids a composite index
            rows = [s.to_dict() for s in q.where(filter=fs.FieldFilter("user_id", "==", user_id)).stream()]
            rows = [r for r in rows if since is None or r["accepted_at"] >= since]
        else:
            if since:
                q = q.where(filter=fs.FieldFilter("accepted_at", ">=", since))
            rows = [s.to_dict() for s in q.order_by("accepted_at").limit(limit).stream()]
        for r in rows:
            r.pop("expire_at", None)
        return sorted(rows, key=lambda d: d["accepted_at"])[:limit]
