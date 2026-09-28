"""Strong app CSV export → canonical sessions.

Handles the three known variants (docs/research/hevy-api-and-strong-csv.md):
  1. 12 columns, comma:  Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,
                         Distance,Seconds,Notes,Workout Notes,RPE
  2. 10 columns, comma:  same without Notes / Workout Notes
  3. semicolon-delimited with unit-suffixed headers like "Weight (kg)" (reported, not seen)

Units: the comma variants carry no unit, so `weight_unit` is config. A unit-suffixed header
overrides it. Warm-up sets carry Set Order "W"; "D" and "F" are accepted as drop/failure.
One session = one (Date, Workout Name); the source_key is exactly that.

Set Order "Rest Timer" is not a set: it is the rest taken after the set above it, weight 0,
reps 0, the rest in Seconds. Exports from recent Strong versions have them; older history
has none. Dropped here, and
`Store.drop_rest_timers` clears the ones imported before this knew about them.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path

from ..exercises import Catalog
from ..model import ExerciseEntry, Session, Set, SetType
from ..units import to_kg

SOURCE = "strong"
REST_TIMER = "rest timer"  # a Set Order value, casefolded
_DUR = re.compile(r"(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?")


def parse_duration(text: str) -> timedelta | None:
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    m = _DUR.fullmatch(text.replace(" ", ""))
    if not m or not any(m.groups()):
        return None
    h, mi, s = (int(g) if g else 0 for g in m.groups())
    return timedelta(hours=h, minutes=mi, seconds=s)


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    t = text.strip().replace(",", ".")
    if t == "":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _header_map(fields: list[str]) -> tuple[dict[str, str], str | None]:
    """Map canonical column names to actual header names; detect a unit suffix on Weight."""
    m: dict[str, str] = {}
    unit = None
    for f in fields:
        base = f.strip()
        um = re.fullmatch(r"(.+?)\s*\((kg|lbs?)\)", base, re.IGNORECASE)
        if um:
            base, u = um.group(1).strip(), um.group(2).lower()
            if base.lower() == "weight":
                unit = "kg" if u == "kg" else "lb"
        m[base.lower()] = f
    return m, unit


class StrongCsvSource:
    name = SOURCE

    def __init__(self, text: str, catalog: Catalog, weight_unit: str = "lb"):
        self.text = text
        self.catalog = catalog
        self.weight_unit = weight_unit

    @classmethod
    def from_path(cls, path, catalog: Catalog, weight_unit: str = "lb") -> StrongCsvSource:
        raw = Path(path).read_bytes()
        return cls(raw.decode("utf-8-sig"), catalog, weight_unit)

    def fetch_sessions(self, since: datetime | None = None) -> Iterable[Session]:
        sessions = list(self._parse())
        if since:
            sessions = [s for s in sessions if s.started_at >= since]
        return sessions

    def _parse(self) -> Iterable[Session]:
        sample = self.text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(self.text), dialect=dialect)
        header = next(reader, None)
        if not header:
            return
        cols, header_unit = _header_map(header)
        unit = header_unit or self.weight_unit
        for req in ("date", "exercise name", "set order", "weight", "reps"):
            if req not in cols:
                raise ValueError(f"not a Strong export: missing column {req!r}")
        pos = {name.strip().lower(): i for i, name in enumerate(header)}
        for base, actual in cols.items():
            pos[base] = header.index(actual)
        width = len(header)

        def col(row, key, default=""):
            i = pos.get(key)
            return row[i] if i is not None and i < len(row) else default

        by_key: dict[str, Session] = {}
        order_by_key: dict[str, dict[str, ExerciseEntry]] = {}
        for i, row in enumerate(reader, start=2):
            if not row or not any(cell.strip() for cell in row):
                continue
            row = _repair_row(row, width, pos.get("duration"))
            date_text = col(row, "date").strip()
            if not date_text or col(row, "set order").strip().casefold() == REST_TIMER:
                continue
            started = _parse_date(date_text)
            title = col(row, "workout name").strip()
            key = f"{date_text}|{title}"
            sess = by_key.get(key)
            if sess is None:
                sess = Session(
                    source=SOURCE, source_key=key, started_at=started,
                    duration=parse_duration(col(row, "duration")), title=title,
                    notes=col(row, "workout notes").strip(),
                )
                by_key[key] = sess
                order_by_key[key] = {}
            raw_name = col(row, "exercise name").strip()
            entries = order_by_key[key]
            entry = entries.get(raw_name)
            if entry is None:
                entry = ExerciseEntry(
                    exercise_id=self.catalog.resolve(SOURCE, raw_name), order=len(entries),
                    notes=col(row, "notes").strip(), source_name=raw_name,
                )
                entries[raw_name] = entry
                sess.entries.append(entry)
            set_order = col(row, "set order").strip()
            set_type, idx = _set_type(set_order, len(entry.sets))
            weight = _num(col(row, "weight"))
            reps = _num(col(row, "reps"))
            entry.sets.append(
                Set(
                    index=idx, set_type=set_type,
                    weight_kg=to_kg(weight, unit) if weight is not None else None,
                    reps=int(reps) if reps is not None else None,
                    rpe=_num(col(row, "rpe")),
                    source_ref=f"strong:{key}:{raw_name}:{set_order}:r{i}",
                )
            )
        yield from by_key.values()


def _repair_row(row: list[str], width: int, duration_pos: int | None) -> list[str]:
    """Strong writes a duration over 999 hours as `1,301h 4m`, unquoted, which splits the
    row one field wide. Re-join it when the two halves read as a thousands-separated
    duration. Seen in a real 2024 export (the timer had been left running for 54 days)."""
    if len(row) == width + 1 and duration_pos is not None and duration_pos + 1 < len(row):
        a, b = row[duration_pos], row[duration_pos + 1]
        if a.isdigit() and re.fullmatch(r"\d{3}h.*", b.strip()):
            return row[:duration_pos] + [f"{a}{b}"] + row[duration_pos + 2 :]
    return row


def _parse_date(text: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognised Strong date {text!r}")


def _set_type(set_order: str, position: int) -> tuple[SetType, int]:
    s = set_order.strip().upper()
    if s.isdigit():
        return SetType.WORK, int(s)
    if s.startswith("W"):
        return SetType.WARMUP, position + 1
    if s.startswith("D"):
        return SetType.DROP, position + 1
    if s.startswith("F"):
        return SetType.FAILURE, position + 1
    return SetType.WORK, position + 1
