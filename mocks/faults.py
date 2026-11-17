"""Fault injection and baseline behaviour (docs/API.md §6, POST /mock/admin/faults).

A target (promo, fcm, sms, email, whatsapp) can carry several faults at once: one latency rule and one error
rule (error_rate or outage). Faults expire at `until` (virtual clock). `reset` clears a target, or all targets.
The `default` profile is the baseline from API.md §6: Promo API 0.5 % 503 with p50 120 ms, FCM 0.5 %
UNAVAILABLE. Profile `none` (tests) starts with no faults. Seeded, so a run can be replayed.
"""
from __future__ import annotations

import math
import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from mocks.clock import Clock, parse_ts

TARGETS = ("promo", "fcm", "sms", "email", "whatsapp")
ERRORS = {   # error name -> HTTP status, per target family
    "promo": {"UNAVAILABLE": 503, "RATE_LIMITED": 429, "INTERNAL": 500},
    "fcm": {"UNAVAILABLE": 503, "QUOTA_EXCEEDED": 429, "INTERNAL": 500, "SENDER_ID_MISMATCH": 403,
            "THIRD_PARTY_AUTH_ERROR": 401},
    "gateway": {"UNAVAILABLE": 503, "RATE_LIMITED": 429},
}
PROFILES = {
    "none": [],
    "default": [
        {"target": "promo", "mode": "error_rate", "rate": 0.005, "error": "UNAVAILABLE"},
        {"target": "promo", "mode": "latency", "p50_ms": 120, "p99_ms": 360},
        {"target": "fcm", "mode": "error_rate", "rate": 0.005, "error": "UNAVAILABLE"},
    ],
}


def errors_for(target: str) -> dict[str, int]:
    return ERRORS.get(target, ERRORS["gateway"])


@dataclass
class Fault:
    mode: str
    rate: float = 1.0
    error: str = "UNAVAILABLE"
    p50_ms: float = 0.0
    p99_ms: float = 0.0
    until: datetime | None = None


class FaultError(Exception):
    def __init__(self, target: str, error: str):
        super().__init__(error)
        self.target, self.error, self.status = target, error, errors_for(target)[error]


class Faults:
    def __init__(self, clock: Clock, seed: int = 0, profile: str = "default", sleep=time.sleep):
        self.clock, self._sleep = clock, sleep
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._faults: dict[str, dict[str, Fault]] = defaultdict(dict)   # target -> {"latency"|"error": Fault}
        self.stats: dict[str, dict] = {t: {"requests": 0, "errors": defaultdict(int), "latency_ms": []}
                                       for t in TARGETS}
        for spec in PROFILES[profile]:
            self.apply(spec)

    def apply(self, spec: dict) -> dict:
        """Validate and install one fault spec; returns the active faults."""
        mode, target = spec.get("mode"), spec.get("target")
        if mode == "reset":
            with self._lock:
                for t in ([target] if target else TARGETS):
                    self._faults[t].clear()
            return self.active()
        if target not in TARGETS:
            raise ValueError(f"target must be one of {TARGETS}")
        until = parse_ts(spec["until"]) if spec.get("until") else None
        if mode == "latency":
            p50, p99 = float(spec.get("p50_ms", 0)), float(spec.get("p99_ms", spec.get("p50_ms", 0)))
            if p50 < 0 or p99 < p50:
                raise ValueError("need 0 <= p50_ms <= p99_ms")
            fault, slot = Fault("latency", p50_ms=p50, p99_ms=p99, until=until), "latency"
        elif mode in ("error_rate", "outage"):
            error = spec.get("error", "UNAVAILABLE")
            if error not in errors_for(target):
                raise ValueError(f"error for {target} must be one of {sorted(errors_for(target))}")
            rate = 1.0 if mode == "outage" else float(spec.get("rate", 0))
            if not 0 <= rate <= 1:
                raise ValueError("rate must be in [0, 1]")
            fault, slot = Fault(mode, rate=rate, error=error, until=until), "error"
        else:
            raise ValueError("mode must be error_rate, outage, latency or reset")
        with self._lock:
            self._faults[target][slot] = fault
        return self.active()

    def active(self) -> dict:
        now = self.clock.now()
        out = {}
        with self._lock:
            for t, fs in self._faults.items():
                live = {slot: {k: v for k, v in vars(f).items() if v not in (None, 0.0) and k != "until"}
                        | ({"until": f.until.isoformat()} if f.until else {})
                        for slot, f in fs.items() if not f.until or f.until > now}
                if live:
                    out[t] = live
        return out

    def _current(self, target: str, slot: str) -> Fault | None:
        f = self._faults[target].get(slot)
        if f and f.until and f.until <= self.clock.now():
            del self._faults[target][slot]
            return None
        return f

    def gate(self, target: str) -> float:
        """Call at the start of a request: sleeps for injected latency, raises FaultError on an injected error.
        Returns the injected latency in ms (recorded in stats)."""
        with self._lock:
            lat, err = self._current(target, "latency"), self._current(target, "error")
            ms = 0.0
            if lat and lat.p50_ms > 0:
                sigma = math.log(lat.p99_ms / lat.p50_ms) / 2.326 if lat.p99_ms > lat.p50_ms else 0.0
                ms = lat.p50_ms * math.exp(sigma * self._rng.gauss(0, 1))
            fail = bool(err) and self._rng.random() < err.rate
            s = self.stats[target]
            s["requests"] += 1
            s["latency_ms"].append(round(ms, 1))
            if fail:
                s["errors"][err.error] += 1
        if ms:
            self._sleep(ms / 1000)
        if fail:
            raise FaultError(target, err.error)
        return ms

    def count_error(self, target: str, code: str) -> None:
        with self._lock:
            self.stats[target]["errors"][code] += 1

    def uniform(self) -> float:
        with self._lock:
            return self._rng.random()

    def summary(self) -> dict:
        def pct(xs, q):
            xs = sorted(xs)
            return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None
        with self._lock:
            return {t: {"requests": s["requests"], "errors": dict(s["errors"]),
                        "latency_ms": {"p50": pct(s["latency_ms"], 0.5), "p99": pct(s["latency_ms"], 0.99)}}
                    for t, s in self.stats.items()}
