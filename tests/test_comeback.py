"""`comeback` as a program: the elbow constraints, the two-speed progression, and the
percentage floor the ceiling arithmetic imposes.

Most of these tests exist to stop a *well-meaning* future edit. "Add a curl back, the gym
has one", "drop the upper top set to 70 %, it's safer" and "make the isolation work
lighter" all look like improvements, and all three undo something load-bearing. The
reasons are in docs/research/radial-head-return.md; these are the tripwires.
"""

from __future__ import annotations

import pytest

from onemore import estimate
from onemore.exercises import Catalog
from onemore.program.programs import PROGRAMS, comeback
from onemore.program.spec import Pct, Rpe, WeekKind

CAT = Catalog.load()


def _every_set(program):
    for w in program.weeks:
        for d in w.days:
            for slot in d.slots:
                for s in slot.sets:
                    yield w, d, slot, s


@pytest.fixture(scope="module")
def p():
    return comeback.build(4)


# --- shape ---------------------------------------------------------------------------

def test_every_prescribed_lift_exists_and_is_at_this_gym(p):
    assert p.unavailable(CAT) == []
    for _, _, slot, _ in _every_set(p):
        assert slot.lift in p.lifts, f"{slot.lift} is prescribed but not declared"
        assert CAT.get(slot.lift) is not None, f"{slot.lift} is not in the catalog"


def test_nothing_reads_rpe(p):
    """PLAN.md § RPE is not logged: 3 of 2532 logged sets carry one."""
    assert not any(isinstance(s.load, Rpe) for *_, s in _every_set(p))


def test_only_four_days_is_supported():
    with pytest.raises(ValueError):
        comeback.build(3)


def test_each_day_leads_with_a_distinct_lift(p):
    """`missed_week_repeat` matches a logged session to a planned day by that day's first
    slot. Two days sharing one undercounts the week and fires a spurious repeat --
    PLAN.md records `rebuild`'s three-day layout doing exactly this."""
    for n in range(1, len(p.weeks) + 1):
        leads = [d.main_lift for d in p.week(n).days]
        assert len(set(leads)) == len(leads), f"week {n} has duplicate lead lifts: {leads}"


# --- the elbow constraints -----------------------------------------------------------

# Every one of these is in the program for a documented clinical reason. See the research
# doc before deleting an entry; do not add one back because the gym has the machine.
BANNED = {
    "captains_chair_knee_raise": "hangs bodyweight through the forearms, pressure on the olecranon",
    "preacher_curl": "loads the elbow at maximum flexion; positive Tinel's at the cubital tunnel",
    "tricep_pushdown": "finishes in terminal extension, the 0-30 deg peak-load window",
    "triceps_extension_machine": "direct triceps pull on a fractured olecranon",
    "tricep_press_machine": "direct triceps pull on a fractured olecranon",
    "skullcrusher": "deep flexion plus a direct olecranon pull",
    "barbell_bicep_curl": "supinated; loaded supination is a documented aggravator",
    "bicep_curl": "supinated; loaded supination is a documented aggravator",
    "machine_bicep_curl": "supinated; loaded supination is a documented aggravator",
    "dumbbell_bench_press": "carrying the dumbbells is the documented 'carrying heavier objects'",
    "smith_squat": "hard grip, flexed elbows, under a bar, with a fall risk",
    "pull_up": "bodyweight through a flexed elbow with a sustained grip",
    "chin_up": "bodyweight through a supinated, flexed elbow",
    "dip": "full bodyweight into terminal elbow extension",
    "push_up": "axial load through a near-straight arm, the exact aggravator",
}


@pytest.mark.parametrize("lift,why", sorted(BANNED.items()))
def test_contraindicated_movements_are_absent(p, lift, why):
    assert lift not in p.lifts, f"{lift} is contraindicated here: {why}"
    for _, _, slot, _ in _every_set(p):
        assert slot.lift != lift, f"{lift} is prescribed: {why}"


