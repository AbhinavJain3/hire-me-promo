"""Synthetic rider population: personas, latent traits, identity, reachability (DUMMY_DATA_PLAN §4).

Each rider has its own random stream derived from (seed, user number), so a rider's traits and behaviour do not
depend on how many other riders are generated or in which order.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np

from sim.generator.world import IST, World, load_yaml

SCALES = {
    "tiny":   {"riders": 500,    "days": 30},
    "demo":   {"riders": 3000,   "days": 45},   # free-tier default (D-083)
    "small":  {"riders": 2000,   "days": 180},
    "medium": {"riders": 20000,  "days": 180},
    "large":  {"riders": 100000, "days": 180},
}


def load_personas() -> dict:
    """personas.yaml with defaults merged into every persona."""
    raw = load_yaml("personas.yaml")
    merged = {}
    for pid, p in raw["personas"].items():
        merged[pid] = {**raw["defaults"], **p}
    raw["merged"] = merged
    return raw


def draw(rng: np.random.Generator, spec: Any) -> Any:
    if isinstance(spec, list) and len(spec) == 2 and all(isinstance(x, (int, float)) for x in spec):
        return float(rng.uniform(spec[0], spec[1]))
    if isinstance(spec, dict) and "beta" in spec:
        a, b = spec["beta"]
        return float(rng.beta(a, b))
    return spec


def pick(rng: np.random.Generator, weights: dict[str, float]) -> str:
    keys = list(weights)
    w = np.array([weights[k] for k in keys], dtype=float)
    return keys[int(rng.choice(len(keys), p=w / w.sum()))]


def hex_id(rng: np.random.Generator, n: int = 32) -> str:
    return rng.bytes(n // 2).hex()


@dataclass
class Rider:
    idx: int
    user_num: int
    user_id: str
    persona_id: str
    p: dict                          # merged persona config
    traits: dict                     # latent traits (ground truth only)
    rng: np.random.Generator
    city_id: int
    home_zone: str
    work_zone: str
    platform: str                    # ANDROID | IOS
    pseudo_id: str
    signup_ts: datetime
    install_ts: datetime
    language: str
    first_name: str
    phone: str
    phone_dnd: bool
    has_email: bool
    email: str | None
    push_tokens: list[dict]
    consent: dict
    device_id_hash: str
    payment_fingerprints: list[str]
    wallet: float
    birth_month_day: str | None
    referral_code: str
    referred_by: str | None
    skew_s: float
    upgrade_lag_days: float
    active_until: date | None = None             # last ride date for lapsed-band personas
    bad_ride_day: date | None = None
    reinstall_at: datetime | None = None
    uninstall_at: datetime | None = None
    # mutable state during generation
    total_rides: int = 0
    last_ride_date: date | None = None
    welcome_used: bool = False
    busy_until: datetime | None = None
    bundle_seq: int = 0
    pending: list[tuple[datetime, dict]] = field(default_factory=list)
    signup_in_window: bool = False
    removed: bool = False

    @property
    def lifecycle(self) -> str:
        return self.p["lifecycle"]


def persona_counts(personas: dict, n: int) -> dict[str, int]:
    """Largest-remainder allocation; every persona gets at least one rider and the fraud ring at least one device."""
    shares = {pid: p["share"] for pid, p in personas.items()}
    raw = {pid: s * n for pid, s in shares.items()}
    counts = {pid: int(math.floor(v)) for pid, v in raw.items()}
    for pid in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)[: n - sum(counts.values())]:
        counts[pid] += 1
    minimum = {pid: (p.get("accounts_per_device", 1) if p["lifecycle"] == "fraud_ring" else 1)
               for pid, p in personas.items()}
    for pid, m in minimum.items():
        while counts[pid] < m:
            donor = max(counts, key=counts.get)
            counts[donor] -= 1
            counts[pid] += 1
    # the fraud ring fills whole devices, so every ring device carries the full number of accounts
    for pid, p in personas.items():
        if p["lifecycle"] == "fraud_ring":
            k = p["accounts_per_device"]
            while counts[pid] % k:
                donor = max(counts, key=counts.get)
                counts[donor] -= 1
                counts[pid] += 1
    return counts


def _random_time(rng: np.random.Generator, d: date, hour_weights: list[float]) -> datetime:
    w = np.array(hour_weights, dtype=float)
    hour = int(rng.choice(24, p=w / w.sum()))
    return datetime.combine(d, time(hour), IST) + timedelta(seconds=float(rng.uniform(0, 3600)))


def build_population(seed: int, n: int, window_start: date, world: World, cfg: dict) -> list[Rider]:
    personas = cfg["merged"]
    counts = persona_counts(personas, n)
    master = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    assignment = [pid for pid in sorted(counts) for _ in range(counts[pid])]
    master.shuffle(assignment)

    reach = cfg["reachability"]
    ident = cfg["synthetic_identity"]
    hw = cfg["hour_weights"]
    end = world.history_end
    cities = world.geo["cities"]
    city_ids = [c["city_id"] for c in cities]
    city_p = np.array([c["rider_share"] for c in cities], dtype=float)

    # fraud ring: accounts share devices and payment instruments
    fraud_pids = [pid for pid, p in personas.items() if p["lifecycle"] == "fraud_ring"]
    fraud_idx = [i for i, pid in enumerate(assignment) if pid in fraud_pids]
    fraud_device, fraud_payment, fraud_group_start, device_start = {}, {}, {}, {}
    for k, i in enumerate(fraud_idx):
        p = personas[assignment[i]]
        dev = k // p["accounts_per_device"]
        fraud_device[i] = hashlib.sha256(f"fraud-device-{seed}-{dev}".encode()).hexdigest()[:32]
        fraud_payment[i] = f"pf_fr{k // p['accounts_per_payment_instrument']:04d}"
        if dev not in device_start:
            span = max((end - window_start).days - 10, 1)
            device_start[dev] = window_start + timedelta(days=int(master.integers(0, span)))
        fraud_group_start[i] = device_start[dev]

    riders: list[Rider] = []
    for i, pid in enumerate(assignment):
        p = personas[pid]
        user_num = 10000 + i
        rng = np.random.default_rng(np.random.SeedSequence([seed, 1, user_num]))
        traits = {k: draw(rng, p[k]) for k in ("ride_rate_per_week", "price_elasticity", "promo_affinity",
                                                "push_open_rate", "email_open_rate", "churn_hazard",
                                                "service_tolerance", "fare_checks_per_intent")}
        traits["weekend_share"] = draw(rng, p["weekend_share"])
        if "airport_rides_per_90d" in p:
            traits["airport_rides_per_90d"] = draw(rng, p["airport_rides_per_90d"])
        traits["preferred_hour_am"] = float(rng.uniform(7.5, 10.0))
        traits["preferred_hour_pm"] = float(rng.uniform(17.5, 20.5))
        traits["m_user"] = float(np.clip(0.7 + 0.6 * traits["promo_affinity"] * 0.5 + rng.normal(0, 0.1), 0.7, 1.3))
        if p["lifecycle"] == "new_not_activated":
            traits["browsing_rider"] = bool(rng.random() < p["browsing_rider_share"])
            traits["never_ride_without_nudge"] = bool(rng.random() < p["never_ride_without_nudge"])

        city_id = int(city_ids[int(rng.choice(len(city_ids), p=city_p / city_p.sum()))])
        zones = world.zones_by_city[city_id]
        res = [z for z in zones if z.zone_type == "residential"]
        home = res[int(rng.choice(len(res), p=_w(res)))].zone_id
        if rng.random() < 0.2 and city_id in (2, 3):      # cross-city commute into Delhi
            biz = [z for z in world.zones_by_city[1] if z.zone_type == "business"]
        else:
            biz = [z for z in zones if z.zone_type == "business"]
        work = biz[int(rng.choice(len(biz), p=_w(biz)))].zone_id
        lang_hi = world.cities[city_id]["lang_hi_share"]
        language = "hi" if rng.random() < lang_hi else "en"

        # lifecycle dates
        active_until = bad_ride_day = None
        if p["lifecycle"] == "lapsed_band":
            lo, hi = p["last_ride_days_before_end"]
            active_until = end - timedelta(days=int(rng.integers(lo, hi + 1)))
        if "bad_ride_days_before_end" in p:
            lo, hi = p["bad_ride_days_before_end"]
            bad_ride_day = end - timedelta(days=int(rng.integers(lo, hi + 1)))

        if p["lifecycle"] == "new_not_activated":
            lo, hi = p["signup_days_before_end"]
            sd = end - timedelta(days=int(rng.integers(lo, hi + 1)))
        elif p["lifecycle"] == "fraud_ring":
            sd = min(fraud_group_start[i] + timedelta(days=int(rng.integers(0, 3))), end)
        else:
            latest = end - timedelta(days=7)
            if active_until:
                latest = min(latest, active_until - timedelta(days=30))
            earliest = date.fromisoformat(p["signup_earliest"])
            if rng.random() < p["signup_within_history_share"] and latest >= window_start:
                sd = window_start + timedelta(days=int(rng.integers(0, (latest - window_start).days + 1)))
            else:
                hi_d = min(window_start - timedelta(days=1), latest)
                sd = earliest + timedelta(days=int(rng.integers(0, max((hi_d - earliest).days, 1))))
        signup_ts = _random_time(rng, sd, hw["weekday"])
        install_ts = signup_ts - timedelta(minutes=float(rng.uniform(1, 120)))

        platform = "ANDROID" if rng.random() < reach["platform_android"] else "IOS"
        first = ident["first_names"][int(rng.integers(len(ident["first_names"])))]
        has_email = bool(rng.random() < reach["has_email"])
        email = f"{first.lower()}.{user_num}@{ident['email_domain']}" if has_email else None
        ts_iso = signup_ts.isoformat(timespec="seconds")

        def entry(opted: bool) -> dict:
            return {"opted_in": opted, "updated_at": ts_iso if opted else None, "source": "signup" if opted else None}
        consent = {
            "push": entry(bool(rng.random() < reach["consent_push"])),
            "email": entry(has_email and bool(rng.random() < reach["consent_email"] / reach["has_email"])),
            "sms": entry(bool(rng.random() < reach["consent_sms"])),
            "whatsapp": entry(bool(rng.random() < reach["consent_whatsapp"])),
        }
        tokens = []
        if rng.random() < reach["push_token_present"]:
            tokens.append({"token": f"fcm_tok_synthetic_{user_num}", "platform": platform,
                           "updated_at": ts_iso, "stale": bool(rng.random() < reach["push_token_stale"])})
        if i in fraud_device:
            device_hash, fps = fraud_device[i], [fraud_payment[i]]
        else:
            device_hash = hashlib.sha256(f"device-{seed}-{user_num}".encode()).hexdigest()[:32]
            fps = [f"pf_{hex_id(rng, 6)}" for _ in range(int(rng.integers(1, 3)))]
        wallet_share = p["payment_mix"].get("wallet", 0)
        wallet = float(round(rng.uniform(0, 300))) if rng.random() < wallet_share * 2 else 0.0
        referred_by = None
        if i > 0 and rng.random() < reach["referred_by_share"]:
            referred_by = f"u_{10000 + int(rng.integers(0, i))}"

        r = Rider(
            idx=i, user_num=user_num, user_id=f"u_{user_num}", persona_id=pid, p=p, traits=traits, rng=rng,
            city_id=city_id, home_zone=home, work_zone=work, platform=platform, pseudo_id=hex_id(rng),
            signup_ts=signup_ts, install_ts=install_ts, language=language, first_name=first,
            phone=f"{ident['phone_prefix']}{i + 10000:06d}", phone_dnd=bool(rng.random() < reach["phone_dnd"]),
            has_email=has_email, email=email, push_tokens=tokens, consent=consent,
            device_id_hash=device_hash, payment_fingerprints=fps, wallet=wallet,
            birth_month_day=(f"{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 29)):02d}"
                             if rng.random() < reach["birth_month_day_present"] else None),
            referral_code=f"{first[:6].upper()}{user_num % 100:02d}",
            referred_by=referred_by,
            skew_s=float(np.clip(rng.normal(0, 12), -30, 30)),
            upgrade_lag_days=float(rng.exponential(world.cal["upgrade_lag_mean_days"])),
            active_until=active_until, bad_ride_day=bad_ride_day,
        )
        r.signup_in_window = signup_ts.date() >= window_start
        if rng.random() < 0.03:     # reinstall: new Firebase app instance id (DUMMY_DATA_PLAN §7)
            span = max((end - window_start).days, 1)
            r.reinstall_at = datetime.combine(window_start, time(0), IST) + timedelta(days=float(rng.uniform(0, span)))
        if p.get("uninstall_prob") and platform == "ANDROID" and active_until and rng.random() < p["uninstall_prob"]:
            r.uninstall_at = (datetime.combine(active_until, time(0), IST)
                              + timedelta(days=float(rng.uniform(14, 60)), seconds=float(rng.uniform(0, 86400))))
        _pre_window_state(r, window_start)
        riders.append(r)
    return riders


def _w(zones) -> np.ndarray:
    w = np.array([z.base_demand_weight for z in zones], dtype=float)
    return w / w.sum()


def expected_book_rate(p: dict) -> float:
    """Expected share of trip intents that end in a ride (used for pre-window ride counts)."""
    walk = p["browse_prob"] + p["abandon_prob"]
    later = p["quick_rebook_prob"] + (1 - p["quick_rebook_prob"]) * (p["p0_after_abandon"] + p["p0_after_browse"]) / 2
    return (1 - walk) + walk * later


def _pre_window_state(r: Rider, window_start: date) -> None:
    """Rides before the generated window are not emitted as events, but they exist in the rider's history:
    carry them in total_rides / last_ride_date (user properties) so the engine sees a consistent rider."""
    if r.lifecycle in ("new_not_activated", "fraud_ring") or r.signup_in_window:
        return
    signup = r.signup_ts.date()
    stop = window_start - timedelta(days=1)
    if r.active_until and r.active_until < window_start:
        stop = r.active_until
    weeks = max((stop - signup).days, 0) / 7
    rate = r.traits["ride_rate_per_week"] * expected_book_rate(r.p)
    if r.p.get("commute"):
        rate = r.traits["ride_rate_per_week"] * 0.85
    r.total_rides = int(r.rng.poisson(rate * weeks)) if weeks > 0 else 0
    if r.total_rides > 0:
        if r.active_until and r.active_until < window_start:
            r.last_ride_date = r.active_until
            return
        gap = int(min(r.rng.exponential(7 / max(rate, 0.05)), (stop - signup).days))
        r.last_ride_date = stop - timedelta(days=gap)
    elif r.active_until and r.active_until < window_start:
        r.total_rides, r.last_ride_date = 1, r.active_until


def rider_profile(r: Rider) -> dict:
    """Firestore hireme_riders document = RiderProfile (contracts/openapi/rider-api.v1.yaml, D-074)."""
    return {
        "user_id": r.user_id, "city_id": r.city_id, "first_name": r.first_name, "language": r.language,
        "signup_ts": r.signup_ts.isoformat(timespec="seconds"),
        "contact": {"phone_e164": r.phone, "email": r.email, "phone_dnd": r.phone_dnd,
                    "email_verified": bool(r.has_email)},
        "push_tokens": [dict(t) for t in r.push_tokens],
        "consent": {k: dict(v) for k, v in r.consent.items()},
        "wallet_balance_inr": float(round(r.wallet, 2)),
        "device_id_hash": r.device_id_hash,
        "payment_fingerprints": list(r.payment_fingerprints),
        "birth_month_day": r.birth_month_day,
        "referral": {"code": r.referral_code, "referred_by_user_id": r.referred_by},
        "status": "active",
        "is_synthetic": True,
    }


def riders_snapshot_row(r: Rider, snapshot_date: date) -> dict:
    """hireme_backend_stub.riders_snapshot: PII-free columns only."""
    return {
        "snapshot_date": snapshot_date.isoformat(), "user_id": r.user_id, "city_id": r.city_id,
        "signup_ts": r.signup_ts.isoformat(timespec="seconds"), "language": r.language,
        "has_email": r.has_email, "has_push_token": bool(r.push_tokens),
        "push_platform": r.push_tokens[0]["platform"] if r.push_tokens else None,
        "consent_push": r.consent["push"]["opted_in"], "consent_email": r.consent["email"]["opted_in"],
        "consent_sms": r.consent["sms"]["opted_in"], "consent_whatsapp": r.consent["whatsapp"]["opted_in"],
        "wallet_balance_inr": float(round(r.wallet, 2)), "device_id_hash": r.device_id_hash,
        "payment_fingerprints": list(r.payment_fingerprints),
        "referral_code_used": None, "referred_by_user_id": r.referred_by,
        "birth_month_day": r.birth_month_day, "is_synthetic": True,
    }


def persona_truth_row(r: Rider, generation_id: str) -> dict:
    """engage_sim.personas (ground truth; never readable by the engine, D-012)."""
    latent = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.traits.items()}
    latent.update({"home_zone": r.home_zone, "work_zone": r.work_zone, "language": r.language,
                   "active_until": r.active_until.isoformat() if r.active_until else None,
                   "bad_ride_day": r.bad_ride_day.isoformat() if r.bad_ride_day else None})
    return {"user_id": r.user_id, "persona_id": r.persona_id, "generation_id": generation_id, "latent": latent}
