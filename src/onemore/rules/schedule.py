"""Week-level scheduling rules."""

from __future__ import annotations

from ..model import Adjustment
from .base import Context


def missed_week_repeat(ctx: Context) -> list[Adjustment]:
    """Fewer than two of the planned days logged: repeat the week instead of advancing.
    The engine reads a `week` adjustment with old == new as "do not advance"."""
    logged = ctx.planned_days_logged()
    if logged >= 2:
        return []
    return [ctx.adj("missed_week_repeat", "*", "week", ctx.week_no, ctx.week_no,
                    f"{logged} of {len(ctx.week.days)} planned days logged: week {ctx.week_no} repeats",
                    tuple(s.source_key for s in ctx.sessions))]


def deload_after_reductions(ctx: Context) -> list[Adjustment]:
    """Two or more main lifts reduced their TM this week: insert a deload before continuing.
    The structural deload at the end of each block is in the program itself; this is the
    fatigue trigger read off the bar. `recovery_deload` is the one read off the body."""
    reduced = [a.lift for a in ctx._cache.get("adjustments_so_far", [])
               if a.rule == "tm_reduce" and a.field == "tm_kg"]
    if len(set(reduced)) < 2:
        return []
    return [ctx.adj("deload_after_reductions", "*", "deload_next", 0, 1,
                    f"TM reduced on {', '.join(sorted(set(reduced)))} in one week: deload next")]
