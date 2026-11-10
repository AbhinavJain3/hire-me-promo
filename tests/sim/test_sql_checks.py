"""Offline tests for sql/checks and the BigQuery runner (no cloud access)."""
from __future__ import annotations

import re

from sim.validate.bq import CHECK_DIR, placeholders, render


def test_every_check_renders_without_placeholders():
    values = placeholders("hireme-engage-dev", "analytics_999999999")
    files = sorted(CHECK_DIR.glob("*.sql"))
    assert len(files) >= 11
    for f in files:
        sql = render(f, values)
        assert "${" not in sql, f.name
        for col in ("metric", "value", "lo", "hi", "ok", "detail"):
            assert re.search(rf"\b{col}\b", sql), (f.name, col)


def test_required_params_come_from_the_catalog():
    values = placeholders("hireme-engage-dev", "analytics_999999999")
    req = values["${REQUIRED_PARAMS}"]
    assert "STRUCT('*' AS event_name, 'event_uuid' AS key)" in req
    assert "'ride_booked'" in req and "'app_remove'" in values["${NULLABLE_USER_EVENTS}"]


def test_reach_targets_come_from_personas_yaml():
    t = placeholders("hireme-engage-dev", "analytics_999999999")["${REACH_TARGETS}"]
    assert "STRUCT('consent_push' AS k, 0.85 AS target)" in t
