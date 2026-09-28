"""What elevation in resting HR is unusual for this lifter? Run against the real database.

`recovery_deload` fires when a training week's mean resting HR sits far enough above the
28-day mean to be worth a deload. "Far enough" is not a number anyone should invent: this
prints the distribution of that gap over every week the export covers, which is how the
threshold in `rules/recovery.py` was chosen. Re-run it when a year more data has landed.

    uv run python scripts/recovery_threshold.py [path/to/onemore.db]

Not a test: it reads real readings, which never enter the suite (CLAUDE.md).
"""

from __future__ import annotations

import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from onemore.store import Store
from onemore.vitals import daily_means

MIN_READINGS = 4  # a week with fewer than this says nothing; the rule uses the same floor


def _training_span(db: str) -> tuple[date, date] | None:
    """First and last logged session. Weeks outside it are not weeks the rule can see."""
    store = Store(Path(db))
    try:
        sessions = store.sessions()
    finally:
        store.close()
    return (sessions[0].date, sessions[-1].date) if sessions else None


def main(db: str = "data/onemore.db") -> int:
    store = Store(Path(db))
    try:
        metrics = store.metrics("resting_heart_rate")
    finally:
        store.close()
    if not metrics:
        print("no resting_heart_rate readings in", db)
        return 1

    daily = daily_means(metrics)
    days = sorted(daily)
    print(f"{len(metrics)} readings over {len(days)} days, {days[0]} → {days[-1]}")

    def mean(lo: date, hi: date) -> tuple[float | None, int]:
        vals = [v for d, v in daily.items() if lo <= d <= hi]
        return (sum(vals) / len(vals) if vals else None), len(vals)

    gaps: list[tuple[date, float]] = []
    cur = days[0] + timedelta(days=28)
    while cur <= days[-1]:
        m7, n7 = mean(cur - timedelta(days=6), cur)
        m28, _ = mean(cur - timedelta(days=27), cur)
        if m7 is not None and m28 is not None and n7 >= MIN_READINGS:
            gaps.append((cur, m7 - m28))
        cur += timedelta(days=7)

    vals = sorted(g for _, g in gaps)
    print(f"\n{len(vals)} week-ends with at least {MIN_READINGS} readings in the 7-day window")
    print(f"  sd {statistics.pstdev(vals):.2f} bpm, min {min(vals):+.2f}, max {max(vals):+.2f}")
    for p in (50, 75, 90, 95, 99):
        print(f"  p{p:<2}  7-day mean is {vals[int(len(vals) * p / 100) - 1]:+.2f} bpm vs 28-day")
    # The rule only ever sees weeks the lifter is training in, and those run hotter than the
    # quiet stretches between programs. Tuning on every week makes a threshold look rarer
    # than it will be — the mistake this script exists to stop being repeated.
    trained = _training_span(db)
    hot = sorted(g for when, g in gaps if trained and trained[0] <= when <= trained[1])
    print(f"\n  of those, {len(hot)} fall in the training span {trained[0]} → {trained[1]}"
          if trained else "\n  no logged sessions, so no training span")

    def rate(sample: list[float], t: float) -> str:
        n = sum(1 for v in sample if v >= t)
        if not n:
            return "never"
        return f"{n}/{len(sample)} = {100 * n / len(sample):4.1f}% (~1 in {len(sample) / n:.0f})"

    print(f"\n  {'threshold':<12}{'all week-ends':<26}training weeks")
    for t in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0):
        print(f"  +{t:<11.1f}{rate(vals, t):<26}{rate(hot, t) if hot else '-'}")

    # The 92nd percentile of training weeks is how THRESHOLD_BPM's own 5.0 was picked
    # (see rules/recovery.py's docstring) — the line to set ONEMORE_RHR_THRESHOLD to,
    # re-measured, never tuned by feel.
    if hot:
        p92 = sorted(hot)[min(len(hot) - 1, max(0, int(len(hot) * 92 / 100) - 1))]
        print(f"\n  the value to set:  ONEMORE_RHR_THRESHOLD={p92:.1f}")
    else:
        print("\n  no training weeks to measure a threshold from")

    print("\n  the last 12 week-ends:")
    for when, gap in gaps[-12:]:
        print(f"    {when}  {gap:+.2f} bpm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
