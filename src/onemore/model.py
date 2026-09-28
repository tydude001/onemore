"""Canonical data model. Every source adapter produces these; everything else consumes them.

Loads are kilograms. `Set.rpe` is the logged RPE if the source has one; `rir` likewise.
`source_key` is the natural key a source dedupes on, so re-importing the same data is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class SetType(StrEnum):
    WORK = "work"
    WARMUP = "warmup"
    DROP = "drop"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class Set:
    index: int
    set_type: SetType
    weight_kg: float | None
    reps: int | None
    rpe: float | None = None
    rir: float | None = None
    completed: bool = True
    source_ref: str = ""


@dataclass(slots=True)
class ExerciseEntry:
    exercise_id: str
    order: int
    sets: list[Set] = field(default_factory=list)
    notes: str = ""
    source_name: str = ""  # the raw name the source used, kept for alias review

    def work_sets(self) -> list[Set]:
        return [s for s in self.sets if s.set_type == SetType.WORK and s.completed]


@dataclass(slots=True)
class Session:
    source: str
    source_key: str
    started_at: datetime
    duration: timedelta | None = None
    title: str = ""
    notes: str = ""
    bodyweight_kg: float | None = None
    entries: list[ExerciseEntry] = field(default_factory=list)

    @property
    def date(self):
        return self.started_at.date()


@dataclass(frozen=True, slots=True)
class Metric:
    """One health reading — bodyweight, resting HR, a night's sleep, a workout's mean HR.
    Enrichment only: nothing in the engine requires these. `at` keeps the source's own
    timezone offset when it has one, and a daily aggregate is dated at local midnight."""

    source: str
    name: str  # snake_case; multi-valued readings are "metric/part", e.g. "heart_rate/avg"
    at: datetime
    value: float
    unit: str = ""


@dataclass(frozen=True, slots=True)
class Adjustment:
    """One rule firing. Persisted so `onemore explain` can show why a plan changed."""

    rule: str
    lift: str
    field: str
    old: float | None
    new: float | None
    reason: str
    evidence: tuple[str, ...] = ()  # set source_refs or session keys the rule looked at
    week: int | None = None
