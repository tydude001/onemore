"""Program spec: a small internal DSL of dataclasses. Programs are Python modules, not text.

Borrowed from Liftoscript: loads as % of a state variable, @RPE, or absolute; `+` (AMRAP)
sets; per-lift persistent state; post-workout rules only (Liftoscript's `progress:`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ..model import Adjustment


@dataclass(frozen=True, slots=True)
class Pct:
    value: float  # 0.75 == 75 %
    of: str = "tm"  # "tm" (training max) or "e1rm"


@dataclass(frozen=True, slots=True)
class Rpe:
    value: float


@dataclass(frozen=True, slots=True)
class Abs:
    kg: float


@dataclass(frozen=True, slots=True)
class Bodyweight:
    added_kg: float = 0.0


Load = Pct | Rpe | Abs | Bodyweight


@dataclass(frozen=True, slots=True)
class Sets:
    n: int
    reps: int | tuple[int, int]
    load: Load
    amrap: bool = False  # last set is "as many reps as possible", Liftoscript's `1x5+`
    rest_s: int | None = None  # rest after each of these sets; None means "not prescribed"

    @property
    def min_reps(self) -> int:
        return self.reps if isinstance(self.reps, int) else self.reps[0]


@dataclass(frozen=True, slots=True)
class Warmup:
    """A ramp to the slot's first prescribed set, as (fraction of its load, reps) —
    Liftoscript's `warmup:` with percentages of the first working set. Loads round on
    the lift's own step at render time; a step that rounds to nothing, or to the same
    load as the one before it, is dropped there. Logged as warm-up sets in Strong these
    are ignored by every rule, which is the point."""

    steps: tuple[tuple[float, int], ...]


@dataclass(frozen=True, slots=True)
class Slot:
    lift: str
    sets: tuple[Sets, ...]
    note: str = ""
    warmup: Warmup | None = None


@dataclass(frozen=True, slots=True)
class Day:
    name: str
    slots: tuple[Slot, ...]

    @property
    def main_lift(self) -> str:
        return self.slots[0].lift


class WeekKind(StrEnum):
    CALIBRATION = "calibration"
    WORK = "work"
    DELOAD = "deload"


@dataclass(frozen=True, slots=True)
class Week:
    number: int
    kind: WeekKind
    days: tuple[Day, ...]
    label: str = ""

    def slots_for(self, lift: str) -> list[Slot]:
        return [s for d in self.days for s in d.slots if s.lift == lift]


@dataclass(frozen=True, slots=True)
class LiftSpec:
    """A lift as the *program* sees it: is it a main lift, and how is its TM handled.

    `inc_kg` is None by default and means "the catalog's step for this exercise". The
    increment is a property of the equipment, not of the program, so a program that
    hard-codes one is overriding measured data — do it only deliberately.
    """

    id: str
    inc_kg: float | None = None
    main: bool = True
    tm_factor: float = 0.9


@dataclass(slots=True)
class Program:
    name: str
    lifts: dict[str, LiftSpec]
    weeks: list[Week]
    rules: list[Callable] = field(default_factory=list)
    days_per_week: int = 3

    def week(self, n: int) -> Week:
        if 1 <= n <= len(self.weeks):
            return self.weeks[n - 1]
        # Past the defined weeks, keep cycling the last block (everything after calibration).
        body = [w for w in self.weeks if w.kind != WeekKind.CALIBRATION]
        w = body[(n - 1 - (len(self.weeks) - len(body))) % len(body)]
        return Week(number=n, kind=w.kind, days=w.days, label=w.label)

    def main_lifts(self) -> list[str]:
        return [lid for lid, spec in self.lifts.items() if spec.main]

    def unavailable(self, catalog) -> list[str]:
        """Lifts this program prescribes that the gym does not have. A program that
        prescribes a barbell at Planet Fitness should say so, not render a number."""
        return catalog.unavailable(self.lifts)


RuleResult = list[Adjustment]
