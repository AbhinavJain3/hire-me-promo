"""Contract tests: the validator must accept the contract and reject realistic mistakes."""
from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from engage.contract.catalog import GENERATED_DIR, load_catalog
from engage.contract.ga4 import from_ga4_row, to_ga4_row
from engage.contract.generate import auto_event_uuid, uuid7_from
from engage.tools import validate_contract as vc

CAT = load_catalog()
V = vc.envelope_validator()


def example(name: str) -> dict:
    return json.loads((GENERATED_DIR / "examples" / f"{name}.json").read_text())


def errs(env: dict) -> list[str]:
    return vc.envelope_errors(env, V)


# ----------------------------------------------------------------------------- whole repo

def test_all_repository_checks_pass():
    report = vc.run_all()
    failed = [(n, p) for n, ok, p in report.results if not ok]
    assert not failed, failed


def test_catalog_has_27_events_24_from_spec():
    assert len(CAT.events) == 27
    assert sum(e.in_spec for e in CAT.events.values()) == 24


def test_doc_examples_are_actually_found():
    envs = list(vc._doc_envelopes())
    assert len(envs) >= 3  # DATA_MODEL §2.1 envelope + API §4 webhook batch (2 events)


# ----------------------------------------------------------------------------- envelope: accept

@pytest.mark.parametrize("name", sorted(CAT.events))
def test_every_generated_example_is_valid(name):
    assert errs(example(name)) == []


def test_sign_up_started_allows_null_user_id():
    assert example("sign_up_started")["user_id"] is None
    assert errs(example("sign_up_started")) == []


def test_unknown_optional_param_omitted_is_fine():
    env = example("booking_abandoned")
    del env["params"]["booking_attempt_id"]
    assert errs(env) == []


def test_deep_link_attribution_param_allowed_on_any_event():
    env = example("fare_check")
    env["params"]["engage_message_id"] = "msg_8f3a91c2e0d4b7a65c1e2f90_1"
    assert errs(env) == []


def test_server_event_without_user_pseudo_id_is_valid():
    env = example("ride_booked")
    assert "user_pseudo_id" not in env and errs(env) == []


# ----------------------------------------------------------------------------- envelope: reject

def mutate(name, fn):
    env = copy.deepcopy(example(name))
    fn(env)
    return errs(env)


@pytest.mark.parametrize("name,fn,needle", [
    ("booking_abandoned", lambda e: e["params"].pop("step"), "step"),
    ("booking_abandoned", lambda e: e["params"].update(stepp="confirm"), "stepp"),
    ("booking_abandoned", lambda e: e["params"].update(step="checkout"), "checkout"),
    ("fare_check", lambda e: e["params"].update(pickup_zone="sector 62"), "sector 62"),
    ("fare_check", lambda e: e["params"].update(fare_estimate="420"), "420"),
    ("fare_check", lambda e: e["params"].update(surge_multiplier=0.5), "0.5"),
    ("fare_check", lambda e: e.update(user_id=None), "None"),
    ("fare_check", lambda e: e.pop("user_pseudo_id"), "user_pseudo_id"),
    ("fare_check", lambda e: e.pop("app_version"), "app_version"),
    ("fare_check", lambda e: e.update(event_ts="2026-10-21T18:10:12"), "event_ts"),
    ("fare_check", lambda e: e.update(event_uuid="3f2b8c1e-6b1a-4c3e-9a4f-2b8d1e0c5a77"), "event_uuid"),
    ("fare_check", lambda e: e.update(event_name="fare_checked"), "fare_checked"),
    ("fare_check", lambda e: e.update(source="client"), "client"),
    ("ride_booked", lambda e: e.update(origin="client"), "client"),
    ("ride_booked", lambda e: e.update(platform="ANDROID"), "SERVER"),
    ("ride_booked", lambda e: e["params"].update(is_scheduled=0), "0"),
    ("ride_rated", lambda e: e["params"].update(rating=6), "6"),
    ("sign_up", lambda e: e["user_properties"].update(total_rides=37), "37"),
    ("sign_up", lambda e: e["user_properties"].update(price_band="high"), "price_band"),
])
def test_rejects_realistic_mistakes(name, fn, needle):
    problems = mutate(name, fn)
    assert problems, f"mutation was accepted: {name} {needle}"


def test_auto_event_requires_v5_or_v7_uuid_and_device_platform():
    env = example("app_remove")
    assert errs(env) == []
    env2 = dict(env, platform="SERVER")
    assert errs(env2)


# ----------------------------------------------------------------------------- GA4 mapping

def test_ga4_row_types_follow_contract():
    row = to_ga4_row(example("ride_booked"), device_platform="IOS", cat=CAT)
    params = {p["key"]: p["value"] for p in row["event_params"]}
    assert params["is_scheduled"]["int_value"] == 0                    # bool -> 0/1
    assert params["fare_estimate"]["double_value"] == 420.0
    assert params["ride_id"]["string_value"] == "r_4821"
    assert params["city_id"]["int_value"] == 3
    assert params["origin"]["string_value"] == "server"
    assert row["platform"] == "IOS"                                    # device platform in GA4
    assert row["event_date"] == "20261021"                             # IST date


