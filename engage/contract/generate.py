"""Generate contract artefacts from the event catalogue (D-067).

Outputs (all under contracts/events/v1/generated/):
  envelope.schema.json   bundled, self-contained JSON Schema (draft 2020-12) for one event envelope (D-068)
  ga4_mapping.json       envelope <-> GA4 BigQuery export column mapping (D-003, D-057)
  examples/<event>.json  one valid example envelope per event
  EVENTS.md              human-readable event reference for the HireMe app and backend teams

`render_all()` returns {relative_path: text}; the generator writes them and the validator
compares them with what is on disk (drift check).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from engage.contract.catalog import Catalog, Event, Param, load_catalog

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

UUID7_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
UUID_V5_OR_V7_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[57][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
TS_PATTERN = (r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?"
              r"(Z|[+-][0-9]{2}:[0-9]{2})$")

# Namespace for deterministic UUIDv5 ids synthesised for Firebase automatic events (D-072).
AUTO_EVENT_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://hireme.app/engage/ga4-auto-events")

EXAMPLE_TS = "2026-10-21T18:10:12.345+05:30"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
EXAMPLE_TS_MS = (datetime.fromisoformat(EXAMPLE_TS) - _EPOCH) // timedelta(milliseconds=1)
EXAMPLE_PSEUDO_ID = "6f1c2b9a8e7d4c3b9a0e1f2d3c4b5a69"


# ----------------------------------------------------------------------------- helpers

def uuid7_from(seed: str, ts_ms: int = EXAMPLE_TS_MS) -> str:
    """Deterministic UUIDv7 (for examples and fixtures): 48-bit ms timestamp + hashed bits."""
    h = hashlib.sha256(seed.encode()).digest()
    rand_a = int.from_bytes(h[0:2], "big") & 0x0FFF
    rand_b = int.from_bytes(h[2:10], "big") & ((1 << 62) - 1)
    value = (ts_ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return str(uuid.UUID(int=value))


def auto_event_uuid(user_pseudo_id: str, event_timestamp_us: int, event_name: str,
                    bundle_sequence_id: int | None = None) -> str:
    """UUIDv5 for Firebase automatic events that carry no event_uuid param (D-072)."""
    key = f"{user_pseudo_id}|{event_timestamp_us}|{event_name}|{bundle_sequence_id or ''}"
    return str(uuid.uuid5(AUTO_EVENT_UUID_NAMESPACE, key))


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def param_schema(p: Param, string_max: int) -> dict:
    s: dict[str, Any]
    if p.base == "enum":
        s = {"type": "string", "enum": list(p.values or [])}
    elif p.base == "string":
        s = {"type": "string", "maxLength": min(p.max_length or string_max, string_max)}
        if p.min_length is not None:
            s["minLength"] = p.min_length
        if p.pattern:
            s["pattern"] = p.pattern
    elif p.base == "int":
        s = {"type": "integer"}
    elif p.base == "double":
        s = {"type": "number"}
    elif p.base == "bool":
        s = {"type": "boolean"}
    else:  # pragma: no cover - guarded by the catalogue loader
        raise ValueError(p.base)
    if p.base in ("int", "double"):
        if p.minimum is not None:
            s["minimum"] = p.minimum
        if p.maximum is not None:
            s["maximum"] = p.maximum
    desc = f"[{p.type_label}] " + (p.notes or "")
    s["description"] = desc.strip()
    s["examples"] = [p.example]
    return s


def params_schema(e: Event, cat: Catalog) -> dict:
    string_max = cat.limits["string_value_max_len"]
    props = {p.name: param_schema(p, string_max) for p in e.params}
    for c in cat.common_params:
        props[c.name] = param_schema(c, string_max)
    return {
        "type": "object",
        "title": f"params of {e.name}",
        "description": e.description,
        "additionalProperties": False,
        "required": [p.name for p in e.params if p.required],
        "properties": props,
    }


def user_properties_schema(cat: Catalog) -> dict:
    vmax = cat.limits["user_property_value_max_len"]
    props: dict[str, Any] = {}
    for u in cat.user_properties.values():
        s: dict[str, Any] = {"type": "string", "maxLength": vmax,
                             "description": f"owner: {u.owner}; {u.now_later}", "examples": [u.example]}
        if u.values:
            s["enum"] = list(u.values)
        if u.pattern:
            s["pattern"] = u.pattern
        props[u.name] = s
    return {"type": "object", "additionalProperties": False, "properties": props,
            "description": "Only properties that changed. All values are strings (Firebase setUserProperty, D-070)."}


# ----------------------------------------------------------------------------- envelope schema

def envelope_schema(cat: Catalog) -> dict:
    defs: dict[str, Any] = {"user_properties": user_properties_schema(cat)}
    for e in cat.events.values():
        defs[f"params_{e.name}"] = params_schema(e, cat)

    rules: list[dict] = [
        {   # client events come from a device
            "if": {"properties": {"origin": {"const": "client"}}, "required": ["origin"]},
            "then": {"required": ["user_pseudo_id", "app_version"],
                     "properties": {"platform": {"enum": ["ANDROID", "IOS"]},
                                    "event_uuid": {"pattern": UUID7_PATTERN}}},
        },
        {   # server events are authored by the HireMe backend (D-069)
            "if": {"properties": {"origin": {"const": "server"}}, "required": ["origin"]},
            "then": {"properties": {"platform": {"const": "SERVER"},
                                    "event_uuid": {"pattern": UUID7_PATTERN}}},
        },
        {   # Firebase automatic events (GA4 export only)
            "if": {"properties": {"origin": {"const": "auto"}}, "required": ["origin"]},
            "then": {"required": ["user_pseudo_id"],
                     "properties": {"platform": {"enum": ["ANDROID", "IOS"]}}},
        },
    ]
    for e in cat.events.values():
        then: dict[str, Any] = {
            "properties": {
                "origin": {"enum": list(e.origins)},
                "params": {"$ref": f"#/$defs/params_{e.name}"},
            }
        }
        if not e.user_id_nullable:
            then["properties"]["user_id"] = {"type": "string"}
        rules.append({"if": {"properties": {"event_name": {"const": e.name}}, "required": ["event_name"]},
                      "then": then})

    ver = cat.event_contract_version
    major = ver.split(".")[0]
    return {
        "$schema": SCHEMA_DIALECT,
        "title": f"HireMe engagement event envelope (contract {cat.contract} v{ver})",
        "description": (
            "One analytics event as the engine receives it. Exact body item of POST /engage/v1/events. "
            "GENERATED from contracts/events/v1/catalog.yaml - do not edit. "
            f"Document version {cat.document_version}."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["contract_version", "event_uuid", "event_name", "event_ts", "user_id",
                     "platform", "origin", "params"],
        "properties": {
            "contract_version": {"type": "string", "pattern": f"^{major}\\.[0-9]+$", "examples": [ver]},
            "event_uuid": {"type": "string", "pattern": UUID_V5_OR_V7_PATTERN,
                           "description": "UUIDv7 generated by the sender; dedupe key across GA4 and webhook. "
                                          "UUIDv5 only for Firebase automatic events synthesised by the engine (D-072)."},
            "event_name": {"enum": list(cat.events)},
            "event_ts": {"type": "string", "pattern": TS_PATTERN,
                         "description": "ISO-8601 with offset. Device time for client events, server time for server events."},
            "user_id": {"type": ["string", "null"], "pattern": "^u_[0-9]{1,12}$",
                        "description": "Null only for pre-login and automatic events (see user_id_nullable)."},
            "user_pseudo_id": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{8,64}$",
                               "description": "Firebase app instance id. Required for client events; optional for server events (D-069)."},
            "platform": {"enum": ["ANDROID", "IOS", "SERVER"]},
            "app_version": {"type": "string", "maxLength": 20, "description": "Required for client events."},
            "city_id": {"type": "integer", "minimum": 1, "description": "1 Delhi, 2 Gurgaon, 3 Noida (D-037). When known."},
            "origin": {"enum": ["client", "server", "auto"],
                       "description": "Which system authored the event (D-042)."},
            "source": {"enum": ["simulator", "webhook", "ga4_export", "replay"],
                       "description": "Set by the engine adapter on ingest; ignored if a sender sets it."},
            "params": {"type": "object"},
            "user_properties": {"$ref": "#/$defs/user_properties"},
            "received_at": {"type": "string", "pattern": TS_PATTERN, "description": "Stamped by the engine on ingest."},
        },
        "allOf": rules,
        "$defs": defs,
    }


# ----------------------------------------------------------------------------- GA4 mapping

def ga4_mapping(cat: Catalog) -> dict:
    return {
        "description": "Envelope <-> GA4 BigQuery export mapping. GENERATED from catalog.yaml - do not edit.",
        "contract_version": cat.event_contract_version,
        "envelope_fields": {
            "event_name": "event_name",
            "event_ts": "event_timestamp (microseconds since epoch, UTC); event_date = IST date as YYYYMMDD",
            "user_id": "user_id",
            "user_pseudo_id": "user_pseudo_id",
            "platform": "platform (server-origin events: rider device platform in GA4; SERVER in the envelope, D-069)",
            "app_version": "app_info.version",
            "event_uuid": "event_params[key=event_uuid].value.string_value",
            "contract_version": "event_params[key=contract_version].value.string_value",
            "origin": "event_params[key=origin].value.string_value",
            "city_id": "event_params[key=city_id].value.int_value",
            "params.<name>": "event_params[key=<name>].value.<column per param below>",
            "user_properties.<name>": "user_properties[key=<name>].value.string_value",
            "source": "(not in GA4; set by the engine adapter)",
            "received_at": "(not in GA4; set by the engine on ingest)",
        },
        "common_params": {k: v["ga4_column"] for k, v in cat.ga4_common_params.items()}
                         | {p.name: p.ga4_column for p in cat.common_params},
        "events": {
            e.name: {"delivery": e.delivery, "origins": e.origins,
                     "params": {p.name: p.ga4_column for p in e.params}}
            for e in cat.events.values()
        },
        "user_properties": {u: "string_value" for u in cat.user_properties},
    }


# ----------------------------------------------------------------------------- examples

def example_envelope(e: Event, cat: Catalog) -> dict:
    origin = e.origins[0]
    env: dict[str, Any] = {"contract_version": cat.event_contract_version}
    if origin == "auto":
        env["event_uuid"] = auto_event_uuid(EXAMPLE_PSEUDO_ID, EXAMPLE_TS_MS * 1000, e.name)
    else:
        env["event_uuid"] = uuid7_from(f"example:{e.name}")
    env["event_name"] = e.name
    env["event_ts"] = EXAMPLE_TS
    env["user_id"] = None if e.name == "sign_up_started" else "u_88213"
    if origin == "server":
        env["platform"] = "SERVER"
    else:
        env["user_pseudo_id"] = EXAMPLE_PSEUDO_ID
        env["platform"] = "ANDROID"
    if origin == "client":
        env["app_version"] = "5.4.1"
    if origin != "auto":
        env["city_id"] = 3
    env["origin"] = origin
    env["params"] = {p.name: p.example for p in e.params}
    if e.name == "sign_up":
        env["user_properties"] = {"city": "Noida", "signup_date": "2026-10-21", "language": "en"}
    return env


# ----------------------------------------------------------------------------- EVENTS.md

def _md_cell(v: Any) -> str:
    return str(v).replace("|", "\\|")


def events_markdown(cat: Catalog) -> str:
    lines = [
        "# HireMe engagement events: reference",
        "",
        f"Contract `{cat.contract}` v{cat.event_contract_version} (document version {cat.document_version}).",
        "**GENERATED from `contracts/events/v1/catalog.yaml`. Do not edit.**",
        "",
        "Machine-readable schema: `generated/envelope.schema.json`. GA4 mapping: `generated/ga4_mapping.json`. "
        "Examples: `generated/examples/`. Conventions and context: `docs/DATA_MODEL.md` §1-2.",
        "",
        "Every event is sent as an envelope with `contract_version`, `event_uuid` (UUIDv7), `event_name`, "
        "`event_ts`, `user_id`, `user_pseudo_id`, `platform`, `app_version`, `city_id`, `origin` and `params`. "
        "In GA4, `event_uuid`, `contract_version`, `origin` and `city_id` are also written as event parameters. "
        "Every event may carry the optional param `engage_message_id` (deep-link attribution).",
        "",
        "Origins: `client` = rider app, `server` = HireMe backend (server-authoritative after handoff), "
        "`auto` = Firebase automatic. Delivery after handoff: `ga4` = Firebase Analytics BigQuery export, "
        "`webhook` = `POST /engage/v1/events`.",
        "",
        "| Event | Group | In spec | Origins | Delivery | GA4 params (incl. common) |",
        "|---|---|---|---|---|---|",
    ]
    n_common = len(cat.ga4_common_params) + len(cat.common_params)
    for e in cat.events.values():
        lines.append(f"| `{e.name}` | {e.group} | {'yes' if e.in_spec else 'added'} | "
                     f"{', '.join(e.origins)} | {', '.join(e.delivery)} | {len(e.params) + n_common} |")
    current_group = None
    for e in cat.events.values():
        if e.group != current_group:
            current_group = e.group
            lines += ["", f"## {current_group.replace('_', ' ').capitalize()}"]
        flags = []
        if e.server_authoritative:
            flags.append("server-authoritative")
        if e.user_id_nullable:
            flags.append("user_id may be null")
        lines += ["", f"### `{e.name}`" + (f" ({', '.join(flags)})" if flags else ""), "",
                  f"{e.description} Origins: {', '.join(e.origins)}. Delivery: {', '.join(e.delivery)}.", ""]
        if not e.params:
            lines.append("No event-specific params.")
            continue
        lines += ["| Param | Type | Required | Constraint | Example | GA4 column | In spec | Notes |",
                  "|---|---|---|---|---|---|---|---|"]
        for p in e.params:
            cons = []
            if p.values:
                cons.append(" / ".join(p.values))
            if p.pattern:
                cons.append(f"`{p.pattern}`")
            if p.minimum is not None:
                cons.append(f">= {p.minimum}")
            if p.maximum is not None:
                cons.append(f"<= {p.maximum}")
            lines.append(
                f"| `{p.name}` | {p.type_label} | {'yes' if p.required else 'no'} | {_md_cell('; '.join(cons))} | "
                f"`{_md_cell(json.dumps(p.example, ensure_ascii=False))}` | {p.ga4_column} | "
                f"{'yes' if p.in_spec else 'added'} | {_md_cell(p.notes)} |")
    lines += ["", "## User properties", "", "All values are strings.", "",
              "| Property | Allowed values | Owner | Example | Now / later |", "|---|---|---|---|---|"]
    for u in cat.user_properties.values():
        allowed = " / ".join(u.values) if u.values else (f"`{u.pattern}`" if u.pattern else "")
        lines.append(f"| `{u.name}` | {_md_cell(allowed)} | {u.owner} | `{u.example}` | {_md_cell(u.now_later)} |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- all

def render_all(cat: Catalog | None = None) -> dict[str, str]:
    cat = cat or load_catalog()
    out = {
        "envelope.schema.json": _dump(envelope_schema(cat)),
        "ga4_mapping.json": _dump(ga4_mapping(cat)),
        "EVENTS.md": events_markdown(cat),
    }
    for e in cat.events.values():
        out[f"examples/{e.name}.json"] = _dump(example_envelope(e, cat))
    return out
