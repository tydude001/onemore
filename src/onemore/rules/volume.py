"""Accessory volume autoregulation from logged RPE."""

from __future__ import annotations

from ..model import Adjustment
from .base import Context


def accessory_volume(ctx: Context) -> list[Adjustment]:
    """Non-main lifts prescribed by RPE: mean logged RPE > 9 for two weeks running drops a
    set; < 7 for two weeks adds one. Bounded to [-1, +2] sets. Needs RPE logged in Strong;
    with none logged the rule stays silent rather than guessing."""
    if ctx.week.kind == "deload":
        return []
    out = []
    for lift, spec in ctx.program.lifts.items():
        if spec.main:
            continue
        rpes = [s.rpe for _, s in ctx.sets_in_week(lift) if s.rpe is not None]
        if not rpes:
            continue
        mean = sum(rpes) / len(rpes)
        hard = int(ctx.state(lift, "hard_weeks") or 0)
        easy = int(ctx.state(lift, "easy_weeks") or 0)
        delta = int(ctx.state(lift, "sets_delta") or 0)
        ev = tuple(s.source_ref for _, s in ctx.sets_in_week(lift) if s.rpe is not None)
        if mean > 9:
            hard, easy = hard + 1, 0
        elif mean < 7:
            easy, hard = easy + 1, 0
        else:
            hard = easy = 0
        if hard >= 2 and delta > -1:
            out.append(ctx.adj("accessory_volume", lift, "sets_delta", delta, delta - 1,
                               f"mean RPE {mean:.1f} > 9 two weeks running: one set fewer", ev))
            hard = 0
        elif easy >= 2 and delta < 2:
            out.append(ctx.adj("accessory_volume", lift, "sets_delta", delta, delta + 1,
                               f"mean RPE {mean:.1f} < 7 two weeks running: one set more", ev))
            easy = 0
        for key, val in (("hard_weeks", hard), ("easy_weeks", easy)):
            if int(ctx.state(lift, key) or 0) != val:
                out.append(ctx.adj("accessory_volume", lift, key, ctx.state(lift, key), val,
                                   f"mean RPE this week {mean:.1f}", ev))
    return out
