"""Estimated maxes from submaximal sets. Nothing here tests a max cold.

- Epley e1RM for sets without RPE, reps <= 12.
- RPE-adjusted e1RM (RTS-style table) when the set has an RPE, reps <= 10.
- Rolling e1RM per lift = best e1RM from completed work sets in a window.
- Training max = 0.9 x rolling e1RM, the 5/3/1 convention the rules progress.
"""

from __future__ import annotations

from datetime import date, timedelta

from .model import Set, SetType

# %1RM by (RPE, reps). Rows RPE 10 -> 6 in 0.5 steps, columns reps 1..10.
_RPE_TABLE: dict[float, tuple[float, ...]] = {
    10.0: (1.000, 0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739),
    9.5: (0.978, 0.939, 0.907, 0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723),
    9.0: (0.955, 0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707),
    8.5: (0.939, 0.907, 0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694),
    8.0: (0.922, 0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680),
    7.5: (0.907, 0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694, 0.667),
    7.0: (0.892, 0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680, 0.653),
    6.5: (0.878, 0.850, 0.824, 0.799, 0.774, 0.751, 0.723, 0.694, 0.667, 0.640),
    6.0: (0.863, 0.837, 0.811, 0.786, 0.762, 0.739, 0.707, 0.680, 0.653, 0.626),
}


def rpe_pct(rpe: float, reps: int) -> float | None:
    """Fraction of 1RM a set of `reps` at `rpe` represents, or None if off the table."""
    r = round(rpe * 2) / 2
    if r not in _RPE_TABLE or not 1 <= reps <= 10:
        return None
    return _RPE_TABLE[r][reps - 1]


def load_for(pct_or_rpe_target: float, reps: int, e1rm_kg: float) -> float:
    """Load (kg) that makes `reps` land at RPE `pct_or_rpe_target`."""
    pct = rpe_pct(pct_or_rpe_target, reps)
    if pct is None:
        raise ValueError(f"no RPE table entry for rpe={pct_or_rpe_target} reps={reps}")
    return e1rm_kg * pct


def epley(weight_kg: float, reps: int) -> float:
    return weight_kg if reps == 1 else weight_kg * (1 + reps / 30)


def e1rm(s: Set) -> float | None:
    """Estimated 1RM for one set, or None if the set cannot support an estimate."""
    if s.weight_kg is None or not s.reps or s.reps <= 0 or not s.completed:
        return None
    if s.set_type != SetType.WORK:
        return None
    if s.rpe is not None:
        pct = rpe_pct(s.rpe, s.reps)
        if pct:
            return s.weight_kg / pct
    if s.reps > 12:
        return None
    return epley(s.weight_kg, s.reps)


def rolling_e1rm(
    dated_sets: list[tuple[date, Set]], asof: date, window_days: int = 21
) -> tuple[float | None, tuple[str, ...]]:
    """Best e1RM among work sets inside the window; returns (kg, evidence source_refs)."""
    start = asof - timedelta(days=window_days)
    best: float | None = None
    ref: tuple[str, ...] = ()
    for d, s in dated_sets:
        if d < start or d > asof:
            continue
        v = e1rm(s)
        if v is not None and (best is None or v > best):
            best, ref = v, (s.source_ref,)
    return best, ref


def historical_best(dated_sets: list[tuple[date, Set]]) -> tuple[float | None, date | None]:
    best: float | None = None
    when: date | None = None
    for d, s in dated_sets:
        v = e1rm(s)
        if v is not None and (best is None or v > best):
            best, when = v, d
    return best, when


def training_max(e1rm_kg: float, factor: float = 0.9) -> float:
    return e1rm_kg * factor
