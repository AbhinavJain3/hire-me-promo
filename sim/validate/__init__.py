"""Local validation of a generated dataset (file-based versions of DUMMY_DATA_PLAN §10 checks V1-V10, V13, V14).

V11 (IAM: engine cannot read engage_sim) and V12 (ground-truth recovery after a simulated run) need the cloud
project and the live simulator; they are reported as not applicable here. The same checks run as SQL in
sql/checks/ after loading (M0.3 loaders).

Events and rides are streamed (one pass each), so memory stays flat from `tiny` to `large`.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Callable

from jsonschema import Draft202012Validator

from engage.contract.catalog import load_catalog
from engage.contract.ga4 import from_ga4_row
from engage.tools.validate_contract import OPENAPI_DIR, envelope_validator, openapi_registry
from sim.generator.emit import open_text
from sim.generator.world import IST, SIM_DIR

PHONE_RE = re.compile(r"^\+919990[0-9]{6}$")
GROUND_TRUTH_KEYS = ("persona", "price_elasticity", "churn_hazard", "promo_affinity")


def read_ndjson(path: Path):
    with open_text(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


@dataclass
class EventStats:
    total: int = 0
    by_name: Counter = field(default_factory=Counter)
    duplicate_uuids: int = 0
    schema_checked: int = 0
    schema_errors: list = field(default_factory=list)
    schema_bad: int = 0
    roundtrip_checked: int = 0
    roundtrip_errors: list = field(default_factory=list)
    pair_mismatch: list = field(default_factory=list)
    date_mismatch: int = 0
    last_ride_prop: dict = field(default_factory=dict)
    first_day: str = "9999"
    last_day: str = ""
    truth_leaks: int = 0


@dataclass
class RideStats:
    total: int = 0
    weekday_by_persona: dict = field(default_factory=lambda: defaultdict(lambda: [0, 0, 0]))  # weekday, fri-sun, all
    last_completed: dict = field(default_factory=dict)
    s62cp_mini: list = field(default_factory=list)
    fare_out_of_range: int = 0
    rides_by_persona: Counter = field(default_factory=Counter)


class Data:
    def __init__(self, root: Path, sample: int = 20000):
        self.root = root
        self.sample = sample
        self.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.env_files = sorted((root / "envelopes").glob("events_*.ndjson*"))
        self.ga4_dir = root / "bigquery" / "analytics_999999999"
        stub = root / "bigquery" / "hireme_backend_stub"
        self.rides_path = stub / "rides.ndjson"
        self.snapshot_ids = {s["user_id"] for s in read_ndjson(stub / "riders_snapshot.ndjson")}
        self.riders = list(read_ndjson(root / "firestore" / "hireme_riders.ndjson"))
        self.personas = {p["user_id"]: p for p in read_ndjson(root / "bigquery" / "engage_sim" / "personas.ndjson")}
        self.end = date.fromisoformat(self.manifest["window"]["end_ist"])
        self.start = date.fromisoformat(self.manifest["window"]["start_ist"])
        self._events: EventStats | None = None
        self._rides: RideStats | None = None

    def persona_of(self, user_id: str) -> str:
        return self.personas[user_id]["persona_id"]

    # ------------------------------------------------------------------ one pass over events
    @property
    def events(self) -> EventStats:
        if self._events is None:
            self._events = self._scan_events()
        return self._events

    def _scan_events(self) -> EventStats:
        s = EventStats()
        cat = load_catalog()
        validator = envelope_validator()
        expected = max(self.manifest["counts"]["events_total"], 1)
        every = max(1, math.ceil(expected / self.sample))
        for env_path in self.env_files:
            day = env_path.name.split("_")[1].split(".")[0]
            s.first_day, s.last_day = min(s.first_day, day), max(s.last_day, day)
            ga4_path = self.ga4_dir / env_path.name
            # UUIDv7 ids embed the event time, so an id can only repeat within its own IST day file.
            seen: set[str] = set()
            with open_text(env_path) as fe, open_text(ga4_path) as fg:
                for env_line, row_line in zip(fe, fg, strict=True):
                    env, row = json.loads(env_line), json.loads(row_line)
                    s.total += 1
                    s.by_name[env["event_name"]] += 1
                    uid = env["event_uuid"]
                    if uid in seen:
                        s.duplicate_uuids += 1
                    seen.add(uid)
                    if datetime.fromtimestamp(row["event_timestamp"] / 1e6, IST).strftime("%Y%m%d") != \
                            row["event_date"]:
                        s.date_mismatch += 1
                    ups = env.get("user_properties") or {}
                    if env["user_id"] and "last_ride_date" in ups:
                        s.last_ride_prop[env["user_id"]] = ups["last_ride_date"]
                    if s.total % every:
                        continue
                    if any(k in env_line for k in GROUND_TRUTH_KEYS):
                        s.truth_leaks += 1
                    s.schema_checked += 1
                    errs = list(validator.iter_errors(env))
                    if errs:
                        s.schema_bad += 1
                        if len(s.schema_errors) < 10:
                            s.schema_errors.append(f"{env['event_name']} {uid}: {errs[0].message[:160]}")
                    s.roundtrip_checked += 1
                    self._roundtrip(env, row, cat, s)
        return s

    @staticmethod
    def _roundtrip(env: dict, row: dict, cat, s: EventStats) -> None:
        back = from_ga4_row(row, cat=cat)
        back.pop("source", None)
        for k in sorted(set(env) | set(back)):
            a, b = env.get(k), back.get(k)
            if k == "event_ts":
                if datetime.fromisoformat(a) != datetime.fromisoformat(b):
                    s.roundtrip_errors.append(f"{env['event_name']} event_ts {a} -> {b}")
            elif a != b:
                s.roundtrip_errors.append(f"{env['event_name']} {k}: {a!r} -> {b!r}")

    # ------------------------------------------------------------------ one pass over rides
    @property
    def rides(self) -> RideStats:
        if self._rides is None:
            self._rides = self._scan_rides()
        return self._rides

    def _scan_rides(self) -> RideStats:
        s = RideStats()
        for r in read_ndjson(self.rides_path):
            s.total += 1
            pid = self.persona_of(r["user_id"])
            s.rides_by_persona[pid] += 1
            if r["gross_fare_inr"] is not None and not (40 <= r["gross_fare_inr"] <= 3000):
                s.fare_out_of_range += 1
            if r["status"] != "completed":
                continue
            booked = datetime.fromisoformat(r["booked_ts"]).astimezone(IST)
            w = s.weekday_by_persona[pid]
            w[0] += booked.weekday() < 5
            w[1] += booked.weekday() >= 4
            w[2] += 1
            day = datetime.fromisoformat(r["completed_ts"]).astimezone(IST).date().isoformat()
            if day > s.last_completed.get(r["user_id"], ""):
                s.last_completed[r["user_id"]] = day
            if r["vehicle_type"] == "mini" and r["pickup_zone"] == "NOI-S62" and r["drop_zone"] == "DEL-CP":
                s.s62cp_mini.append(r["gross_fare_inr"])
        return s


Result = tuple[str, str, list[str]]      # (check id + name, PASS|FAIL|N/A, details)


def tol(p: float, n: int, points: float = 0.02) -> float:
    """±2 points (spec) widened to 3 standard errors for small samples."""
    return max(points, 3 * math.sqrt(max(p * (1 - p), 1e-9) / max(n, 1)))


# ----------------------------------------------------------------------------- checks
# Each check returns detail lines; a line containing "FAIL" or "OUT OF RANGE" fails the check.

def v1_schema(d: Data) -> list[str]:
    e = d.events
    out = list(e.schema_errors)
    status = "FAIL" if e.schema_bad else "ok"
    out.append(f"{e.schema_checked - e.schema_bad}/{e.schema_checked} sampled envelopes valid "
               f"(of {e.total}) {status}")
    if e.truth_leaks:
        out.append(f"{e.truth_leaks} sampled events mention ground-truth fields FAIL")
    return out


def v2_unique(d: Data) -> list[str]:
    n = d.events.duplicate_uuids
    return [f"{n} duplicate event_uuid {'FAIL' if n else 'ok'}"]


def v3_roundtrip(d: Data) -> list[str]:
    e = d.events
    out = e.roundtrip_errors[:10]
    out.append(f"{e.roundtrip_checked} sampled GA4 rows round-trip to their envelope "
               f"{'FAIL' if e.roundtrip_errors else 'ok'}")
    return out


def v4_funnel(d: Data) -> list[str]:
    c = d.events.by_name
    booked, abandoned, completed = c["ride_booked"], c["booking_abandoned"], c["ride_completed"]
    checks = [
        ("fare_check -> ride_booked", booked / max(c["fare_check"], 1), 0.30, 0.45),
        ("ride_booked -> ride_completed", completed / max(booked, 1), 0.85, 0.92),
        # share of booking flows that end in booking_abandoned instead of ride_booked (D-081)
        ("abandon share of booking flows", abandoned / max(abandoned + booked, 1), 0.20, 0.30),
    ]
    return [f"{name}: {v:.3f} (target {lo}-{hi}) {'ok' if lo <= v <= hi else 'OUT OF RANGE'}"
            for name, v, lo, hi in checks]


def v5_personas(d: Data) -> list[str]:
    w = d.rides.weekday_by_persona
    out = []
    wk, _, n = w["P02"]
    s = wk / n if n else 0
    out.append(f"commuter (P02) weekday share {s:.2f} over {n} rides (target > 0.8) {'ok' if s > 0.8 else 'FAIL'}")
    _, fs, n = w["P03"]
    s = fs / n if n else 0
    out.append(f"weekend (P03) Fri-Sun share {s:.2f} over {n} rides (target > 0.7) {'ok' if s > 0.7 else 'FAIL'}")
    cutoff = (d.end - timedelta(days=90)).isoformat()
    late = [u for u, day in d.rides.last_completed.items() if d.persona_of(u) == "P09" and day > cutoff]
    out.append(f"dormant (P09) riders with a ride in the last 90 days: {len(late)} {'ok' if not late else 'FAIL'}")
    p05 = d.rides.rides_by_persona["P05"]
    out.append(f"not-activated (P05) rides: {p05} {'ok' if not p05 else 'FAIL'}")
    return out


def v6_recency(d: Data) -> list[str]:
    bands = {"P07": (7, 14), "P08": (30, 89), "P09": (90, 10_000)}
    last = dict(d.events.last_ride_prop)
    for u, day in d.rides.last_completed.items():
        if day > last.get(u, ""):
            last[u] = day
    out = []
    for pid, (lo, hi) in bands.items():
        users = [u for u in d.personas if d.persona_of(u) == pid]
        inside = 0
        for u in users:
            lr = last.get(u) or d.personas[u]["latent"].get("active_until")
            if lr:
                inside += lo <= (d.end - date.fromisoformat(lr)).days <= hi
        ok = inside >= 0.95 * len(users)
        out.append(f"{pid} last ride {lo}-{hi} days before end: {inside}/{len(users)} {'ok' if ok else 'FAIL'}")
    return out


def v7_fares(d: Data) -> list[str]:
    fares = d.rides.s62cp_mini
    out = []
    if len(fares) >= 20:
        m = median(fares)
        out.append(f"NOI-S62 -> DEL-CP mini median ₹{m:.0f} over {len(fares)} rides (target 330-430) "
                   f"{'ok' if 330 <= m <= 430 else 'FAIL'}")
    else:
        info = f", median so far ₹{median(fares):.0f}" if fares else ""
        out.append(f"NOI-S62 -> DEL-CP mini: only {len(fares)} rides{info}; check needs >= 20 (runs at medium)")
    n = d.rides.fare_out_of_range
    out.append(f"fares outside ₹40-₹3000: {n} {'ok' if not n else 'FAIL'}")
    return out


def v8_timezones(d: Data) -> list[str]:
    n = d.events.date_mismatch
    return [f"{n} rows where event_date != IST date of event_timestamp {'FAIL' if n else 'ok'}"]


def v9_consent(d: Data) -> list[str]:
    import yaml
    reach = yaml.safe_load((SIM_DIR / "personas.yaml").read_text())["reachability"]
    n = len(d.riders)
    shares = {
        "consent_push": sum(r["consent"]["push"]["opted_in"] for r in d.riders) / n,
        "consent_email": sum(r["consent"]["email"]["opted_in"] for r in d.riders) / n,
        "consent_sms": sum(r["consent"]["sms"]["opted_in"] for r in d.riders) / n,
        "consent_whatsapp": sum(r["consent"]["whatsapp"]["opted_in"] for r in d.riders) / n,
        "has_email": sum(r["contact"]["email"] is not None for r in d.riders) / n,
        "phone_dnd": sum(r["contact"]["phone_dnd"] for r in d.riders) / n,
        "push_token_present": sum(bool(r["push_tokens"]) for r in d.riders) / n,
    }
    out = []
    for k, v in shares.items():
        target = reach[k]
        t = tol(target, n)
        out.append(f"{k}: {v:.3f} (target {target} ± {t:.3f}) {'ok' if abs(v - target) <= t else 'FAIL'}")
    return out


def v10_fraud(d: Data) -> list[str]:
    by_dev = Counter(r["device_id_hash"] for r in d.riders)
    rings = [dev for dev, k in by_dev.items() if k >= 3]
    fraud = [u for u in d.personas if d.persona_of(u) == "P12"]
    expected = math.ceil(len(fraud) / 4)
    flagged = {r["user_id"] for r in d.riders if by_dev[r["device_id_hash"]] >= 3}
    missed = [u for u in fraud if u not in flagged]
    false_pos = [u for u in flagged if d.persona_of(u) != "P12"]
    return [f"devices with >= 3 accounts: {len(rings)} (expected {expected}) {'ok' if len(rings) == expected else 'FAIL'}",
            f"fraud accounts not on a shared device: {len(missed)} {'ok' if not missed else 'FAIL'}",
            f"non-fraud accounts on a shared device: {len(false_pos)} {'ok' if not false_pos else 'FAIL'}"]


def v13_riders(d: Data) -> list[str]:
    reg = openapi_registry()
    uri = (OPENAPI_DIR / "rider-api.v1.yaml").resolve().as_uri()
    v = Draft202012Validator({"$ref": f"{uri}#/components/schemas/RiderProfile"}, registry=reg)
    out = []
    bad = 0
    for r in d.riders:
        errs = list(v.iter_errors(r))
        if errs:
            bad += 1
            if bad <= 10:
                out.append(f"{r['user_id']}: {errs[0].message[:160]} FAIL")
        if any(k in json.dumps(r) for k in GROUND_TRUTH_KEYS):
            out.append(f"{r['user_id']}: ground-truth field in rider document FAIL")
    n_expected = d.manifest["riders"]
    out.append(f"{len(d.riders)} rider docs (expected {n_expected}), {bad} invalid "
               f"{'ok' if len(d.riders) == n_expected and not bad else 'FAIL'}")
    if d.snapshot_ids != {r["user_id"] for r in d.riders}:
        out.append("riders_snapshot user_ids differ from hireme_riders FAIL")
    return out


def v14_pii(d: Data) -> list[str]:
    bad = []
    for r in d.riders:
        if r["contact"]["phone_e164"] and not PHONE_RE.match(r["contact"]["phone_e164"]):
            bad.append(f"{r['user_id']} phone {r['contact']['phone_e164']} FAIL")
        if r["contact"]["email"] and not r["contact"]["email"].endswith("@example.test"):
            bad.append(f"{r['user_id']} email {r['contact']['email']} FAIL")
        if not r.get("is_synthetic"):
            bad.append(f"{r['user_id']} is_synthetic missing FAIL")
    return bad[:10] or [f"{len(d.riders)} riders: synthetic phones and emails only ok"]


def window_check(d: Data) -> list[str]:
    e = d.events
    lo, hi = d.start.strftime("%Y%m%d"), d.end.strftime("%Y%m%d")
    ok = e.first_day >= lo and e.last_day <= hi
    return [f"event days {e.first_day}..{e.last_day} within window {lo}..{hi} {'ok' if ok else 'FAIL'}"]


# ----------------------------------------------------------------------------- runner

CHECKS: list[tuple[str, Callable[[Data], list[str]]]] = [
    ("V1 envelopes conform to contract", v1_schema),
    ("V2 event_uuid unique", v2_unique),
    ("V3 GA4 round trip lossless", v3_roundtrip),
    ("V4 funnel ratios", v4_funnel),
    ("V5 persona sanity", v5_personas),
    ("V6 recency bands", v6_recency),
    ("V7 fares", v7_fares),
    ("V8 event_date is the IST date", v8_timezones),
    ("V9 consent and reachability shares", v9_consent),
    ("V10 fraud ring", v10_fraud),
    ("V13 rider docs (count, RiderProfile schema)", v13_riders),
    ("V14 PII hygiene", v14_pii),
    ("Window events stay inside the history window", window_check),
]
NOT_LOCAL = [("V11 engine cannot read engage_sim", "IAM check; runs after load in the dev project"),
             ("V12 ground-truth recovery", "needs a simulated engine run (M1.4)")]


def run(root: Path, sample: int = 20000) -> list[Result]:
    d = Data(root, sample=sample)
    results: list[Result] = []
    for cid, fn in CHECKS:
        try:
            details = fn(d)
        except Exception as exc:       # report, do not crash the whole run
            results.append((cid, "FAIL", [f"{type(exc).__name__}: {exc}"]))
            continue
        failed = any(("FAIL" in x or "OUT OF RANGE" in x) for x in details)
        results.append((cid, "FAIL" if failed else "PASS", details))
    results += [(cid, "N/A", [why]) for cid, why in NOT_LOCAL]
    return results
