"""Run the validation checks in sql/checks/ against a loaded dev project (DUMMY_DATA_PLAN §10).

    .venv/bin/python -m sim.validate.bq --project hireme-engage-dev
    .venv/bin/python -m sim.validate.bq --project hireme-engage-dev --only V04,V06 --max-gb 1

Every query is dry-run first and refused if it would scan more than --max-gb. V13 (Firestore hireme_riders
against BigQuery riders_snapshot) runs here with the Firestore client. Exit code 1 if any check fails.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import yaml
from google.cloud import bigquery, firestore

from engage.contract.catalog import REPO_ROOT, load_catalog
from sim.generator.world import SIM_DIR
from sim.loaders import check_project

CHECK_DIR = REPO_ROOT / "sql" / "checks"
LOCATION = "asia-south1"
REACH_KEYS = ("consent_push", "consent_email", "consent_sms", "consent_whatsapp", "has_email", "push_token_present")
V13_FIELDS = ("city_id", "language", "is_synthetic")


def _sql_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def placeholders(project: str, ga4_dataset: str) -> dict[str, str]:
    cat = load_catalog()
    req = [("*", k) for k in ("event_uuid", "contract_version", "origin")]
    req += [(e.name, p.name) for e in cat.events.values() for p in e.params if p.required]
    personas = yaml.safe_load((SIM_DIR / "personas.yaml").read_text())
    reach = personas["reachability"]
    per_device = next(p["accounts_per_device"] for p in personas["personas"].values() if "accounts_per_device" in p)
    return {
        "${PROJECT}": project,
        "${GA4_DATASET}": ga4_dataset,
        "${REQUIRED_PARAMS}": "[" + ", ".join(f"STRUCT({_sql_str(e)} AS event_name, {_sql_str(k)} AS key)"
                                              for e, k in req) + "]",
        "${NULLABLE_USER_EVENTS}": "[" + ", ".join(_sql_str(e.name) for e in cat.events.values()
                                                   if e.user_id_nullable) + "]",
        "${REACH_TARGETS}": "[" + ", ".join(f"STRUCT({_sql_str(k)} AS k, {float(reach[k])} AS target)"
                                            for k in REACH_KEYS) + "]",
        "${ACCOUNTS_PER_DEVICE}": str(int(per_device)),
    }


def render(path: Path, values: dict[str, str]) -> str:
    sql = path.read_text()
    for k, v in values.items():
        sql = sql.replace(k, v)
    if "${" in sql:
        raise ValueError(f"{path.name}: unfilled placeholder")
    return sql


def run_sql_check(client: bigquery.Client, path: Path, values: dict[str, str], max_bytes: int):
    sql = render(path, values)
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
    scanned = dry.total_bytes_processed or 0
    if scanned > max_bytes:
        return "SKIP", [f"dry run: {scanned / 1e9:.2f} GB exceeds --max-gb; not run"], scanned
    rows = list(client.query(sql).result())
    lines = [f"{r.metric}: {'' if r.value is None else round(r.value, 4)} "
             f"(target {r.lo if r.lo == r.hi else f'{r.lo:.3g}-{r.hi:.3g}'}) {'ok' if r.ok else 'FAIL'}"
             + (f" [{r.detail}]" if r.detail else "") for r in rows]
    return ("PASS" if rows and all(r.ok for r in rows) else "FAIL"), lines, scanned


def v13_firestore(project: str, bq: bigquery.Client, sample: int = 100, seed: int = 0):
    snap = {r.user_id: r for r in bq.query(
        f"SELECT user_id, city_id, language, is_synthetic FROM `{project}.hireme_backend_stub.riders_snapshot` "
        f"WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM `{project}.hireme_backend_stub.riders_snapshot`)").result()}
    db = firestore.Client(project=project)
    col = db.collection("hireme_riders")
    count = col.count().get()[0][0].value
    lines = [f"hireme_riders docs: {count} (riders_snapshot {len(snap)}) {'ok' if count == len(snap) else 'FAIL'}"]
    ids = random.Random(seed).sample(sorted(snap), min(sample, len(snap)))
    docs = {d.id: d.to_dict() for d in db.get_all([col.document(u) for u in ids])}
    bad = [u for u in ids if u not in docs or any(docs[u].get(f) != getattr(snap[u], f) for f in V13_FIELDS)]
    lines.append(f"{len(ids) - len(bad)}/{len(ids)} sampled docs match the snapshot on {', '.join(V13_FIELDS)} "
                 f"{'ok' if not bad else 'FAIL'}" + (f" [e.g. {', '.join(bad[:5])}]" if bad else ""))
    return ("PASS" if all(line.endswith("ok") for line in lines) else "FAIL"), lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, type=check_project)
    ap.add_argument("--ga4-dataset", default="analytics_999999999")
    ap.add_argument("--only", help="comma-separated check prefixes, e.g. V04,V13")
    ap.add_argument("--max-gb", type=float, default=2.0, help="per-query dry-run limit")
    ap.add_argument("--no-firestore", action="store_true", help="skip V13")
    args = ap.parse_args(argv)
    only = tuple(args.only.split(",")) if args.only else None
    client = bigquery.Client(project=args.project, location=LOCATION)
    values = placeholders(args.project, args.ga4_dataset)

    results, total = [], 0
    for path in sorted(CHECK_DIR.glob("*.sql")):
        cid = path.stem
        if only and not cid.startswith(only):
            continue
        try:
            status, lines, scanned = run_sql_check(client, path, values, int(args.max_gb * 1e9))
            total += scanned
        except Exception as exc:          # report and continue
            status, lines = "FAIL", [f"{type(exc).__name__}: {str(exc)[:300]}"]
        results.append((cid, status, lines))
    if not args.no_firestore and (not only or "V13".startswith(only) or any(o.startswith("V13") for o in only)):
        try:
            results.append(("V13_firestore_riders", *v13_firestore(args.project, client)))
        except Exception as exc:
            results.append(("V13_firestore_riders", "FAIL", [f"{type(exc).__name__}: {str(exc)[:300]}"]))
    if not only:
        results += [("V03_ga4_round_trip", "N/A", ["local only: .venv/bin/python -m sim.validate <dir>"]),
                    ("V11_engage_sim_iam", "N/A", ["needs the engine service account (M0.5)"]),
                    ("V12_ground_truth_recovery", "N/A", ["needs a simulated engine run (M1.4)"])]

    for cid, status, lines in results:
        print(f"{status:4}  {cid}")
        for line in lines:
            print(f"        {line}")
    failed = sum(s == "FAIL" for _, s, _ in results)
    passed = sum(s == "PASS" for _, s, _ in results)
    print(f"\n{passed} passed, {failed} failed, {sum(s in ('N/A', 'SKIP') for _, s, _ in results)} not run; "
          f"{total / 1e6:.0f} MB scanned")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