def test_ga4_back_to_envelope_restores_server_platform_and_bools():
    env = from_ga4_row(to_ga4_row(example("ride_booked"), cat=CAT), cat=CAT)
    assert env["platform"] == "SERVER" and env["params"]["is_scheduled"] is False
    assert env["source"] == "ga4_export"


def test_ga4_ist_date_boundary():
    env = example("fare_check")
    env["event_ts"] = "2026-10-21T23:59:59.999+05:30"
    assert to_ga4_row(env, cat=CAT)["event_date"] == "20261021"
    env["event_ts"] = "2026-10-21T18:30:00.000Z"   # = 2026-10-22 00:00 IST
    assert to_ga4_row(env, cat=CAT)["event_date"] == "20261022"


def test_auto_event_uuid_is_deterministic_and_v5():
    a = auto_event_uuid("abc12345", 1792595412345000, "app_remove")
    assert a == auto_event_uuid("abc12345", 1792595412345000, "app_remove")
    assert a[14] == "5"
    assert uuid7_from("x")[14] == "7"


def test_unknown_ga4_params_are_dropped():
    row = to_ga4_row(example("fare_check"), cat=CAT)
    row["event_params"].append({"key": "ga_session_id", "value": {"int_value": 99}})
    assert "ga_session_id" not in from_ga4_row(row, cat=CAT)["params"]


# ----------------------------------------------------------------------------- playbooks

PB = Draft202012Validator(json.loads(vc.PLAYBOOK_SCHEMA.read_text()))
SPEC_B2 = json.loads((vc.CONTRACTS_DIR / "examples" / "playbooks" / "spec_section7_B2.json").read_text())


def test_spec_section7_example_validates_unchanged():
    assert list(PB.iter_errors(SPEC_B2)) == []


@pytest.mark.parametrize("patch", [
    {"trigger": {"type": "relative_time", "event": "ride_scheduled", "time_param": "scheduled_time"}},  # no offsets
    {"trigger": {"type": "schedule", "audience_segment": "lapsed_30"}},                                   # no cron
    {"trigger": {"event": "booking_abandoned"}},                                                          # no wait
    {"message_class": "transactional"},                                                                   # promo allowed
    {"autonomy": 4},
    {"holdout_percent": 60},
    {"channels": ["push", "fax"]},
])
def test_playbook_schema_rejects(patch):
    pb = copy.deepcopy(SPEC_B2) | patch
    assert list(PB.iter_errors(pb))


def test_playbook_semantics_catch_unknown_events_and_params():
    pb = copy.deepcopy(SPEC_B2)
    pb["trigger"]["cancel_if"] = ["ride_confirmed", {"event": "ride_completed", "match_params": ["ride_id"]}]
    pb["trigger"]["where"] = [{"param": "stage", "op": "eq", "value": "confirm"}]
    problems = vc._playbook_semantics(pb, CAT, "test")
    assert any("ride_confirmed" in p for p in problems)
    assert any("stage" in p for p in problems)
    assert any("match_param 'ride_id' is not a param of trigger booking_abandoned" in p for p in problems)


# ----------------------------------------------------------------------------- templates and conformance CLI

def test_template_rules(tmp_path, monkeypatch):
    bad = {"template_id": "tpl_B2_push_en_v9", "playbook_id": "B2_abandoned_booking", "channel": "push",
           "language": "en", "message_class": "marketing", "title": "Save 15%!",
           "body": "Use {promo_code} before {expiry}", "variables": ["promo_code"], "status": "draft"}
    (tmp_path / "tpl_B2_push_en_v9.json").write_text(json.dumps(bad))
    monkeypatch.setattr(vc, "TEMPLATE_DIRS", [tmp_path])
    problems = vc.check_templates()
    assert any("not declared" in p for p in problems)
    assert any("literal digits" in p for p in problems)


def test_sms_template_requires_dlt():
    tv = Draft202012Validator(json.loads(vc.TEMPLATE_SCHEMA.read_text()))
    t = json.loads((vc.CONTRACTS_DIR / "examples" / "templates" / "tpl_B2_sms_en_v1.json").read_text())
    assert list(tv.iter_errors(t)) == []
    del t["dlt"]
    assert list(tv.iter_errors(t))


def test_conformance_cli_ndjson(tmp_path, capsys):
    good, bad = example("fare_check"), example("fare_check")
    bad["params"]["vehicle_type"] = "auto_rickshaw"
    f = tmp_path / "events.ndjson"
    f.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
    assert vc.main(["--events", str(f)]) == 1
    out = capsys.readouterr().out
    assert "1/2 events conform" in out and "auto_rickshaw" in out
    f.write_text(json.dumps({"events": [good]}))
    assert vc.main(["--events", str(f)]) == 0
