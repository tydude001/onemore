"""Loads are stored in kg and rounded, per exercise, at render time only."""

from __future__ import annotations

import pytest

from onemore.exercises import Catalog
from onemore.program.render import bump_reps, render_week
from onemore.program.spec import Day, Pct, Sets, Slot, Week, WeekKind
from onemore.units import to_kg

CAT = Catalog.load()


def _week(*lifts):
    return Week(1, WeekKind.WORK,
                (Day("Day A", tuple(Slot(l, (Sets(3, 5, Pct(1.0)),)) for l in lifts)),))


def _loads(rw):
    from onemore.program.render import fmt_load
    return {s.lift: fmt_load(s.prescribed[0], rw.unit, rw.step(s.lift))
            for d in rw.days for s in d.slots}


def test_each_exercise_rounds_to_its_own_step_not_one_global_constant():
    """The leg press moves in 5 lb, the machine curl in 2.5 and the pulldown in 10.
    A single rounding constant is wrong for at least two of the three."""
    lifts = ["leg_press", "machine_bicep_curl", "lat_pulldown"]
    states = {l: {"tm_kg": to_kg(103, "lb")} for l in lifts}
    rw = render_week(_week(*lifts), states, CAT, unit="lb")
    got = _loads(rw)
    assert got["leg_press"] == "105 lb"          # 103 -> nearest 5
    assert got["machine_bicep_curl"] == "102.5 lb"  # 103 -> nearest 2.5
    assert got["lat_pulldown"] == "100 lb"       # 103 -> nearest 10


def test_rounding_happens_in_the_render_unit_so_it_lands_on_the_stack():
    """A 5 lb stack expressed in kg is 2.268 kg apart. Rounding the kg value to a
    kg-converted step and converting back lands between the pins; converting first
    does not. The kg rendering must be the exact kg value of a real lb setting."""
    from onemore.units import round_load

    states = {"leg_press": {"tm_kg": to_kg(103, "lb")}}
    rw = render_week(_week("leg_press"), states, CAT, unit="kg")
    p = rw.days[0].slots[0].prescribed[0]
    # Compared before formatting: fmt_load prints with %g, which is a display rounding.
    kg = round_load(p.load_kg, "kg", rw.step("leg_press"))
    assert kg == pytest.approx(to_kg(105, "lb"), abs=1e-6)


def test_an_exercise_without_a_catalog_step_takes_the_fallback():
    states = {"no_such_exercise": {"tm_kg": to_kg(103, "lb")}}
    rw = render_week(_week("no_such_exercise"), states, CAT, unit="lb", fallback_step_lb=10)
    assert _loads(rw)["no_such_exercise"] == "100 lb"


def test_reps_delta_reaches_the_prescription():
    """dumbbell_ceiling's reps half is only real if the renderer reads reps_delta."""
    assert bump_reps(8, 2) == 10
    assert bump_reps((8, 12), 2) == (10, 14)
    assert bump_reps((8, 12), 0) == (8, 12)

    w = Week(1, WeekKind.WORK,
             (Day("A", (Slot("dumbbell_bench_press", (Sets(3, (8, 12), Pct(1.0)),)),)),))
    rw = render_week(w, {"dumbbell_bench_press": {"tm_kg": to_kg(70, "lb"), "reps_delta": 2}},
                     CAT, unit="lb")
    p = rw.days[0].slots[0].prescribed[0]
    assert p.reps == (10, 14)
