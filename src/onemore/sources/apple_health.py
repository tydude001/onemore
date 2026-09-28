"""Apple Health via the Health Auto Export app (iOS), as JSON.

HealthKit has no server-side API; Health Auto Export is the phone-side bridge. Its REST
automation POSTs a JSON body on a schedule (custom headers supported, so the same
`X-Token` guards it), and its manual export produces the same document. The shape, from
the vendor's format pages (docs/research/strong-data-out.md § Apple Health):

    {"data": {
       "metrics": [
         {"name": "step_count", "units": "count", "data": [{"date": "...", "qty": 8500}]},
         {"name": "heart_rate", "units": "bpm",
          "data": [{"date": "...", "Min": 65, "Avg": 72, "Max": 85}]},
         {"name": "sleep_analysis", "units": "hr",
          "data": [{"date": "2024-02-06", "asleep": 7.0, "deep": 1.5, ...}]}],
       "workouts": [
         {"id": "...", "name": "Traditional Strength Training",
          "start": "2024-02-06 07:00:00 -0800", "end": "...", "duration": 3600,
          "activeEnergyBurned": {"qty": 300, "units": "kcal"},
          "heartRate": {"min": 80, "avg": 120, "max": 160}}]}}

Dates are `yyyy-MM-dd HH:mm:ss Z`; daily aggregates carry a bare date. Every reading
becomes a `Metric`: a single-valued entry under the metric's name, a multi-valued one
under `name/part` (`heart_rate/avg`, `sleep_analysis/asleep`), and a workout under
`workout/hr_avg`, `workout/hr_max`, `workout/kcal`, `workout/minutes` at its start.

Enrichment only. Nothing in the engine requires any of this; `onemore status` and the
phone page show the trend, and a recovery rule can read it once there is enough of it to
set a threshold against.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from ..model import Metric

SOURCE = "apple_health"

_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def parse_date(s: str) -> datetime:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(s)


def norm(name: str) -> str:
    """`Weight & Body Mass` / `weight_&_body_mass` / `totalSleep` -> snake_case."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return re.sub(r"_+", "_", s)


def parse_health_json(text: str) -> list[Metric]:
    doc = json.loads(text)
    data = doc.get("data", doc)
    out: list[Metric] = []
    for m in data.get("metrics", []) or []:
        name, unit = norm(str(m.get("name", ""))), str(m.get("units", "") or "")
        if not name:
            continue
        for entry in m.get("data", []) or []:
            if "date" not in entry:
                continue
            at = parse_date(str(entry["date"]))
            values = {k: v for k, v in entry.items()
                      if k != "date" and isinstance(v, (int, float)) and not isinstance(v, bool)}
            if "qty" in values and len(values) == 1:
                out.append(Metric(SOURCE, name, at, float(values["qty"]), unit))
                continue
            for k, v in values.items():
                out.append(Metric(SOURCE, f"{name}/{norm(k)}", at, float(v), unit))
    for w in data.get("workouts", []) or []:
        if "start" not in w:
            continue
        at = parse_date(str(w["start"]))
        hr = w.get("heartRate") or {}
        for part, key in (("hr_avg", "avg"), ("hr_max", "max"), ("hr_min", "min")):
            v = hr.get(key, hr.get(key.capitalize()))
            if isinstance(v, dict):
                v = v.get("qty")
            if isinstance(v, (int, float)):
                out.append(Metric(SOURCE, f"workout/{part}", at, float(v), "bpm"))
        kcal = (w.get("activeEnergyBurned") or {}).get("qty")
        if isinstance(kcal, (int, float)):
            out.append(Metric(SOURCE, "workout/kcal", at, float(kcal), "kcal"))
        dur = w.get("duration")
        if isinstance(dur, (int, float)):
            out.append(Metric(SOURCE, "workout/minutes", at, float(dur) / 60, "min"))
    return out


def import_health_text(store, text: str, filename: str = "-") -> tuple[int, int]:
    """Parse and store; returns (new readings, readings in the document)."""
    metrics = parse_health_json(text)
    new = store.upsert_metrics(metrics)
    store.record_import(SOURCE, filename, hashlib.sha256(text.encode()).hexdigest(),
                        new, len(metrics))
    return new, len(metrics)