def test_every_press_slot_warns_about_lockout(p):
    """Movement rule 1, and the highest-value instruction in the program: the radial head
    takes 50-60 % of the elbow's axial load and transmission peaks at 0-30 deg of flexion.
    If the note is missing the lifter is never told."""
    presses = {"chest_press", "machine_shoulder_press"}
    for w, _, slot, _ in _every_set(p):
        if slot.lift in presses:
            assert "lockout" in slot.note, f"week {w.number} {slot.lift} has no lockout note"


def test_no_direct_arm_work_in_block_one(p):
    """Neither curls nor triceps isolation. The biceps inserts on the radial tuberosity
    just below the fractured radial head and the triceps on the fractured olecranon, so
    both isolation families pull directly on injured bone. The rows and pulldowns already
    load elbow flexion, and OT is already prescribing loaded flexion isometrics. Direct
    arm work is a block 2 decision, after the re-evaluation."""
    arms = [sl.lift for _, _, sl, _ in _every_set(p)
            if ("curl" in sl.lift and "leg" not in sl.lift) or "tricep" in sl.lift]
    assert arms == [], f"direct arm work is deferred in block 1, found {set(arms)}"


@pytest.mark.parametrize("program_name", sorted(PROGRAMS))
def test_accessories_sit_at_or_above_the_ratchet_floor(program_name):
    """Below ~0.71 of e1RM an accessory can only lose e1RM, week after week, and because
    `e1rm_refresh` takes the best set in a 21-day window the shrinking is lagged and easy
    to miss. This is the tripwire for 'let's make the isolation work lighter, it's safer' --
    it is not safer, it deletes the slot. Parametrized over every program in `PROGRAMS`
    (PLAN.md § Phase 3) so the ratchet -- `rebuild`'s original fault, restored and fixed --
    cannot come back in a third program."""
    prog = PROGRAMS[program_name]()
    for w, _, slot, s in _every_set(prog):
        if isinstance(s.load, Pct) and s.load.of == "e1rm" and w.kind == WeekKind.WORK:
            assert s.load.value >= 0.71, (
                f"{program_name} week {w.number} {slot.lift} at {s.load.value} of e1RM "
                "ratchets down")


# --- the two-speed progression -------------------------------------------------------

def test_upper_lifts_are_main_lifts(p):
    """Not accessories. An accessory progresses only through `e1rm_refresh`, which cannot
    raise an e1RM prescribed below ~0.71 of it -- see the ratchet test below."""
    for lift in comeback.UPPER:
        assert lift in p.main_lifts(), f"{lift} must be a main lift to progress at all"


def test_upper_body_does_not_wave(p):
    """Weeks 2-4 prescribe an identical upper scheme so that week-to-week comparison is
    clean while the elbow is being assessed."""
    work = [p.week(n) for n in range(2, 5)]
    assert all(w.kind == WeekKind.WORK for w in work)
    for lift in comeback.UPPER:
        schemes = {tuple(sl.sets) for w in work for sl in w.slots_for(lift)}
        assert len(schemes) == 1, f"{lift} varies across block 1: {schemes}"


def test_lower_body_does_wave(p):
    """The legs are uninjured and get a real wave. This is the whole point of the split."""
    tops = set()
    for n in range(2, 5):
        for slot in p.week(n).slots_for("leg_press"):
            for s in slot.sets:
                if s.amrap:
                    tops.add((s.min_reps, s.load.value))
    assert len(tops) == 3, f"leg press should see three schemes in block 1, saw {tops}"


def test_no_maximal_singles_anywhere(p):
    """`rebuild` waves to a 95 % single. Twenty months detrained, with a healing elbow,
    nothing here tests a max and no rule needs one."""
    for w, _, slot, s in _every_set(p):
        assert s.min_reps >= 3, f"week {w.number} {slot.lift} prescribes {s.min_reps} reps"
        if isinstance(s.load, Pct) and s.load.of == "tm":
            assert s.load.value <= 0.92, f"week {w.number} {slot.lift} at {s.load.value} of TM"


# --- the percentage floor ------------------------------------------------------------

