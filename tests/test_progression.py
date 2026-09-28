"""The training-max rules and the week-scheduling rule, on synthetic sets."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from onemore import engine, estimate
from onemore.exercises import Catalog
from onemore.model import ExerciseEntry, Session, Set, SetType
from onemore.program.programs import comeback
from onemore.program.spec import Day, LiftSpec, Pct, Program, Sets, Slot, Week, WeekKind
from onemore.rules import DEFAULT_RULES
from onemore.rules.base import Context
from onemore.rules.progression import calibrate_tm, e1rm_ceiling, e1rm_refresh, tm_progress
from onemore.rules.schedule import missed_week_repeat
from onemore.units import to_kg

CAT = Catalog.load()
LIFT = "leg_press"  # step 5 lb, no ceiling
TM = to_kg(200, "lb")
STEP = to_kg(5, "lb")


def lb(x):
    return to_kg(x, "lb")


def session(sets_by_lift: dict[str, list[tuple[float, int]]], key="k1", day=2) -> Session:
    entries = []
    for lift, sets in sets_by_lift.items():
        entries.append(ExerciseEntry(lift, len(entries), [
            Set(i, SetType.WORK, lb(w), reps, source_ref=f"{lift}:{key}:{i}")
            for i, (w, reps) in enumerate(sets)]))
    return Session("strong", key, datetime(2026, 9, day, 18, tzinfo=UTC), entries=entries)


def top_slot(top_reps=5, top_pct=0.85, back=(4, 12, 0.65)) -> Slot:
    return Slot(LIFT, (Sets(1, top_reps, Pct(top_pct), amrap=True),
                       Sets(back[0], back[1], Pct(back[2]))))


def ctx(week: Week, sessions, states=None, program: Program | None = None,
        history=None) -> Context:
    prog = program or Program("t", {LIFT: LiftSpec(LIFT)}, [week], list(DEFAULT_RULES))
    return Context(program=prog, week_no=week.number, week=week, start=date(2026, 9, 1),
                   end=date(2026, 9, 8), sessions=sessions, states=states or {},
                   catalog=CAT, history=history)


def work_week(*slots: Slot, number=2) -> Week:
    return Week(number, WeekKind.WORK, tuple(Day(f"D{i}", (s,)) for i, s in enumerate(slots)))


def by_field(adjs, lift=LIFT):
    return {a.field: a for a in adjs if a.lift == lift}


# -- calibrate_tm -------------------------------------------------------------------------


def test_calibration_sets_the_tm_from_the_weeks_best_set():
    week = Week(1, WeekKind.CALIBRATION, (Day("L1", (
        Slot(LIFT, (Sets(1, 5, Pct(0.72, of="e1rm"), amrap=True),)),)),))
    adjs = calibrate_tm(ctx(week, [session({LIFT: [(130, 5), (145, 9)]})]))
    a = by_field(adjs)["tm_kg"]
    assert a.new == pytest.approx(estimate.epley(lb(145), 9) * 0.9)
    assert a.evidence == ("leg_press:k1:1",), "the top set, by name"
    assert a.rule == "calibrate_tm"


def test_calibration_is_silent_outside_the_seeded_week_and_for_untrained_lifts():
    assert calibrate_tm(ctx(work_week(top_slot()), [session({LIFT: [(145, 9)]})])) == []
    week = Week(1, WeekKind.CALIBRATION, (Day("L1", (top_slot(),)),))
    assert calibrate_tm(ctx(week, [])) == []


# -- tm_progress --------------------------------------------------------------------------


def test_two_reps_over_target_add_one_load_step():
    """85 % of a 200 lb TM is 170 lb; 7 reps against a target of 5 earns the step."""
    adjs = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(170, 7)]})],
                           {LIFT: {"tm_kg": TM}}))
    a = by_field(adjs)["tm_kg"]
    assert a.rule == "tm_progress"
    assert a.new == pytest.approx(TM + STEP)
    assert a.evidence == ("leg_press:k1:0",)


def test_hitting_the_target_without_two_spare_holds_and_says_why():
    adjs = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(170, 6)]})],
                           {LIFT: {"tm_kg": TM}}))
    a = by_field(adjs)["tm_kg"]
    assert a.rule == "tm_hold" and a.new == a.old == TM
    assert "not +2" in a.reason


def test_two_consecutive_misses_cut_the_tm_ten_percent():
    first = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(170, 3)]})],
                            {LIFT: {"tm_kg": TM}}))
    assert [a.rule for a in first] == ["tm_miss"]
    assert by_field(first)["misses"].new == 1
    second = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(170, 3)]})],
                             {LIFT: {"tm_kg": TM, "misses": 1}}))
    f = by_field(second)
    assert f["tm_kg"].rule == "tm_reduce" and f["tm_kg"].new == pytest.approx(TM * 0.9)
    assert f["misses"].new == 0, "the streak is consumed by the cut"


def _with_note(sess: Session, note: str) -> Session:
    sess.entries[0].notes = note
    return sess


def test_a_set_stopped_for_pain_holds_and_is_not_a_miss():
    note = "My elbow couldn’t take much weight today before it began to hurt"
    adjs = tm_progress(ctx(work_week(top_slot()),
                           [_with_note(session({LIFT: [(170, 3)]}), note)],
                           {LIFT: {"tm_kg": TM, "misses": 1}}))
    f = by_field(adjs)
    assert f["tm_kg"].rule == "tm_pain_hold" and f["tm_kg"].new == f["tm_kg"].old == TM
    assert "misses" not in f, "a pain week neither extends nor resets the streak"
    assert note in f["tm_kg"].reason and f["tm_kg"].evidence


def test_a_note_without_pain_leaves_a_short_set_a_miss():
    adjs = tm_progress(ctx(work_week(top_slot()),
                           [_with_note(session({LIFT: [(170, 3)]}), "machine was taken")],
                           {LIFT: {"tm_kg": TM}}))
    assert [a.rule for a in adjs] == ["tm_miss"]


def test_a_success_resets_the_miss_streak():
    adjs = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(170, 8)]})],
                           {LIFT: {"tm_kg": TM, "misses": 1}}))
    assert by_field(adjs)["misses"].new == 0


def test_a_week_of_backoffs_only_is_a_miss_however_many_reps_they_had():
    """Regression: the heaviest logged set was judged on reps alone, so a skipped top set
    left four backoff sets of twelve at 65 % to read as a two-reps-over success."""
    adjs = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(130, 12)] * 4})],
                           {LIFT: {"tm_kg": TM}}))
    assert [a.rule for a in adjs] == ["tm_miss"]
    assert "under the prescribed" in adjs[0].reason


def test_a_top_set_rounded_down_to_the_step_still_counts():
    """The plan prints the rounded load, so a set one rounding step under the exact
    percentage is the prescribed set, not a downgrade."""
    adjs = tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(165, 7)]})],
                           {LIFT: {"tm_kg": TM}}))
    assert by_field(adjs)["tm_kg"].rule == "tm_progress"


def test_a_phase_offset_week_is_judged_on_its_heaviest_top_set():
    """Two days, two schemes: a 5+ at 85 % and a 1+ at 95 %. The week's top set is the
    single, and its reps are read against the single's target, not the five."""
    week = work_week(top_slot(5, 0.85), top_slot(1, 0.95, back=(4, 4, 0.85)))
    sessions = [session({LIFT: [(170, 9)]}, key="d1", day=2),
                session({LIFT: [(190, 1)]}, key="d2", day=4)]
    adjs = tm_progress(ctx(week, sessions, {LIFT: {"tm_kg": TM}}))
    a = by_field(adjs)["tm_kg"]
    assert a.rule == "tm_hold", "one rep hit the single's target of one; the nine at 85 % do not vote"
    assert a.evidence == ("leg_press:d2:0",)
    sessions[1] = session({LIFT: [(190, 3)]}, key="d2", day=4)
    assert by_field(tm_progress(ctx(week, sessions, {LIFT: {"tm_kg": TM}})))["tm_kg"].rule == "tm_progress"


