from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from ..exercises import Catalog
from ..model import Adjustment, Metric, Session, Set, SetType
from ..program.spec import Day, Program, Week

Rule = Callable[["Context"], list[Adjustment]]

HISTORY_DAYS = 21  # the rolling e1RM window; the engine loads this much before the week


def match_days(days: tuple[Day, ...] | list[Day],
               sessions: list[Session]) -> list[tuple[int, Session]]:
    """(index into `days`, the session that trained it), in logged order. The one matching
    `Context.logged_days` documents; the week page reads it too, so a day the page shows
    as done is exactly a day the rules counted."""
    unmatched = list(range(len(days)))
    out = []
    for s in sessions:
        for e in sorted(s.entries, key=lambda e: e.order):
            hit = next((i for i in unmatched if days[i].main_lift == e.exercise_id), None)
            if hit is not None:
                unmatched.remove(hit)
                out.append((hit, s))
                break
    return out


@dataclass(slots=True)
class Context:
    """Everything a rule may look at when a week closes. Rules read; the engine writes."""

    program: Program
    week_no: int
    week: Week
    start: date
    end: date  # exclusive
    sessions: list[Session]
    states: dict[str, dict[str, float | None]]
    catalog: Catalog  # load steps and ceilings; rules must not hard-code either
    unit: str = "lb"
    repeated: bool = False  # set by the engine when missed_week_repeat fired
    # Sessions from HISTORY_DAYS before the week through its end, for the rolling e1RM.
    # None means "only this week's sessions are known", which is what a bare Context
    # built in a test has.
    history: list[Session] | None = None
    # Health readings covering the 28 days that end with this week, or None where the
    # engine did not load any. None and "no readings" both mean every rule that reads
    # them stays silent: they are enrichment, and no rule may require them.
    metrics: list[Metric] | None = None
    _cache: dict = field(default_factory=dict, repr=False)

    def state(self, lift: str, key: str) -> float | None:
        return self.states.get(lift, {}).get(key)

    def step_kg(self, lift: str) -> float:
        """This lift's load increment. The program may override it; otherwise it is the
        catalog's, which is measured from the equipment rather than assumed."""
        spec = self.program.lifts.get(lift)
        if spec is not None and spec.inc_kg is not None:
            return spec.inc_kg
        return self.catalog.step_kg(lift)

    def ceiling_kg(self, lift: str) -> float | None:
        """The load this lift cannot exceed, or None where it is genuinely unknown.
        None is common and means "no ceiling rule fires", never "no ceiling exists"."""
        return self.catalog.ceiling_kg(lift)

    def sets_in_week(self, lift: str, work_only: bool = True) -> list[tuple[date, Set]]:
        k = (lift, work_only, "week")
        if k not in self._cache:
            self._cache[k] = self._sets(self.sessions, lift, work_only)
        return self._cache[k]

    def sets_in_history(self, lift: str) -> list[tuple[date, Set]]:
        """Completed work sets over the history window, this week included. What the
        rolling e1RM reads; a rule judging *this week's* performance reads
        `sets_in_week`, or a good set from three weeks ago would count again."""
        k = (lift, True, "history")
        if k not in self._cache:
            src = self.sessions if self.history is None else self.history
            self._cache[k] = self._sets(src, lift, True)
        return self._cache[k]

    @staticmethod
    def _sets(sessions: list[Session], lift: str, work_only: bool) -> list[tuple[date, Set]]:
        out = []
        for s in sessions:
            for e in s.entries:
                if e.exercise_id != lift:
                    continue
                for st in e.sets:
                    if work_only and (st.set_type != SetType.WORK or not st.completed):
                        continue
                    out.append((s.date, st))
        return out

    def notes_in_week(self, lift: str) -> list[str]:
        """This week's non-empty exercise notes on `lift` -- Strong's per-exercise note,
        the only place a logged set can say why it stopped."""
        return [e.notes for s in self.sessions for e in s.entries
                if e.exercise_id == lift and e.notes.strip()]

    def sessions_with(self, lift: str) -> list[Session]:
        return [s for s in self.sessions if any(e.exercise_id == lift for e in s.entries)]

    def logged_days(self) -> list[Day]:
        """The week's planned days that were trained, matching each logged session to at
        most one planned day. Two lower days that share the leg press must not both count
        from one session, and one circuit session that happens to hit three main lifts is
        still one day trained.

        A session is the day whose main lift it reaches first, in logged order. `comeback`
        puts the leg curl on both lower days, so "the first day whose main lift appears
        anywhere in the session" called a Lower 2 session Lower 1 whenever Lower 1 was
        still unmatched, and `tm_progress` would then judge the wrong day's top set."""
        return [self.week.days[i] for i, _ in match_days(self.week.days, self.sessions)]

    def planned_days_logged(self) -> int:
        return len(self.logged_days())

    def adj(self, rule: str, lift: str, fld: str, old, new, reason: str, evidence=()) -> Adjustment:
        return Adjustment(rule, lift, fld, old, new, reason, tuple(evidence), self.week_no)

    def fmt(self, kg: float | None) -> str:
        if kg is None:
            return "none"
        from ..units import from_kg

        return f"{from_kg(kg, self.unit):.0f} {self.unit}"