def test_epley_ratchet_floor_is_what_the_docstring_claims():
    """The constraint the upper percentage is chosen against, asserted from `estimate`
    itself rather than restated arithmetic. A set at `f x e1RM` can only raise the stored
    e1RM if Epley on it exceeds that e1RM, and `estimate.e1rm` refuses above 12 reps.
    Below the floor, `e1rm_refresh` ratchets a lift *down* forever."""
    from onemore.model import Set, SetType

    def best(f, e1=100.0):
        vals = [estimate.e1rm(Set(1, SetType.WORK, f * e1, r, source_ref="x"))
                for r in range(1, 20)]
        return max(v for v in vals if v is not None)

    assert best(0.70) < 100.0, "0.70 should not be able to sustain its own e1RM"
    assert best(0.75) > 100.0, "0.75 should be able to"


def test_upper_top_set_clears_the_ceiling_floor(p):
    """`e1rm_ceiling` clamps TM to the rolling e1RM, so a top set at `f x TM` must satisfy
    `f x tm_factor x (1 + reps/30) > 1` at the rep count that earns a step, or the clamp
    eats every step `tm_progress` grants. Guards against 'let's use a safer 70 %'."""
    for lift in comeback.UPPER:
        factor = p.lifts[lift].tm_factor
        top = next(s for s in p.week(2).slots_for(lift)[0].sets if s.amrap)
        earned = top.min_reps + 2  # what `tm_progress` requires to step the TM
        implied = top.load.value * factor * (1 + min(earned, 12) / 30)
        assert implied > 1.0, (
            f"{lift}: top set {top.load.value} of TM for {earned} reps measures "
            f"{implied:.3f} of the stored e1RM - the ceiling will claw the step back")


def test_week_one_seeds_off_e1rm_and_work_weeks_off_tm(p):
    """There is no TM before week 1, so the seeded week must resolve against the decayed
    historical e1RM; from week 2 the main lifts hang off the calibrated TM."""
    assert p.week(1).kind == WeekKind.CALIBRATION
    for lift in p.main_lifts():
        for slot in p.week(1).slots_for(lift):
            for s in slot.sets:
                assert isinstance(s.load, Pct) and s.load.of == "e1rm"
        for slot in p.week(2).slots_for(lift):
            for s in slot.sets:
                assert isinstance(s.load, Pct) and s.load.of == "tm"


def test_the_seeded_upper_week_is_much_lighter_than_the_seeded_lower_week(p):
    """Safety comes from the seed, not the percentage: a light week 1 produces a low TM
    and therefore low absolute loads for every week after it."""
    def seed_top(lift):
        return next(s for s in p.week(1).slots_for(lift)[0].sets if s.amrap).load.value
    assert seed_top("chest_press") <= 0.55
    assert seed_top("leg_press") >= 0.70


# --- the checkpoint ------------------------------------------------------------------

def test_block_one_ends_in_a_deload_at_the_checkpoint(p):
    """A clinical re-evaluation lands around the end of block 1. Block 1 is five weeks
    so the deload lands there, and upper block 2 is deliberately unwritten."""
    assert len(p.weeks) == 5
    assert p.weeks[-1].kind == WeekKind.DELOAD
    assert "re-evaluation" in p.weeks[-1].label


def test_cycling_past_the_checkpoint_holds_the_same_shape(p):
    """`Program.week()` cycles weeks 2-5 past the end. Nothing should get heavier by
    template alone -- the only thing that moves a load here is a logged rep count."""
    for n in range(6, 14):
        cycled, original = p.week(n), p.week(((n - 2) % 4) + 2)
        assert [d.name for d in cycled.days] == [d.name for d in original.days]
        assert cycled.kind == original.kind


def test_there_is_no_template_creep(p):
    """`rebuild` adds percentage points per block on top of what the log earns. Here the
    same week of the cycle must prescribe the same percentages every time round."""
    def pcts(w):
        return [s.load.value for d in w.days for sl in d.slots for s in sl.sets
                if isinstance(s.load, Pct)]
    for n in range(2, 6):
        assert pcts(p.week(n)) == pcts(p.week(n + 4)), f"week {n} creeps by week {n + 4}"


