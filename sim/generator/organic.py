"""Organic rider behaviour, day by day (DUMMY_DATA_PLAN §7.3): trip intents -> sessions -> funnel -> rides.

No engine messages exist in the history (the engine did not exist yet). Later bookings after an abandon or a
fare-check-only session happen with the ground-truth p0 of that context, so history and live run agree.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np

from sim.generator.emit import Emitter, dumps, iso
from sim.generator.population import Rider, pick
from sim.generator.world import IST, World

ABANDON_STEPS = {"fare": 0.15, "vehicle": 0.25, "payment": 0.20, "confirm": 0.40}
PAYMENT_ERRORS = {"card": ["CARD_DECLINED", "INSUFFICIENT_FUNDS", "BANK_TIMEOUT"],
                  "upi": ["UPI_TIMEOUT", "UPI_DECLINED", "INSUFFICIENT_FUNDS"]}
LANDMARKS = ["Gate 1", "Gate 2", "Main Gate", "Tower A", "Tower B", "Block C"]


def secs(x: float) -> timedelta:
    return timedelta(seconds=float(x))


@dataclass
class Trip:
    pickup: str
    drop: str
    vehicle: str
    km: float
    minutes: float
    surge: float
    fare: float
    payment: str
    fq: str | None = None
    ba: str | None = None
    promo: dict | None = None
    bad: bool = False
    sure: bool = False            # forced ride that must complete (last ride of a lapsed rider)


@dataclass
class Behaviour:
    world: World
    em: Emitter
    cfg: dict
    riders: list[Rider]
    window_start: date
    rides_file: object
    redemptions_file: object
    open_scheduled: list = field(default_factory=list)
    rides_by_status: dict = field(default_factory=dict)

    def __post_init__(self):
        self.ride_cfg = self.cfg["ride"]
        self.promos = {p["code"]: p for p in self.cfg["historical_promos"]}
        self.hw = self.cfg["hour_weights"]
        self.end = self.world.history_end
        self.all_zones = list(self.world.zones.values())
        self._dest_cache: dict = {}

    # ================================================================== day loop
    def run_day(self, r: Rider, d: date) -> None:
        if d < r.signup_ts.date() or r.removed:
            return
        if r.signup_in_window and d == r.signup_ts.date():
            self.signup_session(r)
        queue = self.plan_intents(r, d)
        queue += self._take_pending(r, d)
        while queue:
            queue.sort(key=lambda x: x[0])
            t, spec = queue.pop(0)
            if t <= r.signup_ts or (r.uninstall_at and t >= r.uninstall_at):
                continue
            if r.lifecycle == "lapsed_band" and spec.get("mode") != "idle" and t.date() > r.active_until:
                continue
            if r.busy_until and t < r.busy_until:
                t = r.busy_until + secs(r.rng.uniform(300, 1800))
                if t.date() != d:
                    r.pending.append((t, spec))
                    continue
            self.run_spec(r, t, spec)
            queue += self._take_pending(r, d)
        self._consent_drift(r, d)
        if r.uninstall_at and r.uninstall_at.date() == d:
            self.em.emit(r, "app_remove", r.uninstall_at, {}, origin="auto")
            r.removed = True

    def _take_pending(self, r: Rider, d: date) -> list:
        today = [(t, s) for t, s in r.pending if t.date() <= d]
        r.pending = [(t, s) for t, s in r.pending if t.date() > d]
        return [(max(t, datetime.combine(d, time(0), IST)), s) for t, s in today]

    def plan_intents(self, r: Rider, d: date) -> list:
        rng, p, tr = r.rng, r.p, r.traits
        lc = r.lifecycle
        out: list = []
        mult = self.world.demand_multiplier(d)
        weekend = d.weekday() >= 5
        hours = self.hw["weekend"] if weekend else self.hw["weekday"]

        idle = rng.poisson(p["idle_app_opens_per_week"] / 7)
        for _ in range(idle):
            out.append((self._time(rng, d, hours), {"mode": "idle"}))
        if lc == "fraud_ring":
            return out
        if lc == "lapsed_band" and d > r.active_until:
            return out
        if lc == "lapsed_band" and d == r.active_until:
            out.append((self._time(rng, d, hours), {"mode": "book", "sure": True, **self._route(r)}))
        if r.bad_ride_day == d:
            out.append((self._time(rng, d, hours), {"mode": "book", "bad": True, **self._route(r)}))

        if lc == "new_not_activated":
            if tr.get("browsing_rider"):
                for _ in range(rng.poisson(tr["ride_rate_per_week"] / 7 * mult)):
                    out.append((self._time(rng, d, hours), {"mode": "no_book", **self._route(r)}))
            return out

        rate = tr["ride_rate_per_week"]
        if p.get("commute"):
            is_holiday = self.world.day_kind(d) == "holiday"
            if not weekend and not is_holiday:
                if rng.random() < 0.92:
                    out.append((self._at_hour(rng, d, tr["preferred_hour_am"]),
                                {"mode": "normal", "pickup": r.home_zone, "drop": r.work_zone}))
                if rng.random() < 0.92:
                    out.append((self._at_hour(rng, d, tr["preferred_hour_pm"]),
                                {"mode": "normal", "pickup": r.work_zone, "drop": r.home_zone}))
            elif weekend:
                for _ in range(rng.poisson(rate * (tr["weekend_share"] or 0.05) / 2 * mult)):
                    out.append((self._time(rng, d, hours), {"mode": "normal", **self._route(r)}))
            return out

        ws = tr.get("weekend_share")
        if ws is None:
            per_day = rate / 7
        elif d.weekday() >= 4:        # Fri-Sun
            per_day = rate * ws / 3
        else:
            per_day = rate * (1 - ws) / 4
        for _ in range(rng.poisson(per_day * mult)):
            out.append((self._time(rng, d, hours), {"mode": "normal", **self._route(r)}))
        if "airport_rides_per_90d" in tr and rng.random() < tr["airport_rides_per_90d"] / 90:
            out.append((self._at_hour(rng, d, float(rng.uniform(19, 23))), {"mode": "airport"}))
        return out

    def _time(self, rng, d: date, hours: list[float]) -> datetime:
        w = np.array(hours, dtype=float)
        h = int(rng.choice(24, p=w / w.sum()))
        return datetime.combine(d, time(h), IST) + secs(rng.uniform(0, 3600))

    def _at_hour(self, rng, d: date, hour: float) -> datetime:
        h = min(max(hour + rng.normal(0, 0.4), 0.0), 23.9)
        return datetime.combine(d, time(0), IST) + timedelta(hours=float(h))

    def _route(self, r: Rider) -> dict:
        rng = r.rng
        u = rng.random()
        origin = r.home_zone if u < 0.55 else (r.work_zone if u > 0.85 else None)
        if origin is None:      # returning home from somewhere
            return {"pickup": self._dest(r, r.home_zone), "drop": r.home_zone}
        return {"pickup": origin, "drop": self._dest(r, origin)}

    def _dest(self, r: Rider, frm: str) -> str:
        key = (r.persona_id, frm)
        cum = self._dest_cache.get(key)
        if cum is None:
            tw = r.p["dest_type_weights"]
            w = []
            for z in self.all_zones:
                km = self.world.distance_km(frm, z.zone_id, 0.5)
                wt = tw.get(z.zone_type, 0.3) * z.base_demand_weight * math.exp(-km / 14)
                w.append(wt * (0.3 if z.zone_id == frm else 1.0))
            cum = np.cumsum(w) / sum(w)
            self._dest_cache[key] = cum
        i = min(int(np.searchsorted(cum, r.rng.random(), side="right")), len(cum) - 1)
        return self.all_zones[i].zone_id

    def run_spec(self, r: Rider, t: datetime, spec: dict) -> None:
        mode = spec["mode"]
        if mode == "idle":
            self.app_open(r, t)
        elif mode == "airport":
            self.airport_booking(r, t)
        else:
            self.session(r, t, spec["pickup"], spec["drop"], mode, bad=spec.get("bad", False),
                         promo=self.promos.get(spec["promo"]) if spec.get("promo") else None,
                         quick=spec.get("quick", False), sure=spec.get("sure", False))

    # ================================================================== onboarding
    def signup_session(self, r: Rider) -> None:
        rng = r.rng
        t = r.install_ts + secs(rng.uniform(5, 60))
        method = pick(rng, {"phone": 0.8, "google": 0.15 if r.platform == "ANDROID" else 0.05,
                            "apple": 0.0 if r.platform == "ANDROID" else 0.15})
        self.em.emit(r, "app_open", t, {"source": "organic", "app_version": self._app_version(r, t)},
                     logged_in=False)
        self.em.emit(r, "sign_up_started", t + secs(rng.uniform(10, 90)), {"method": method}, logged_in=False)
        referral = None
        if r.referred_by:
            ref = self.riders[int(r.referred_by[2:]) - 10000]
            referral = ref.referral_code
        self.em.emit(r, "sign_up", r.signup_ts, {"method": method, "referral_code": referral,
                                                 "city": self.world.cities[r.city_id]["city_name"],
                                                 "device_id_hash": r.device_id_hash})
        t = r.signup_ts + secs(rng.uniform(5, 40))
        granted = rng.random() < 0.85
        self.em.emit(r, "location_permission", t, {"status": "granted" if granted else "denied",
                                                   "precision": ("precise" if rng.random() < 0.8 else "approximate")
                                                   if granted else None})
        if rng.random() < 0.6:
            self.em.emit(r, "profile_completed", t + secs(rng.uniform(30, 600)), {"has_email": r.has_email})
        if r.lifecycle == "fraud_ring":
            if rng.random() < 0.9:
                r.pending.append((r.signup_ts + timedelta(hours=float(rng.uniform(1, 72))),
                                  {"mode": "book", "promo": "WELCOME50", **self._route(r)}))
            lo, hi = r.p["full_fare_rides"]
            for _ in range(int(rng.integers(lo, hi + 1))):
                r.pending.append((r.signup_ts + timedelta(days=float(rng.uniform(3, 30))),
                                  {"mode": "book", **self._route(r)}))

    def app_open(self, r: Rider, t: datetime) -> datetime:
        src = pick(r.rng, {"organic": 0.90, "push": 0.05, "deeplink": 0.03, "email": 0.01, "sms": 0.01})
        self.em.emit(r, "app_open", t, {"source": src, "app_version": self._app_version(r, t)})
        if r.rng.random() < self.ride_cfg["referral_share_prob"]:
            self.em.emit(r, "referral_shared", t + secs(r.rng.uniform(5, 60)),
                         {"channel": pick(r.rng, {"whatsapp": 0.7, "sms": 0.1, "copy_link": 0.15, "other": 0.05})})
        return t

    def _app_version(self, r: Rider, t: datetime) -> str:
        return self.world.app_version(t.date(), r.upgrade_lag_days, r.signup_ts.date())

    def _consent_drift(self, r: Rider, d: date) -> None:
        rng = r.rng
        if rng.random() >= self.cfg["reachability"]["monthly_optout_prob"] / 30:
            return
        opted = [c for c, e in r.consent.items() if e["opted_in"]]
        if not opted:
            return
        ch = opted[int(rng.integers(len(opted)))]
        t = self._time(rng, d, self.hw["weekday"])
        if r.busy_until and t < r.busy_until:
            t = r.busy_until + secs(60)
        if t <= r.signup_ts or t.date() != d:
            return
        r.consent[ch] = {"opted_in": False, "updated_at": t.isoformat(timespec="seconds"), "source": "app_settings"}
        self.em.emit(r, "consent_changed", t, {"channel": ch, "opted_in": False, "change_source": "app_settings"},
                     origin="server")

    # ================================================================== booking funnel
    def session(self, r: Rider, t: datetime, pickup: str, drop: str, mode: str, bad: bool = False,
                promo: dict | None = None, quick: bool = False, sure: bool = False) -> None:
        rng, p, tr = r.rng, r.p, r.traits
        if not quick:
            self.app_open(r, t)
        vehicle = pick(rng, p["vehicle_mix"])
        surge = self.world.surge(pickup, t)
        km = self.world.distance_km(pickup, drop, rng.random())
        mins = self.world.minutes(km, t)
        drop_name = self.world.zones[drop].zone_name
        n_fc = 1 if quick else 1 + int(rng.poisson(max(tr["fare_checks_per_intent"] - 1, 0)))
        trip = None
        for k in range(n_fc):
            t += secs(rng.uniform(8, 60))
            v = vehicle if k == 0 or rng.random() < 0.6 else pick(rng, p["vehicle_mix"])
            trip = Trip(pickup, drop, v, km, mins, surge, self.world.fare(v, km, mins, surge),
                        pick(rng, p["payment_mix"]), fq=self.em.ids.next_fq())
            self.em.emit(r, "fare_check", t, {
                "pickup_zone": pickup, "drop_zone": drop, "distance_km": km, "fare_estimate": trip.fare,
                "vehicle_type": v, "surge_multiplier": surge, "fare_quote_id": trip.fq,
                "drop_area_name": drop_name, "pickup_area_name": self.world.zones[pickup].zone_name})
        assert trip is not None
        trip.bad, trip.sure = bad, sure

        if mode == "book":
            outcome = "book"
        elif mode == "no_book":
            outcome = "abandon" if rng.random() < 0.5 else "browse"
        else:
            b, a = p["browse_prob"], p["abandon_prob"]
            if surge > 1.2:
                b, a = b * (1 + tr["price_elasticity"]), a * (1 + tr["price_elasticity"])
            u = rng.random()
            outcome = "browse" if u < b else ("abandon" if u < b + a else "book")

        if outcome == "browse":
            r.busy_until = t + secs(rng.uniform(30, 120))
            self.follow_up(r, t, trip, "browse", mode)
            return
        if outcome == "abandon":
            step = pick(rng, ABANDON_STEPS)
            if step in ("payment", "confirm"):
                t += secs(rng.uniform(5, 30))
                self.em.emit(r, "vehicle_selected", t, {"vehicle_type": trip.vehicle, "fare_estimate": trip.fare,
                                                        "fare_quote_id": trip.fq})
                t += secs(rng.uniform(5, 40))
                trip.ba = self.em.ids.next_ba()
                self._booking_started(r, t, trip)
            t += secs(rng.uniform(10, 90))
            self.em.emit(r, "booking_abandoned", t, {
                "step": step, "fare_estimate": trip.fare, "vehicle_type": trip.vehicle,
                "payment_method": trip.payment if step in ("payment", "confirm") else None,
                "pickup_zone": pickup, "drop_zone": drop, "drop_area_name": drop_name,
                "fare_quote_id": trip.fq, "booking_attempt_id": trip.ba})
            r.busy_until = t + secs(rng.uniform(30, 120))
            self.follow_up(r, t, trip, "abandon", mode)
            return

        # book
        if rng.random() < 0.6:
            t += secs(rng.uniform(5, 30))
            self.em.emit(r, "vehicle_selected", t, {"vehicle_type": trip.vehicle, "fare_estimate": trip.fare,
                                                    "fare_quote_id": trip.fq})
        trip.promo = promo or self.choose_promo(r)
        if trip.promo:
            t += secs(rng.uniform(5, 30))
            pv = {"promo_code": trip.promo["code"], "campaign_id": trip.promo["campaign_id"]}
            if rng.random() < self.ride_cfg["promo_viewed_prob"]:
                self.em.emit(r, "promo_viewed", t, pv)
                t += secs(rng.uniform(3, 20))
            self.em.emit(r, "promo_applied", t, pv)
        t += secs(rng.uniform(5, 40))
        trip.ba = self.em.ids.next_ba()
        self._booking_started(r, t, trip)
        self.ride(r, t + secs(rng.uniform(1, 3)), trip)

    def _booking_started(self, r: Rider, t: datetime, trip: Trip) -> None:
        if trip.payment == "wallet" and r.wallet < trip.fare:
            need = trip.fare * 3 - r.wallet
            amount = next((a for a in (500.0, 1000.0, 2000.0, 5000.0) if a >= need),
                          float(math.ceil((trip.fare - r.wallet) / 500) * 500))
            r.wallet += amount
            self.em.emit(r, "wallet_topup", t - secs(r.rng.uniform(20, 60)),
                         {"amount": amount, "balance_after": float(round(r.wallet, 2))}, origin="server")
        self.em.emit(r, "booking_started", t, {"vehicle_type": trip.vehicle, "payment_method": trip.payment,
                                               "fare_estimate": trip.fare, "fare_quote_id": trip.fq,
                                               "booking_attempt_id": trip.ba})

    def follow_up(self, r: Rider, t: datetime, trip: Trip, kind: str, mode: str) -> None:
        """After an abandon or a browse: quick self-rebook (cancels a B2 timer), later booking with p0, or nothing."""
        if mode == "no_book":
            return
        rng, p = r.rng, r.p
        if rng.random() < p["quick_rebook_prob"]:
            r.pending.append((t + secs(rng.uniform(60, 600)),
                              {"mode": "book", "pickup": trip.pickup, "drop": trip.drop, "quick": True}))
            return
        p0 = p["p0_after_abandon"] if kind == "abandon" else p["p0_after_browse"]
        if rng.random() < p0:
            delay_h = float(np.clip(rng.lognormal(math.log(2.0), 1.0), 1 / 6, 24))
            delay_h = max(delay_h, p.get("rebook_delay_min_hours", 0))
            r.pending.append((t + timedelta(hours=delay_h),
                              {"mode": "book", "pickup": trip.pickup, "drop": trip.drop}))

    def choose_promo(self, r: Rider) -> dict | None:
        rng = r.rng
        if r.lifecycle == "fraud_ring":
            return None
        if r.signup_in_window and not r.welcome_used and r.total_rides == 0 \
                and rng.random() < self.cfg["welcome_offer_use_prob"]:
            return self.promos["WELCOME50"]
        if rng.random() < r.p["promo_ride_share"]:
            return self.promos["SAVE20"] if rng.random() < 0.6 else self.promos["RIDE30"]
        return None

    # ================================================================== scheduled airport rides (P04)
    def airport_booking(self, r: Rider, t: datetime) -> None:
        rng = r.rng
        airport = "DEL-IGI-T3" if rng.random() < 0.7 else "DEL-IGI-T1"
        days_ahead = int(rng.integers(1, 4))
        sched = datetime.combine(t.date() + timedelta(days=days_ahead), time(0), IST) \
            + timedelta(hours=float(rng.uniform(4.5, 7.5)))
        self.app_open(r, t)
        vehicle = pick(rng, r.p["vehicle_mix"])
        km = self.world.distance_km(r.home_zone, airport, 0.5)
        mins = self.world.minutes(km, sched)
        trip = Trip(r.home_zone, airport, vehicle, km, mins, 1.0, self.world.fare(vehicle, km, mins, 1.0),
                    pick(rng, r.p["payment_mix"]), fq=self.em.ids.next_fq())
        t += secs(rng.uniform(10, 60))
        self.em.emit(r, "fare_check", t, {
            "pickup_zone": trip.pickup, "drop_zone": airport, "distance_km": km, "fare_estimate": trip.fare,
            "vehicle_type": vehicle, "surge_multiplier": 1.0, "fare_quote_id": trip.fq,
            "drop_area_name": self.world.zones[airport].zone_name,
            "pickup_area_name": self.world.zones[trip.pickup].zone_name})
        t += secs(rng.uniform(5, 30))
        self.em.emit(r, "vehicle_selected", t, {"vehicle_type": vehicle, "fare_estimate": trip.fare,
                                                "fare_quote_id": trip.fq})
        trip.ba = self.em.ids.next_ba()
        t += secs(rng.uniform(5, 40))
        self._booking_started(r, t, trip)
        booked = t + secs(rng.uniform(1, 3))
        ride_id = self.em.ids.next_ride()
        self._ride_booked(r, booked, trip, ride_id, scheduled=True)
        landmark = LANDMARKS[int(rng.integers(len(LANDMARKS)))] if rng.random() < 0.5 else None
        self.em.emit(r, "ride_scheduled", booked + secs(1), {
            "ride_id": ride_id, "scheduled_time": sched.isoformat(timespec="seconds"),
            "pickup_zone": trip.pickup, "drop_zone": airport,
            "drop_area_name": self.world.zones[airport].zone_name, "pickup_landmark": landmark}, origin="server")
        r.busy_until = booked + secs(60)
        if rng.random() < r.p["scheduled_ride_cancel_prob"]:
            hours_before = float(round(rng.uniform(1, (sched - booked).total_seconds() / 3600), 1))
            ct = sched - timedelta(hours=hours_before)
            self.em.emit(r, "scheduled_ride_cancelled", ct, {"ride_id": ride_id, "hours_before": hours_before},
                         origin="server")
            self._ride_row(r, ride_id, trip, "cancelled", booked, None, None, scheduled=sched, final_at=ct)
            return
        if sched >= self.em.cutoff:
            self.open_scheduled.append({"ride_id": ride_id, "user_id": r.user_id, "scheduled_time": iso(sched),
                                        "pickup_zone": trip.pickup, "drop_zone": airport,
                                        "vehicle_type": vehicle, "fare_estimate": trip.fare})
            return
        self._lifecycle(r, sched - timedelta(minutes=10), trip, ride_id, booked, scheduled=sched)
        r.pending.append((sched + timedelta(days=float(rng.uniform(2, 7))),
                          {"mode": "book", "pickup": airport, "drop": r.home_zone}))

    # ================================================================== ride lifecycle
    def _ride_booked(self, r: Rider, t: datetime, trip: Trip, ride_id: str, scheduled: bool = False) -> None:
        self.em.emit(r, "ride_booked", t, {
            "ride_id": ride_id, "fare_estimate": trip.fare,
            "promo_code": trip.promo["code"] if trip.promo else None, "is_scheduled": scheduled,
            "vehicle_type": trip.vehicle, "payment_method": trip.payment, "pickup_zone": trip.pickup,
            "drop_zone": trip.drop, "fare_quote_id": trip.fq, "booking_attempt_id": trip.ba}, origin="server")

    def ride(self, r: Rider, booked: datetime, trip: Trip, retry: int = 0) -> None:
        ride_id = self.em.ids.next_ride()
        self._ride_booked(r, booked, trip, ride_id)
        self._lifecycle(r, booked, trip, ride_id, booked, retry=retry)

    def _rebook(self, r: Rider, t: datetime, trip: Trip, retry: int) -> None:
        trip = Trip(**{**trip.__dict__, "ba": self.em.ids.next_ba(), "bad": False})
        self._booking_started(r, t, trip)
        self.ride(r, t + secs(r.rng.uniform(1, 3)), trip, retry=retry + 1)

    def _lifecycle(self, r: Rider, t0: datetime, trip: Trip, ride_id: str, booked: datetime,
                   scheduled: datetime | None = None, retry: int = 0) -> None:
        rng, rc = r.rng, self.ride_cfg
        peak_biz = self.world.is_peak(t0, trip.pickup)
        if not (trip.bad or trip.sure) and rng.random() < rc["no_driver_base"] * (2 if peak_biz else 1):
            wait = int(rng.uniform(180, 300))
            t = t0 + secs(wait)
            self.em.emit(r, "no_driver_found", t, {"pickup_zone": trip.pickup, "wait_seconds": wait,
                                                   "vehicle_type": trip.vehicle,
                                                   "booking_attempt_id": trip.ba or self.em.ids.next_ba()},
                         origin="server")
            self._ride_row(r, ride_id, trip, "no_driver", booked, None, None, scheduled=scheduled, final_at=t)
            r.busy_until = t
            if retry < 2 and rng.random() < rc["no_driver_retry_prob"]:
                self._rebook(r, t + secs(rng.uniform(30, 90)), trip, retry)
            return

        wait = float(rng.lognormal(math.log(rc["pickup_wait_median_s"]), rc["pickup_wait_sigma"]))
        bad_kind = None
        if trip.bad:
            bad_kind = "driver_cancel" if rng.random() < 0.4 else "long_wait"
            if bad_kind == "long_wait":
                wait = float(rng.uniform(700, 1300))
        wait_i = int(wait)
        if bad_kind == "driver_cancel" or (not (trip.bad or trip.sure) and rng.random() < rc["driver_cancel_prob"]):
            ct = t0 + secs(rng.uniform(60, max(min(wait, 900), 61)))
            waited = int((ct - t0).total_seconds())
            self.em.emit(r, "ride_cancelled", ct, {"ride_id": ride_id, "cancelled_by": "driver",
                                                   "reason": "driver_far" if rng.random() < 0.6 else "other",
                                                   "wait_seconds": waited}, origin="server")
            self._ride_row(r, ride_id, trip, "cancelled", booked, None, None, scheduled=scheduled, final_at=ct)
            r.busy_until = ct
            if trip.bad and rng.random() < 0.5:
                self.em.emit(r, "support_ticket_opened", ct + timedelta(minutes=float(rng.uniform(5, 120))),
                             {"category": "driver_behaviour", "ride_id": ride_id}, origin="server")
            if retry < 2 and rng.random() < rc["driver_cancel_rebook_prob"]:
                self._rebook(r, ct + secs(rng.uniform(20, 120)), trip, retry)
            return
        if not (trip.bad or trip.sure) and rng.random() < rc["rider_cancel_prob"]:
            reason = "wait_too_long" if wait > rc["long_wait_s"] else pick(rng, {"changed_plans": 0.6, "price": 0.2,
                                                                                 "driver_far": 0.1, "other": 0.1})
            ct = t0 + secs(rng.uniform(30, max(wait, 31)))
            self.em.emit(r, "ride_cancelled", ct, {"ride_id": ride_id, "cancelled_by": "rider", "reason": reason,
                                                   "wait_seconds": int((ct - t0).total_seconds())}, origin="server")
            self._ride_row(r, ride_id, trip, "cancelled", booked, None, None, scheduled=scheduled, final_at=ct)
            r.busy_until = ct
            return

        started = (scheduled or t0) + secs(wait_i if scheduled is None else rng.uniform(-120, 300))
        self.em.emit(r, "ride_started", started, {"ride_id": ride_id}, origin="server")
        done = started + timedelta(minutes=trip.minutes * float(rng.uniform(0.9, 1.2)))
        gross = float(round(trip.fare * float(rng.uniform(0.97, 1.08)) * 2) / 2)
        discount = 0.0
        if trip.promo:
            pr = trip.promo
            discount = float(pr["value"]) if pr["kind"] == "flat" else min(gross * pr["value"] / 100,
                                                                          float(pr.get("max_discount", 1e9)))
            discount = float(round(min(discount, gross), 1))
        final = float(round(gross - discount, 1))
        pay = trip.payment
        if pay in PAYMENT_ERRORS and rng.random() < rc["payment_failed_prob"]:
            errs = PAYMENT_ERRORS[pay]
            self.em.emit(r, "payment_failed", done, {"ride_id": ride_id, "method": pay,
                                                     "error_code": errs[int(rng.integers(len(errs)))],
                                                     "amount_inr": final}, origin="server")
            done += secs(rng.uniform(60, 300))
            pay = "upi" if rng.random() < 0.5 else "cash"
        if pay == "wallet":
            r.wallet = max(r.wallet - final, 0.0)
        r.total_rides += 1
        r.last_ride_date = done.astimezone(IST).date()
        self.em.emit(r, "ride_completed", done, {
            "ride_id": ride_id, "final_fare": final, "distance_km": trip.km, "payment_method": pay,
            "promo_used": bool(trip.promo), "promo_code": trip.promo["code"] if trip.promo else None,
            "discount_inr": discount if trip.promo else None, "gross_fare": gross, "vehicle_type": trip.vehicle,
            "pickup_zone": trip.pickup, "drop_zone": trip.drop}, origin="server")
        if trip.promo:
            rt = done + secs(rng.uniform(2, 20))
            self.em.emit(r, "promo_redeemed", rt, {"promo_id": trip.promo["promo_id"], "promo_code": trip.promo["code"],
                                                   "ride_id": ride_id, "discount_inr": discount}, origin="server")
            if trip.promo["code"] == "WELCOME50":
                r.welcome_used = True
            if rt < self.em.cutoff:
                self.redemptions_file.write(dumps({"promo_id": trip.promo["promo_id"], "code": trip.promo["code"],
                                                   "user_id": r.user_id, "ride_id": ride_id,
                                                   "redeemed_ts": iso(rt), "discount_inr": discount}) + "\n")
        rating = None
        if rng.random() < (0.9 if trip.bad else rc["rating_prob"]):
            if trip.bad:
                rating = int(rng.integers(1, 3))
            else:
                w = {int(k): v for k, v in rc["rating_weights"].items()}
                if wait > rc["long_wait_s"]:
                    w = {k: v * (3 if k <= 3 else 1) for k, v in w.items()}
                rating = int(pick(rng, {str(k): v for k, v in w.items()}))
            rt = done + timedelta(minutes=float(rng.uniform(2, 40)))
            self.em.emit(r, "ride_rated", rt, {"ride_id": ride_id, "rating": rating,
                                               "has_comment": bool(rng.random() < (0.6 if rating <= 2 else
                                                                                  rc["rating_comment_prob"]))})
        tp = 0.5 if trip.bad else (rc["ticket_prob_low_rating"] if rating and rating <= 2 else rc["ticket_prob"])
        if rng.random() < tp:
            cat = pick(rng, {"ride_issue": 0.5, "driver_behaviour": 0.25, "payment": 0.15, "lost_item": 0.05,
                             "other": 0.05})
            self.em.emit(r, "support_ticket_opened", done + timedelta(minutes=float(rng.uniform(10, 180))),
                         {"category": cat, "ride_id": ride_id}, origin="server")
        r.busy_until = done + secs(60)
        self._ride_row(r, ride_id, trip, "completed", booked, started, done, scheduled=scheduled, final_at=done,
                       gross=gross, discount=discount, final=final, rating=rating, pay=pay)

    def _ride_row(self, r: Rider, ride_id: str, trip: Trip, status: str, booked: datetime,
                  started: datetime | None, done: datetime | None, scheduled: datetime | None, final_at: datetime,
                  gross: float | None = None, discount: float = 0.0, final: float | None = None,
                  rating: int | None = None, pay: str | None = None) -> None:
        """hireme_backend_stub.rides; rides still in progress at the end of history are left out."""
        if final_at >= self.em.cutoff:
            return
        self.rides_by_status[status] = self.rides_by_status.get(status, 0) + 1
        self.rides_file.write(dumps({
            "ride_id": ride_id, "user_id": r.user_id, "city_id": r.city_id, "status": status,
            "booked_ts": iso(booked), "started_ts": iso(started) if started else None,
            "completed_ts": iso(done) if done else None, "is_scheduled": scheduled is not None,
            "scheduled_ts": iso(scheduled) if scheduled else None,
            "pickup_zone": trip.pickup, "drop_zone": trip.drop, "distance_km": trip.km,
            "vehicle_type": trip.vehicle, "payment_method": pay or trip.payment,
            "gross_fare_inr": gross, "discount_inr": discount if trip.promo and status == "completed" else None,
            "final_fare_inr": final, "promo_code": trip.promo["code"] if trip.promo and status == "completed" else None,
            "promo_id": trip.promo["promo_id"] if trip.promo and status == "completed" else None,
            "surge_multiplier": trip.surge,
            "driver_id": f"d_{r.city_id}{int(r.rng.integers(0, 2000)):05d}" if status != "no_driver" else None,
            "rating": rating}) + "\n")
