"""Load and normalise the event catalogue (contracts/events/v1/catalog.yaml).

The catalogue is the single source of truth for the analytics event contract (D-067).
Everything else (JSON Schemas, examples, GA4 mapping, EVENTS.md) is generated from the
normalised structures returned here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
EVENTS_DIR = CONTRACTS_DIR / "events" / "v1"
CATALOG_PATH = EVENTS_DIR / "catalog.yaml"
GENERATED_DIR = EVENTS_DIR / "generated"

BASE_TYPES = {"string", "int", "double", "bool", "enum"}
GA4_COLUMN = {"string": "string_value", "enum": "string_value", "int": "int_value",
              "bool": "int_value", "double": "double_value"}
_CONSTRAINT_KEYS = ("pattern", "minimum", "maximum", "min_length", "max_length")


@dataclass
class Param:
    name: str
    base: str                      # string | int | double | bool | enum
    type_label: str                # base or named type, for docs
    required: bool
    example: Any
    in_spec: bool
    notes: str = ""
    values: list[str] | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None

    @property
    def ga4_column(self) -> str:
        return GA4_COLUMN[self.base]


@dataclass
class Event:
    name: str
    group: str
    in_spec: bool
    origins: list[str]
    delivery: list[str]
    description: str
    user_id_nullable: bool
    server_authoritative: bool
    params: list[Param] = field(default_factory=list)


@dataclass
class UserProperty:
    name: str
    owner: str
    example: str
    now_later: str
    values: list[str] | None = None
    pattern: str | None = None


@dataclass
class Catalog:
    raw: dict
    contract: str
    document_version: str
    event_contract_version: str
    limits: dict
    events: dict[str, Event]
    common_params: list[Param]
    ga4_common_params: dict[str, dict]
    user_properties: dict[str, UserProperty]


class CatalogError(ValueError):
    pass


def _resolve_param(name: str, spec: dict, raw: dict, default_in_spec: bool, where: str) -> Param:
    types, enums = raw.get("types", {}), raw.get("enums", {})
    t = spec.get("type")
    if t is None:
        raise CatalogError(f"{where}.{name}: missing type")
    resolved: dict[str, Any] = {}
    if t in BASE_TYPES:
        base, label = t, t
    elif t in types:
        named = types[t]
        base, label = named["base"], t
        for k in (*_CONSTRAINT_KEYS, "example", "values", "values_from"):
            if k in named:
                resolved[k] = named[k]
    else:
        raise CatalogError(f"{where}.{name}: unknown type {t!r}")
    if base not in BASE_TYPES:
        raise CatalogError(f"{where}.{name}: named type {t!r} has invalid base {base!r}")
    # param-level overrides win over the named type
    for k in (*_CONSTRAINT_KEYS, "example", "values", "values_from"):
        if k in spec:
            resolved[k] = spec[k]
    values = resolved.get("values")
    if "values_from" in resolved:
        src = resolved["values_from"]
        if src not in enums:
            raise CatalogError(f"{where}.{name}: values_from {src!r} not in enums")
        values = list(enums[src])
    if base == "enum" and not values:
        raise CatalogError(f"{where}.{name}: enum without values")
    example = resolved.get("example")
    if example is None:
        example = values[0] if values else None
    if example is None:
        raise CatalogError(f"{where}.{name}: no example (add one to the param or its named type)")
    return Param(
        name=name, base=base, type_label=label,
        required=bool(spec.get("required", False)),
        example=example,
        in_spec=bool(spec.get("in_spec", default_in_spec)),
        notes=spec.get("notes", ""),
        values=values,
        pattern=resolved.get("pattern"),
        minimum=resolved.get("minimum"),
        maximum=resolved.get("maximum"),
        min_length=resolved.get("min_length"),
        max_length=resolved.get("max_length"),
    )


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    enums, types = raw.get("enums", {}), raw.get("types", {})

    events: dict[str, Event] = {}
    for ename, e in raw["events"].items():
        params = [
            _resolve_param(pname, pspec, raw, bool(e.get("in_spec", False)), f"events.{ename}")
            for pname, pspec in (e.get("params") or {}).items()
        ]
        events[ename] = Event(
            name=ename, group=e["group"], in_spec=bool(e.get("in_spec", False)),
            origins=list(e["origins"]), delivery=list(e["delivery"]),
            description=e.get("description", ""),
            user_id_nullable=bool(e.get("user_id_nullable", False)),
            server_authoritative=bool(e.get("server_authoritative", False)),
            params=params,
        )

    common = [_resolve_param(n, s, raw, False, "common_params")
              for n, s in (raw.get("common_params") or {}).items()]

    ups: dict[str, UserProperty] = {}
    for uname, u in raw.get("user_properties", {}).items():
        values = u.get("values")
        if "enum_from" in u:
            values = list(enums[u["enum_from"]])
        pattern = u.get("pattern")
        if "type" in u:
            pattern = types[u["type"]].get("pattern")
        ups[uname] = UserProperty(name=uname, owner=u["owner"], example=str(u["example"]),
                                  now_later=u.get("now_later", ""), values=values, pattern=pattern)

    return Catalog(
        raw=raw, contract=raw["contract"], document_version=raw["document_version"],
        event_contract_version=str(raw["event_contract_version"]), limits=raw["limits"],
        events=events, common_params=common, ga4_common_params=raw["ga4_common_params"],
        user_properties=ups,
    )