def test_a_phase_offset_week_with_one_day_trained_is_judged_on_that_days_top_set():
    """The single's day was skipped, so the 5+ is the only top set attempted: nine reps
    at 85 % is progress, not a miss against a single nobody did."""
    week = work_week(top_slot(5, 0.85), top_slot(1, 0.95, back=(4, 4, 0.85)))
    adjs = tm_progress(ctx(week, [session({LIFT: [(170, 9)]})], {LIFT: {"tm_kg": TM}}))
    assert by_field(adjs)["tm_kg"].rule == "tm_progress"


CURL = "leg_curl"


def _two_lower_days() -> Week:
    """`comeback`'s lower pair: the leg curl's top set leads Lower 2, and Lower 1 carries
    it as three light straight sets after the leg press."""
    light = Slot(CURL, (Sets(3, 8, Pct(0.5)),))
    top = Slot(CURL, (Sets(1, 8, Pct(0.85), amrap=True), Sets(3, 12, Pct(0.65))))
    return Week(3, WeekKind.WORK, (Day("Lower 1", (top_slot(), light)),
                                   Day("Lower 2", (top, Slot(LIFT, (Sets(3, 8, Pct(0.6)),))))))


def _curl_ctx(sessions, states):
    week = _two_lower_days()
    prog = Program("t", {LIFT: LiftSpec(LIFT), CURL: LiftSpec(CURL)}, [week], list(DEFAULT_RULES))
    return ctx(week, sessions, states, program=prog)


