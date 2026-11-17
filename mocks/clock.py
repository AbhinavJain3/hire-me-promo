"""Clock shared by all mock services.

Virtual time = anchor + (real seconds since anchoring) x scale. With scale 60 one real second is one virtual
minute, matching the simulator's 60x live mode (D-083). Callback delays are in virtual seconds.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    def __init__(self, now: datetime | None = None, scale: float = 1.0):
        self._lock = threading.Lock()
        self.set(now, scale)

    def set(self, now: datetime | None = None, scale: float | None = None) -> None:
        with self._lock:
            self._real0 = time.monotonic()
            self._virt0 = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            if scale is not None:
                if scale <= 0:
                    raise ValueError("scale must be > 0")
                self.scale = float(scale)

    def now(self) -> datetime:
        with self._lock:
            return self._virt0 + timedelta(seconds=(time.monotonic() - self._real0) * self.scale)

    def advance(self, seconds: float) -> None:
        """Jump virtual time forward (tests and scripted scenarios)."""
        with self._lock:
            self._virt0 += timedelta(seconds=seconds)

    def real_seconds(self, virtual_seconds: float) -> float:
        return virtual_seconds / self.scale

    def state(self) -> dict:
        return {"now": self.now().isoformat(), "now_ist": self.now().astimezone(IST).isoformat(), "scale": self.scale}


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without offset: {s}")
    return dt


def iso_ist(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat(timespec="seconds")
