"""Outbound webhooks from the mocks to the engine (delivery receipts, promo redemptions), HMAC-signed.

Jobs run on a background thread at their due time (virtual delay / clock scale). A failed POST is retried
3 times with backoff, as a provider would. `drain()` runs every pending job now (tests, scripted scenarios).
If no engine URL is configured the job is recorded as `not_sent` but its state change still happens.
"""
from __future__ import annotations

import heapq
import itertools
import json
import logging
import threading
import time
from typing import Callable

import httpx

from engage.core.signing import sign_headers

log = logging.getLogger("mocks.callbacks")
Poster = Callable[[str, bytes, dict], int]     # (url, body, headers) -> HTTP status
RETRY_BACKOFF_S = (0.5, 2.0, 5.0)


def httpx_poster(timeout: float = 5.0) -> Poster:
    client = httpx.Client(timeout=timeout)

    def post(url: str, body: bytes, headers: dict) -> int:
        return client.post(url, content=body, headers=headers).status_code
    return post


class Webhooks:
    def __init__(self, engine_url: str | None, secret: str, key_id: str, poster: Poster | None = None,
                 autostart: bool = True):
        self.engine_url = engine_url.rstrip("/") if engine_url else None
        self.secret, self.key_id = secret, key_id
        self.poster = poster or httpx_poster()
        self._heap: list = []
        self._seq = itertools.count()
        self._cv = threading.Condition()
        self._stop = False
        self.sent: list[dict] = []          # audit trail: url, status, attempts
        self._thread = None
        if autostart:
            self._thread = threading.Thread(target=self._run, name="mock-webhooks", daemon=True)
            self._thread.start()

    # A job: effect() changes mock state and returns (path, payload) to send, or None to send nothing.
    def schedule(self, delay_real_s: float, effect: Callable[[], tuple[str, dict] | None]) -> None:
        with self._cv:
            heapq.heappush(self._heap, (time.monotonic() + max(delay_real_s, 0), next(self._seq), effect))
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._stop and (not self._heap or self._heap[0][0] > time.monotonic()):
                    self._cv.wait(timeout=None if not self._heap else max(self._heap[0][0] - time.monotonic(), 0))
                if self._stop:
                    return
                _, _, effect = heapq.heappop(self._heap)
            self._execute(effect, sleep=time.sleep)

    def drain(self) -> int:
        """Run all pending jobs now, in due order (jobs they schedule run too). Returns the number run."""
        n = 0
        while True:
            with self._cv:
                if not self._heap:
                    return n
                _, _, effect = heapq.heappop(self._heap)
            self._execute(effect, sleep=lambda s: None)
            n += 1

    def pending(self) -> int:
        with self._cv:
            return len(self._heap)

    def close(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify()

    def _execute(self, effect, sleep) -> None:
        try:
            out = effect()
        except Exception:
            log.exception("mock callback effect failed")
            return
        if out is not None:
            self.send(*out, sleep=sleep)

    def send(self, path: str, payload: dict, sleep=time.sleep) -> dict:
        rec = {"path": path, "payload": payload, "status": None, "attempts": 0}
        if not self.engine_url:
            rec["status"] = "not_sent"
        else:
            body = json.dumps(payload, separators=(",", ":")).encode()
            for attempt, backoff in enumerate((*RETRY_BACKOFF_S, None), start=1):
                rec["attempts"] = attempt
                try:
                    rec["status"] = self.poster(self.engine_url + path, body,
                                                sign_headers(body, self.secret, self.key_id))
                except httpx.HTTPError as exc:
                    rec["status"] = f"error: {type(exc).__name__}"
                if isinstance(rec["status"], int) and rec["status"] < 500 and rec["status"] != 429:
                    break
                if backoff is not None:
                    sleep(backoff)
        self.sent.append(rec)
        return rec