def test_light_sets_on_another_day_are_not_a_miss_when_the_top_set_day_was_skipped():
    """Regression, week 3 of the live plan: Lower 2 was skipped and the leg curl's only
    sets were Lower 1's light ones, which read as a miss against Lower 2's top set."""
    states = {LIFT: {"tm_kg": TM}, CURL: {"tm_kg": lb(76), "misses": 1}}
    lower_1 = session({LIFT: [(170, 7)], CURL: [(45, 10)] * 3})
    adjs = tm_progress(_curl_ctx([lower_1], states))
    assert by_field(adjs, CURL) == {}, "untouched: no miss, and the streak is not reset"
    assert by_field(adjs)["tm_kg"].rule == "tm_progress", "Lower 1's own top set still counts"


def test_skipping_the_top_set_on_its_own_day_is_still_a_miss():
    states = {LIFT: {"tm_kg": TM}, CURL: {"tm_kg": lb(76)}}
    lower_2 = session({CURL: [(45, 12)] * 3, LIFT: [(120, 8)] * 3})
    adjs = tm_progress(_curl_ctx([lower_2], states))
    assert by_field(adjs, CURL)["misses"].rule == "tm_miss"


def test_a_session_is_the_day_whose_main_lift_it_reaches_first():
    """Regression: a Lower 2 session also holds the leg press, and was matched to Lower 1
    because Lower 1 comes first in the week and was still unmatched."""
    c = _curl_ctx([session({CURL: [(65, 8)], LIFT: [(120, 8)]})], {})
    assert [d.name for d in c.logged_days()] == ["Lower 2"]
    c = _curl_ctx([session({LIFT: [(170, 5)], CURL: [(45, 10)]})], {})
    assert [d.name for d in c.logged_days()] == ["Lower 1"]


def test_tm_progress_leaves_deloads_calibration_and_untrained_lifts_alone():
    assert tm_progress(ctx(work_week(top_slot()), [], {LIFT: {"tm_kg": TM}})) == []
    deload = Week(5, WeekKind.DELOAD, (Day("D", (top_slot(),)),))
    assert tm_progress(ctx(deload, [session({LIFT: [(170, 12)]})], {LIFT: {"tm_kg": TM}})) == []
    assert tm_progress(ctx(work_week(top_slot()), [session({LIFT: [(170, 12)]})])) == []


