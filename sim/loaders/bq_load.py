"""Load generated NDJSON into BigQuery with load jobs (DUMMY_DATA_PLAN §8 steps 2, 4, 5; D-011, D-082).

    .venv/bin/python -m sim.loaders.bq_load --project hireme-engage-dev --dir data/gen/demo_s42
    .venv/bin/python -m sim.loaders.bq_load --project hireme-engage-dev --dir data/gen/demo_s42 --what ref,stubs

Every table is replaced (WRITE_TRUNCATE), so re-running is safe. Event shards events_YYYYMMDD use the GA4
export schema from contracts/bigquery/ga4_events_schema.json; other tables use the schema created by bq_ddl.
Load jobs are free and allowed in the BigQuery sandbox (no streaming, D-082).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from google.cloud import bigquery

from engage.contract.catalog import REPO_ROOT
from sim.loaders import check_project

LOCATION = "asia-south1"
GROUPS = {"ref": "hireme_ref", "stubs": "hireme_backend_stub", "truth": "engage_sim"}
GA4_SCHEMA = REPO_ROOT / "contracts" / "bigquery" / "ga4_events_schema.json"


def _job_config(schema) -> bigquery.LoadJobConfig:
    return bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON, schema=schema,
                                  write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                                  ignore_unknown_values=False, max_bad_records=0)


def _load(client: bigquery.Client, path: Path, table: str, schema) -> tuple[str, int]:
    with path.open("rb") as fh:
        job = client.load_table_from_file(fh, table, job_config=_job_config(schema))
    job.result()
    return table, job.output_rows


def plan(client: bigquery.Client, project: str, gen_dir: Path, what: set[str], ga4_dataset: str):
    manifest = json.loads((gen_dir / "manifest.json").read_text())
    expected = {f["path"]: f["rows"] for f in manifest["files"]}
    jobs = []
    for group, dataset in GROUPS.items():
        if group in what:
            for p in sorted((gen_dir / "bigquery" / dataset).glob("*.ndjson")):
                table = f"{project}.{dataset}.{p.stem}"
                jobs.append((p, table, client.get_table(table).schema))
    if "events" in what:
        schema = [bigquery.SchemaField.from_api_repr(f) for f in json.loads(GA4_SCHEMA.read_text())]
        for p in sorted((gen_dir / "bigquery" / "analytics_999999999").glob("events_*.ndjson*")):
            jobs.append((p, f"{project}.{ga4_dataset}.{p.name.split('.')[0]}", schema))
    return manifest, expected, jobs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, type=check_project)
    ap.add_argument("--dir", required=True, type=Path, help="generator output directory")
    ap.add_argument("--what", default="ref,events,stubs,truth")
    ap.add_argument("--ga4-dataset", default="analytics_999999999")
    ap.add_argument("--parallel", type=int, default=8)
    args = ap.parse_args(argv)
    what = set(args.what.split(","))
    client = bigquery.Client(project=args.project, location=LOCATION)
    manifest, expected, jobs = plan(client, args.project, args.dir, what, args.ga4_dataset)
    print(f"{manifest['generation_id']}: {len(jobs)} load jobs into {args.project}")
    bad = 0
    with ThreadPoolExecutor(args.parallel) as ex:
        for (path, _, _), (table, rows) in zip(jobs, ex.map(lambda j: _load(client, *j), jobs)):
            want = expected.get(str(path.relative_to(args.dir)))
            ok = want is None or want == rows
            bad += not ok
            print(f"  {'ok ' if ok else 'BAD'} {table.split('.', 1)[1]}: {rows} rows" + ("" if ok else f" (expected {want})"))
    print("done" if not bad else f"{bad} tables with row-count mismatches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
