"""Generate HireMe synthetic history to local files (no cloud access needed).

Usage:
    .venv/bin/python -m sim.generator --scale tiny --seed 42
    .venv/bin/python -m sim.generator --scale small --seed 42 --out data/gen/small_s42
    .venv/bin/python -m sim.generator --scale tiny --seed 7 --riders 120 --days 14   # custom size (tests)
    .venv/bin/python -m sim.generator --scale demo --seed 42 --history-end yesterday  # free-tier load (D-084)

Output goes to data/gen/<scale>_s<seed>/ by default (git-ignored). The same (scale, seed, config) always
produces byte-identical files, so a project can be filled by re-running the generator instead of copying files.
With --history-end yesterday the resolved date is written to manifest.json; pass that date to reproduce the run.
Check the result with:  .venv/bin/python -m sim.validate <out dir>
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from engage.contract.catalog import REPO_ROOT
from sim.generator.population import SCALES
from sim.generator.run import generate
from sim.generator.world import IST


def parse_history_end(value: str) -> date:
    if value == "yesterday":
        return (datetime.now(IST) - timedelta(days=1)).date()
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD or 'yesterday', got {value!r}") from e


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", choices=sorted(SCALES), default="tiny")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, help="output directory (default data/gen/<scale>_s<seed>)")
    ap.add_argument("--riders", type=int, help="override the preset's rider count")
    ap.add_argument("--days", type=int, help="override the preset's history length in days")
    ap.add_argument("--history-end", type=parse_history_end, metavar="YYYY-MM-DD|yesterday",
                    help="last IST date of history (default: sim/calendar.yaml, 2026-10-31); use a recent date "
                         "for the BigQuery sandbox, whose 60-day expiry drops older data")
    ap.add_argument("--force", action="store_true", help="replace an existing output directory")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    out = args.out or REPO_ROOT / "data" / "gen" / f"{args.scale}_s{args.seed}"
    if out.exists() and any(out.iterdir()):
        if not args.force:
            print(f"{out} already exists; use --force to replace it", file=sys.stderr)
            return 2
        shutil.rmtree(out)

    started = time.time()

    def progress(d, n_days):
        if not args.quiet:
            print(f"\r  generated {d.isoformat()}", end="", flush=True)

    m = generate(args.scale, args.seed, out, riders=args.riders, days=args.days,
                 history_end=args.history_end, progress=progress)
    if not args.quiet:
        print()
        c = m["counts"]
        print(f"generation_id {m['generation_id']}  ({time.time() - started:.1f}s)")
        print(f"window {m['window']['start_ist']} .. {m['window']['end_ist']} IST, {m['riders']} riders")
        print(f"events {c['events_total']:,}  rides {c['rides_by_status']}")
        print(f"output {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
