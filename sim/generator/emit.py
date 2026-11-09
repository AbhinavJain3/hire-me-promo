"""Event emission: canonical envelope (contract v1) -> GA4 export row, buffered per IST day (DUMMY_DATA_PLAN §7.5).

The envelope is built exactly as a sender would build it (UUIDv7 event_uuid, contract_version, origin, ...).
The GA4 row comes from engage.contract.ga4.to_ga4_row (shared with the engine's GA4 poller, so the round trip
is tested in both directions), plus the GA4 columns a real export fills (device, geo, app_info, privacy_info, ...).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from engage.contract.catalog import Catalog
from engage.contract.ga4 import iso_to_micros, to_ga4_row
from engage.contract.generate import auto_event_uuid
from sim.generator.population import Rider
from sim.generator.world import IST, World

ANDROID_DEVICES = [("Samsung", "SM-A546E", "Galaxy A54"), ("Xiaomi", "23049RAD8I", "Redmi Note 12"),
                   ("Vivo", "V2250", "Vivo V27"), ("OnePlus", "CPH2491", "Nord CE 3"),
                   ("Realme", "RMX3771", "Realme 11 Pro"), ("Oppo", "CPH2577", "Reno 10")]
IOS_DEVICES = [("Apple", "iPhone15,2", "iPhone 14 Pro"), ("Apple", "iPhone14,7", "iPhone 14"),
               ("Apple", "iPhone16,1", "iPhone 15 Pro")]


def uuid7(ts_ms: int, rand: bytes) -> str:
    rand_a = int.from_bytes(rand[0:2], "big") & 0x0FFF
    rand_b = int.from_bytes(rand[2:10], "big") & ((1 << 62) - 1)
    value = (ts_ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


def iso(t: datetime) -> str:
    return t.astimezone(IST).isoformat(timespec="milliseconds")


def open_text(path: Path, mode: str = "r"):
    """Open .ndjson or .ndjson.gz as text. Gzip output uses mtime 0 so files stay byte-identical (D-078)."""
    if path.suffix == ".gz":
        raw = gzip.GzipFile(filename="", mode=mode + "b", fileobj=path.open(mode + "b"), mtime=0,
                            compresslevel=6) if mode == "w" else gzip.open(path, "rb")
        return io.TextIOWrapper(raw, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


@dataclass
class Ids:
    ride: int = 1_000_000
    fare_quote: int = 7_000_000
    attempt: int = 500_000

    def next_ride(self) -> str:
        self.ride += 1
        return f"r_{self.ride}"

    def next_fq(self) -> str:
        self.fare_quote += 1
        return f"fq_{self.fare_quote}"

    def next_ba(self) -> str:
        self.attempt += 1
        return f"ba_{self.attempt}"


@dataclass
class Emitter:
    cat: Catalog
    world: World
    out: Path
    cutoff: datetime                       # events at or after this instant (end of history) are dropped
    window_start: date
    ids: Ids = field(default_factory=Ids)
    buffers: dict[str, list] = field(default_factory=dict)
    flushed: set = field(default_factory=set)
    seq: int = 0
    dropped_after_end: int = 0
    events_by_name: dict[str, int] = field(default_factory=dict)
    files: dict[str, int] = field(default_factory=dict)       # relative path -> rows

    # ------------------------------------------------------------------ helpers
    def pseudo_id(self, r: Rider, t: datetime) -> str:
        if r.reinstall_at and t >= r.reinstall_at:
            return hashlib.sha256(f"{r.pseudo_id}-reinstall".encode()).hexdigest()[:32]
        return r.pseudo_id

    def user_properties(self, r: Rider, t: datetime) -> dict[str, str]:
        up = {
            "city": self.world.cities[r.city_id]["city_name"],
            "signup_date": r.signup_ts.date().isoformat(),
            "total_rides": str(r.total_rides),
            "language": r.language,
            "marketing_opt_in_push": "1" if r.consent["push"]["opted_in"] else "0",
            "marketing_opt_in_email": "1" if r.consent["email"]["opted_in"] else "0",
            "marketing_opt_in_sms": "1" if r.consent["sms"]["opted_in"] else "0",
            "marketing_opt_in_wa": "1" if r.consent["whatsapp"]["opted_in"] else "0",
            "is_synthetic": "1",
        }
        if r.last_ride_date:
            up["last_ride_date"] = r.last_ride_date.isoformat()
        return up

    # ------------------------------------------------------------------ emit
    def emit(self, r: Rider, name: str, t: datetime, params: dict, origin: str = "client",
             logged_in: bool = True) -> None:
        """Build one event at true time t. Client events carry the rider's device clock skew."""
        if origin == "client":
            t = t + timedelta(seconds=r.skew_s + float(r.rng.normal(0, 1.5)))
        if t >= self.cutoff:
            self.dropped_after_end += 1
            return
        ts_iso = iso(t)
        ts_ms = int(t.timestamp() * 1000)
        env: dict = {"contract_version": self.cat.event_contract_version,
                     "event_uuid": None if origin == "auto" else uuid7(ts_ms, r.rng.bytes(10)),
                     "event_name": name, "event_ts": ts_iso,
                     "user_id": r.user_id if logged_in else None}
        pseudo = self.pseudo_id(r, t)
        if origin in ("client", "auto") or logged_in:
            env["user_pseudo_id"] = pseudo
        env["platform"] = "SERVER" if origin == "server" else r.platform
        if origin == "client":
            env["app_version"] = self.world.app_version(t.date(), r.upgrade_lag_days, r.signup_ts.date())
        env["city_id"] = r.city_id
        env["origin"] = origin
        env["params"] = {k: v for k, v in params.items() if v is not None}
        if logged_in:
            env["user_properties"] = self.user_properties(r, t)

        row = to_ga4_row({**env, "event_uuid": env["event_uuid"] or ""}, device_platform=r.platform, cat=self.cat)
        r.bundle_seq += 1
        self._enrich(row, r, origin, pseudo, env.get("app_version"))
        if origin == "auto":     # Firebase automatic event: no event_uuid param; engine synthesises UUIDv5 (D-072)
            env["event_uuid"] = auto_event_uuid(pseudo, row["event_timestamp"], name, row["event_bundle_sequence_id"])
        self.seq += 1
        day = row["event_date"]
        if day in self.flushed:
            raise RuntimeError(f"event for already written day {day}: {name} {ts_iso}")
        self.buffers.setdefault(day, []).append((row["event_timestamp"], self.seq, env, row))
        self.events_by_name[name] = self.events_by_name.get(name, 0) + 1

    def _enrich(self, row: dict, r: Rider, origin: str, pseudo: str, app_version: str | None) -> None:
        devices = ANDROID_DEVICES if r.platform == "ANDROID" else IOS_DEVICES
        brand, model, marketing = devices[r.user_num % len(devices)]
        city = self.world.cities[r.city_id]
        late = origin == "client" and r.rng.random() < 0.02          # 2 % arrive late (batched up to 2 h)
        offset_s = float(r.rng.uniform(60, 7200)) if late else float(r.rng.uniform(0.2, 5.0))
        if origin == "client":
            offset_s -= r.skew_s
        row.update({
            "event_previous_timestamp": None,
            "event_value_in_usd": None,
            "event_bundle_sequence_id": r.bundle_seq,
            "event_server_timestamp_offset": int(offset_s * 1_000_000),
            "user_pseudo_id": pseudo,
            "privacy_info": {"analytics_storage": "Yes", "ads_storage": "No", "uses_transient_token": "No"},
            "user_first_touch_timestamp": iso_to_micros(r.install_ts.isoformat()),
            "user_ltv": None,
            "device": {"category": "mobile", "mobile_brand_name": brand, "mobile_model_name": model,
                       "mobile_marketing_name": marketing, "mobile_os_hardware_model": model,
                       "operating_system": "Android" if r.platform == "ANDROID" else "iOS",
                       "operating_system_version": ("Android 14" if r.platform == "ANDROID" else "iOS 18.1"),
                       "vendor_id": None, "advertising_id": None,
                       "language": "hi-in" if r.language == "hi" else "en-in",
                       "is_limited_ad_tracking": "No", "time_zone_offset_seconds": 19800},
            "geo": {"city": city["city_name"], "country": "India", "continent": "Asia",
                    "region": city["state"], "sub_continent": "Southern Asia", "metro": "(not set)"},
            "app_info": {"id": "com.hireme.rider", "version": app_version,
                         "install_store": None,
                         "firebase_app_id": f"1:999999999:{'android' if r.platform == 'ANDROID' else 'ios'}:synthetic",
                         "install_source": "com.android.vending" if r.platform == "ANDROID" else "iTunes"},
            "traffic_source": {"name": "(direct)", "medium": "(none)", "source": "(direct)"},
            "stream_id": "9999999990" if r.platform == "ANDROID" else "9999999991",
            "platform": r.platform,
            "is_active_user": True,
        })

    # ------------------------------------------------------------------ files
    def flush(self, up_to: date | None = None) -> None:
        """Write and drop buffered days <= up_to (all days if None)."""
        for day in sorted(self.buffers):
            if up_to is not None and day > up_to.strftime("%Y%m%d"):
                continue
            rows = sorted(self.buffers.pop(day), key=lambda x: (x[0], x[1]))
            self._write(f"envelopes/events_{day}.ndjson.gz", (env for _, _, env, _ in rows))
            self._write(f"bigquery/analytics_999999999/events_{day}.ndjson.gz", (row for _, _, _, row in rows))
            self.flushed.add(day)

    def _write(self, rel: str, items) -> None:
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open_text(path, "w") as f:
            for item in items:
                f.write(dumps(item))
                f.write("\n")
                n += 1
        self.files[rel] = n
