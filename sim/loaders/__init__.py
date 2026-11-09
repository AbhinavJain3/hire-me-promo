"""Loaders: generated files (data/gen/<scale>_s<seed>/) -> BigQuery and Firestore (DUMMY_DATA_PLAN §8, D-011).

Only dev projects are accepted (CLAUDE.md): `hireme-engage-dev` or an emulator `demo-*` id.
"""
from __future__ import annotations

ALLOWED_PROJECTS = ("hireme-engage-dev",)


def check_project(project: str) -> str:
    if project in ALLOWED_PROJECTS or project.startswith("demo-"):
        return project
    raise SystemExit(f"refusing project {project!r}: loaders only write to {ALLOWED_PROJECTS} or demo-* emulator ids")
