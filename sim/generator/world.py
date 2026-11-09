"""Static world for the synthetic data: geography, fares, surge, calendar, app releases (DUMMY_DATA_PLAN §3).

Everything here is deterministic given the seed: surge for (zone, IST date, hour) is the same for every rider,
like a real market, and does not depend on the order in which riders are generated.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

IST = ZoneInfo("Asia/Kolkata")
SIM_DIR = Path(__file__).resolve().parents[1]


def load_yaml(name: str) -> dict:
    return yaml.safe_load((SIM_DIR / name).read_text(encoding="utf-8"))


def stable_uniform(*keys: object) -> float:
    """Deterministic U[0,1) from arbitrary keys (independent of generation order)."""
    h = hashlib.blake2b("|".join(map(str, keys)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


@dataclass(frozen=True)
class Zone:
    zone_id: str
    city_id: int
    zone_name: str
    zone_type: str
    lat: float
    lng: float
    base_demand_weight: float


def haversine_km(a: Zone, b: Zone) -> float:
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class World:
    def __init__(self, seed: int, history_end: date | None = None):
        self.seed = seed
        self.geo = load_yaml("geo.yaml")
        self.cal = load_yaml("calendar.yaml")
        self.cities = {c["city_id"]: c for c in self.geo["cities"]}
        self.zones = {z["zone_id"]: Zone(**z) for z in self.geo["zones"]}
        self.zones_by_city: dict[int, list[Zone]] = {}
        for z in self.zones.values():
            self.zones_by_city.setdefault(z.city_id, []).append(z)
        self.vehicles = {v["vehicle_type"]: v for v in self.geo["vehicle_types"]}
        self.trip = self.geo["trip"]
        self.default_history_end = date.fromisoformat(self.cal["history_end"])
        # Overridable so loaded data stays inside the BigQuery sandbox's 60-day window (D-082, D-084).
        self.history_end = history_end or self.default_history_end
        self.calendar: dict[date, dict] = {}
        for e in self.cal["events"]:
            self.calendar[date.fromisoformat(e["event_date"])] = e
        self.app_versions = [(v["version"], date.fromisoformat(v["released"])) for v in self.cal["app_versions"]]

    # ------------------------------------------------------------------ calendar
    def demand_multiplier(self, d: date) -> float:
        e = self.calendar.get(d)
        return float(e["demand_multiplier"]) if e else 1.0

    def day_kind(self, d: date) -> str | None:
        e = self.calendar.get(d)
        return e["kind"] if e else None

    # ------------------------------------------------------------------ trips
    def distance_km(self, pickup: str, drop: str, u: float) -> float:
        """Road distance; u in [0,1) picks the intra-zone distance."""
        if pickup == drop:
            lo, hi = self.trip["intra_zone_km"]
            return round(lo + (hi - lo) * u, 1)
        return round(haversine_km(self.zones[pickup], self.zones[drop]) * self.trip["road_factor"], 1)

    def is_peak(self, t: datetime, zone_id: str | None = None) -> bool:
        if t.weekday() >= 5:
            return False
        h = t.hour + t.minute / 60
        in_peak = any(lo <= h < hi for lo, hi in self.trip["surge"]["peak_hours_weekday"])
        if zone_id is None:
            return in_peak
        return in_peak and self.zones[zone_id].zone_type in self.trip["surge"]["peak_zone_types"]

    def minutes(self, km: float, t: datetime) -> float:
        per_km = self.trip["min_per_km_peak"] if self.is_peak(t) else self.trip["min_per_km_offpeak"]
        return round(km * per_km, 1)

    def surge(self, zone_id: str, t: datetime) -> float:
        s = self.trip["surge"]
        d, hour = t.date(), t.hour
        u1 = stable_uniform(self.seed, "surge", zone_id, d.isoformat(), hour)
        u2 = stable_uniform(self.seed, "surge-level", zone_id, d.isoformat(), hour)
        kind = self.day_kind(d)
        if self.is_peak(t, zone_id) and u1 < s["peak_probability"]:
            lo, hi = s["peak_range"]
        elif kind == "rain" and u1 < s["rain_probability"]:
            lo, hi = s["rain_range"]
        elif kind == "festival" and s["festival_evening_hours"][0] <= hour <= s["festival_evening_hours"][1] \
                and u1 < s["festival_probability"]:
            lo, hi = s["festival_range"]
        else:
            return 1.0
        return round(lo + (hi - lo) * u2, 1)

    def fare(self, vehicle: str, km: float, minutes: float, surge: float) -> float:
        v = self.vehicles[vehicle]
        base = float(v["base_fare_inr"])
        f = max(base, base + float(v["per_km_inr"]) * km + float(v["per_min_inr"]) * minutes) * surge
        return float(round(f))

    # ------------------------------------------------------------------ app versions
    def app_version(self, t: date, lag_days: float, signup: date) -> str:
        """Version on the rider's phone at date t: the latest release at install (signup), then upgrades after a lag."""
        current = self.app_versions[0][0]
        for version, released in self.app_versions:
            effective = signup if released <= signup else released + timedelta(days=lag_days)
            if effective <= t:
                current = version
        return current

    # ------------------------------------------------------------------ reference rows (hireme_ref)
    def ref_rows(self) -> dict[str, list[dict]]:
        cities = [{k: c[k] for k in ("city_id", "city_name", "state", "country", "timezone", "currency", "is_pilot")}
                  for c in self.geo["cities"]]
        zones = [dict(z) for z in self.geo["zones"]]
        vehicles = [dict(v) for v in self.geo["vehicle_types"]]
        calendar = [dict(e) for e in self.cal["events"]]
        return {"cities": cities, "zones": zones, "vehicle_types": vehicles, "calendar_events": calendar}
