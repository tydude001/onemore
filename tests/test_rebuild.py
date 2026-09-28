"""`rebuild` as a program: at this gym, off a rep count only, shaped like the DUP sheet."""

from __future__ import annotations

import pytest

from onemore.exercises import Catalog
from onemore.program.programs import rebuild
from onemore.program.render import fmt_load, render_week
from onemore.program.spec import Pct, Rpe, WeekKind
from onemore.units import to_kg

CAT = Catalog.load()


def _every_set(program):
    for w in program.weeks:
        for d in w.days:
            for slot in d.slots:
                for s in slot.sets:
                    yield w, d, slot, s


def _top(program, week_no, day_idx=0):
    slot = program.week(week_no).days[day_idx].slots[0]
    return next(s for s in slot.sets if s.amrap), next(s for s in slot.sets if not s.amrap)


@pytest.mark.parametrize("days", [3, 4])
def test_every_prescribed_lift_exists_and_is_at_this_gym(days):
    p = rebuild.build(days)
    assert p.unavailable(CAT) == []
    for _, _, slot, _ in _every_set(p):
        assert slot.lift in p.lifts, f"{slot.lift} is prescribed but not declared"
        assert CAT.get(slot.lift) is not None, f"{slot.lift} is not in the catalog"


@pytest.mark.parametrize("days", [3, 4])
def test_nothing_reads_rpe(days):
    """Three of 2532 logged sets carry an RPE (PLAN.md § RPE is not logged)."""
    assert not any(isinstance(s.load, Rpe) for *_, s in _every_set(rebuild.build(days)))


@pytest.mark.parametrize("days", [3, 4])
def test_every_main_lift_has_an_amrap_top_set_every_work_week(days):
    p = rebuild.build(days)
    for n in range(1, len(p.weeks) + 1):
        w = p.week(n)
        if w.kind == WeekKind.DELOAD:
            continue
        for lift in p.main_lifts():
            sets = [s for slot in w.slots_for(lift) for s in slot.sets]
            assert sets, f"{lift} is missing from week {n}"
            assert any(s.amrap for s in sets), f"{lift} has no AMRAP in week {n}"


def test_week_one_is_seeded_off_e1rm_and_work_weeks_off_tm():
    """There is no TM before week 1; the seeded week resolves against the decayed
    historical e1RM and `calibrate_tm` sets the TM from its top set."""
    p = rebuild.build(4)
    w1 = p.week(1)
    assert w1.kind == WeekKind.CALIBRATION
    for lift in p.main_lifts():
        for s in (s for slot in w1.slots_for(lift) for s in slot.sets):
            assert isinstance(s.load, Pct) and s.load.of == "e1rm"
    for n in range(2, len(p.weeks) + 1):
        for lift in p.main_lifts():
            for s in (s for slot in p.week(n).slots_for(lift) for s in slot.sets):
                assert isinstance(s.load, Pct) and s.load.of == "tm", (n, lift)


def test_the_wave_is_the_dup_sheets():
    """5RM / 1RM / 3RM top sets at 85 / 95 / 90 with 4x12 / 4x4 / 4x8 backoffs at
    65 / 85 / 75 — docs/research/dup-spreadsheet.md."""
    got = []
    for n in (2, 3, 4):
        top, back = _top(rebuild.build(4), n)
        got.append((top.reps, top.load.value, back.n, back.reps, back.load.value))
    assert got == [(5, 0.85, 4, 12, 0.65), (1, 0.95, 4, 4, 0.85), (3, 0.90, 4, 8, 0.75)]


def test_the_two_leg_press_days_are_phase_offset():
    p = rebuild.build(4)
    for n in (2, 3, 4):
        (a, _), (b, _) = _top(p, n, 0), _top(p, n, 2)
        assert a.reps != b.reps, f"week {n}: both lower days run the {a.reps}RM scheme"


def test_percentages_creep_between_blocks_and_reset_when_the_program_cycles():
    p = rebuild.build(4)

    def pcts(n):
        top, back = _top(p, n)
        return top.load.value, back.load.value

    b1, b2, b3 = pcts(2), pcts(6), pcts(10)
    assert b2 == pytest.approx((b1[0] + 0.015, b1[1] + 0.010))
    assert b3 == pytest.approx((b1[0] + 0.030, b1[1] + 0.020))
    assert p.week(14).kind == WeekKind.WORK
    assert pcts(14) == b1, "past the defined weeks the creep restarts against the new TM"


