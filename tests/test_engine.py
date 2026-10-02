"""`advance()` end to end on an in-memory store: seed, calibrate, progress, repeat."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from onemore import engine, estimate
from onemore.exercises import Catalog
from onemore.model import ExerciseEntry, Session, Set, SetType
from onemore.program.programs import comeback
from onemore.program.render import render_week
from onemore.store import Store
from onemore.units import to_kg

CAT = Catalog.load()
START = date(2026, 9, 7)  # a Monday


def lb(x):
    return to_kg(x, "lb")


def log(store: Store, when: date, sets_by_lift: dict[str, list[tuple[float, int]]], key=None):
    key = key or f"{when}:{'+'.join(sets_by_lift)}"
    entries = [ExerciseEntry(lift, i, [Set(j, SetType.WORK, lb(w), r, source_ref=f"{key}:{lift}:{j}")
                                      for j, (w, r) in enumerate(sets)])
               for i, (lift, sets) in enumerate(sets_by_lift.items())]
    assert store.upsert_session(Session("strong", key, datetime.combine(when, datetime.min.time(),
                                                                         UTC), entries=entries))


@pytest.fixture
def started():
    store = Store(":memory:")
    prog = comeback.build(4)
    engine.start_plan(store, prog, START)
    return store, prog


def test_the_seeded_week_calibrates_the_tm_and_advances(started):
    store, prog = started
    # Two planned days trained: Lower 1 and Upper 1. calf_press is a comeback accessory.
    log(store, START + timedelta(days=1), {"leg_press": [(130, 5), (130, 5), (145, 9)],
                                           "calf_press": [(100, 12)]})
    log(store, START + timedelta(days=3), {"chest_press": [(90, 5), (100, 8)],
                                           "machine_lat_pulldown": [(100, 7)]})
    fired, status = engine.advance(store, prog, asof=START + timedelta(days=7), catalog=CAT)

    assert status.current_week == 2
    rules = {(a.rule, a.lift) for a in fired}
    assert ("calibrate_tm", "leg_press") in rules
    assert ("calibrate_tm", "chest_press") in rules
    assert ("e1rm_refresh", "calf_press") in rules, "accessories keep an e1RM too"
    assert ("missed_week_repeat", "*") not in rules
    assert store.get_state("leg_press", "tm_kg") == pytest.approx(estimate.epley(lb(145), 9) * 0.9)
    assert store.get_state("machine_shoulder_press", "tm_kg") is None, "not trained: unseeded"
    # The audit trail is queryable by week and names the set it read.
    cal = [a for a in store.adjustments(week=1) if a.rule == "calibrate_tm" and a.lift == "leg_press"]
    assert len(cal) == 1 and cal[0].evidence[0].endswith("leg_press:2")


def test_the_new_tm_reaches_the_next_weeks_plan(started):
    store, prog = started
    log(store, START + timedelta(days=1), {"leg_press": [(145, 9)]})
    log(store, START + timedelta(days=3), {"chest_press": [(100, 8)]})
    engine.advance(store, prog, asof=START + timedelta(days=7), catalog=CAT)
    tm = store.get_state("leg_press", "tm_kg")
    rw = render_week(engine.effective_week(prog, engine.plan_status(store), 2),
                     store.all_state(), CAT)
    top = next(s for d in rw.days for s in d.slots if s.lift == "leg_press").prescribed[0]
    assert top.amrap and top.reps == 8
    assert top.load_kg == pytest.approx(tm * 0.80)


def test_beating_the_top_set_by_two_moves_the_tm_one_step_and_the_ceiling_lets_it(started):
    store, prog = started
    log(store, START + timedelta(days=1), {"leg_press": [(145, 9)]})
    log(store, START + timedelta(days=3), {"chest_press": [(100, 8)]})
    engine.advance(store, prog, asof=START + timedelta(days=7), catalog=CAT)
    tm1 = store.get_state("leg_press", "tm_kg")

    def printed(pct):  # what the plan prints: the percentage on the 5 lb step
        return round(tm1 * pct / lb(5)) * 5

    # Week 2: Lower 1 is the 8+ at 80 %, beaten by two; Lower 2 (led by the leg curl)
    # repeats the leg press as a lighter secondary with no AMRAP, which must not be what
    # the week is judged on. (Two AMRAPs at two loads: test_progression's phase-offset test.)
    log(store, START + timedelta(days=8), {"leg_press": [(printed(0.80), 10), (printed(0.65), 12)]})
    log(store, START + timedelta(days=10), {"chest_press": [(100, 6)]})
    log(store, START + timedelta(days=12), {"leg_curl": [(80, 8)],
                                            "leg_press": [(printed(0.62), 10)]})
    fired, status = engine.advance(store, prog, asof=START + timedelta(days=14), catalog=CAT)

    assert status.current_week == 3
    prog_adj = [a for a in fired if a.rule == "tm_progress" and a.lift == "leg_press"
                and a.field == "tm_kg"]
    assert len(prog_adj) == 1
    assert prog_adj[0].new == pytest.approx(tm1 + lb(5))
    assert not any(a.rule == "e1rm_ceiling" for a in fired), (
        "the ceiling must not undo an earned step: the calibration set is inside the window")
    assert store.get_state("leg_press", "tm_kg") == pytest.approx(tm1 + lb(5))


def test_a_missed_week_repeats_and_shifts_the_schedule(started):
    store, prog = started
    log(store, START + timedelta(days=1), {"leg_press": [(145, 9)]})  # one day of four
    fired, status = engine.advance(store, prog, asof=START + timedelta(days=7), catalog=CAT)
    assert [a.rule for a in fired if a.lift == "*"] == ["missed_week_repeat"]
    assert status.current_week == 1
    assert status.started_on == START + timedelta(days=7)
    assert store.get_state("leg_press", "tm_kg") is None, "nothing downstream ran"


def test_a_repeat_leaves_every_closed_week_on_the_dates_it_was_trained(started):
    """A repeat moves `started_on`, and week 1's dates used to move with it -- so the page
    re-read week 2's log as week 1's. Each closed week keeps the window it closed on, and
    the plan still began on START."""
    store, prog = started
    log(store, START + timedelta(days=1), {"leg_press": [(145, 9)]})
    log(store, START + timedelta(days=3), {"chest_press": [(100, 8)]})
    _, status = engine.advance(store, prog, asof=START + timedelta(days=7), catalog=CAT)
    assert status.current_week == 2
    _, status = engine.advance(store, prog, asof=START + timedelta(days=14), catalog=CAT)
    assert status.current_week == 2 and status.started_on == START + timedelta(days=7)
    assert engine.week_window(status, 1) == (START, START + timedelta(days=7))
    assert engine.week_window(status, 2) == (START + timedelta(days=14),
                                             START + timedelta(days=21))


def test_a_plan_closed_before_windows_were_recorded_is_backfilled(started):
    """Weeks closed before the record existed are pinned at the next advance, from
    `started_on`, before a repeat can move it."""
    store, prog = started
    p = store.get_plan("plan")
    store.set_plan("plan", {**p, "current_week": 3})  # weeks 1-2 closed, nothing recorded
    _, status = engine.advance(store, prog, asof=START + timedelta(days=21), catalog=CAT)
    assert status.current_week == 3, "nothing logged: week 3 repeats"
    assert engine.week_window(status, 1) == (START, START + timedelta(days=7))
    assert engine.week_window(status, 2) == (START + timedelta(days=7),
                                             START + timedelta(days=14))
    assert engine.week_window(status, 3)[0] == START + timedelta(days=21)


def test_advance_refuses_to_close_a_week_early(started):
    store, prog = started
    with pytest.raises(RuntimeError, match="--force"):
        engine.advance(store, prog, asof=START + timedelta(days=3), catalog=CAT)


def test_seed_from_history_covers_accessories_and_decays_old_data():
    store = Store(":memory:")
    prog = comeback.build(4)
    today = date.today()
    log(store, today - timedelta(days=400), {"leg_curl": [(100, 10)], "leg_press": [(200, 8)]})
    log(store, today - timedelta(days=10), {"chest_press": [(100, 8)]})
    seeded = {a.lift: a for a in engine.seed_from_history(store, prog, "lb")}
    assert seeded["leg_curl"].new == pytest.approx(estimate.epley(lb(100), 10) * 0.8)
    assert "decay" in seeded["leg_curl"].reason
    assert seeded["chest_press"].new == pytest.approx(estimate.epley(lb(100), 8))
    assert "recent" in seeded["chest_press"].reason
    assert "lateral_raise" not in seeded, "no history, no seed"
    assert store.get_state("leg_press", "e1rm_kg") == pytest.approx(seeded["leg_press"].new)
    assert all(a.rule == "seed_from_history" for a in store.adjustments(week=0))


def test_a_plan_stored_under_a_retired_program_reads_as_the_default():
    """`rebuild` was retired 2026-09-21 and the live db could not be checked for a plan
    naming it. Every caller indexes PROGRAMS by the stored name, so it must not KeyError."""
    from onemore.program.programs import DEFAULT_PROGRAM, PROGRAMS

    store = Store(":memory:")
    store.set_plan("plan", {"program": "rebuild", "days": 3, "started_on": "2026-09-07",
                            "current_week": 2, "deload_next": False})
    st = engine.plan_status(store)
    assert st.program == DEFAULT_PROGRAM and st.current_week == 2
    assert PROGRAMS[st.program](st.days).name == DEFAULT_PROGRAM
