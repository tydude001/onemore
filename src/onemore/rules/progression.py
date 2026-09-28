"""Training-max rules for main lifts."""

from __future__ import annotations

import re
from datetime import timedelta

from .. import estimate
from ..model import Adjustment
from ..program.spec import Pct
from .base import HISTORY_DAYS, Context


def e1rm_refresh(ctx: Context) -> list[Adjustment]:
    """Set each lift's rolling e1RM from the best work set logged in the last HISTORY_DAYS.
    Fires for every lift with data, main or not, so percent-of-e1RM loads can resolve.

    The window is what makes the ceiling below workable: a week whose top set was a
    heavy single says less about the max than last week's 5+ did, and the ceiling must
    not be re-derived from whichever set happened to be this week's."""
    out = []
    for lift in ctx.program.lifts:
        sets = ctx.sets_in_history(lift)
        best, ref = estimate.rolling_e1rm(sets, ctx.end - timedelta(days=1),
                                          window_days=HISTORY_DAYS)
        old = ctx.state(lift, "e1rm_kg")
        if best is None:
            continue
        if old is None or abs(best - old) > 0.05:
            out.append(ctx.adj("e1rm_refresh", lift, "e1rm_kg", old, best,
                               f"best e1RM this week {ctx.fmt(best)} (was {ctx.fmt(old)})", ref))
    return out


def calibrate_tm(ctx: Context) -> list[Adjustment]:
    """After the seeded week, set each main lift's training max at `tm_factor` x the best
    e1RM it logged that week — in practice the 5+ top set prescribed off the decayed
    historical e1RM. A lift with no logged sets stays unseeded and its percent-of-TM
    prescriptions keep rendering as "no tm yet" until it is trained."""
    if ctx.week.kind != "calibration":
        return []
    out = []
    for lift in ctx.program.main_lifts():
        spec = ctx.program.lifts[lift]
        sets = ctx.sets_in_week(lift)
        best, ref = estimate.rolling_e1rm(sets, ctx.end - timedelta(days=1), window_days=7)
        if best is None:
            continue
        tm = estimate.training_max(best, spec.tm_factor)
        out.append(ctx.adj("calibrate_tm", lift, "tm_kg", ctx.state(lift, "tm_kg"), tm,
                           f"calibration: e1RM {ctx.fmt(best)} x {spec.tm_factor:g} = TM {ctx.fmt(tm)}",
                           ref))
    return out


def calibrate_new_lift(ctx: Context) -> list[Adjustment]:
    """A main lift with no TM that was trained in a work week gets one, set exactly as
    `calibrate_tm` would: `tm_factor` x the best e1RM it logged that week.

    `calibrate_tm` runs only in the seeded week, so a main lift that joins a running plan
    -- `comeback` moved its pulldown onto the machine in week 3 -- has nothing to set its TM
    and would print "no tm yet" for good, because `Program.week()` cycles the work weeks and
    never returns to week 1. Until it fires, the slot's percent-of-TM loads have nothing to
    resolve against, so the first week is the lifter's own light AMRAP, which is what the
    seeded week asks for anyway. It never touches a lift that already has a TM, so it cannot
    reset one. Runs after `tm_progress`, which skips a TM-less lift, so the week that sets a
    TM is not also judged against it."""
    if ctx.week.kind != "work":
        return []
    out = []
    for lift in ctx.program.main_lifts():
        if ctx.state(lift, "tm_kg") is not None:
            continue
        sets = ctx.sets_in_week(lift)
        best, ref = estimate.rolling_e1rm(sets, ctx.end - timedelta(days=1), window_days=7)
        if best is None:
            continue
        spec = ctx.program.lifts[lift]
        tm = estimate.training_max(best, spec.tm_factor)
        out.append(ctx.adj("calibrate_new_lift", lift, "tm_kg", None, tm,
                           f"no TM yet: e1RM {ctx.fmt(best)} this week x {spec.tm_factor:g}"
                           f" = TM {ctx.fmt(tm)}", ref))
    return out


def _top_prescription(ctx: Context, lift: str, tm: float) -> tuple[int, float | None] | None:
    """The AMRAP set the week is judged on: (target reps, prescribed kg or None), or None
    when no day that was trained carries one.

    A lift trained twice a week runs its two days phase-offset, so the week holds two
    AMRAPs at different loads and rep targets. The heaviest prescribed one is the top set
    of the week, and the heaviest logged set is compared against *its* target — comparing
    a 95 % single's reps to the other day's 5-rep target would call every single a miss.
    The prescribed load is known only for percent-of-TM sets; anything else judges on
    reps alone.

    Only days that were logged count. `comeback` puts the leg curl's top set on Lower 2 and
    three light sets of it on Lower 1, so a week that skipped Lower 2 logged the light sets
    and nothing else: judged against Lower 2's top set, that was a miss for a set nobody
    was asked to do that week (2026-09-28, week 3).
    """
    best = None
    for day in ctx.logged_days():
        for slot in day.slots:
            if slot.lift != lift:
                continue
            for s in slot.sets:
                if not s.amrap:
                    continue
                kg = tm * s.load.value if isinstance(s.load, Pct) and s.load.of == "tm" else None
                key = kg if kg is not None else -1.0
                if best is None or key > best[0]:
                    best = (key, s.min_reps, kg)
    return None if best is None else (best[1], best[2])


# Words that say a set stopped because something hurt. Matched in the week's Strong note on
# the lift; real examples read "couldn't take much weight today before it began to hurt" and
# "my elbow was bugging me". A note that merely mentions a word ("no pain today") also
# matches -- the cost of that is one held week instead of one miss, never a load bump.
PAIN_WORDS = re.compile(r"hurt|pain|sore|\bach(e|es|ing|y)\b|bugging|twinge|tweak", re.IGNORECASE)