# -- e1rm_refresh and e1rm_ceiling --------------------------------------------------------


def test_the_rolling_e1rm_reads_the_history_window_not_only_this_week():
    """Regression: the refresh read this week's sets only, so a week whose top set was a
    heavy single re-derived the ceiling from the single and clamped the TM."""
    old = session({LIFT: [(145, 9)]}, key="old", day=1)  # e1RM 188.5 lb, last week
    now = session({LIFT: [(180, 1)]}, key="now", day=4)  # e1RM 180 lb, this week
    week = work_week(top_slot(1, 0.95))
    a = by_field(e1rm_refresh(ctx(week, [now], history=[old, now])))["e1rm_kg"]
    assert a.new == pytest.approx(estimate.epley(lb(145), 9))
    assert a.evidence == ("leg_press:old:0",)
    only_now = by_field(e1rm_refresh(ctx(week, [now])))["e1rm_kg"]
    assert only_now.new == pytest.approx(lb(180)), "with no history the week is all there is"


def test_an_earned_step_survives_the_ceiling():
    """Calibration puts the TM at 0.9 x e1RM. A 5+ at 85 % of TM that beats its target
    by two implies, by Epley, an e1RM below the seed — so a 0.9 ceiling clamped every
    earned step straight back down. The ceiling is the e1RM itself."""
    e1 = estimate.epley(lb(145), 9)
    tm = e1 * 0.9
    states = {LIFT: {"tm_kg": tm + STEP, "e1rm_kg": e1}}
    assert e1rm_ceiling(ctx(work_week(top_slot()), [], states)) == []


def test_the_ceiling_clamps_a_tm_that_has_outrun_the_e1rm():
    states = {LIFT: {"tm_kg": lb(210), "e1rm_kg": lb(200)}}
    a = by_field(e1rm_ceiling(ctx(work_week(top_slot()), [], states)))["tm_kg"]
    assert a.new == pytest.approx(lb(200)) and "clamped" in a.reason


# -- missed_week_repeat -------------------------------------------------------------------


def _comeback_ctx(sessions):
    p = comeback.build(4)
    return ctx(p.week(2), sessions, program=p)


def _shared_lead_ctx(sessions):
    """Two lower days that both lead with the leg press, as the retired `rebuild` had.
    `comeback` leads every day with a distinct lift (test_comeback enforces it), so the
    matching this guards needs a layout that shares one."""
    def day(name, lead):
        return Day(name, (Slot(lead, (Sets(1, 5, Pct(0.8), amrap=True),)),))
    days = (day("Lower 1", "leg_press"), day("Upper 1", "chest_press"),
            day("Lower 2", "leg_press"), day("Upper 2", "machine_shoulder_press"))
    lifts = {x: LiftSpec(x) for x in ("leg_press", "chest_press", "machine_shoulder_press")}
    p = Program("shared_lead", lifts, [Week(2, WeekKind.WORK, days)], list(DEFAULT_RULES),
                days_per_week=4)
    return ctx(p.week(2), sessions, program=p)


def test_one_session_covering_three_main_lifts_is_one_day_trained():
    """Regression: days were counted by "was this day's main lift trained", so one
    circuit that hit the leg press counted both lower days, and a session with three
    upper mains counted two upper days."""
    circuit = session({"leg_press": [(200, 10)], "chest_press": [(100, 10)],
                       "machine_shoulder_press": [(60, 10)]})
    adjs = missed_week_repeat(_shared_lead_ctx([circuit]))
    assert [a.field for a in adjs] == ["week"]
    assert "1 of 4" in adjs[0].reason
    assert adjs[0].evidence == ("k1",)
    # comeback: one circuit hitting every day's lead lift is still one day trained.
    circuit = session({"leg_press": [(200, 10)], "chest_press": [(100, 10)],
                       "leg_curl": [(80, 10)], "seated_row": [(90, 10)]})
    adjs = missed_week_repeat(_comeback_ctx([circuit]))
    assert [a.field for a in adjs] == ["week"]
    assert "1 of 4" in adjs[0].reason
    assert adjs[0].evidence == ("k1",)


