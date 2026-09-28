"""Apple Health's own export — the zip from Health → profile → Export All Health Data.

No app needed, but it is everything HealthKit holds: a first export ran to a 1.1 GB
`export.xml` of 2.3 million records, so this is a streaming parse that keeps only what
the vitals summary reads, under the same metric names `apple_health.py` produces from
Health Auto Export. Either path fills the same table.

    <HealthData>
      <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Withings" unit="lb"
              startDate="2025-01-06 08:00:00 -0500" endDate="..." value="180.0"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate=".." endDate=".."
              value="HKCategoryValueSleepAnalysisAsleepDeep"/>
      <Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining"
               duration="16.25" durationUnit="min" startDate=".." endDate="..">
        <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" sum="65.8" unit="Cal"/>
        <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" average="84.7" minimum="66" maximum="116"/>
      </Workout>

What is derived rather than copied:

- **Steps** are summed per day per source, and the day takes the largest source — the
  phone and the Watch both count the same steps, and Apple dedupes them in the app but
  not in the export.
- **Sleep** is one row per night, dated on the morning it ended, from the stage intervals:
  `asleep` is the Core + Deep + REM + Unspecified hours, `in_bed` the InBed hours, plus
  `deep` and `rem`. Older phone-only nights have only `in_bed`.
- **Workout heart rate** comes from the workout's own statistics when it has them; the
  older Watch workouts do not, so their mean and max are taken from the raw heart-rate
  samples inside the workout's window. Strength and core-training workouts only — this
  is a onemore repo, and "last workout" should mean the last session.
- **Body fat** is stored as a percentage whichever way the source wrote it (Withings
  writes a fraction under a `%` unit).
"""

from __future__ import annotations

import hashlib
import zipfile
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from ..model import Metric
from .apple_health import SOURCE, parse_date

Q = "HKQuantityTypeIdentifier"
C = "HKCategoryTypeIdentifier"

# HealthKit type -> metric name, taken one reading at a time.
QUANTITIES = {
    f"{Q}BodyMass": "weight_body_mass",
    f"{Q}BodyFatPercentage": "body_fat_percentage",
    f"{Q}LeanBodyMass": "lean_body_mass",
    f"{Q}RestingHeartRate": "resting_heart_rate",
    f"{Q}HeartRateVariabilitySDNN": "heart_rate_variability",
    f"{Q}VO2Max": "vo2_max",
    f"{Q}RespiratoryRate": "respiratory_rate",
}
UNITS = {"count/min": "bpm", "Cal": "kcal"}  # HealthKit's spellings -> the JSON path's
STEPS = f"{Q}StepCount"
HEART_RATE = f"{Q}HeartRate"
SLEEP = f"{C}SleepAnalysis"
ASLEEP_STAGES = {"AsleepCore": "core", "AsleepDeep": "deep", "AsleepREM": "rem",
                 "AsleepUnspecified": "unspecified"}
ONEMORE_WORKOUTS = {"HKWorkoutActivityTypeTraditionalStrengthTraining",
                    "HKWorkoutActivityTypeCoreTraining"}


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


