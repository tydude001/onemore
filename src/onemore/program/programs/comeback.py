"""`comeback`: return to lifting with a healing left radial head fracture.

Supersedes `rebuild` (retired 2026-09-21). `rebuild` was written for a detrained lifter
with two intact elbows; this one is written for a lifter who is both twenty months out
of the gym *and* some months out from a left elbow fracture that displaced during
nonoperative management. The clinical reasoning, the biomechanics and every movement
dropped or kept because of them are in `docs/research/radial-head-return.md`. Read that
before editing the layouts; the exercise selection here is not taste, and a well-meaning
substitution can undo it.

The lifter is cleared for a gradual return to training, with no restrictions on activity.
Nothing here overrides a clinician, and nothing here is rehab -- a separately prescribed
home exercise program is not duplicated, referenced or adjusted by this program.

**The organising idea: the legs are uninjured, so decouple them from the arms.** One
program, two progressions running at different speeds. Lower body gets a real wave and
real load. Upper body gets a fixed, deliberately light scheme whose absolute loads are
set by how a light calibration set actually goes. `rebuild` couples them and cannot
express this.

**The four movement rules, each from the research doc:**

1. *Stop pressing short of lockout.* The radial head carries 50-60 % of the axial load
   across the elbow and that transmission peaks between 0 and 30 degrees of flexion. This
   is the single biggest lever available and it costs almost nothing: press through the
   flexed range, leave out the last thirty degrees. Every press slot carries the note.
   It also explains a documented aggravator: pushing up off a couch.
2. *No loaded supination or pronation.* Forearm rotation is a documented aggravator, so
   every supinated movement is out -- which, together with the block 1 rule below, is
   why there is no curl of any kind here. Grip on the presses and pulls is the lifter's
   call by feel: the two studies on radiocapitellar load by forearm position disagree, so
   nothing in this program depends on grip.
3. *No loaded deep flexion.* There is a positive Tinel's at the cubital tunnel, where
   pressure and nerve traction both rise with flexion. Preacher curls are out; so is
   resting between sets with the elbow held bent.
4. *Nothing that risks a fall or a carry.* A second fall is what displaced this fracture.
   `smith_squat` is gone -- not for the legs' sake but because it is a hard grip with
   flexed elbows under a bar. Heavy dumbbell carries to a bench are gone for the same
   reason. Leg press gives the squat pattern with no arm involvement at all.

Dropped from `rebuild` and why, in one line each: `captains_chair_knee_raise` hangs
bodyweight through the forearms with pressure over the olecranon; `preacher_curl` loads
maximum flexion; `tricep_pushdown` / `triceps_extension_machine` / `skullcrusher` pull on
the olecranon and finish in terminal extension; `barbell_bicep_curl` / `bicep_curl` are
supinated; `dumbbell_bench_press` is a carry plus a deep-flexion bottom.

**Why the upper lifts are `main=True` and not accessories.** The obvious way to hold the
arms back is to make them accessories -- rep range at a fraction of their own e1RM, last
set AMRAP, progressed by `e1rm_refresh`. It does not work, and the reason is worth
recording because it is a live defect in `rebuild` too. `estimate.e1rm` returns None
above 12 reps, so the best e1RM one set at `f x e1RM` can ever measure is
`f x e1RM x (1 + 12/30)`. That exceeds the stored e1RM only when `f > 1/1.4 = 0.714`.
Every `rebuild` accessory is prescribed at 0.60-0.70, so `e1rm_refresh` can only ever
ratchet them *down*, about 2 % a week, forever. An accessory-shaped upper body would have
decayed instead of progressed. Being main lifts, they progress through `tm_progress`,
which compares rep counts to a target and never touches Epley.

**The percentage floor that follows.** `e1rm_ceiling` clamps the TM to the rolling e1RM,
and that e1RM comes back through the same Epley cap. A top set at `f x TM` with
`TM = 0.9 x e1RM` sustains its own e1RM only when `f x 0.9 x (1 + reps/30) > 1`. At 12
reps that needs `f > 0.79`. A "safer-looking" 0.70 top set would decay the e1RM, the
ceiling would follow it down and eat every step `tm_progress` earned -- the failure
PLAN.md records under § The seeded week and the ceiling, reappearing at a different
percentage. So the upper top set is 0.82 of TM, not lower.

**Safety comes from the calibration seed, not from the percentage.** Week 1 prescribes
the upper lifts at 0.50 of the decayed historical e1RM for a 10+ AMRAP -- genuinely easy,
and stopped early if the elbow says so. `calibrate_tm` then sets each TM at 0.9 x
whatever that set actually measured, so a cautious week 1 produces a low TM and a low
absolute load for every week after it, while the percentages stay high enough for the
ratchet to work. Stopping the AMRAP early is not cheating the program; it *is* the
program's input.

**Upper body does not wave.** Weeks 2-4 prescribe the identical upper scheme -- top set
at 0.82 TM for 10+, then two backoffs at 0.66 -- so that week-to-week the stimulus is
the same and "did that feel worse than last week?" is a question with a clean answer.
Diagnostic value beats variety for three weeks. Lower body waves 8 / 5 / 3.

**There is no template creep and no 1RM phase.** `rebuild` adds percentage points per
block on top of what the log earns; here the only thing that moves a load is
`tm_progress` reading a logged rep count. Twenty months off is not the time for two
progressions stacked, and a heavy single is not the time for either elbow.

**Block 1 ends at a checkpoint, on purpose.** A clinical re-evaluation is expected around
the end of block 1. Week 5 is a deload that lands on that visit. Upper
body block 2 is deliberately unwritten: planning thirteen weeks of arm progression across
a scheduled reassessment that could change the diagnosis is the failure mode this program
exists to avoid. Past week 5 `Program.week()` cycles weeks 2-5, which holds the same
conservative shape until someone edits this file with the new information.

**Accessories are prescribed at 0.75 of e1RM, and that number is not cosmetic.** It is
the other side of the same ratchet. Below about 0.71 an accessory can only lose e1RM;
at 0.75 a set of twelve measures 1.05 of the stored e1RM and a set of eight measures
0.95, so the slot is *self-correcting* -- too heavy means fewer reps means a lighter
prescription next week, and comfortably light means the load creeps up. `rebuild` puts
its accessories at 0.60-0.70 and they decay instead. Anything moved below 0.75 here is a
slot that will quietly shrink to nothing; `e1rm_refresh` takes the best set in a 21-day
window, so the shrinking is lagged and easy to miss.

**No direct arm work in block 1.** Not just the triceps: the biceps inserts on the radial
tuberosity, immediately below the fractured radial head, so loaded elbow flexion pulls on
the injured bone. The rows and pulldowns already train elbow flexion under load, OT is
already prescribing loaded flexion isometrics, and neither needs a curl on top. Direct arm
work is a block 2 decision, after the re-evaluation -- the same call, for the same kind of
reason, as deferring the triceps.

Four days, about an hour. Lower days are four slots because a top set at three minutes
plus three backoffs at two is already twenty minutes of one exercise. No three-day
variant: four is the settled answer, and an untested layout is not worth carrying.
"""