def test_two_sessions_on_two_planned_days_do_not_repeat_the_week():
    sessions = [session({"leg_press": [(200, 10)]}, key="a", day=2),
                session({"chest_press": [(100, 10)]}, key="b", day=4)]
    assert missed_week_repeat(_comeback_ctx(sessions)) == []


def test_two_lower_sessions_count_as_both_lower_days():
    sessions = [session({"leg_press": [(200, 10)]}, key="a", day=2),
                session({"leg_press": [(200, 10)]}, key="b", day=5)]
    assert missed_week_repeat(_shared_lead_ctx(sessions)) == []


# -- the contract every rule shares -------------------------------------------------------


def test_every_field_the_progression_rules_write_is_persisted_or_transient():
    written = set()
    scenarios = [
        (calibrate_tm, ctx(Week(1, WeekKind.CALIBRATION, (Day("L", (top_slot(),)),)),
                           [session({LIFT: [(145, 9)]})])),
        (tm_progress, ctx(work_week(top_slot()), [session({LIFT: [(170, 8)]})],
                          {LIFT: {"tm_kg": TM, "misses": 1}})),
        (tm_progress, ctx(work_week(top_slot()), [session({LIFT: [(170, 3)]})],
                          {LIFT: {"tm_kg": TM, "misses": 1}})),
        (e1rm_refresh, ctx(work_week(top_slot()), [session({LIFT: [(170, 8)]})])),
        (e1rm_ceiling, ctx(work_week(top_slot()), [],
                           {LIFT: {"tm_kg": lb(210), "e1rm_kg": lb(200)}})),
        (missed_week_repeat, ctx(work_week(top_slot()), [])),
    ]
    for rule, c in scenarios:
        fields = {a.field for a in rule(c)}
        assert fields, f"{rule.__name__} fired nothing; the scenario stopped exercising it"
        written |= fields
    assert written <= engine.PERSISTED_STATE | engine.TRANSIENT_FIELDS


# -- calibrate_new_lift -------------------------------------------------------------------


def test_a_main_lift_that_joins_mid_plan_gets_a_tm_from_its_first_work_week():
    """`calibrate_tm` runs only in the seeded week and the work weeks cycle, so a main lift
    added to a running plan would otherwise print "no tm yet" forever."""
    from onemore.rules.progression import calibrate_new_lift

    adjs = calibrate_new_lift(ctx(work_week(top_slot()), [session({LIFT: [(130, 5), (145, 9)]})]))
    a = by_field(adjs)["tm_kg"]
    assert a.rule == "calibrate_new_lift" and a.old is None
    assert a.new == pytest.approx(estimate.epley(lb(145), 9) * 0.9)
    assert a.evidence == ("leg_press:k1:1",)


def test_calibrate_new_lift_never_touches_an_existing_tm_or_an_untrained_lift():
    from onemore.rules.progression import calibrate_new_lift

    trained = [session({LIFT: [(145, 9)]})]
    assert calibrate_new_lift(ctx(work_week(top_slot()), trained, {LIFT: {"tm_kg": TM}})) == []
    assert calibrate_new_lift(ctx(work_week(top_slot()), [])) == []
    seeded = Week(1, WeekKind.CALIBRATION, (Day("L1", (top_slot(),)),))
    assert calibrate_new_lift(ctx(seeded, trained)) == [], "the seeded week is calibrate_tm's"


def test_the_week_that_sets_a_new_lifts_tm_is_not_also_judged_against_it():
    """Order matters: run before `tm_progress`, a 12-rep calibration set would also step
    the TM it had just set."""
    from onemore.rules.progression import calibrate_new_lift

    order = [r.__name__ for r in DEFAULT_RULES]
    assert order.index("tm_progress") < order.index("calibrate_new_lift")
    assert calibrate_new_lift in DEFAULT_RULES
