"""Progression for lifts whose load cannot rise.

The gym is Planet Fitness: the dumbbell rack stops around 80 lb and a pin stack stops
where it stops. When a lift is at that limit, the training-max rules have nothing left to
add — so progress becomes reps, then a set, and never a load bump.

This rule is silent unless the exercise has a *known* ceiling in the catalog. The heaviest
load in the export is a floor on a machine's stack top, not the stack top, so guessing one
would invent a limit and stall a lift that had room left. Today only the dumbbells have a
ceiling recorded; the machines get theirs when someone reads them off the equipment.
"""

from __future__ import annotations

from ..model import Adjustment
from ..program.render import bump_reps
from ..program.spec import WeekKind
from .base import Context

REP_CAP = 3  # extra reps carried before the progression converts into an extra set
SET_CAP = 2  # extra sets, matching accessory_volume's bound


def _prescribed_top_reps(ctx: Context, lift: str) -> int | None:
    """The top of the rep range the plan actually printed for this lift, or None if the
    lift is unprescribed this week.

    The carried `reps_delta` has to be included. Reading the spec's bare rep target would
    let the same 12 reps that earned the first extra rep earn the second and the third,
    so the ladder would climb without ever being re-earned — the rule's whole point.
    This must stay in step with `render.resolve_sets`, which bumps the same way.
    """
    delta = int(ctx.state(lift, "reps_delta") or 0)
    tops = []
    for slot in ctx.week.slots_for(lift):
        for s in slot.sets:
            reps = bump_reps(s.reps, delta)
            tops.append(reps if isinstance(reps, int) else reps[1])
    return max(tops) if tops else None


def dumbbell_ceiling(ctx: Context) -> list[Adjustment]:
    """A lift at its known load ceiling progresses by reps, then by a set.

    Fires when the week's heaviest work set is within half a load step of the ceiling and
    every work set at that load hit the top of the *prescribed* rep range — prescribed
    including any reps already carried, so each rung is earned at the number the plan
    printed. Adds one rep (`reps_delta`) up to REP_CAP; at the cap, converts the carried
    reps into one extra set (`sets_delta`) and resets the rep counter. A training max
    sitting above the ceiling is clamped down to it, since no such load can be loaded.

    Nothing walks `reps_delta` back down. The only rule that sheds volume is
    `accessory_volume`, which needs a logged RPE the Strong export does not carry, so a
    lift that ratchets to +REP_CAP reps and +SET_CAP sets stays there until it is given a
    harder variation. That matches the rule as specified in PLAN.md; it is a known gap,
    not an oversight.
    """
    if ctx.week.kind == WeekKind.DELOAD:
        # Accessories keep their RPE prescription through a deload, so without this the
        # rule would earn another rep during the week meant to shed fatigue.
        return []
    out: list[Adjustment] = []
    for lift in ctx.program.lifts:
        ceiling = ctx.ceiling_kg(lift)
        if ceiling is None:
            continue
        step = ctx.step_kg(lift)

        tm = ctx.state(lift, "tm_kg")
        if tm is not None and tm > ceiling + 0.05:
            out.append(ctx.adj("dumbbell_ceiling", lift, "tm_kg", tm, ceiling,
                               f"TM {ctx.fmt(tm)} is above the {ctx.fmt(ceiling)} rack "
                               f"ceiling and cannot be loaded: clamped"))

        sets = ctx.sets_in_week(lift)
        if not sets:
            continue
        top_load = max((s.weight_kg or 0) for _, s in sets)
        at_ceiling = top_load >= ceiling - step / 2
        was = int(ctx.state(lift, "at_ceiling") or 0)
        if int(at_ceiling) != was:
            out.append(ctx.adj("dumbbell_ceiling", lift, "at_ceiling", was, int(at_ceiling),
                               f"heaviest work set {ctx.fmt(top_load)} vs ceiling "
                               f"{ctx.fmt(ceiling)}"))
        if not at_ceiling:
            continue

        target = _prescribed_top_reps(ctx, lift)
        if target is None:
            continue
        topset = [(d, s) for d, s in sets if (s.weight_kg or 0) >= ceiling - step / 2]
        if not all((s.reps or 0) >= target for _, s in topset):
            continue  # still earning the reps at this load; nothing to change

        ev = tuple(s.source_ref for _, s in topset)
        reps_delta = int(ctx.state(lift, "reps_delta") or 0)
        sets_delta = int(ctx.state(lift, "sets_delta") or 0)
        n = len(topset)
        if reps_delta < REP_CAP:
            out.append(ctx.adj("dumbbell_ceiling", lift, "reps_delta", reps_delta,
                               reps_delta + 1,
                               f"{n} sets at the {ctx.fmt(ceiling)} ceiling all hit "
                               f"{target} reps; load cannot rise, so +1 rep "
                               f"({reps_delta + 1} carried)", ev))
        elif sets_delta < SET_CAP:
            out.append(ctx.adj("dumbbell_ceiling", lift, "sets_delta", sets_delta,
                               sets_delta + 1,
                               f"{REP_CAP} carried reps held at the {ctx.fmt(ceiling)} "
                               f"ceiling: converted to one more set", ev))
            out.append(ctx.adj("dumbbell_ceiling", lift, "reps_delta", reps_delta, 0,
                               "carried reps consumed by the added set", ev))
        else:
            out.append(ctx.adj("dumbbell_ceiling", lift, "reps_delta", reps_delta, reps_delta,
                               f"at the {ctx.fmt(ceiling)} ceiling with +{REP_CAP} reps and "
                               f"+{SET_CAP} sets already: held, this lift has run out of "
                               f"room and wants a harder variation", ev))
    return out