from __future__ import annotations

from ...rules import DEFAULT_RULES
from ..spec import Bodyweight, Day, LiftSpec, Pct, Program, Sets, Slot, Warmup, Week, WeekKind

# No inc_kg anywhere: the load step is a property of the equipment and comes from the
# catalog. Every lift here is a selectorized machine or a cable, which is the point --
# the fixed path is what lets him stop short of lockout without balancing anything.
LIFTS = {
    # Lower body: uninjured, waved, progressed at full speed.
    "leg_press": LiftSpec("leg_press"),
    "leg_curl": LiftSpec("leg_curl"),
    # Upper body: main lifts so that `tm_progress` drives them, but on the flat
    # low-load scheme above rather than the wave. See the docstring.
    "chest_press": LiftSpec("chest_press"),
    "machine_shoulder_press": LiftSpec("machine_shoulder_press"),
    # The machine, not the cable: it's the better fit here (2026-09-21). Its own TM, because the
    # two are different load scales -- see the split in exercises.toml.
    "machine_lat_pulldown": LiftSpec("machine_lat_pulldown"),
    "seated_row": LiftSpec("seated_row"),
    # Accessories.
    "leg_extension": LiftSpec("leg_extension", main=False),
    "calf_press": LiftSpec("calf_press", main=False),
    "hip_abductor": LiftSpec("hip_abductor", main=False),
    "lateral_raise": LiftSpec("lateral_raise", main=False),
    "crunch_machine": LiftSpec("crunch_machine", main=False),
    "decline_crunch": LiftSpec("decline_crunch", main=False),
}

UPPER = frozenset({"chest_press", "machine_shoulder_press", "machine_lat_pulldown",
                   "seated_row"})

