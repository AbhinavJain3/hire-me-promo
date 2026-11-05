"""Convert between the canonical event envelope and a GA4 BigQuery export row (D-003, D-057).

Used by the synthetic data generator and simulator (envelope -> GA4 row) and by the
GA4 BigQuery poller (GA4 row -> envelope). The round trip envelope -> row -> envelope is
lossless for every field that exists in GA4 (checked by validate_contract).

Only the GA4 columns we populate are produced; loaders create the full official schema
(contracts/bigquery/ga4_events_schema.json) and leave the other columns NULL.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from engage.contract.catalog import Catalog, load_catalog
from engage.contract.generate import auto_event_uuid

IST = ZoneInfo("Asia/Kolkata")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_COMMON_ENVELOPE_PARAMS = ("event_uuid", "contract_version", "origin", "city_id")


def iso_to_micros(ts: str) -> int:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without offset: {ts}")
    return (dt - _EPOCH) // timedelta(microseconds=1)


def micros_to_iso_ist(us: int) -> str:
    dt = _EPOCH + timedelta(microseconds=us)
    return dt.astimezone(IST).isoformat(timespec="milliseconds")


def _value(column: str, v: Any) -> dict:
    val = {"string_value": None, "int_value": None, "float_value": None, "double_value": None}
    if column == "int_value":
        val["int_value"] = int(v)          # bool -> 0/1
    elif column == "double_value":
        val["double_value"] = float(v)
    else:
        val["string_value"] = str(v)
    return val


def _read(value: dict, column: str) -> Any:
    return value.get(column)


def to_ga4_row(env: dict, *, device_platform: str = "ANDROID", cat: Catalog | None = None) -> dict:
    """Envelope -> GA4 export row (populated columns only)."""
    cat = cat or load_catalog()
    event = cat.events[env["event_name"]]
    columns = {p.name: p.ga4_column for p in event.params} | {p.name: p.ga4_column for p in cat.common_params}
    ts_us = iso_to_micros(env["event_ts"])

    params: list[dict] = []
    if event.origins != ["auto"]:          # automatic events carry no custom params in GA4
        for key in _COMMON_ENVELOPE_PARAMS:
            if env.get(key) is not None:
                params.append({"key": key, "value": _value(cat.ga4_common_params[key]["ga4_column"], env[key])})
    for key, v in env.get("params", {}).items():
        if v is None:
            continue
        params.append({"key": key, "value": _value(columns[key], v)})

    user_props = [
        {"key": k, "value": {"string_value": str(v), "int_value": None, "float_value": None,
                             "double_value": None, "set_timestamp_micros": ts_us}}
        for k, v in (env.get("user_properties") or {}).items()
    ]
    platform = env["platform"] if env["platform"] != "SERVER" else device_platform
    return {
        "event_date": (_EPOCH + timedelta(microseconds=ts_us)).astimezone(IST).strftime("%Y%m%d"),
        "event_timestamp": ts_us,
        "event_name": env["event_name"],
        "event_params": params,
        "user_id": env.get("user_id"),
        "user_pseudo_id": env.get("user_pseudo_id"),
        "user_properties": user_props,
        "platform": platform,
        "app_info": {"version": env["app_version"]} if env.get("app_version") else None,
    }


def from_ga4_row(row: dict, *, cat: Catalog | None = None, source: str = "ga4_export") -> dict:
    """GA4 export row -> envelope. Unknown params are dropped (engine is tolerant, D-068)."""
    cat = cat or load_catalog()
    name = row["event_name"]
    event = cat.events.get(name)
    if event is None:
        raise KeyError(f"event {name!r} is not in contract v{cat.event_contract_version}")
    by_key = {p["key"]: p["value"] for p in row.get("event_params") or []}
    types = {p.name: p for p in event.params} | {p.name: p for p in cat.common_params}

    env: dict[str, Any] = {}
    env["contract_version"] = _read(by_key.get("contract_version", {}), "string_value") or cat.event_contract_version
    uuid_ = _read(by_key.get("event_uuid", {}), "string_value")
    if uuid_ is None:   # Firebase automatic event: synthesise a deterministic id (D-072)
        uuid_ = auto_event_uuid(row.get("user_pseudo_id") or "", row["event_timestamp"], name,
                                row.get("event_bundle_sequence_id"))
    env["event_uuid"] = uuid_
    env["event_name"] = name
    env["event_ts"] = micros_to_iso_ist(row["event_timestamp"])
    env["user_id"] = row.get("user_id")
    if row.get("user_pseudo_id") is not None:
        env["user_pseudo_id"] = row["user_pseudo_id"]
    origin = _read(by_key.get("origin", {}), "string_value") or ("auto" if event.origins == ["auto"] else "client")
    env["platform"] = "SERVER" if origin == "server" else row.get("platform")
    if row.get("app_info") and row["app_info"].get("version"):
        env["app_version"] = row["app_info"]["version"]
    city = _read(by_key.get("city_id", {}), "int_value")
    if city is not None:
        env["city_id"] = int(city)
    env["origin"] = origin
    env["source"] = source

    params: dict[str, Any] = {}
    for key, value in by_key.items():
        if key in _COMMON_ENVELOPE_PARAMS or key not in types:
            continue
        p = types[key]
        raw = _read(value, p.ga4_column)
        if raw is None:
            continue
        if p.base == "bool":
            params[key] = bool(raw)
        elif p.base == "int":
            params[key] = int(raw)
        elif p.base == "double":
            params[key] = float(raw)
        else:
            params[key] = raw
    env["params"] = params
    ups = {u["key"]: u["value"]["string_value"] for u in row.get("user_properties") or []
           if u["key"] in cat.user_properties}
    if ups:
        env["user_properties"] = ups
    return env
