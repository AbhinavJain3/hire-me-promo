"""Orchestrates one generation: population -> day-by-day behaviour -> files + manifest (DUMMY_DATA_PLAN §7-§8).

Output layout (all NDJSON, one JSON object per line; nothing is loaded anywhere):

  manifest.json                                    generation_id, seed, scale, window, counts, files
  envelopes/events_YYYYMMDD.ndjson.gz              canonical contract envelopes (simulator replay, conformance)
  bigquery/analytics_999999999/events_YYYYMMDD.ndjson.gz   GA4 export rows, one file per IST day
                                                   (gzip: BigQuery loads it directly; ~10x smaller)
  bigquery/hireme_ref/{cities,zones,vehicle_types,calendar_events}.ndjson
  bigquery/hireme_backend_stub/{rides,promo_redemptions,riders_snapshot}.ndjson
  bigquery/engage_sim/{personas,true_effects}.ndjson    ground truth: dev only, never readable by the engine
  firestore/hireme_riders.ndjson                   RiderProfile documents (Firestore Admin SDK loader)
  state/open_scheduled_rides.ndjson                scheduled rides that fall after history end (live simulator)
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

from engage.contract.catalog import load_catalog
from sim.generator.emit import Emitter, dumps
from sim.generator.organic import Behaviour
from sim.generator.population import (SCALES, build_population, load_personas, persona_truth_row, rider_profile,
                                      riders_snapshot_row)
from sim.generator.world import IST, SIM_DIR, World

CONFIG_FILES = ("personas.yaml", "geo.yaml", "calendar.yaml")


def config_hash() -> str:
    h = hashlib.sha256()
    for name in CONFIG_FILES:
        h.update((SIM_DIR / name).read_bytes())
    for mod in ("population.py", "organic.py", "emit.py", "world.py", "run.py"):
        h.update((SIM_DIR / "generator" / mod).read_bytes())
    return h.hexdigest()


def _write_rows(out: Path, rel: str, rows) -> int:
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(dumps(row) + "\n")
            n += 1
    return n


def _count_lines(path: Path) -> int:
    with path.open("rb") as f:
        return sum(1 for _ in f)


def generate(scale: str, seed: int, out: Path, riders: int | None = None, days: int | None = None,
             history_end: date | None = None, progress=None) -> dict:
    preset = SCALES[scale]
    n = riders or preset["riders"]
    n_days = days or preset["days"]
    cfg = load_personas()
    world = World(seed, history_end)
    cat = load_catalog()
    end = world.history_end
    window_start = end - timedelta(days=n_days - 1)
    chash = config_hash()
    end_tag = "" if end == world.default_history_end else f"-e{end:%Y%m%d}"
    generation_id = f"gen-{scale}-s{seed}-r{n}-d{n_days}{end_tag}-{chash[:8]}"

    out.mkdir(parents=True, exist_ok=True)
    population = build_population(seed, n, window_start, world, cfg)
    cutoff = datetime.combine(end + timedelta(days=1), time(0), IST)
    em = Emitter(cat=cat, world=world, out=out, cutoff=cutoff, window_start=window_start)

    stub = out / "bigquery" / "hireme_backend_stub"
    stub.mkdir(parents=True, exist_ok=True)
    with (stub / "rides.ndjson").open("w", encoding="utf-8") as rides_f, \
            (stub / "promo_redemptions.ndjson").open("w", encoding="utf-8") as red_f:
        beh = Behaviour(world=world, em=em, cfg=cfg, riders=population, window_start=window_start,
                        rides_file=rides_f, redemptions_file=red_f)
        d = window_start
        while d <= end:
            for r in population:
                beh.run_day(r, d)
            em.flush(up_to=d - timedelta(days=1))
            if progress:
                progress(d, n_days)
            d += timedelta(days=1)
        em.flush()

    files: dict[str, int] = dict(em.files)
    files["bigquery/hireme_backend_stub/rides.ndjson"] = _count_lines(stub / "rides.ndjson")
    files["bigquery/hireme_backend_stub/promo_redemptions.ndjson"] = _count_lines(stub / "promo_redemptions.ndjson")
    for table, rows in world.ref_rows().items():
        rel = f"bigquery/hireme_ref/{table}.ndjson"
        files[rel] = _write_rows(out, rel, rows)
    files["bigquery/hireme_backend_stub/riders_snapshot.ndjson"] = _write_rows(
        out, "bigquery/hireme_backend_stub/riders_snapshot.ndjson", (riders_snapshot_row(r, end) for r in population))
    files["bigquery/engage_sim/personas.ndjson"] = _write_rows(
        out, "bigquery/engage_sim/personas.ndjson", (persona_truth_row(r, generation_id) for r in population))
    effects = []
    for e in cfg["true_effects"]:
        for action, p in e["p"].items():
            effects.append({"generation_id": generation_id, "persona_id": e["persona"], "playbook_id": e["playbook"],
                            "action": action, "p_convert": p, "p_optout": cfg["base_optout_per_message"]})
    files["bigquery/engage_sim/true_effects.ndjson"] = _write_rows(out, "bigquery/engage_sim/true_effects.ndjson",
                                                                   effects)
    files["firestore/hireme_riders.ndjson"] = _write_rows(out, "firestore/hireme_riders.ndjson",
                                                          (rider_profile(r) for r in population))
    files["state/open_scheduled_rides.ndjson"] = _write_rows(out, "state/open_scheduled_rides.ndjson",
                                                             beh.open_scheduled)

    file_info = []
    for rel in sorted(files):
        path = out / rel
        file_info.append({"path": rel, "rows": files[rel], "bytes": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {
        "generation_id": generation_id,
        "generator_version": cfg["generator_version"],
        "contract_version": cat.event_contract_version,
        "contract_document_version": cat.document_version,
        "scale": scale, "seed": seed, "riders": n,
        "window": {"start_ist": window_start.isoformat(), "end_ist": end.isoformat(), "days": n_days},
        "config_sha256": chash,
        "counts": {
            "riders_by_persona": dict(sorted(Counter(f"{r.persona_id}_{r.p['name']}" for r in population).items())),
            "riders_by_city": dict(sorted(Counter(world.cities[r.city_id]["city_name"]
                                                  for r in population).items())),
            "events_total": sum(em.events_by_name.values()),
            "events_by_name": dict(sorted(em.events_by_name.items(), key=lambda kv: -kv[1])),
            "events_dropped_after_history_end": em.dropped_after_end,
            "rides_by_status": dict(sorted(beh.rides_by_status.items())),
            "open_scheduled_rides": len(beh.open_scheduled),
        },
        "files": file_info,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