# The note that carries movement rule 1. Every press slot gets it; the renderer prints it.
LOCKOUT = "stop ~30 deg short of lockout - do not straighten the arm under load"
GRIP = "neutral grip if the machine has one; whichever grip hurts less"
PULL = "controlled; no yanking, no deep stretch at the top"
# Pain cues. No clinician has set a threshold for this, so these say only "don't push
# through", which needs none. The engine still reads nothing but the logged loads: a set
# cut short feeds `tm_reduce` as a miss.
PAIN = "if the elbow hurts, drop the weight or end the set - don't push through"
SKIP = "if it hurts even light, skip it until your next follow-up"

# Lower-body wave: rep-max phase -> (top-set % TM, backoff sets, backoff reps, backoff % TM).
# `rebuild`'s 95 % single is gone: twenty months detrained is not the time to test a max,
# and nothing in the rules needs one.
LOWER_WAVE = {
    8: (0.80, 3, 12, 0.65),
    5: (0.87, 3, 8, 0.72),
    3: (0.91, 3, 6, 0.78),
}
PHASE_A = (8, 5, 3)
PHASE_B = (5, 3, 8)  # the second lower day, phase-offset, so the week sees two schemes
WEEKS_PER_BLOCK = len(PHASE_A)

# Rest, in seconds. Upper rests are shorter because the loads are light; the point of the
# longer lower rests is that the top set has to be fresh.
REST_TOP, REST_BACKOFF, REST_SECONDARY = 180, 120, 90
REST_UPPER_TOP, REST_UPPER_BACKOFF, REST_ACCESSORY, REST_DELOAD = 150, 90, 60, 90

# Warm-up ramps as fractions of the slot's first prescribed set. The upper ramp is longer
# and lighter than the lower one on purpose: more submaximal reps through the flexed range
# before anything heavy, which is also what OT's "heat before exercise" is getting at.
RAMP_LOWER = Warmup(((0.5, 8), (0.7, 5), (0.85, 3)))
RAMP_UPPER = Warmup(((0.4, 10), (0.6, 8), (0.8, 5)))

# --- Week 1, the seeded week -------------------------------------------------------
# Lower seeds like `rebuild` did. Upper seeds far lighter -- 0.50 of an e1RM that
# `seed_from_history` has already decayed by 0.8 for age, so about 0.4 of a twenty-month-old
# best -- and `calibrate_tm` turns whatever that set does into the TM everything else
# hangs off.
SEED_LOWER = (Sets(1, 5, Pct(0.72, of="e1rm"), amrap=True, rest_s=REST_TOP),
              Sets(2, 5, Pct(0.65, of="e1rm"), rest_s=REST_BACKOFF))
SEED_UPPER = (Sets(1, 10, Pct(0.50, of="e1rm"), amrap=True, rest_s=REST_UPPER_TOP),
              Sets(2, 10, Pct(0.42, of="e1rm"), rest_s=REST_UPPER_BACKOFF))

# --- Work weeks --------------------------------------------------------------------
# The flat upper scheme. 0.82 clears the 0.79 floor the ceiling arithmetic imposes
# (docstring); the 10+ target means `tm_progress` steps the TM at 12 reps, which is also
# the rep count at which the measured e1RM rises. The two agree by construction.
UPPER_WORK = (Sets(1, 10, Pct(0.82), amrap=True, rest_s=REST_UPPER_TOP),
              Sets(2, 12, Pct(0.66), rest_s=REST_UPPER_BACKOFF))
# The lower lift on its *secondary* day: moderate, not waved, no AMRAP.
LOWER_SECONDARY = (Sets(3, (8, 10), Pct(0.62), rest_s=REST_SECONDARY),)

# --- Deload / checkpoint week ------------------------------------------------------
DELOAD_LOWER = (Sets(3, 5, Pct(0.60), rest_s=REST_DELOAD),)
DELOAD_UPPER = (Sets(2, 10, Pct(0.55), rest_s=REST_DELOAD),)
DELOAD_SECONDARY = (Sets(2, 8, Pct(0.50), rest_s=REST_DELOAD),)


def lower_wave(phase: tuple[int, ...], week_in_block: int) -> tuple[Sets, ...]:
    """One lower-body main prescription: the top AMRAP set, then its backoffs."""
    rm = phase[week_in_block]
    top_pct, n, backoff_reps, backoff_pct = LOWER_WAVE[rm]
    return (
        Sets(1, rm, Pct(top_pct), amrap=True, rest_s=REST_TOP),
        Sets(n, backoff_reps, Pct(backoff_pct), rest_s=REST_BACKOFF),
    )


def lower(lift: str, sets: tuple[Sets, ...], note: str = "") -> Slot:
    return Slot(lift, sets, note, warmup=RAMP_LOWER)


