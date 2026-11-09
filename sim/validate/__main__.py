"""Validate a generated dataset on disk.

Usage:
    .venv/bin/python -m sim.validate data/gen/tiny_s42 [--sample 20000]

Exit code 0 if no check fails (N/A checks do not count), 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sim.validate import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", type=Path)
    ap.add_argument("--sample", type=int, default=20000, help="max envelopes for schema / round-trip checks")
    args = ap.parse_args(argv)
    results = run(args.dir, sample=args.sample)
    failed = 0
    for cid, status, details in results:
        print(f"{status:<5} {cid}")
        for line in details:
            print(f"        {line}")
        failed += status == "FAIL"
    passed = sum(1 for _, s, _ in results if s == "PASS")
    print(f"\n{passed} passed, {failed} failed, {sum(1 for _, s, _ in results if s == 'N/A')} not applicable locally")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
