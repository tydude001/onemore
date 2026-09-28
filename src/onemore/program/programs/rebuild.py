"""`rebuild`: a detrained-but-not-novice return program at Planet Fitness.

Machines carry the load (PLAN.md § Which movements are main): leg press, chest press,
machine shoulder press, lat pulldown and seated row are the main lifts, because they are
the movements with a load history to seed a training max from. The Smith squat rides
along as an accessory with its own slow progression until it has a history of its own.

Nothing here reads RPE (PLAN.md § RPE is not logged). Every load is a percentage of a
state variable and every top set is an AMRAP, so the only signal the rules need is a rep
count, which Strong records on every set.

**Week 1 is the seeded week.** There is no training max yet, so the main lifts are
prescribed off the e1RM `seed_from_history` decays out of the old export: three easy
fives and a 5+ top set at ~80 % of what that TM would be. `calibrate_tm` reads the top
set and sets the real TM from it; percentages of TM start in week 2. For a lift with no
history at all the renderer prints "work up to" and the same rule seeds from whatever
was logged.

**Work weeks run the old DUP sheet's wave** (docs/research/dup-spreadsheet.md): a
three-week cycle of 5-rep-max / 1-rep-max / 3-rep-max top sets at 85 / 95 / 90 % with
4x12 / 4x4 / 4x8 backoffs at 65 / 85 / 75 %. The sheet's percentages were of a true 1RM;
here they are of TM, which is 0.9 x e1RM, so the program starts about ten percent more
conservative than the sheet did. Deliberate, for a return after twenty months off: the
AMRAP top set and `tm_progress` close the gap within a few weeks, and `e1rm_ceiling`
stops them overshooting. A lift trained twice a week runs the two days phase-offset, as
the sheet did for squat and deadlift, so it sees two of the three schemes every week.
Each three-week block ends in a deload, which the sheet did not have.

**Between blocks the percentages creep** — +1.5 points on top sets and +1.0 on backoffs
per block, the sheet's rule — as template progression. It is deterministic from the week
index and reads nothing logged, so it lives here and not in the rules layer, and it emits
no `Adjustment`. It stacks with `tm_progress`, which does read the log; the e1RM ceiling
bounds the sum. After the three defined blocks `Program.week()` cycles the body, and the
creep restarts from zero against whatever the TM has become.

**Accessories** are percent-of-e1RM for a rep range with the last set AMRAP. Their
progression is implicit but inspectable: `e1rm_refresh` fires for every lift in the
program, so more reps on the AMRAP raise the e1RM and next week's load with it. Bodyweight
core work is prescribed as reps only.

`build(days=4)` is the upper/lower split (the settled call); `build(days=3)` is the
full-body rotation kept reachable.
"""

from __future__ import annotations

from ...rules import DEFAULT_RULES
from ..spec import Bodyweight, Day, LiftSpec, Pct, Program, Sets, Slot, Warmup, Week, WeekKind

# No inc_kg: the load step is a property of the equipment, so it comes from the catalog.
# Passing one here overrides measured data and should be deliberate.
LIFTS = {
    "leg_press": LiftSpec("leg_press"),
    "chest_press": LiftSpec("chest_press"),
    "machine_shoulder_press": LiftSpec("machine_shoulder_press"),
    "lat_pulldown": LiftSpec("lat_pulldown"),
    "seated_row": LiftSpec("seated_row"),
    # Probationary: the one pattern the machines do not give. Promote to main with a
    # one-line change once it has a history worth seeding from.
    "smith_squat": LiftSpec("smith_squat", main=False),
    "leg_curl": LiftSpec("leg_curl", main=False),
    "calf_press": LiftSpec("calf_press", main=False),
    "dumbbell_bench_press": LiftSpec("dumbbell_bench_press", main=False),
    "lateral_raise": LiftSpec("lateral_raise", main=False),
    "tricep_pushdown": LiftSpec("tricep_pushdown", main=False),
    "bicep_curl": LiftSpec("bicep_curl", main=False),
    "face_pull": LiftSpec("face_pull", main=False),
    "captains_chair_knee_raise": LiftSpec("captains_chair_knee_raise", inc_kg=0.0, main=False),
}