def test_a_deload_follows_every_block():
    kinds = [w.kind for w in rebuild.build(4).weeks]
    block = [WeekKind.WORK] * 3 + [WeekKind.DELOAD]
    assert kinds == [WeekKind.CALIBRATION] + block * 3


def test_rendered_loads_round_on_each_lifts_own_step():
    p = rebuild.build(4)
    tm = to_kg(180, "lb")  # 85 % = 153 lb
    rw = render_week(p.week(2), {lift: {"tm_kg": tm} for lift in p.lifts}, CAT)
    lower1, upper1 = rw.days[0].slots[0], rw.days[1].slots[1]
    assert (lower1.lift, upper1.lift) == ("leg_press", "lat_pulldown")
    assert fmt_load(lower1.prescribed[0], "lb", rw.step("leg_press")) == "155 lb"
    assert fmt_load(upper1.prescribed[0], "lb", rw.step("lat_pulldown")) == "150 lb"


def test_an_unseeded_lift_says_so_instead_of_printing_bodyweight():
    """Regression: a percent-of-TM set with no TM rendered as "bodyweight"."""
    rw = render_week(rebuild.build(4).week(1), {}, CAT)
    slot = next(s for d in rw.days for s in d.slots if s.lift == "machine_shoulder_press")
    text = fmt_load(slot.prescribed[0], "lb", 5)
    assert "no e1rm yet" in text and "bodyweight" not in text


def test_every_set_carries_a_rest_and_every_main_lift_a_warm_up_ramp():
    p = rebuild.build(4)
    for w, _, slot, s in _every_set(p):
        assert s.rest_s, f"{slot.lift} in week {w.number} has no rest prescribed"
        if s.amrap and slot.lift in p.main_lifts():
            # The top-set slot ramps; the same lift as the secondary press at 60 % does not.
            assert slot.warmup is not None, f"{slot.lift} in week {w.number} has no ramp"
    top = next(s for s in p.week(2).days[0].slots[0].sets if s.amrap)
    assert top.rest_s == rebuild.REST_TOP


def test_warm_ups_render_on_the_lifts_step_below_the_working_load():
    """Ramp fractions of the 5+ top set at 85 % of a 180 lb TM (153 -> 155 lb): 50 / 70 /
    85 % round on the 5 lb leg-press step to 75, 105, 130; the pulldown's 10 lb step
    gives 80, 110, 130. Nothing may print at or above the working load."""
    from onemore.program.render import fmt_warmup, to_text

    p = rebuild.build(4)
    rw = render_week(p.week(2), {lift: {"tm_kg": to_kg(180, "lb")} for lift in p.lifts}, CAT)
    lp, pd = rw.days[0].slots[0], rw.days[1].slots[1]
    assert fmt_warmup(lp.warmup, lp.prescribed[0].load_kg, "lb", rw.step("leg_press")) == "75x8, 105x5, 130x3"
    assert fmt_warmup(pd.warmup, pd.prescribed[0].load_kg, "lb", rw.step("lat_pulldown")) == "80x8, 110x5, 130x3"
    text = to_text(rw, header="bw 182.4 lb")
    assert "1x5+ 155 lb (rest 3:00), 4x12 115 lb (rest 2:00)" in text
    assert "      warm-up: 75x8, 105x5, 130x3" in text
    assert text.split("\n")[1] == "bw 182.4 lb"


def test_a_ramp_with_nothing_to_resolve_against_prints_nothing():
    from onemore.program.render import fmt_warmup

    rw = render_week(rebuild.build(4).week(2), {}, CAT)
    lp = rw.days[0].slots[0]
    assert lp.warmup is None and fmt_warmup(lp.warmup, None, "lb", 5) == ""
    # A tiny working load (in kg here, as the renderer holds it): 2 lb rounds to nothing,
    # 3 lb to the 5 lb pin, 5 lb to the same pin again — one rung survives under a 10 lb
    # working set, and none at all when the working set is itself the bottom pin.
    lb = lambda x: to_kg(x, "lb")
    assert fmt_warmup([(lb(2), 8), (lb(3), 5), (lb(5), 3)], lb(12), "lb", 5) == "5x5"
    assert fmt_warmup([(lb(2), 8), (lb(3), 5), (lb(5), 3)], lb(6), "lb", 5) == ""
