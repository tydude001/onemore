"""The recovery rule, on synthetic readings. The real ones never enter the suite."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from onemore.model import Metric
from onemore.program.spec import Day, LiftSpec, Pct, Program, Sets, Slot, Week, WeekKind
from onemore.rules import DEFAULT_RULES
from onemore.rules.base import Context
from onemore.rules.recovery import METRIC, recovery_deload

LIFT = "leg_press"
START, END = date(2026, 9, 1), date(2026, 9, 8)  # the closing week, end exclusive


def readings(values: dict[date, float]) -> list[Metric]:
    return [Metric("apple_health", METRIC, datetime(d.year, d.month, d.day, 7, tzinfo=UTC), v,
                   "bpm") for d, v in values.items()]


def series(baseline: float, week: list[float], days_of_base: int = 21) -> list[Metric]:
    """`days_of_base` days at `baseline` before the week, then the week's own readings."""
    vals = {START - timedelta(days=i + 1): baseline for i in range(days_of_base)}
    vals |= {START + timedelta(days=i): v for i, v in enumerate(week)}
    return readings(vals)


def ctx(metrics, week_no=4, kind=WeekKind.WORK) -> Context:
    week = Week(week_no, kind, (Day("D1", (Slot(LIFT, (Sets(3, 5, Pct(0.8)),)),)),))
    prog = Program("t", {LIFT: LiftSpec(LIFT)}, [week], list(DEFAULT_RULES))
    return Context(program=prog, week_no=week_no, week=week, start=START, end=END,
                   sessions=[], states={}, catalog=None, metrics=metrics)


def test_fires_when_the_week_runs_hot():
    adjs = recovery_deload(ctx(series(56.0, [63, 64, 62, 63, 64])))
    assert len(adjs) == 1
    a = adjs[0]
    assert a.rule == "recovery_deload" and a.field == "deload_next" and a.new == 1
    assert "resting HR" in a.reason and "+" in a.reason
    assert len(a.evidence) == 5, "one evidence key per day that carried a reading"
    assert all(k.startswith(f"apple_health:{METRIC}:2026-09-") for k in a.evidence)


def test_the_threshold_is_where_it_says_it_is():
    """The two sides of +5.0 bpm, a fifth of a beat apart.

    The 28-day baseline contains the closing week, which drags it toward the week and
    makes the gap smaller than a naive before/after reading of the same numbers: 21 days
    at 56 plus four at 61.9 is a 4.92 bpm gap, not 5.9."""
    assert recovery_deload(ctx(series(56.0, [61.9] * 4))) == [], "4.92 bpm: quiet"
    assert recovery_deload(ctx(series(56.0, [62.1] * 4))), "5.08 bpm: fires"


def test_silent_without_enough_days_in_the_week():
    """Three hot readings are three days of a watch on the nightstand, not a signal."""
    assert recovery_deload(ctx(series(56.0, [66, 67, 66]))) == []


def test_silent_when_no_health_data_was_loaded():
    assert recovery_deload(ctx(None)) == []
    assert recovery_deload(ctx([])) == []


def test_silent_before_week_four():
    """Weeks 1-3 have a 28-day window reaching back before the plan started, where the
    baseline is untrained life and every trained week looks like fatigue."""
    hot = series(56.0, [63, 64, 62, 63, 64])
    for week_no in (1, 2, 3):
        assert recovery_deload(ctx(hot, week_no=week_no)) == [], f"week {week_no}"
    assert recovery_deload(ctx(hot, week_no=4)), "week 4 is the first that may fire"


def test_silent_in_a_deload_week():
    """The week already backed off; a second deload is not the answer to it being hot."""
    assert recovery_deload(ctx(series(56.0, [63, 64, 62, 63, 64]), kind=WeekKind.DELOAD)) == []


def test_ignores_readings_after_the_week():
    """A Health export landing weeks late must not be read as the week that is closing."""
    late = readings({END + timedelta(days=i): 70.0 for i in range(7)})
    assert recovery_deload(ctx(series(56.0, [56, 56, 56, 56]) + late)) == []


def test_reads_only_its_own_metric():
    noise = [Metric("apple_health", "heart_rate_variability",
                    datetime(2026, 9, d, 7, tzinfo=UTC), 20.0, "ms") for d in range(1, 8)]
    assert recovery_deload(ctx(series(56.0, [56, 56, 56, 56]) + noise)) == []


def test_onemore_rhr_threshold_overrides_the_default(monkeypatch):
    """A +2.5 bpm week is quiet at the 5.0 default and fires once the env var lowers it."""
    mild = series(56.0, [59, 59, 59, 59])
    assert recovery_deload(ctx(mild)) == [], "quiet at the default 5.0 threshold"
    monkeypatch.setenv("ONEMORE_RHR_THRESHOLD", "2.0")
    adjs = recovery_deload(ctx(mild))
    assert len(adjs) == 1
    assert "+2 threshold" in adjs[0].reason


def test_onemore_rhr_threshold_fails_loudly_on_an_invalid_value(monkeypatch):
    monkeypatch.setenv("ONEMORE_RHR_THRESHOLD", "not-a-number")
    with pytest.raises(ValueError):
        recovery_deload(ctx(series(56.0, [63, 64, 62, 63, 64])))
