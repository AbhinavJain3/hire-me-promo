"""Apply contracts/bigquery/ddl/*.sql to a dev project (DUMMY_DATA_PLAN §8 step 1).

    .venv/bin/python -m sim.loaders.bq_ddl --project hireme-engage-dev            # datasets + tables
    .venv/bin/python -m sim.loaders.bq_ddl --project hireme-engage-dev --views    # views (after events are loaded)

Statements are idempotent (CREATE ... IF NOT EXISTS / CREATE OR REPLACE VIEW).
"""
from __future__ import annotations

import argparse
import sys

from google.cloud import bigquery

from engage.contract.catalog import REPO_ROOT
from sim.loaders import check_project

DDL_DIR = REPO_ROOT / "contracts" / "bigquery" / "ddl"
LOCATION = "asia-south1"


def render(sql: str, project: str, ga4_dataset: str) -> str:
    return sql.replace("${PROJECT}", project).replace("${GA4_DATASET}", ga4_dataset)


def apply(project: str, ga4_dataset: str = "analytics_999999999", views: bool = False) -> list[str]:
    client = bigquery.Client(project=project, location=LOCATION)
    done = []
    for f in sorted(DDL_DIR.glob("*.sql")):
        is_view = f.name.startswith("70_")
        if is_view != views:
            continue
        client.query(render(f.read_text(), project, ga4_dataset)).result()
        done.append(f.name)
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, type=check_project)
    ap.add_argument("--ga4-dataset", default="analytics_999999999")
    ap.add_argument("--views", action="store_true", help="apply 70_views.sql only (needs events_* shards)")
    args = ap.parse_args(argv)
    for name in apply(args.project, args.ga4_dataset, args.views):
        print(f"applied {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