# The DUP sheet's three rep schemes: rep-max phase -> (top-set % TM, backoff reps, backoff % TM).
WAVE = {
    5: (0.85, 12, 0.65),
    1: (0.95, 4, 0.85),
    3: (0.90, 8, 0.75),
}
BACKOFF_SETS = 4
# The order each phase visits the schemes over a block. A lift trained twice a week runs
# A on its first day and B on its second, so the two days never share a scheme.
PHASE_A = (5, 1, 3)
PHASE_B = (3, 5, 1)
# Per block: (added to every top-set %, added to every backoff %). Template progression.
CREEP = ((0.0, 0.0), (0.015, 0.010), (0.030, 0.020))
BLOCKS = len(CREEP)
WEEKS_PER_BLOCK = len(PHASE_A)

# Rest, in seconds. Machines and dumbbells recover faster than a barbell would, and the
# top set is the only one that has to be fresh.
REST_TOP, REST_BACKOFF, REST_SECONDARY, REST_ACCESSORY, REST_DELOAD = 180, 120, 90, 75, 90

# Warm-up ramps, as fractions of the slot's first prescribed set — the top set. Three
# steps for a main lift; one feel set for the two loaded accessories that need it.
RAMP = Warmup(((0.5, 8), (0.7, 5), (0.85, 3)))
FEEL = Warmup(((0.6, 6),))
FEEL_LIFTS = frozenset({"smith_squat", "dumbbell_bench_press"})

# Week 1, off the seeded e1RM: 0.72 x e1RM is 0.8 x the TM that e1RM implies.
SEED_MAIN = (Sets(1, 5, Pct(0.72, of="e1rm"), amrap=True, rest_s=REST_TOP),
             Sets(3, 5, Pct(0.65, of="e1rm"), rest_s=REST_BACKOFF))
SEED_SECONDARY = (Sets(3, (8, 10), Pct(0.54, of="e1rm"), rest_s=REST_SECONDARY),)  # 0.6 x TM
SECONDARY = (Sets(3, (8, 10), Pct(0.60), rest_s=REST_SECONDARY),)  # the other press, upper days
DELOAD_MAIN = (Sets(3, 5, Pct(0.60), rest_s=REST_DELOAD),)
DELOAD_SECONDARY = (Sets(2, 8, Pct(0.50), rest_s=REST_DELOAD),)


def wave(phase: tuple[int, ...], week_in_block: int, block: int) -> tuple[Sets, ...]:
    """One main-lift prescription: the top AMRAP set, then the backoffs."""
    rm = phase[week_in_block]
    top_pct, backoff_reps, backoff_pct = WAVE[rm]
    creep_top, creep_backoff = CREEP[block]
    return (
        Sets(1, rm, Pct(round(top_pct + creep_top, 3)), amrap=True, rest_s=REST_TOP),
        Sets(BACKOFF_SETS, backoff_reps, Pct(round(backoff_pct + creep_backoff, 3)),
             rest_s=REST_BACKOFF),
    )


def main(lift: str, sets: tuple[Sets, ...]) -> Slot:
    """A main-lift slot: the prescription plus the three-step ramp to its top set."""
    return Slot(lift, sets, warmup=RAMP)


def acc(lift: str, reps: tuple[int, int] = (10, 12), pct: float = 0.75, n: int = 3,
        note: str = "") -> Slot:
    """An accessory: `n` sets in a rep range at a fraction of the lift's own e1RM, last set
    AMRAP. Below ~0.71 of e1RM the slot can only ratchet down (PLAN.md § The Epley
    ratchet: Epley is capped at 12 reps, so a set at `f x e1RM` only measures a rise when
    `f > 0.714`); 0.75 clears the floor with room, and the rep range straddles it — twelve
    reps measures 1.05 of e1RM, eight measures 0.95 — so the slot finds its own weight."""
    return Slot(lift, (Sets(n, reps, Pct(pct, of="e1rm"), amrap=True, rest_s=REST_ACCESSORY),),
                note, warmup=FEEL if lift in FEEL_LIFTS else None)


