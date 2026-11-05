"""Validate the HireMe engagement data contract.

Usage:
    .venv/bin/python -m engage.tools.validate_contract --all
        Run every check on the repository (CI, contract-steward agent, validate-contract skill).
    .venv/bin/python -m engage.tools.validate_contract --events FILE [FILE ...]
        Conformance check for event payloads (for the HireMe backend/app teams): FILE may hold one
        envelope, a JSON array of envelopes, a webhook body {"events": [...]}, or NDJSON (one envelope per line).

Exit code 0 when everything passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from engage.contract.catalog import (CONTRACTS_DIR, GENERATED_DIR, REPO_ROOT, Catalog, CatalogError,
                                     load_catalog)
from engage.contract.ga4 import from_ga4_row, iso_to_micros, to_ga4_row
from engage.tools.gen_contract import stale_files

ENVELOPE_SCHEMA = GENERATED_DIR / "envelope.schema.json"
PLAYBOOK_SCHEMA = CONTRACTS_DIR / "playbook.schema.json"
TEMPLATE_SCHEMA = CONTRACTS_DIR / "template.schema.json"
OPENAPI_DIR = CONTRACTS_DIR / "openapi"
DOCS = [REPO_ROOT / "docs" / "DATA_MODEL.md", REPO_ROOT / "docs" / "API.md"]
PLAYBOOK_DIRS = [CONTRACTS_DIR / "examples" / "playbooks", REPO_ROOT / "playbooks"]
TEMPLATE_DIRS = [CONTRACTS_DIR / "examples" / "templates", REPO_ROOT / "templates"]
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


# ----------------------------------------------------------------------------- reporting

@dataclass
class Report:
    results: list[tuple[str, bool, list[str]]] = field(default_factory=list)

    def check(self, name: str, fn: Callable[[], list[str] | None]) -> None:
        try:
            problems = fn() or []
        except Exception as exc:  # a crashing check is a failing check
            problems = [f"{type(exc).__name__}: {exc}"]
        self.results.append((name, not problems, problems))

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.results)

    def print(self) -> None:
        for name, ok, problems in self.results:
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
            for p in problems[:50]:
                print(f"        - {p}")
            if len(problems) > 50:
                print(f"        ... {len(problems) - 50} more")
        n_fail = sum(1 for _, ok, _ in self.results if not ok)
        print(f"\n{len(self.results) - n_fail}/{len(self.results)} checks passed" +
              ("" if not n_fail else f", {n_fail} failed"))


# ----------------------------------------------------------------------------- helpers

def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _errors(validator: Draft202012Validator, instance: Any) -> list[str]:
    out = []
    for e in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        loc = "/" + "/".join(str(p) for p in e.absolute_path)
        out.append(f"{loc}: {e.message[:300]}")
    return out


def envelope_validator() -> Draft202012Validator:
    return Draft202012Validator(_load(ENVELOPE_SCHEMA))


def envelope_errors(env: Any, validator: Draft202012Validator | None = None) -> list[str]:
    """Schema errors for one envelope. For an event_name that matches a schema branch, report the params errors."""
    return _errors(validator or envelope_validator(), env)


def _strip_engine_fields(env: dict) -> dict:
    return {k: v for k, v in env.items() if k not in ("source", "received_at")}


def roundtrip_problems(env: dict, cat: Catalog) -> list[str]:
    back = from_ga4_row(to_ga4_row(env, cat=cat), cat=cat)
    a, b = _strip_engine_fields(env), _strip_engine_fields(back)
    problems = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k), b.get(k)
        if k == "event_ts" and va and vb:
            if iso_to_micros(va) != iso_to_micros(vb):
                problems.append(f"event_ts {va} -> {vb}")
        elif k == "user_id" and va is None and vb is None:
            continue
        elif va != vb:
            problems.append(f"{k}: {va!r} -> {vb!r}")
    return problems


def doc_json_blocks(path: Path) -> list[tuple[int, Any]]:
    text = path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"```json\n(.*?)```", text, re.S):
        line = text[: m.start()].count("\n") + 1
        try:
            out.append((line, json.loads(m.group(1))))
        except json.JSONDecodeError:
            continue  # illustrative snippets with ellipses are not contract examples
    return out


# ----------------------------------------------------------------------------- checks

def check_catalog_lint(cat: Catalog) -> list[str]:
    lim = cat.limits
    problems: list[str] = []
    reserved = set(lim["reserved_event_names"])
    n_common = len(cat.ga4_common_params) + len(cat.common_params)
    for e in cat.events.values():
        if not SNAKE.match(e.name) or len(e.name) > lim["name_max_len"]:
            problems.append(f"event {e.name}: must be lowercase snake_case <= {lim['name_max_len']} chars")
        if e.origins != ["auto"]:
            if e.name in reserved:
                problems.append(f"event {e.name}: reserved Firebase event name")
            if any(e.name.startswith(p) for p in lim["reserved_prefixes"]):
                problems.append(f"event {e.name}: reserved prefix")
        if len(e.params) + n_common > lim["params_per_event_max"]:
            problems.append(f"event {e.name}: {len(e.params) + n_common} GA4 params > {lim['params_per_event_max']}")
        if not set(e.origins) <= {"client", "server", "auto"} or not set(e.delivery) <= {"ga4", "webhook"}:
            problems.append(f"event {e.name}: invalid origins/delivery")
        if "server" in e.origins and "webhook" not in e.delivery:
            problems.append(f"event {e.name}: server-origin events must be delivered by webhook")
        seen = set()
        for p in e.params:
            if p.name in seen:
                problems.append(f"{e.name}.{p.name}: duplicate param")
            seen.add(p.name)
            if not SNAKE.match(p.name) or len(p.name) > lim["name_max_len"]:
                problems.append(f"{e.name}.{p.name}: param name must be snake_case <= {lim['name_max_len']} chars")
            if any(p.name.startswith(x) for x in lim["reserved_prefixes"]):
                problems.append(f"{e.name}.{p.name}: reserved prefix")
            if p.name in cat.ga4_common_params or p.name in {c.name for c in cat.common_params}:
                problems.append(f"{e.name}.{p.name}: clashes with a common param")
            for v in p.values or []:
                if len(str(v)) > lim["string_value_max_len"]:
                    problems.append(f"{e.name}.{p.name}: enum value too long: {v}")
            if p.base in ("string", "enum") and isinstance(p.example, str) and len(p.example) > lim["string_value_max_len"]:
                problems.append(f"{e.name}.{p.name}: example longer than {lim['string_value_max_len']}")
    for u in cat.user_properties.values():
        if not SNAKE.match(u.name) or len(u.name) > lim["user_property_name_max_len"]:
            problems.append(f"user property {u.name}: must be snake_case <= {lim['user_property_name_max_len']} chars")
        if len(u.example) > lim["user_property_value_max_len"]:
            problems.append(f"user property {u.name}: example longer than {lim['user_property_value_max_len']}")
    if len(cat.user_properties) > 25:
        problems.append(f"{len(cat.user_properties)} user properties > 25 (GA4 project limit)")
    return problems


def check_generated_fresh() -> list[str]:
    return [f"stale: {s} (run .venv/bin/python -m engage.tools.gen_contract)" for s in stale_files()]


def check_schemas_compile() -> list[str]:
    problems = []
    for path in (ENVELOPE_SCHEMA, PLAYBOOK_SCHEMA, TEMPLATE_SCHEMA):
        try:
            Draft202012Validator.check_schema(_load(path))
        except Exception as exc:
            problems.append(f"{_rel(path)}: {exc}")
    return problems


def check_generated_examples() -> list[str]:
    v = envelope_validator()
    problems = []
    for path in sorted((GENERATED_DIR / "examples").glob("*.json")):
        problems += [f"{path.name}{e}" for e in envelope_errors(_load(path), v)]
    return problems


def _doc_envelopes() -> Iterable[tuple[str, dict]]:
    for path in DOCS:
        for line, obj in doc_json_blocks(path):
            if isinstance(obj, dict) and "event_name" in obj and "contract_version" in obj:
                yield f"{_rel(path)}:{line}", obj
            elif isinstance(obj, dict) and isinstance(obj.get("events"), list):
                for i, env in enumerate(obj["events"]):
                    yield f"{_rel(path)}:{line} events[{i}]", env


def check_doc_examples() -> list[str]:
    v = envelope_validator()
    pv = Draft202012Validator(_load(PLAYBOOK_SCHEMA))
    problems, n = [], 0
    for where, env in _doc_envelopes():
        n += 1
        problems += [f"{where} {e}" for e in envelope_errors(env, v)]
    for path in DOCS:
        for line, obj in doc_json_blocks(path):
            if isinstance(obj, dict) and "playbook_id" in obj and "trigger" in obj:
                n += 1
                problems += [f"{_rel(path)}:{line} playbook {e}" for e in _errors(pv, obj)]
    if n == 0:
        problems.append("no contract examples found in docs (expected the envelope and B2 playbook examples)")
    return problems


def check_ga4_roundtrip(cat: Catalog) -> list[str]:
    problems = []
    envs = [(p.name, _load(p)) for p in sorted((GENERATED_DIR / "examples").glob("*.json"))]
    envs += list(_doc_envelopes())
    for where, env in envs:
        problems += [f"{where}: {p}" for p in roundtrip_problems(env, cat)]
    return problems


def _json_pointer(parts: list[str]) -> str:
    return "#/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def openapi_registry() -> Registry:
    reg = Registry()
    for path in [*sorted(OPENAPI_DIR.glob("*.yaml")), ENVELOPE_SCHEMA]:
        reg = reg.with_resource(path.resolve().as_uri(),
                                Resource(contents=_load(path), specification=DRAFT202012))
    return reg


def _iter_media_examples(spec: dict) -> Iterable[tuple[list[str], str, Any]]:
    """Yield (path to media object, example name, example value) for every example in paths and webhooks."""
    def walk(node: Any, parts: list[str]):
        if isinstance(node, dict):
            if "schema" in node and ("examples" in node or "example" in node):
                if "example" in node:
                    yield parts, "example", node["example"]
                for name, ex in (node.get("examples") or {}).items():
                    yield parts, name, ex
            for k, v in node.items():
                yield from walk(v, parts + [k])
    for top in ("paths", "webhooks"):
        yield from walk(spec.get(top) or {}, [top])


def check_openapi() -> list[str]:
    problems = []
    reg = openapi_registry()
    for path in sorted(OPENAPI_DIR.glob("*.yaml")):
        spec = _load(path)
        try:
            validate_openapi(spec, base_uri=path.resolve().as_uri())
        except Exception as exc:
            problems.append(f"{path.name}: invalid OpenAPI: {str(exc)[:300]}")
            continue
        uri = path.resolve().as_uri()
        n = 0
        for parts, name, ex in _iter_media_examples(spec):
            if isinstance(ex, dict) and "$ref" in ex:  # components/examples reference
                target: Any = spec
                for seg in ex["$ref"].lstrip("#/").split("/"):
                    target = target[seg]
                ex = target
            value = ex.get("value") if isinstance(ex, dict) and "value" in ex else ex
            v = Draft202012Validator({"$ref": uri + _json_pointer(parts + ["schema"])}, registry=reg)
            n += 1
            problems += [f"{path.name} {'/'.join(parts)} example '{name}' {e}" for e in _errors(v, value)]
        if n == 0:
            problems.append(f"{path.name}: no examples to validate")
    return problems


def _playbook_semantics(pb: dict, cat: Catalog, where: str) -> list[str]:
    problems = []
    trig = pb.get("trigger", {})
    events = [trig["event"]] if trig.get("event") else list(trig.get("events_any") or [])
    for ev in events:
        if ev not in cat.events:
            problems.append(f"{where}: trigger event {ev!r} is not in the contract")
            continue
        params = {p.name for p in cat.events[ev].params}
        for cond in trig.get("where") or []:
            if cond["param"] not in params:
                problems.append(f"{where}: where param {cond['param']!r} is not a param of {ev}")
        for cond in (trig.get("event_where") or {}).get(ev, []):
            if cond["param"] not in params:
                problems.append(f"{where}: event_where param {cond['param']!r} is not a param of {ev}")
    if trig.get("time_param") and events and events[0] in cat.events:
        p = {x.name: x for x in cat.events[events[0]].params}.get(trig["time_param"])
        if p is None or p.type_label != "timestamp":
            problems.append(f"{where}: time_param {trig['time_param']!r} is not a timestamp param of {events[0]}")
    for c in trig.get("cancel_if") or []:
        name = c if isinstance(c, str) else c["event"]
        if name not in cat.events:
            problems.append(f"{where}: cancel_if event {name!r} is not in the contract")
            continue
        if isinstance(c, dict):
            cparams = {p.name for p in cat.events[name].params}
            for mp in c.get("match_params") or []:
                if mp not in cparams:
                    problems.append(f"{where}: match_param {mp!r} is not a param of {name}")
                for ev in events:
                    if ev in cat.events and mp not in {p.name for p in cat.events[ev].params}:
                        problems.append(f"{where}: match_param {mp!r} is not a param of trigger {ev}")
    conv = (pb.get("attribution") or {}).get("conversion_event")
    if conv and conv not in cat.events:
        problems.append(f"{where}: conversion_event {conv!r} is not in the contract")
    for ch in (pb.get("templates") or {}):
        if ch not in pb.get("channels", []):
            problems.append(f"{where}: templates for channel {ch!r} that is not in channels")
    return problems


def check_playbooks(cat: Catalog) -> list[str]:
    v = Draft202012Validator(_load(PLAYBOOK_SCHEMA))
    problems, n = [], 0
    for d in PLAYBOOK_DIRS:
        for path in sorted(d.glob("*.json")) if d.exists() else []:
            n += 1
            pb = _load(path)
            problems += [f"{_rel(path)}{e}" for e in _errors(v, pb)]
            problems += _playbook_semantics(pb, cat, _rel(path))
    if n == 0:
        problems.append("no playbooks found")
    return problems


def check_templates() -> list[str]:
    v = Draft202012Validator(_load(TEMPLATE_SCHEMA))
    problems, n = [], 0
    for d in TEMPLATE_DIRS:
        for path in sorted([*d.glob("*.json"), *d.glob("*.yaml")]) if d.exists() else []:
            n += 1
            t = _load(path)
            where = _rel(path)
            problems += [f"{where}{e}" for e in _errors(v, t)]
            if isinstance(t, dict):
                if t.get("template_id") and path.stem != t["template_id"]:
                    problems.append(f"{where}: file name must equal template_id")
                used = set(PLACEHOLDER.findall((t.get("title") or "") + " " + (t.get("body") or "")))
                declared = set(t.get("variables") or [])
                if used - declared:
                    problems.append(f"{where}: placeholders not declared in variables: {sorted(used - declared)}")
                if declared - used:
                    problems.append(f"{where}: variables declared but unused: {sorted(declared - used)}")
                text = PLACEHOLDER.sub("", (t.get("title") or "") + " " + (t.get("body") or ""))
                if re.search(r"[0-9₹%]", text):
                    problems.append(f"{where}: literal digits, ₹ or % outside placeholders (prices and codes must be placeholders, spec 9)")
    if n == 0:
        problems.append("no templates found")
    return problems


def check_firestore() -> list[str]:
    problems = []
    doc = _load(CONTRACTS_DIR / "firestore" / "firestore.indexes.json")
    for i, idx in enumerate(doc.get("indexes", [])):
        if not idx.get("collectionGroup") or len(idx.get("fields", [])) < 2:
            problems.append(f"index {i}: needs collectionGroup and at least 2 fields (single-field indexes are automatic)")
        for f in idx.get("fields", []):
            if f.get("order") not in ("ASCENDING", "DESCENDING"):
                problems.append(f"index {i}: field {f.get('fieldPath')} needs order ASCENDING|DESCENDING")
    rules = (CONTRACTS_DIR / "firestore" / "firestore.rules").read_text(encoding="utf-8")
    if "allow read, write: if false;" not in rules:
        problems.append("firestore.rules must deny all client access (DATA_MODEL §4.9)")
    return problems


def check_bigquery_ddl() -> list[str]:
    problems = []
    ddl_dir = CONTRACTS_DIR / "bigquery" / "ddl"
    files = sorted(ddl_dir.glob("*.sql"))
    if not files:
        return ["no DDL files"]
    for path in files:
        sql = path.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:CREATE (?:TABLE|SCHEMA|OR REPLACE VIEW)(?: IF NOT EXISTS)?|FROM)\s+`([^`]+)`", sql):
            if not m.group(1).startswith("${PROJECT}."):
                problems.append(f"{path.name}: `{m.group(1)}` must be qualified with ${{PROJECT}}")
        if re.search(r"PARTITION BY DATE\([^)]*,", sql):
            problems.append(f"{path.name}: partition expressions cannot take a time zone (D-075)")
    schema = _load(CONTRACTS_DIR / "bigquery" / "ga4_events_schema.json")
    names = {c["name"] for c in schema}
    for required in ("event_date", "event_timestamp", "event_name", "event_params", "user_id",
                     "user_pseudo_id", "user_properties", "app_info", "platform"):
        if required not in names:
            problems.append(f"ga4_events_schema.json: missing column {required}")
    return problems


# ----------------------------------------------------------------------------- entry points

def run_all() -> Report:
    r = Report()
    try:
        cat = load_catalog()
    except (CatalogError, KeyError, yaml.YAMLError) as exc:
        r.results.append(("catalog loads", False, [str(exc)]))
        return r
    r.results.append(("catalog loads", True, []))
    r.check("catalog follows Firebase naming and size limits", lambda: check_catalog_lint(cat))
    r.check("generated files are up to date with catalog.yaml", check_generated_fresh)
    r.check("JSON Schemas compile (draft 2020-12)", check_schemas_compile)
    r.check("generated example envelopes validate", check_generated_examples)
    r.check("envelope and playbook examples in DATA_MODEL.md / API.md validate", check_doc_examples)
    r.check("GA4 round trip (envelope -> GA4 row -> envelope) is lossless", lambda: check_ga4_roundtrip(cat))
    r.check("OpenAPI files are valid and their examples match their schemas", check_openapi)
    r.check("playbooks validate (schema + contract cross-checks)", lambda: check_playbooks(cat))
    r.check("templates validate (schema + placeholder rules)", check_templates)
    r.check("Firestore indexes and rules", check_firestore)
    r.check("BigQuery DDL and GA4 export schema", check_bigquery_ddl)
    return r


def _read_events(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]  # NDJSON
    if isinstance(obj, dict) and isinstance(obj.get("events"), list):
        return obj["events"]
    return obj if isinstance(obj, list) else [obj]


def run_events(files: list[str]) -> int:
    v = envelope_validator()
    total = bad = 0
    for f in files:
        for i, env in enumerate(_read_events(Path(f))):
            total += 1
            errs = envelope_errors(env, v)
            label = env.get("event_uuid", f"#{i}") if isinstance(env, dict) else f"#{i}"
            name = env.get("event_name", "?") if isinstance(env, dict) else "?"
            if errs:
                bad += 1
                print(f"REJECT {f} [{i}] {name} {label}")
                for e in errs:
                    print(f"        - {e}")
    print(f"\n{total - bad}/{total} events conform to contract v{load_catalog().event_contract_version}")
    return 0 if bad == 0 and total > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="run every repository check")
    g.add_argument("--events", nargs="+", metavar="FILE", help="validate event payload files (conformance kit)")
    args = ap.parse_args(argv)
    if args.events:
        return run_events(args.events)
    report = run_all()
    report.print()
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
