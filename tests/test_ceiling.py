"""`dumbbell_ceiling`: when load cannot rise, progress is reps and then a set."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from onemore import engine
from onemore.exercises import Catalog
from onemore.model import ExerciseEntry, Session, Set, SetType
from onemore.program.spec import Day, LiftSpec, Program, Rpe, Sets, Slot, Week, WeekKind
from onemore.rules.base import Context
from onemore.rules.ceiling import REP_CAP, SET_CAP, dumbbell_ceiling
from onemore.units import to_kg

CAT = Catalog.load()
LIFT = "dumbbell_bench_press"  # ceiling_lb = 80, step_lb = 5
NO_CEILING = "leg_press"  # a pin stack whose top nobody has read off the machine


def _program(lift=LIFT):
    week = Week(1, WeekKind.WORK,
                (Day("A", (Slot(lift, (Sets(3, (8, 12), Rpe(8)),)),)),))
    return Program("t", {lift: LiftSpec(lift, main=False)}, [week], [dumbbell_ceiling])


def _ctx(lift=LIFT, lb=80, reps=12, n=3, states=None):
    prog = _program(lift)
    sets = [Set(i, SetType.WORK, to_kg(lb, "lb"), reps, source_ref=f"s{i}") for i in range(n)]
    sess = Session("strong", "k1", datetime(2026, 9, 1, 18, tzinfo=UTC), entries=[
        ExerciseEntry(lift, 0, sets)])
    return Context(program=prog, week_no=1, week=prog.weeks[0], start=date(2026, 9, 1),
                   end=date(2026, 9, 8), sessions=[sess], states=states or {}, catalog=CAT)


def _by_field(adjs):
    return {a.field: a for a in adjs}


def test_at_the_rack_ceiling_with_reps_hit_it_adds_a_rep_not_load():
    adjs = dumbbell_ceiling(_ctx())
    f = _by_field(adjs)
    assert f["reps_delta"].new == 1
    assert f["at_ceiling"].new == 1
    assert not any(a.field == "tm_kg" for a in adjs), "load must never rise at the ceiling"
    assert "80 lb" in f["reps_delta"].reason
    assert f["reps_delta"].evidence == ("s0", "s1", "s2"), "must name the sets it read"


def test_carried_reps_convert_to_a_set_at_the_cap():
    # With REP_CAP carried the plan prints 8+3 to 12+3, so the cap is earned at 15 reps.
    adjs = dumbbell_ceiling(_ctx(reps=12 + REP_CAP,
                                 states={LIFT: {"reps_delta": REP_CAP, "at_ceiling": 1}}))
    f = _by_field(adjs)
    assert f["sets_delta"].new == 1
    assert f["reps_delta"].new == 0, "the carried reps are consumed by the added set"


def test_reps_short_of_the_target_change_nothing():
    """Still earning the reps at this load: no adjustment beyond noting the ceiling."""
    adjs = dumbbell_ceiling(_ctx(reps=9))
    assert [a.field for a in adjs] == ["at_ceiling"]


def test_one_set_short_of_the_target_blocks_the_whole_progression():
    ctx = _ctx()
    ctx.sessions[0].entries[0].sets[1] = Set(1, SetType.WORK, to_kg(80, "lb"), 10,
                                             source_ref="s1")
    assert [a.field for a in dumbbell_ceiling(ctx)] == ["at_ceiling"]


def test_below_the_ceiling_the_rule_stays_out_of_the_way():
    """`at_ceiling` is emitted on a change only, so a lift that was never at the ceiling
    and still is not produces nothing at all rather than a no-op adjustment."""
    assert dumbbell_ceiling(_ctx(lb=50)) == []
    dropped = dumbbell_ceiling(_ctx(lb=50, states={LIFT: {"at_ceiling": 1}}))
    assert [a.field for a in dropped] == ["at_ceiling"]
    assert dropped[0].new == 0


def test_a_lift_with_no_known_ceiling_is_silent():
    """The heaviest logged load is a floor on a machine's stack top, not the stack top.
    Inventing one would stall a lift that had room left."""
    assert dumbbell_ceiling(_ctx(lift=NO_CEILING, lb=400)) == []


def test_a_training_max_above_the_ceiling_is_clamped_down_to_it():
    ctx = _ctx(states={LIFT: {"tm_kg": to_kg(95, "lb")}})
    tm = _by_field(dumbbell_ceiling(ctx))["tm_kg"]
    assert tm.new == pytest.approx(to_kg(80, "lb"))
    assert tm.old > tm.new


def test_within_half_a_step_of_the_ceiling_still_counts_as_at_it():
    """The rack has no 77.5 lb dumbbell; 78 lb logged is the 80 lb pair."""
    assert _by_field(dumbbell_ceiling(_ctx(lb=78)))["at_ceiling"].new == 1
    # 76 lb is more than half a 5 lb step below 80, so it is not the top pair. Seeded as
    # already-at-ceiling, because the rule reports the transition rather than the state.
    below = _by_field(dumbbell_ceiling(_ctx(lb=76, states={LIFT: {"at_ceiling": 1}})))
    assert below["at_ceiling"].new == 0


def test_every_state_key_the_rule_writes_is_one_the_engine_persists():
    """A rule writing state nothing round-trips changes the plan for one week and then
    forgets — silently. This is the assertion that would have caught it."""
    written = set()
    for ctx in (_ctx(),
                _ctx(reps=12 + REP_CAP, states={LIFT: {"reps_delta": REP_CAP}}),
                _ctx(states={LIFT: {"tm_kg": to_kg(95, "lb")}}),
                _ctx(reps=12 + REP_CAP,
                     states={LIFT: {"reps_delta": REP_CAP, "sets_delta": SET_CAP}})):
        written |= {a.field for a in dumbbell_ceiling(ctx)}
    assert written, "the rule fired nothing; the fixtures stopped exercising it"
    assert written <= engine.PERSISTED_STATE


def test_the_engine_refuses_state_it_cannot_persist():
    """The guard itself, so the assertion above cannot be defeated by a new rule."""
    from onemore.model import Adjustment

    a = Adjustment("made_up_rule", LIFT, "invented_key", 0, 1, "…")
    with pytest.raises(ValueError, match="which nothing persists"):
        engine._apply(None, _ctx(), a)


def test_the_rep_target_rises_with_the_carried_reps():
    """Regression: the rule read the spec's rep target and ignored `reps_delta`, so the
    same 12 reps that earned the first extra rep earned the second and third too. The
    ladder has to be re-earned at the prescription the plan actually printed."""
    # reps_delta 1 means the plan says 9-13, so 12 is now short of the target.
    assert dumbbell_ceiling(_ctx(reps=12, states={LIFT: {"reps_delta": 1, "at_ceiling": 1}})) == []
    # 13 earns the next rep.
    got = _by_field(dumbbell_ceiling(
        _ctx(reps=13, states={LIFT: {"reps_delta": 1, "at_ceiling": 1}})))
    assert got["reps_delta"].new == 2


def test_a_deload_week_does_not_ratchet_the_ceiling_progression():
    """Accessories keep their RPE prescription through a deload, so without a guard the
    rule would earn another rep during the week meant to shed fatigue."""
    ctx = _ctx()
    ctx.week = Week(1, WeekKind.DELOAD, ctx.week.days, "deload")
    assert dumbbell_ceiling(ctx) == []
