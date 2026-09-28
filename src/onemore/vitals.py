"""Vitals summary from stored health metrics: latest reading, 7-day and 28-day means.

The two windows are the whole point. A single morning's bodyweight or resting HR is
noise; the 7-day mean against the 28-day mean is a trend a person can act on, and it is
what a recovery rule will eventually compare. Display only for now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .model import Metric
from .store import Store
from .units import from_kg, to_kg

# (label, metric name, fallbacks, display unit or None for "as stored", decimals)
ROWS = (
    ("bodyweight", "weight_body_mass", ("body_mass", "weight"), "mass", 1),
    ("body fat %", "body_fat_percentage", (), None, 1),
    ("lean mass", "lean_body_mass", (), "mass", 1),
    ("resting HR", "resting_heart_rate", (), None, 0),
    ("HRV", "heart_rate_variability", (), None, 0),
    ("sleep h", "sleep_analysis/asleep", ("sleep_analysis/total_sleep", "sleep_analysis/in_bed"),
     None, 1),
    ("steps", "step_count", (), None, 0),
    ("VO2 max", "vo2_max", (), None, 1),
)


@dataclass(frozen=True, slots=True)
class Vital:
    label: str
    unit: str
    latest: float
    latest_on: date
    mean_7d: float | None
    mean_28d: float | None
    decimals: int = 1

    def fmt(self, v: float | None) -> str:
        return "-" if v is None else f"{v:.{self.decimals}f}"


def daily_means(metrics: list[Metric]) -> dict[date, float]:
    """One value per local day: the mean of that day's readings. Public because the
    recovery rule compares the same daily series this summary displays, and two
    implementations of "a day's reading" would drift apart."""
    by: dict[date, list[float]] = {}
    for m in metrics:
        by.setdefault(m.at.date(), []).append(m.value)
    return {d: sum(v) / len(v) for d, v in by.items()}


def _mean(daily: dict[date, float], since: date, until: date) -> float | None:
    vals = [v for d, v in daily.items() if since <= d <= until]
    return sum(vals) / len(vals) if vals else None


def _convert(m: Metric, kind: str | None, unit: str) -> tuple[float, str]:
    if kind == "mass" and m.unit in ("lb", "kg"):
        return from_kg(to_kg(m.value, m.unit), unit), unit
    return m.value, m.unit


def summary(store: Store, asof: date, unit: str = "lb") -> list[Vital]:
    out = []
    for label, name, fallbacks, kind, decimals in ROWS:
        # The latest reading is shown however old it is — a scale last stepped on five
        # months ago is a fact worth seeing — but the means come only from the window.
        metrics = []
        for candidate in (name, *fallbacks):
            metrics = store.metrics(candidate)
            if metrics:
                break
        if not metrics:
            continue
        converted = [Metric(m.source, m.name, m.at, _convert(m, kind, unit)[0], m.unit)
                     for m in metrics if m.at.date() >= asof - timedelta(days=28)]
        last = Metric(metrics[-1].source, name, metrics[-1].at,
                      _convert(metrics[-1], kind, unit)[0], metrics[-1].unit)
        shown_unit = _convert(metrics[-1], kind, unit)[1]
        daily = daily_means(converted)
        out.append(Vital(label, shown_unit, last.value, last.at.date(),
                         _mean(daily, asof - timedelta(days=6), asof),
                         _mean(daily, asof - timedelta(days=27), asof), decimals))
    return out


def last_workout(store: Store) -> str | None:
    """`avg 128 / max 161 bpm, 340 kcal, 58 min on 2026-09-08`, or None."""
    parts = {}
    when = None
    for part in ("hr_avg", "hr_max", "kcal", "minutes"):
        ms = store.metrics(f"workout/{part}")
        if ms:
            parts[part] = ms[-1].value
            when = max(when, ms[-1].at) if when else ms[-1].at
    if not parts:
        return None
    bits = []
    if "hr_avg" in parts or "hr_max" in parts:
        bits.append(f"avg {parts.get('hr_avg', 0):.0f} / max {parts.get('hr_max', 0):.0f} bpm")
    if "kcal" in parts:
        bits.append(f"{parts['kcal']:.0f} kcal")
    if "minutes" in parts:
        bits.append(f"{parts['minutes']:.0f} min")
    return ", ".join(bits) + f" on {when.date()}"


def to_text(vitals: list[Vital], workout: str | None) -> str:
    if not vitals and not workout:
        return ""
    lines = [f"{'vital':12s} {'latest':>10s} {'on':>11s} {'7d':>8s} {'28d':>8s}"]
    for v in vitals:
        lines.append(f"{v.label:12s} {v.fmt(v.latest) + ' ' + v.unit:>10s} {v.latest_on!s:>11s} "
                     f"{v.fmt(v.mean_7d):>8s} {v.fmt(v.mean_28d):>8s}")
    if workout:
        lines.append(f"last workout HR: {workout}")
    return "\n".join(lines)


def to_line(vitals: list[Vital]) -> str:
    """One line for the phone page header: `bw 182.4 lb (7d 182.9, 28d 184.1) · rHR 54`."""
    bits = []
    for v in vitals:
        if v.label == "bodyweight":
            bits.append(f"bw {v.fmt(v.latest)} {v.unit} (7d {v.fmt(v.mean_7d)}, "
                        f"28d {v.fmt(v.mean_28d)})")
        elif v.label == "resting HR":
            bits.append(f"rHR {v.fmt(v.mean_7d)} (28d {v.fmt(v.mean_28d)})")
        elif v.label == "sleep h":
            bits.append(f"sleep {v.fmt(v.mean_7d)} h")
    return " · ".join(bits)


def series(store: Store, label: str, asof: date, days: int | None, unit: str = "lb"
           ) -> tuple[str, list[tuple[date, float]]]:
    """One value per day for a ROWS label ("bodyweight", "resting HR", ...), converted like
    `summary`, oldest first, over the last `days` (None: everything). Returns the unit the
    values are in and the points; ([] if nothing is stored under the label or its fallbacks).
    Charts read this; `summary` reads the same rows for the tiles."""
    row = next((r for r in ROWS if r[0] == label), None)
    if row is None:
        return "", []
    _, name, fallbacks, kind, _ = row
    since = asof - timedelta(days=days) if days else None
    metrics: list[Metric] = []
    for candidate in (name, *fallbacks):
        metrics = store.metrics(candidate, since)
        if metrics:
            break
    if not metrics:
        return "", []
    shown_unit = _convert(metrics[-1], kind, unit)[1]
    daily = daily_means([Metric(m.source, m.name, m.at, _convert(m, kind, unit)[0], m.unit)
                    for m in metrics])
    return shown_unit, sorted(daily.items())