def upper(lift: str, sets: tuple[Sets, ...]) -> Slot:
    """An upper-body slot. The note is not decoration -- it is movement rule 1, and it is
    the only place the lifter is told the thing that matters most."""
    note = f"{LOCKOUT}; {PAIN}; {GRIP}" if lift in ("chest_press", "machine_shoulder_press") \
        else f"{PULL}; {PAIN}; {GRIP}"
    if lift == "machine_shoulder_press":
        note = f"{note}; {SKIP}"
    return Slot(lift, sets, note, warmup=RAMP_UPPER)


# The floor an accessory percentage may not go below; see the docstring. Below ~0.71 the
# slot can only ratchet down.
ACC_PCT = 0.75


def acc(lift: str, reps: tuple[int, int] = (8, 12), pct: float = ACC_PCT, n: int = 3,
        note: str = "") -> Slot:
    """An accessory: `n` sets in a rep range at a fraction of its own e1RM, last set AMRAP.
    The rep range straddles the load: twelve reps at 0.75 raises the e1RM, eight lowers it,
    so the slot finds its own weight within a couple of weeks."""
    return Slot(lift, (Sets(n, reps, Pct(pct, of="e1rm"), amrap=True, rest_s=REST_ACCESSORY),),
                note)


def acc_deload(lift: str, reps: tuple[int, int] = (8, 10), pct: float = 0.70, n: int = 2,
               note: str = "") -> Slot:
    """Deload accessories: fewer sets, no AMRAP. The percentage stays near the floor rather
    than dropping to 0.55 as `rebuild` does -- a deload should shed fatigue, not reset the
    e1RM the next block is prescribed from."""
    return Slot(lift, (Sets(n, reps, Pct(pct, of="e1rm"), rest_s=REST_DELOAD),), note)


def core_bw(n: int = 3, reps: tuple[int, int] = (12, 20)) -> Slot:
    """Bodyweight core. No load, no elbow involvement at all -- which is why it is here and
    `captains_chair_knee_raise`, which hangs bodyweight through the forearms, is not."""
    return Slot("decline_crunch", (Sets(n, reps, Bodyweight(), rest_s=REST_ACCESSORY),))


def _days(lower_a, lower_b, sec, up, a, k) -> tuple[Day, ...]:
    """Four days. The first slot of each is a distinct lift, which is what lets
    `missed_week_repeat` match a logged session to at most one planned day
    (PLAN.md records `rebuild`'s three-day layout undercounting for exactly this reason).
    Keep them distinct."""
    return (
        Day("Lower 1 - leg press", (
            lower("leg_press", lower_a),
            Slot("leg_curl", sec),
            a("calf_press", reps=(10, 15)),
            a("crunch_machine", reps=(10, 15)),
        )),
        Day("Upper 1 - press", (
            upper("chest_press", up),
            upper("machine_shoulder_press", up),
            upper("machine_lat_pulldown", up),
            a("lateral_raise", note="elbow stays softly bent and still - no swinging, "
                                    "and no straightening it out at the top; " + PAIN),
        )),
        Day("Lower 2 - leg curl", (
            lower("leg_curl", lower_b),
            Slot("leg_press", sec),
            a("leg_extension"),
            a("hip_abductor", reps=(10, 15)),
        )),
        Day("Upper 2 - row", (
            upper("seated_row", up),
            upper("machine_lat_pulldown", up),
            upper("chest_press", up),
            k(),
        )),
    )


def build(days: int = 4) -> Program:
    if days != 4:
        raise ValueError("comeback is a four-day program; see the module docstring")
    weeks = [Week(1, WeekKind.CALIBRATION,
                  _days(SEED_LOWER, SEED_LOWER, SEED_UPPER, SEED_UPPER, acc, core_bw),
                  "seeded from history; the light AMRAPs set every training max")]
    for i in range(WEEKS_PER_BLOCK):
        weeks.append(Week(i + 2, WeekKind.WORK,
                          _days(lower_wave(PHASE_A, i), lower_wave(PHASE_B, i),
                                LOWER_SECONDARY, UPPER_WORK, acc, core_bw),
                          f"block 1 week {i + 1}"))
    weeks.append(Week(WEEKS_PER_BLOCK + 2, WeekKind.DELOAD,
                      _days(DELOAD_LOWER, DELOAD_LOWER, DELOAD_SECONDARY, DELOAD_UPPER,
                            acc_deload, lambda: core_bw(n=2, reps=(10, 15))),
                      "deload - placed to land on a clinical re-evaluation"))
    return Program("comeback", LIFTS, weeks, list(DEFAULT_RULES), days_per_week=4)
