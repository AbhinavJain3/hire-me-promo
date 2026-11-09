"""Tests for the synthetic data generator (sim/generator) on a very small custom scale."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.generator.emit import open_text
from sim.generator.population import load_personas, persona_counts
from sim.generator.run import generate
from sim.validate import Data, run

STRUCTURAL = {"V1 envelopes conform to contract", "V2 event_uuid unique", "V3 GA4 round trip lossless",
              "V8 event_date is the IST date", "V13 rider docs (count, RiderProfile schema)", "V14 PII hygiene",
              "V10 fraud ring", "Window events stay inside the history window"}


@pytest.fixture(scope="module")
def gen(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("gen")
    generate("tiny", 7, out, riders=150, days=14)
    return out


def test_structural_checks_pass(gen):
    results = {cid: (status, details) for cid, status, details in run(gen)}
    for cid in STRUCTURAL:
        assert results[cid][0] == "PASS", (cid, results[cid][1])


def test_deterministic(gen, tmp_path):
    generate("tiny", 7, tmp_path, riders=150, days=14)
    a = json.loads((gen / "manifest.json").read_text())["files"]
    b = json.loads((tmp_path / "manifest.json").read_text())["files"]
    assert a == b


def test_other_seed_differs(gen, tmp_path):
    generate("tiny", 8, tmp_path, riders=150, days=14)
    a = {f["path"]: f["sha256"] for f in json.loads((gen / "manifest.json").read_text())["files"]}
    b = {f["path"]: f["sha256"] for f in json.loads((tmp_path / "manifest.json").read_text())["files"]}
    assert a["firestore/hireme_riders.ndjson"] != b["firestore/hireme_riders.ndjson"]


def test_manifest_row_counts_match_files(gen):
    m = json.loads((gen / "manifest.json").read_text())
    for f in m["files"]:
        with open_text(gen / f["path"]) as fh:
            assert sum(1 for _ in fh) == f["rows"], f["path"]
    assert m["counts"]["events_total"] == sum(f["rows"] for f in m["files"] if f["path"].startswith("envelopes/"))


def test_every_event_checked_at_small_size(gen):
    d = Data(gen)
    assert d.events.schema_checked == d.events.total > 0


def test_new_not_activated_riders_never_ride(gen):
    d = Data(gen)
    assert any(d.persona_of(u) == "P05" for u in d.personas)
    assert d.rides.rides_by_persona["P05"] == 0


def test_ground_truth_not_in_engine_visible_data(gen):
    """Personas and latent traits live only in engage_sim (D-012)."""
    d = Data(gen)
    assert d.events.truth_leaks == 0
    for doc in d.riders:
        text = json.dumps(doc)
        assert "persona" not in text and "price_elasticity" not in text


def test_persona_counts_cover_every_persona():
    cfg = load_personas()
    for n in (60, 500, 20000):
        c = persona_counts(cfg["merged"], n)
        assert sum(c.values()) == n
        assert all(v >= 1 for v in c.values())
        k = cfg["merged"]["P12"]["accounts_per_device"]
        assert c["P12"] >= k and c["P12"] % k == 0


def test_history_end_override(tmp_path):
    from datetime import date
    m = generate("tiny", 7, tmp_path, riders=40, days=5, history_end=date(2026, 12, 20))
    assert m["window"] == {"start_ist": "2026-12-16", "end_ist": "2026-12-20", "days": 5}
    assert "-e20261220-" in m["generation_id"]
    dates = {f["path"].rsplit("_", 1)[-1].split(".")[0] for f in m["files"]
             if f["path"].startswith("bigquery/analytics_999999999/events_")}
    assert dates and all("20261216" <= d <= "20261220" for d in dates)


def test_cli_history_end_parsing():
    import argparse
    from datetime import date
    from sim.generator.__main__ import parse_history_end
    assert parse_history_end("2026-12-01") == date(2026, 12, 1)
    assert isinstance(parse_history_end("yesterday"), date)
    with pytest.raises(argparse.ArgumentTypeError):
        parse_history_end("01/12/2026")
