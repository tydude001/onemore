"""Apple Health's native export.xml -> the same metrics the Health Auto Export path makes."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pytest

from onemore import vitals
from onemore.sources.apple_health_xml import import_health_export, parse_health_xml
from onemore.store import Store

FIX = Path(__file__).parent / "fixtures" / "apple_health_export.xml"


def _by_name():
    out = {}
    with open(FIX, "rb") as f:
        for m in parse_health_xml(f):
            out.setdefault(m.name, []).append(m)
    return out


def test_quantity_records_come_through_under_the_shared_names():
    ms = _by_name()
    assert [(m.value, m.unit) for m in ms["weight_body_mass"]] == [(184, "lb"), (182, "lb"), (182.4, "lb")]
    assert ms["weight_body_mass"][0].at.isoformat() == "2026-09-01T07:10:00-05:00"
    assert ms["resting_heart_rate"][0].value == 54
    assert ms["heart_rate_variability"][0].value == 48.2
    assert ms["vo2_max"][0].value == 37.6
    assert ms["lean_body_mass"][0].value == 146.6


def test_body_fat_written_as_a_fraction_is_stored_as_a_percentage():
    assert _by_name()["body_fat_percentage"][0].value == pytest.approx(19.6)


def test_steps_take_the_largest_source_per_day_not_the_sum_of_both():
    """The phone and the Watch both count the same steps: 3000 and 3500 is a 3500 day,
    not 6500."""
    steps = _by_name()["step_count"]
    assert [(m.at.date(), m.value) for m in steps] == [(date(2026, 9, 7), 3500)]


def test_sleep_is_one_row_per_night_from_the_stage_intervals():
    ms = _by_name()
    nights = {m.at.date(): m.value for m in ms["sleep_analysis/asleep"]}
    # Core 4h + Deep 1.5h + REM 1.6h; the 15 min awake does not count.
    assert nights == {date(2026, 9, 7): pytest.approx(7.1)}
    in_bed = {m.at.date(): m.value for m in ms["sleep_analysis/in_bed"]}
    assert in_bed == {date(2026, 9, 7): 8.0, date(2026, 9, 3): 8.0}, "a phone-only night has in_bed alone"
    assert {m.at.date(): m.value for m in ms["sleep_analysis/deep"]} == {date(2026, 9, 7): 1.5}


def test_lifting_workouts_carry_hr_from_stats_or_from_raw_samples_and_walks_are_ignored():
    ms = _by_name()
    by_start = {m.at.isoformat(): m.value for m in ms["workout/hr_avg"]}
    assert by_start["2024-11-18T10:00:00-05:00"] == pytest.approx(112.5), "from WorkoutStatistics"
    assert by_start["2026-09-08T17:30:00-05:00"] == 130, "from the two raw samples inside the window"
    assert {m.at.isoformat(): m.value for m in ms["workout/hr_max"]}["2026-09-08T17:30:00-05:00"] == 150
    assert {m.at.isoformat(): m.value for m in ms["workout/kcal"]}["2026-09-08T17:30:00-05:00"] == 340
    assert {m.at.isoformat(): m.value for m in ms["workout/minutes"]}["2026-09-08T17:30:00-05:00"] == 58
    assert not any(m.at.date() == date(2026, 9, 9) for m in ms["workout/hr_avg"]), "the walk"


def test_import_from_the_zip_health_hands_you_is_idempotent(tmp_path):
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(FIX, "apple_health_export/export.xml")
        zf.writestr("apple_health_export/workout-routes/route.gpx", "<gpx/>")
    store = Store(":memory:")
    new, seen = import_health_export(store, z)
    assert new == seen > 0
    assert import_health_export(store, z) == (0, seen)
    assert import_health_export(store, FIX) == (0, seen), "the unpacked xml is the same readings"
    by = {v.label: v for v in vitals.summary(store, date(2026, 9, 7), "lb")}
    assert by["bodyweight"].latest == 182.4
    assert by["body fat %"].latest == pytest.approx(19.6)
    assert by["sleep h"].latest == pytest.approx(7.1)
    assert by["steps"].latest == 3500
    assert "avg 130 / max 150 bpm, 340 kcal, 58 min on 2026-09-08" == vitals.last_workout(store)