def pain_note(ctx: Context, lift: str) -> str | None:
    """This week's note on `lift` that says it hurt, or None."""
    return next((n for n in ctx.notes_in_week(lift) if PAIN_WORDS.search(n)), None)


def tm_progress(ctx: Context) -> list[Adjustment]:
    """Progress / hold / reduce the training max from the week's AMRAP top set.

    - reps >= target + 2  -> TM += inc                       (tm_progress)
    - target <= reps < target + 2 -> hold, say why           (tm_hold)
    - reps < target -> a miss; two consecutive misses -> TM -10 %  (tm_reduce)
    - reps < target with a pain note on the lift -> hold, streak untouched  (tm_pain_hold)
    A lift not trained this week is left alone, and so is one whose top-set day was not
    trained: sets logged on another day, where the lift is lighter work, say nothing about
    the top set (`_top_prescription`). A week whose heaviest logged set sits
    more than a load step under the prescribed top load is a miss regardless of its reps:
    the top set was not attempted, and a backoff's twelve reps must not read as progress.

    A set stopped for pain is not a strength reading. `comeback` tells the lifter to end a
    set when the elbow hurts, and counting that as a miss would cut the TM for doing as
    told. It neither adds to the miss streak nor resets it: the week says nothing either way.
    """
    if ctx.week.kind != "work":
        return []
    out = []
    for lift in ctx.program.main_lifts():
        tm = ctx.state(lift, "tm_kg")
        if tm is None:
            continue
        top_rx = _top_prescription(ctx, lift, tm)
        if top_rx is None:
            continue
        target, prescribed = top_rx
        sets = ctx.sets_in_week(lift)
        if not sets:
            continue
        # The top set is the heaviest completed work set with reps logged.
        _, top = max(sets, key=lambda ds: (ds[1].weight_kg or 0, ds[1].reps or 0))
        reps = top.reps or 0
        misses = int(ctx.state(lift, "misses") or 0)
        ev = (top.source_ref,)
        inc = ctx.step_kg(lift)
        if prescribed is not None and (top.weight_kg or 0) < prescribed - inc:
            reps = 0  # not attempted at the prescribed load: judged as a miss below
            short = (f"heaviest set {ctx.fmt(top.weight_kg)} is under the prescribed "
                     f"{ctx.fmt(prescribed)} top set")
        else:
            short = ""
        if reps >= target + 2:
            out.append(ctx.adj("tm_progress", lift, "tm_kg", tm, tm + inc,
                               f"top set {ctx.fmt(top.weight_kg)} x{reps} vs target {target}: "
                               f"+{ctx.fmt(inc)}", ev))
            if misses:
                out.append(ctx.adj("tm_progress", lift, "misses", misses, 0, "miss streak reset", ev))
        elif reps >= target:
            out.append(ctx.adj("tm_hold", lift, "tm_kg", tm, tm,
                               f"top set {ctx.fmt(top.weight_kg)} x{reps} hit target {target} "
                               f"but not +2: hold", ev))
            if misses:
                out.append(ctx.adj("tm_hold", lift, "misses", misses, 0, "miss streak reset", ev))
        elif (note := pain_note(ctx, lift)) is not None:
            what = short or f"top set {ctx.fmt(top.weight_kg)} x{reps} under target {target}"
            out.append(ctx.adj("tm_pain_hold", lift, "tm_kg", tm, tm,
                               f"{what}, stopped for pain (note: \"{note}\"): "
                               f"not a miss, TM held", ev))
        else:
            misses += 1
            what = short or f"top set {ctx.fmt(top.weight_kg)} x{reps} under target {target}"
            if misses >= 2:
                new = tm * 0.9
                out.append(ctx.adj("tm_reduce", lift, "tm_kg", tm, new,
                                   f"{what} for the 2nd week running: TM -10% to {ctx.fmt(new)}",
                                   ev))
                out.append(ctx.adj("tm_reduce", lift, "misses", misses - 1, 0, "streak consumed", ev))
            else:
                out.append(ctx.adj("tm_miss", lift, "misses", misses - 1, misses,
                                   f"{what}: miss 1 of 2, TM held", ev))
    return out


CEILING_FACTOR = 1.0


def e1rm_ceiling(ctx: Context) -> list[Adjustment]:
    """A training max may never exceed the rolling e1RM. The guard against step
    progression running away from demonstrated ability.

    Not `tm_factor` (0.9), although PLAN.md first said so. `calibrate_tm` sets the TM at
    exactly 0.9 x e1RM, and a top set that beats its target by the two reps
    `tm_progress` asks for still implies, by Epley, an e1RM *below* the one it was
    prescribed from — a 5+ at 85 % of TM is 76.5 % of e1RM, a nine-rep load, so seven
    reps reads as a worse day. A 0.9 ceiling therefore clamped every earned step straight
    back down and the TM could never move. At 1.0 the TM has the ten percent of headroom
    calibration built in, and the ceiling bites only when reps fall while the TM climbs.
    """
    out = []
    for lift in ctx.program.main_lifts():
        tm = ctx.state(lift, "tm_kg")
        e1 = ctx.state(lift, "e1rm_kg")
        if tm is None or e1 is None:
            continue
        cap = e1 * CEILING_FACTOR
        if tm > cap + 0.05:
            out.append(ctx.adj("e1rm_ceiling", lift, "tm_kg", tm, cap,
                               f"TM {ctx.fmt(tm)} above the rolling e1RM {ctx.fmt(e1)}: "
                               f"clamped to {ctx.fmt(cap)}"))
    return out