def acc_deload(lift: str, reps: tuple[int, int] = (10, 12), pct: float = 0.55, n: int = 2,
               note: str = "") -> Slot:
    """The deload's accessory: two sets, no AMRAP, at 55 % whatever the work weeks asked."""
    return Slot(lift, (Sets(2, reps, Pct(0.55, of="e1rm"), rest_s=REST_DELOAD),), note)


def core(n: int = 3, reps: tuple[int, int] = (10, 15)) -> Slot:
    return Slot("captains_chair_knee_raise", (Sets(n, reps, Bodyweight(), rest_s=60),))


# A layout is a function of (main-lift prescription for phase A, for phase B, secondary
# prescription, accessory factory) so the seeded week, the work weeks and the deload can
# all share one arrangement of movements.


def _days4(main_a, main_b, sec, a, k) -> tuple[Day, ...]:
    return (
        Day("Lower 1 — leg press", (
            main("leg_press", main_a),
            a("smith_squat", reps=(6, 8), pct=0.75, note="added load; the bar is not counted"),
            a("leg_curl"),
            a("calf_press", reps=(12, 15), pct=0.75),
            k(),
        )),
        Day("Upper 1 — chest press", (
            main("chest_press", main_a),
            main("lat_pulldown", main_a),
            Slot("machine_shoulder_press", sec),
            a("tricep_pushdown", reps=(10, 15), pct=0.75),
            a("bicep_curl", reps=(10, 15), pct=0.75),
        )),
        Day("Lower 2 — leg press", (
            main("leg_press", main_b),
            a("leg_curl"),
            a("smith_squat", reps=(6, 8), pct=0.75, note="added load; the bar is not counted"),
            a("calf_press", reps=(12, 15), pct=0.75),
            k(),
        )),
        Day("Upper 2 — shoulder press", (
            main("machine_shoulder_press", main_a),
            main("seated_row", main_a),
            Slot("chest_press", sec),
            a("dumbbell_bench_press", reps=(8, 12)),
            a("lateral_raise", reps=(12, 15), pct=0.75),
            a("face_pull", reps=(15, 20), pct=0.75),
        )),
    )


def _days3(main_a, main_b, sec, a, k) -> tuple[Day, ...]:
    return (
        Day("Day A — leg press", (
            main("leg_press", main_a),
            main("chest_press", main_a),
            main("lat_pulldown", main_a),
            a("leg_curl"),
            a("tricep_pushdown", reps=(10, 15), pct=0.75),
        )),
        Day("Day B — shoulder press", (
            main("machine_shoulder_press", main_a),
            main("seated_row", main_a),
            a("smith_squat", reps=(6, 8), pct=0.75, note="added load; the bar is not counted"),
            a("lateral_raise", reps=(12, 15), pct=0.75),
            a("bicep_curl", reps=(10, 15), pct=0.75),
            k(),
        )),
        Day("Day C — leg press", (
            main("leg_press", main_b),
            main("lat_pulldown", main_b),
            Slot("chest_press", sec),
            a("dumbbell_bench_press", reps=(8, 12)),
            a("face_pull", reps=(15, 20), pct=0.75),
            k(),
        )),
    )


def build(days: int = 4) -> Program:
    if days not in (3, 4):
        raise ValueError("rebuild supports 3 or 4 days per week")
    layout = _days3 if days == 3 else _days4
    weeks = [Week(1, WeekKind.CALIBRATION, layout(SEED_MAIN, SEED_MAIN, SEED_SECONDARY, acc, core),
                  "seeded from history; the 5+ top set sets the training max")]
    n = 2
    for block in range(BLOCKS):
        for i in range(WEEKS_PER_BLOCK):
            days_ = layout(wave(PHASE_A, i, block), wave(PHASE_B, i, block), SECONDARY, acc, core)
            weeks.append(Week(n, WeekKind.WORK, days_, f"block {block + 1} week {i + 1}"))
            n += 1
        weeks.append(Week(n, WeekKind.DELOAD,
                          layout(DELOAD_MAIN, DELOAD_MAIN, DELOAD_SECONDARY, acc_deload,
                                 lambda: core(n=2)),
                          f"deload after block {block + 1}"))
        n += 1
    return Program("rebuild", LIFTS, weeks, list(DEFAULT_RULES), days_per_week=days)
