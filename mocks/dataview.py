"""Read-only summary of the synthetic data for the client demo page /demo/data (D-094). Dev only.

Cloud mode reads the dev project (Firestore hireme_riders + BigQuery) with the caller's application-default
credentials: Firestore count aggregations and a 5-document sample (about 15 reads), and small aggregate BigQuery
queries that are each dry-run first and refused above MAX_BYTES. Results are cached for CACHE_S seconds.
If the cloud is unreachable (or no project is set) the same shape is built from the local generator output.
Contact details are masked before they leave this module, even though all riders are synthetic.
"""
from __future__ import annotations

import gzip
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

GA4_DATASET = "analytics_999999999"
LOCATION = "asia-south1"
MAX_BYTES = 200 * 1024 * 1024      # per query; the demo queries scan well under 50 MB
CACHE_S = 900
SAMPLE_DOCS = 5
SAMPLE_EVENT = "booking_abandoned"
_IST = ZoneInfo("Asia/Kolkata")
TABLE_DATASETS = ("hireme_ref", "hireme_backend_stub", "engage_sim")


def mask_phone(p: str | None) -> str | None:
    return None if not p else p[:5] + "•" * max(len(p) - 7, 0) + p[-2:]


def mask_email(e: str | None) -> str | None:
    if not e or "@" not in e:
        return e
    user, dom = e.split("@", 1)
    return user[:2] + "•••@" + dom


def rider_view(d: dict, cities: dict[int, str]) -> dict:
    """The rider document as shown on the page: same fields, contact masked."""
    c = d.get("contact") or {}
    consent = d.get("consent") or {}
    tokens = d.get("push_tokens") or []
    return {
        "user_id": d.get("user_id"), "first_name": d.get("first_name"),
        "city": cities.get(d.get("city_id"), d.get("city_id")), "language": d.get("language"),
        "signup_ts": d.get("signup_ts"), "status": d.get("status"), "is_synthetic": d.get("is_synthetic"),
        "wallet_balance_inr": d.get("wallet_balance_inr"),
        "contact": {"phone_e164": mask_phone(c.get("phone_e164")), "email": mask_email(c.get("email")),
                    "phone_dnd": c.get("phone_dnd"), "email_verified": c.get("email_verified")},
        "consent": {ch: (v or {}).get("opted_in") for ch, v in consent.items()},
        "push_tokens": [{"platform": t.get("platform"), "stale": t.get("stale"), "token": "fcm_tok_•••"} for t in tokens],
    }


def persona_labels(manifest: dict | None) -> dict[str, str]:
    keys = ((manifest or {}).get("counts") or {}).get("riders_by_persona") or {}
    return {k.split("_", 1)[0]: k.split("_", 1)[1].replace("_", " ") for k in keys if "_" in k}


def _sorted_desc(counter: dict, key: str) -> list[dict]:
    return [{key: k, "n": v} for k, v in sorted(counter.items(), key=lambda kv: -kv[1])]


