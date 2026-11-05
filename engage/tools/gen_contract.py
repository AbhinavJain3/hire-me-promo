"""Regenerate contract artefacts from contracts/events/v1/catalog.yaml.

Usage:
    .venv/bin/python -m engage.tools.gen_contract          # write generated files
    .venv/bin/python -m engage.tools.gen_contract --check  # exit 1 if generated files are stale
"""
from __future__ import annotations

import argparse
import sys

from engage.contract.catalog import GENERATED_DIR, REPO_ROOT
from engage.contract.generate import render_all


def stale_files() -> list[str]:
    expected = render_all()
    stale = []
    for rel, text in expected.items():
        path = GENERATED_DIR / rel
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(rel)
    on_disk = {str(p.relative_to(GENERATED_DIR)) for p in GENERATED_DIR.rglob("*") if p.is_file()} \
        if GENERATED_DIR.exists() else set()
    stale += sorted(f"{rel} (orphan: not produced by the generator)" for rel in on_disk - set(expected))
    return stale


def write_all() -> list[str]:
    files = render_all()
    for rel, text in files.items():
        path = GENERATED_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check for drift, do not write")
    args = ap.parse_args(argv)
    if args.check:
        stale = stale_files()
        for s in stale:
            print(f"STALE {s}")
        print("generated files are up to date" if not stale else
              f"{len(stale)} stale file(s): run .venv/bin/python -m engage.tools.gen_contract")
        return 1 if stale else 0
    written = write_all()
    print(f"wrote {len(written)} files to {GENERATED_DIR.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