def parse_health_xml(stream) -> list[Metric]:
    out: list[Metric] = []
    steps: dict[tuple[date, str], float] = defaultdict(float)
    sleep: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    hr_t: list[float] = []  # raw heart-rate samples, epoch seconds, appended in file order
    hr_v: list[float] = []
    workouts: list[tuple[datetime, datetime, float | None, dict[str, float]]] = []

    it = ET.iterparse(stream, events=("start", "end"))
    _, root = next(it)
    for ev, el in it:
        if ev != "end":
            continue
        if el.tag == "Record":
            _record(el, out, steps, sleep, hr_t, hr_v)
        elif el.tag == "Workout":
            _workout(el, workouts)
        else:
            continue
        el.clear()
        root.clear()  # or every cleared element stays a child of the root, and 2.3M of them add up

    by_day: dict[date, float] = {}
    for (day, _), n in steps.items():
        by_day[day] = max(by_day.get(day, 0.0), n)
    out += [Metric(SOURCE, "step_count", _midnight(d), v, "count") for d, v in sorted(by_day.items())]

    for night, parts in sorted(sleep.items()):
        asleep = sum(parts.get(k, 0.0) for k in ASLEEP_STAGES.values())
        if asleep:
            out.append(Metric(SOURCE, "sleep_analysis/asleep", _midnight(night), asleep, "hr"))
        for key in ("in_bed", "deep", "rem", "core"):
            if parts.get(key):
                out.append(Metric(SOURCE, f"sleep_analysis/{key}", _midnight(night), parts[key], "hr"))

    order = sorted(range(len(hr_t)), key=hr_t.__getitem__)
    hr_t = [hr_t[i] for i in order]
    hr_v = [hr_v[i] for i in order]
    for start, end, minutes, stats in workouts:
        if "hr_avg" not in stats and hr_t:
            lo, hi = bisect_left(hr_t, start.timestamp()), bisect_right(hr_t, end.timestamp())
            if hi > lo:
                window = hr_v[lo:hi]
                stats["hr_avg"] = sum(window) / len(window)
                stats["hr_max"] = max(window)
                stats["hr_min"] = min(window)
        for part, v in stats.items():
            unit = "bpm" if part.startswith("hr_") else "kcal"
            out.append(Metric(SOURCE, f"workout/{part}", start, v, unit))
        if minutes is not None:
            out.append(Metric(SOURCE, "workout/minutes", start, minutes, "min"))
    return out


def _record(el, out, steps, sleep, hr_t, hr_v) -> None:
    t = el.get("type")
    if t in QUANTITIES:
        v = _float(el.get("value"))
        if v is None:
            return
        unit = UNITS.get(el.get("unit") or "", el.get("unit") or "")
        if t.endswith("BodyFatPercentage") and v <= 1.0:
            v *= 100  # Withings writes the fraction under a "%" unit
        out.append(Metric(SOURCE, QUANTITIES[t], parse_date(el.get("startDate")), v, unit))
    elif t == STEPS:
        v = _float(el.get("value"))
        if v is not None:
            steps[(parse_date(el.get("startDate")).date(), el.get("sourceName") or "")] += v
    elif t == HEART_RATE:
        v = _float(el.get("value"))
        if v is not None:
            hr_t.append(parse_date(el.get("startDate")).timestamp())
            hr_v.append(v)
    elif t == SLEEP:
        value = (el.get("value") or "").removeprefix("HKCategoryValueSleepAnalysis")
        start, end = parse_date(el.get("startDate")), parse_date(el.get("endDate"))
        hours = (end - start).total_seconds() / 3600
        if hours <= 0:
            return
        night = end.date()
        if value == "InBed":
            sleep[night]["in_bed"] += hours
        elif value in ASLEEP_STAGES:
            sleep[night][ASLEEP_STAGES[value]] += hours


def _workout(el, workouts) -> None:
    if el.get("workoutActivityType") not in ONEMORE_WORKOUTS:
        return
    start, end = parse_date(el.get("startDate")), parse_date(el.get("endDate"))
    minutes = _float(el.get("duration"))
    if minutes is not None and el.get("durationUnit") == "sec":
        minutes /= 60
    stats: dict[str, float] = {}
    for st in el.findall("WorkoutStatistics"):
        if st.get("type") == HEART_RATE:
            for part, attr in (("hr_avg", "average"), ("hr_max", "maximum"), ("hr_min", "minimum")):
                v = _float(st.get(attr))
                if v is not None:
                    stats[part] = v
        elif st.get("type") == f"{Q}ActiveEnergyBurned":
            v = _float(st.get("sum"))
            if v is not None:
                stats["kcal"] = v
    workouts.append((start, end, minutes, stats))


def _float(s: str | None) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


def open_export(path: str | Path):
    """The zip Health hands you, or an `export.xml` already unpacked from it."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        name = next(n for n in zf.namelist() if n.endswith("export.xml"))
        return zf.open(name)
    return open(path, "rb")


def import_health_export(store, path: str | Path) -> tuple[int, int]:
    """Parse a Health export (zip or xml) into the store; returns (new, readings)."""
    path = Path(path)
    with open_export(path) as f:
        metrics = parse_health_xml(f)
    new = store.upsert_metrics(metrics)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    store.record_import(SOURCE, str(path), h.hexdigest(), new, len(metrics))
    return new, len(metrics)
