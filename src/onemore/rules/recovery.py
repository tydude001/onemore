"""The one rule that reads health data, and the only signal a watch actually gives here.

Sleep was the obvious input and is not available: the Watch is worn on 73 nights in five
years, none of them recent (`docs/research/strong-data-out.md`). HRV is recorded but only
as waking spot checks, which swing far too widely to threshold. Resting heart rate is what
is left, and it is dense — 80 of the last 90 days — because the watch computes it from
ordinary daytime wear.

The threshold is measured, not chosen, the same way `step_lb` is: over the 274 week-ends
the export covers, the 7-day mean sits within ±2.8 bpm (sd) of the 28-day mean, and **+5.0
bpm clears about one training week in twelve** — reproduce with `scripts/recovery_threshold.py`.
Tuning it against *training* weeks rather than all weeks is the part that matters: +4.0
looks like 1 week in 11 across the whole export and is 1 in 7 to 1 in 10 once only weeks
actually trained are counted, which against `comeback`'s five-week block would land an
extra deload almost every block. +5.0
is 1 in 12 at the worst phase — roughly one every second block, a nudge rather than a hair
trigger.

Four things keep it quiet rather than wrong:

- **The windows are the training week's, not "the latest readings".** A Health export that
  lands three weeks late must not be read as this week — so both windows end with the week
  and the rule is silent when the week itself holds fewer than four daily readings.
- **It cannot fire before week 4**, because a 28-day window that reaches back past the
  plan's start compares training against not training and calls the difference fatigue.
- **A deload week is skipped**: the week already backed off, and an elevated reading in it
  is not an argument for another one.
- **No readings at all means silence.** Health metrics are enrichment; no rule may require
  them (CLAUDE.md), and a missing export must never change a plan.
"""

from __future__ import annotations

import os
from datetime import timedelta

from ..model import Adjustment
from ..program.spec import WeekKind
from ..vitals import daily_means
from .base import Context

METRIC = "resting_heart_rate"
# The default: the 92nd percentile of the author's own *training* weeks; see the docstring.
# ONEMORE_RHR_THRESHOLD overrides it for someone else's own measured percentile — re-measure
# with scripts/recovery_threshold.py rather than tuning this by feel.
THRESHOLD_BPM = 5.0
MIN_READINGS = 4  # days with a reading inside the closing week
FIRST_WEEK = 4  # the earliest week whose 28-day window lies inside the plan


def _threshold_bpm() -> float:
    """ONEMORE_RHR_THRESHOLD if set, else the measured default. An invalid value raises
    (fails loudly) rather than silently falling back to the default."""
    raw = os.environ.get("ONEMORE_RHR_THRESHOLD")
    return THRESHOLD_BPM if raw is None else float(raw)


def recovery_deload(ctx: Context) -> list[Adjustment]:
    """Resting HR up over the week against the 28-day baseline: deload before continuing."""
    if ctx.week_no < FIRST_WEEK or ctx.week.kind == WeekKind.DELOAD or ctx.metrics is None:
        return []

    daily = daily_means([m for m in ctx.metrics
                         if m.name == METRIC and m.at.date() < ctx.end])
    week = {d: v for d, v in daily.items() if ctx.start <= d < ctx.end}
    base = {d: v for d, v in daily.items() if ctx.end - timedelta(days=28) <= d < ctx.end}
    if len(week) < MIN_READINGS or not base:
        return []

    m7 = sum(week.values()) / len(week)
    m28 = sum(base.values()) / len(base)
    threshold = _threshold_bpm()
    if m7 - m28 < threshold:
        return []

    evidence = tuple(f"apple_health:{METRIC}:{d}" for d in sorted(week))
    return [ctx.adj("recovery_deload", "*", "deload_next", 0, 1,
                    f"resting HR {m7:.0f} bpm this week against a {m28:.0f} bpm 28-day mean "
                    f"(+{m7 - m28:.1f}, over the +{threshold:.0f} threshold): deload next",
                    evidence)]
