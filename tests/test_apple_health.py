"""Health Auto Export JSON -> metrics -> the vitals summary. Enrichment only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from onemore import vitals
from onemore.sources.apple_health import import_health_text, norm, parse_health_json
from onemore.store import Store

FIX = Path(__file__).parent / "fixtures" / "health_auto_export.json"


def test_metric_names_normalise_to_snake_case():
    assert norm("weight_&_body_mass") == "weight_body_mass"
    assert norm("Weight & Body Mass") == "weight_body_mass"
    assert norm("totalSleep") == "total_sleep"
    assert norm("inBed") == "in_bed"


def test_every_reading_shape_becomes_a_metric():
    ms = {(m.name, m.at.isoformat()): m for m in parse_health_json(FIX.read_text())}
    assert ms[("weight_body_mass", "2026-09-07T07:00:00-05:00")].value == 182.4
    assert ms[("weight_body_mass", "2026-09-07T07:00:00-05:00")].unit == "lb"
    assert ms[("resting_heart_rate", "2026-09-07T00:00:00-05:00")].value == 54
    assert ms[("heart_rate/avg", "2026-09-07T08:00:00-05:00")].value == 74
    assert ms[("sleep_analysis/asleep", "2026-09-07T00:00:00")].value == 7.1
    assert ms[("sleep_analysis/total_sleep", "2026-09-07T00:00:00")].value == 7.4
    w = "2026-09-08T17:30:00-05:00"
    assert ms[("workout/hr_avg", w)].value == 128
    assert ms[("workout/hr_max", w)].value == 161
    assert ms[("workout/kcal", w)].value == 340
    assert ms[("workout/minutes", w)].value == 58
    assert not any(n.startswith("weight_body_mass/") for n, _ in ms), "empty metric adds nothing"


def test_import_is_idempotent_and_a_corrected_value_wins():
    store = Store(":memory:")
    new, seen = import_health_text(store, FIX.read_text(), "x.json")
    assert (new, seen) == (18, 18)
    assert import_health_text(store, FIX.read_text(), "x.json") == (0, 18)
    fixed = FIX.read_text().replace('"qty": 182.4', '"qty": 181.9')
    assert import_health_text(store, fixed, "y.json") == (0, 18)
    assert store.metrics("weight_body_mass")[-1].value == 181.9
    assert [i["source"] for i in store.imports()] == ["apple_health"] * 3


def test_summary_gives_latest_and_the_two_window_means_in_the_display_unit():
    store = Store(":memory:")
    import_health_text(store, FIX.read_text())
    by = {v.label: v for v in vitals.summary(store, date(2026, 9, 7), "lb")}
    bw = by["bodyweight"]
    assert (bw.latest, bw.latest_on, bw.unit) == (182.4, date(2026, 9, 7), "lb")
    # Days 1, 2 and 7 have readings; day 2 has two, averaged first. 7d = days 1..7.
    assert bw.mean_7d == pytest.approx((184.0 + (183.6 + 185.0) / 2 + 182.4) / 3)
    assert bw.mean_28d == bw.mean_7d
    kg = {v.label: v for v in vitals.summary(store, date(2026, 9, 7), "kg")}["bodyweight"]
    assert kg.unit == "kg" and kg.latest == pytest.approx(182.4 * 0.45359237, abs=0.01)
    assert by["resting HR"].mean_7d == 55
    assert by["sleep h"].latest == 7.1
    assert "body fat %" not in by, "no readings, no row"


def test_text_and_header_lines():
    store = Store(":memory:")
    import_health_text(store, FIX.read_text())
    v = vitals.summary(store, date(2026, 9, 8), "lb")
    line = vitals.to_line(v)
    assert line.startswith("bw 182.4 lb (7d ")
    assert "rHR 55 (28d 55)" in line and "sleep 7.1 h" in line
    text = vitals.to_text(v, vitals.last_workout(store))
    assert "last workout HR: avg 128 / max 161 bpm, 340 kcal, 58 min on 2026-09-08" in text
    assert vitals.to_text([], None) == ""