def test_the_deload_actually_deloads_every_slot(p):
    """Including the bodyweight core, which is easy to miss because it carries no
    percentage to turn down and so does not show up in any load-based check."""
    work, deload = p.week(4), p.week(5)
    assert deload.kind == WeekKind.DELOAD
    for wd, dd in zip(work.days, deload.days):
        for ws, ds in zip(wd.slots, dd.slots):
            assert ws.lift == ds.lift
            w_sets = sum(s.n for s in ws.sets)
            d_sets = sum(s.n for s in ds.sets)
            assert d_sets < w_sets, f"{ds.lift}: deload has {d_sets} sets vs {w_sets} in week 4"


def test_no_amrap_survives_into_the_deload(p):
    """A deload with an AMRAP in it is a work week wearing a hat."""
    for d in p.week(5).days:
        for slot in d.slots:
            assert not any(s.amrap for s in slot.sets), f"{slot.lift} still has an AMRAP"


def test_one_constant_decides_the_default_everywhere_a_caller_names_none():
    """One constant is the only place that says which program is the default.

    0650bd7 changed the CLI's default from `rebuild` to `comeback` and left five
    `"rebuild"` fallbacks in `web.py`, so `POST /api/start` with no `program` field
    seeded the superseded program — the one whose accessories could only ratchet down,
    on a healing elbow.

    This first covered `web` and `cli` only, on the reasoning that the browser sends
    `program` explicitly. That reasoning was wrong: the browser sends whatever its
    select was preloaded with, and `app.js` preloaded the literal `"rebuild"` whenever
    no plan was running — which is exactly when the Start button is used. The one
    control that starts a plan was the last one still naming a program literally,
    so the frontend is checked here too.

    `rebuild` now ships as the default and an instance running `comeback` pins it with
    `ONEMORE_PROGRAM` — so neither name may appear as a literal in a caller.
    """
    import inspect
    from importlib import resources

    import pytest

    from onemore import cli, web
    from onemore.program.programs import DEFAULT_PROGRAM, SHIPPED_DEFAULT, default_program

    assert SHIPPED_DEFAULT == "rebuild"
    assert default_program({}) == "rebuild"
    assert default_program({"ONEMORE_PROGRAM": "comeback"}) == "comeback"
    with pytest.raises(ValueError):
        default_program({"ONEMORE_PROGRAM": "rebiuld"})
    assert DEFAULT_PROGRAM == default_program()

    # No module may re-state the choice as a literal; that restatement is the bug.
    for mod in (web, cli):
        src = inspect.getsource(mod)
        for name in ('"rebuild"', '"comeback"'):
            assert name not in src, (
                f"{mod.__name__} names a program literally — use DEFAULT_PROGRAM, or the "
                "API and the CLI drift apart again"
            )

    # The UI gets the default off /api/status ("program"), never from a literal.
    js = resources.files("onemore").joinpath("static/app.js").read_text()
    for name in ('"rebuild"', '"comeback"'):
        assert name not in js, (
            "app.js names a program literally — read st.program, or the Start button "
            "pre-selects a program the server did not choose"
        )


def test_every_arm_slot_says_not_to_push_through_pain(p):
    """A press has flared painfully at low weight before, with no clinician actively
    setting a pain threshold. The engine cannot see pain, so the printed note is the
    only place the lifter is told to stop."""
    arms = {"chest_press", "machine_shoulder_press", "lat_pulldown", "seated_row",
            "lateral_raise"}
    for w, _, slot, _ in _every_set(p):
        if slot.lift in arms:
            assert "don't push through" in slot.note, f"week {w.number} {slot.lift}"


def test_the_pulldown_is_the_machine_and_carries_the_pain_note(p):
    """The lifter prefers the machine pulldown (2026-09-21); the cable is a separate lift with its
    own TM. The pulldown is an arm slot, so it carries the same stop-for-pain note as the
    others in `test_every_arm_slot_says_not_to_push_through_pain`."""
    lifts = {slot.lift for _, _, slot, _ in _every_set(p)}
    assert "machine_lat_pulldown" in lifts and "lat_pulldown" not in lifts
    assert "machine_lat_pulldown" in comeback.UPPER and p.lifts["machine_lat_pulldown"].main
    for w, _, slot, _ in _every_set(p):
        if slot.lift == "machine_lat_pulldown":
            assert "don't push through" in slot.note, f"week {w.number}"
