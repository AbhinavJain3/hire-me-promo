"""Load the hireme_riders stub (Rider DB stand-in, D-013/D-074) into Firestore with the Admin SDK BulkWriter.

    .venv/bin/python -m sim.loaders.fs_riders --project hireme-engage-dev --dir data/gen/demo_s42
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python -m sim.loaders.fs_riders --project demo-hireme-engage-dev --dir ...

Documents are written with set() keyed by user_id, so re-running overwrites instead of duplicating.
On the free tier (Spark, about 20 k writes/day) a run is refused if it would exceed --max-writes (D-082, D-083).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from google.cloud import firestore

from sim.loaders import check_project

COLLECTION = "hireme_riders"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, type=check_project)
    ap.add_argument("--dir", required=True, type=Path, help="generator output directory")
    ap.add_argument("--max-writes", type=int, default=15000, help="free-tier guard (ignored on the emulator)")
    args = ap.parse_args(argv)
    path = args.dir / "firestore" / f"{COLLECTION}.ndjson"
    docs = [json.loads(line) for line in path.open(encoding="utf-8")]
    emulator = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
    if not emulator and len(docs) > args.max_writes:
        print(f"{len(docs)} writes exceed --max-writes {args.max_writes} (Spark quota); use the emulator or a smaller scale",
              file=sys.stderr)
        return 2
    db = firestore.Client(project=args.project)
    writer = db.bulk_writer()
    col = db.collection(COLLECTION)
    for d in docs:
        writer.set(col.document(d["user_id"]), d)
    writer.close()
    count = col.count().get()[0][0].value
    target = "emulator" if emulator else args.project
    print(f"wrote {len(docs)} docs to {target}/{COLLECTION}; collection now has {count} docs")
    return 0 if count >= len(docs) else 1


if __name__ == "__main__":
    sys.exit(main())