class DataView:
    def __init__(self, project: str | None = None, local_dir: Path | None = None, ga4_dataset: str = GA4_DATASET):
        self.project, self.local_dir, self.ga4 = project, local_dir, ga4_dataset
        self._cache: dict | None = None
        self._at = 0.0
        self._lock = threading.Lock()

    # ---- public -------------------------------------------------------------------------------------------
    def summary(self, refresh: bool = False) -> dict:
        with self._lock:
            if self._cache and not refresh and time.monotonic() - self._at < CACHE_S:
                return {**self._cache, "cached": True}
            t0 = time.perf_counter()
            error = None
            if self.project:
                try:
                    out = self._cloud()
                except Exception as exc:        # no credentials, quota, network: fall back to local files
                    error = f"{type(exc).__name__}: {str(exc)[:200]}"
                    out = self._local()
            else:
                out = self._local()
            out.update(error=error, elapsed_ms=round((time.perf_counter() - t0) * 1000), cached=False,
                       loaded_at=datetime.now(timezone.utc).isoformat(), generation=self._generation())
            self._cache, self._at = out, time.monotonic()
            return out

    # ---- shared -------------------------------------------------------------------------------------------
    def _manifest(self) -> dict | None:
        p = self.local_dir and self.local_dir / "manifest.json"
        return json.loads(p.read_text()) if p and p.exists() else None

    def _generation(self) -> dict | None:
        m = self._manifest()
        if not m:
            return None
        return {"id": m["generation_id"], "scale": m["scale"], "seed": m["seed"], "riders": m["riders"],
                "window": m["window"], "contract": m.get("contract_document_version")}

    # ---- cloud --------------------------------------------------------------------------------------------
    def _cloud(self) -> dict:
        from google.cloud import bigquery, firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        from sim.loaders import check_project
        check_project(self.project)
        bq = bigquery.Client(project=self.project, location=LOCATION)
        p, g = self.project, self.ga4
        scanned = [0]

        def q(sql: str) -> list[dict]:
            dry = bq.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            if (dry.total_bytes_processed or 0) > MAX_BYTES:
                raise RuntimeError(f"query would scan {dry.total_bytes_processed / 1e6:.0f} MB (limit {MAX_BYTES / 1e6:.0f} MB)")
            scanned[0] += dry.total_bytes_processed or 0
            job = bq.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES))
            return [dict(r.items()) for r in job.result()]

        events = f"`{p}.{g}.events_*`"
        stub = f"`{p}.hireme_backend_stub"
        queries = {
            "cities": f"SELECT city_id, city_name, is_pilot FROM `{p}.hireme_ref.cities` ORDER BY city_id",
            "daily": f"SELECT _TABLE_SUFFIX AS d, COUNT(*) AS n FROM {events} "
                     f"WHERE _TABLE_SUFFIX NOT LIKE 'intraday%' GROUP BY d ORDER BY d",
            "by_name": f"SELECT event_name AS name, COUNT(*) AS n FROM {events} GROUP BY name ORDER BY n DESC",
            "rides": f"SELECT status, COUNT(*) AS n, ROUND(AVG(gross_fare_inr), 0) AS avg_fare, "
                     f"COUNTIF(promo_code IS NOT NULL) AS with_promo FROM {stub}.rides` GROUP BY status ORDER BY n DESC",
            "promos": f"SELECT code, COUNT(*) AS n, SUM(discount_inr) AS discount FROM {stub}.promo_redemptions` "
                      f"GROUP BY code ORDER BY n DESC",
            "personas": f"SELECT persona_id AS id, COUNT(*) AS n FROM `{p}.engage_sim.personas` GROUP BY id ORDER BY id",
        }
        with ThreadPoolExecutor(max_workers=len(queries)) as pool:
            futs = {k: pool.submit(q, sql) for k, sql in queries.items()}
            res = {k: f.result() for k, f in futs.items()}
        last = res["daily"][-1]["d"] if res["daily"] else None
        sample_event = None
        if last:
            rows = q(f"""SELECT event_name, FORMAT_TIMESTAMP('%FT%T%Ez', TIMESTAMP_MICROS(event_timestamp), 'Asia/Kolkata') AS event_time_ist,
                  event_date, user_id, user_pseudo_id, platform,
                  ARRAY(SELECT AS STRUCT key, COALESCE(value.string_value, CAST(value.int_value AS STRING),
                        CAST(value.double_value AS STRING)) AS value FROM UNNEST(event_params) ORDER BY key) AS event_params
                FROM `{p}.{g}.events_{last}` WHERE event_name = '{SAMPLE_EVENT}' LIMIT 1""")
            sample_event = _jsonable(rows[0]) if rows else None

        tables = []
        for ds in TABLE_DATASETS:
            for t in bq.list_tables(f"{p}.{ds}"):
                tables.append({"dataset": ds, "table": t.table_id, "rows": bq.get_table(t.reference).num_rows})
        tables.append({"dataset": g, "table": f"events_YYYYMMDD ({len(res['daily'])} daily shards)",
                       "rows": sum(r["n"] for r in res["daily"])})

        cities = {r["city_id"]: r["city_name"] for r in res["cities"]}
        db = firestore.Client(project=p)
        col = db.collection("hireme_riders")

        def count(field=None, value=None) -> int:
            qy = col.where(filter=FieldFilter(field, "==", value)) if field else col
            return qy.count().get()[0][0].value

        fs = {
            "collections": sorted(c.id for c in db.collections()),
            "riders_total": count(),
            "by_city": [{"city": cities[c], "pilot": next(r["is_pilot"] for r in res["cities"] if r["city_id"] == c),
                         "n": count("city_id", c)} for c in cities],
            "reach": {"push_opt_in": count("consent.push.opted_in", True),
                      "whatsapp_opt_in": count("consent.whatsapp.opted_in", True),
                      "email_opt_in": count("consent.email.opted_in", True),
                      "phone_dnd": count("contact.phone_dnd", True)},
            "sample": [rider_view(d.to_dict(), cities) for d in col.order_by("user_id").limit(SAMPLE_DOCS).stream()],
        }
        labels = persona_labels(self._manifest())
        return {
            "source": "cloud", "project": p,
            "firestore": fs,
            "bigquery": {
                "datasets": [g, *TABLE_DATASETS], "tables": tables, "scanned_bytes": scanned[0],
                "events_total": sum(r["n"] for r in res["daily"]),
                "daily": [{"d": f"{r['d'][:4]}-{r['d'][4:6]}-{r['d'][6:]}", "n": r["n"]} for r in res["daily"]],
                "by_name": res["by_name"],
                "rides": [{**r, "avg_fare": float(r["avg_fare"] or 0)} for r in res["rides"]],
                "promos": [{**r, "discount": float(r["discount"] or 0)} for r in res["promos"]],
                "personas": [{**r, "label": labels.get(r["id"], "")} for r in res["personas"]],
                "sample_event": sample_event,
            },
        }

    # ---- local fallback -----------------------------------------------------------------------------------
    def _local(self) -> dict:
        m = self._manifest()
        if not m:
            raise FileNotFoundError("no generator output for the data page (pass --data-dir)")
        d, c = self.local_dir, m["counts"]
        cities = {r["city_id"]: r for r in _ndjson(d / "bigquery/hireme_ref/cities.ndjson")}
        names = {r["city_id"]: r["city_name"] for r in cities.values()}
        riders = list(_ndjson(d / "firestore/hireme_riders.ndjson"))
        rides: dict[str, list] = {}
        for r in _ndjson(d / "bigquery/hireme_backend_stub/rides.ndjson"):
            s = rides.setdefault(r["status"], [0, 0.0, 0])
            s[0] += 1
            s[1] += r["gross_fare_inr"] or 0
            s[2] += r["promo_code"] is not None
        promos: dict[str, list] = {}
        for r in _ndjson(d / "bigquery/hireme_backend_stub/promo_redemptions.ndjson"):
            s = promos.setdefault(r["code"], [0, 0.0])
            s[0] += 1
            s[1] += r["discount_inr"] or 0
        daily = [{"d": f"{n[7:11]}-{n[11:13]}-{n[13:15]}", "n": f["rows"]}
                 for f in m["files"] if (n := Path(f["path"]).name).startswith("events_")]
        sample_event = None
        if daily:
            last = d / "bigquery" / self.ga4 / f"events_{daily[-1]['d'].replace('-', '')}.ndjson.gz"
            with gzip.open(last, "rt", encoding="utf-8") as fh:
                for line in fh:
                    e = json.loads(line)
                    if e["event_name"] == SAMPLE_EVENT:
                        v = lambda x: next((str(x[k]) for k in ("string_value", "int_value", "double_value")  # noqa: E731
                                            if x.get(k) is not None), None)
                        ts = datetime.fromtimestamp(int(e["event_timestamp"]) / 1e6, timezone.utc)
                        sample_event = {"event_name": e["event_name"], "event_time_ist": ts.astimezone(_IST).isoformat(),
                                        "event_date": e.get("event_date"), "user_id": e.get("user_id"),
                                        "user_pseudo_id": e.get("user_pseudo_id"), "platform": e.get("platform"),
                                        "event_params": sorted(({"key": p["key"], "value": v(p["value"])}
                                                                for p in e["event_params"]), key=lambda p: p["key"])}
                        break
        reach = Counter()
        for r in riders:
            for ch in ("push", "whatsapp", "email"):
                reach[f"{ch}_opt_in"] += bool(((r.get("consent") or {}).get(ch) or {}).get("opted_in"))
            reach["phone_dnd"] += bool((r.get("contact") or {}).get("phone_dnd"))
        city_counts = Counter(r["city_id"] for r in riders)
        labels = persona_labels(m)
        persona_n = {k.split("_", 1)[0]: v for k, v in c["riders_by_persona"].items()}
        tables = [{"dataset": f.parent.name, "table": f.name.split(".")[0], "rows": sum(1 for _ in f.open())}
                  for ds in TABLE_DATASETS for f in sorted((d / "bigquery" / ds).glob("*.ndjson"))]
        tables.append({"dataset": self.ga4, "table": f"events_YYYYMMDD ({len(daily)} daily shards)", "rows": c["events_total"]})
        return {
            "source": "local", "project": None,
            "firestore": {
                "collections": ["hireme_riders"], "riders_total": len(riders),
                "by_city": [{"city": names[k], "pilot": cities[k]["is_pilot"], "n": city_counts[k]} for k in sorted(names)],
                "reach": dict(reach),
                "sample": [rider_view(r, names) for r in sorted(riders, key=lambda r: r["user_id"])[:SAMPLE_DOCS]],
            },
            "bigquery": {
                "datasets": [self.ga4, *TABLE_DATASETS], "tables": tables, "scanned_bytes": 0,
                "events_total": c["events_total"], "daily": daily,
                "by_name": _sorted_desc(c["events_by_name"], "name"),
                "rides": sorted(({"status": k, "n": v[0], "avg_fare": round(v[1] / v[0]), "with_promo": v[2]}
                                 for k, v in rides.items()), key=lambda r: -r["n"]),
                "promos": sorted(({"code": k, "n": v[0], "discount": round(v[1], 2)} for k, v in promos.items()),
                                 key=lambda r: -r["n"]),
                "personas": [{"id": k, "n": persona_n[k], "label": labels.get(k, "")} for k in sorted(persona_n)],
                "sample_event": sample_event,
            },
        }


def _ndjson(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _jsonable(row: dict) -> dict:
    def conv(v):
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v
    return conv(row)
