"""advance(): close the current week, run the rules, persist adjustments and state."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from .exercises import Catalog
from .model import Adjustment
from .program.programs import DEFAULT_PROGRAM, PROGRAMS
from .program.spec import Program, Week, WeekKind
from .rules.base import HISTORY_DAYS, Context
from .store import Store

# State keys the store round-trips. A rule may only write to these; see _apply().
PERSISTED_STATE = frozenset({
    "tm_kg", "e1rm_kg", "misses", "sets_delta", "hard_weeks", "easy_weeks",
    "reps_delta", "at_ceiling",
})

# Fields a rule emits to speak to advance() rather than to the store.
TRANSIENT_FIELDS = frozenset({"week", "deload_next"})

_log = logging.getLogger(__name__)

RECOVERY_METRIC = "resting_heart_rate"  # the only health series a rule reads (rules/recovery.py)


@dataclass(slots=True)
class PlanStatus:
    program: str
    days: int
    started_on: date
    current_week: int
    deload_next: bool
    # {week number: (start, end exclusive)} for every closed week, as it was actually
    # trained. A repeat moves `started_on`, so dates derived from it are right only for the
    # current week and later; a closed week must keep its own or it re-reads another's log.
    closed: dict[int, tuple[date, date]] = field(default_factory=dict)


def plan_status(store: Store) -> PlanStatus | None:
    p = store.get_plan("plan")
    if not p:
        return None
    program, days = p["program"], p["days"]
    if program not in PROGRAMS:
        # A plan stored under a program name PROGRAMS no longer has (a retired name, a typo,
        # a downgrade) would KeyError in every caller. Read it as the default program at its
        # own day count instead; the stored row is left as it is, and the next `start`
        # overwrites it. `comeback` and `rebuild` are both registered, so a plan stored under
        # either name is read as itself and never hits this branch.
        _log.warning("stored plan names unknown program %r; reading it as %r",
                     program, DEFAULT_PROGRAM)
        program = DEFAULT_PROGRAM
        days = PROGRAMS[DEFAULT_PROGRAM]().days_per_week
    closed = {int(n): (date.fromisoformat(s), date.fromisoformat(e))
              for n, (s, e) in p.get("windows", {}).items()}
    return PlanStatus(program, days, date.fromisoformat(p["started_on"]),
                      int(p["current_week"]), bool(p.get("deload_next", False)), closed)


def start_plan(store: Store, program: Program, on: date) -> PlanStatus:
    store.set_plan("plan", {"program": program.name, "days": program.days_per_week,
                            "started_on": on.isoformat(), "current_week": 1, "deload_next": False})
    return plan_status(store)


def week_window(status: PlanStatus, week_no: int) -> tuple[date, date]:
    if week_no in status.closed:
        return status.closed[week_no]
    start = status.started_on + timedelta(days=7 * (week_no - 1))
    return start, start + timedelta(days=7)


def provisional_tms(store: Store, program: Program, status: PlanStatus,
                    week_no: int) -> dict[str, tuple[float, float]]:
    """{lift: (provisional TM kg, the e1RM it came from)} for each main lift with no TM.

    A main lift that joins a running plan has no TM until `calibrate_new_lift` closes a
    week it was trained in, and until then its percent-of-TM slots would print no load at
    all. This fills the gap with the number that rule will compute: `tm_factor` x the best
    e1RM in the HISTORY_DAYS before the week starts. The window ends at the week's start,
    so the load does not move mid-week when an import lands. A lift with nothing logged
    in that window stays blank on purpose -- pre-injury history is not evidence of what
    the elbow can take now, and the seeded week exists to measure exactly that.

    Render-only: never stored, never read by a rule. The renderer labels it provisional."""
    from . import estimate

    start, _ = week_window(status, week_no)
    out = {}
    for lift in program.main_lifts():
        if store.get_state(lift, "tm_kg") is not None:
            continue
        sets = store.sets_for(lift, since=start - timedelta(days=HISTORY_DAYS))
        best, _ = estimate.rolling_e1rm(sets, start - timedelta(days=1),
                                        window_days=HISTORY_DAYS)
        if best is not None:
            out[lift] = (estimate.training_max(best, program.lifts[lift].tm_factor), best)
    return out


def provisional_note(tm_kg: float, e1rm_kg: float, factor: float, unit: str) -> str:
    """The "why" line for a provisional TM, so the load is never shown unexplained."""
    from .units import from_kg

    return (f"no TM yet: provisional TM {from_kg(tm_kg, unit):.0f} {unit} = {factor:g} x "
            f"best e1RM {from_kg(e1rm_kg, unit):.0f} {unit} in the {HISTORY_DAYS} days before "
            f"this week; calibrate_new_lift sets the real one when this week closes")


def effective_week(program: Program, status: PlanStatus, week_no: int) -> Week:
    w = program.week(week_no)
    if status.deload_next and week_no == status.current_week and w.kind == WeekKind.WORK:
        deload = next(x for x in program.weeks if x.kind == WeekKind.DELOAD)
        return Week(week_no, WeekKind.DELOAD, deload.days, "deload (fatigue trigger)")
    return w


def build_context(store: Store, program: Program, status: PlanStatus, week_no: int,
                  unit: str, catalog: Catalog | None = None) -> Context:
    start, end = week_window(status, week_no)
    week = effective_week(program, status, week_no)
    history = store.sessions(since=start - timedelta(days=HISTORY_DAYS),
                             until=end - timedelta(days=1))
    sessions = [s for s in history if s.date >= start]
    # 28 days back from the week's end: the recovery rule's baseline window. Empty on a
    # database with no Health import, which is the same to every rule as None.
    metrics = store.metrics(RECOVERY_METRIC, since=end - timedelta(days=28))
    return Context(program=program, week_no=week_no, week=week, start=start, end=end,
                   sessions=sessions, states=store.all_state(),
                   catalog=catalog or Catalog.load(), unit=unit, history=history,
                   metrics=metrics)


def advance(store: Store, program: Program, unit: str = "lb", force: bool = False,
            asof: date | None = None,
            catalog: Catalog | None = None) -> tuple[list[Adjustment], PlanStatus]:
    """Evaluate the current week. Returns the adjustments that fired and the new status.

    Refuses to close a week whose window has not ended unless `force`.
    """
    status = plan_status(store)
    if status is None:
        raise RuntimeError("no plan started; run `onemore start`")
    today = asof or date.today()
    start, end = week_window(status, status.current_week)
    if today < end and not force:
        raise RuntimeError(
            f"week {status.current_week} runs {start} to {end - timedelta(days=1)}; "
            f"today is {today}. Use --force to close it early.")
    ctx = build_context(store, program, status, status.current_week, unit, catalog)
    fired: list[Adjustment] = []
    repeat = False
    for rule in program.rules:
        ctx._cache["adjustments_so_far"] = fired
        adjs = rule(ctx)
        fired.extend(adjs)
        for a in adjs:
            _apply(store, ctx, a)
        if any(a.field == "week" for a in adjs):
            repeat = True
            ctx.repeated = True
            break  # nothing else to learn from a week that was not trained
    store.add_adjustments(fired)
    p = store.get_plan("plan")
    # Pin every closed week's dates before a repeat can move `started_on`. Weeks before the
    # current one are backfilled from it: a plan that has never repeated derives them right,
    # and from here on none goes unrecorded.
    windows = p.setdefault("windows", {})
    for n in range(1, status.current_week + (0 if repeat else 1)):
        if str(n) not in windows:
            s, e = week_window(status, n)
            windows[str(n)] = [s.isoformat(), e.isoformat()]
    if repeat:
        # Shift the schedule so the repeated week starts now, not in the past.
        p["started_on"] = (date.fromisoformat(p["started_on"]) + timedelta(days=7)).isoformat()
    else:
        p["current_week"] = status.current_week + 1
        p["deload_next"] = any(a.field == "deload_next" for a in fired) and (
            ctx.week.kind != WeekKind.DELOAD)
        if ctx.week.kind == WeekKind.DELOAD:
            p["deload_next"] = False
    store.set_plan("plan", p)
    return fired, plan_status(store)


def _apply(store: Store, ctx: Context, a: Adjustment) -> None:
    if a.lift == "*":
        return  # plan-level; handled by advance()
    if a.field in PERSISTED_STATE:
        store.set_state(a.lift, a.field, a.new)
        ctx.states.setdefault(a.lift, {})[a.field] = a.new
    elif a.field not in TRANSIENT_FIELDS:
        # A rule that emits state nothing persists changes the plan for exactly one week
        # and then silently forgets — the failure mode CLAUDE.md calls a bug. Loud here
        # rather than invisible in a green test suite.
        raise ValueError(
            f"rule {a.rule!r} set {a.field!r} on {a.lift!r}, which nothing persists; "
            f"add it to engine.PERSISTED_STATE or to TRANSIENT_FIELDS")


def seed_from_history(store: Store, program: Program, unit: str, decay: float = 0.8,
                      max_age_days: int = 180) -> list[Adjustment]:
    """Before week 1: set a decayed e1RM from old history as a ceiling. Recent data (within
    `max_age_days`) is taken at face value. Explicit and recorded like any other rule.

    Every lift in the program is seeded, not only the main lifts: the seeded week
    prescribes accessories as a percentage of their own e1RM too, and without a seed the
    renderer has nothing to resolve them against until the first export lands."""
    from . import estimate

    out = []
    today = date.today()
    for lift in program.lifts:
        sets = store.sets_for(lift)
        best, when = estimate.historical_best(sets)
        if not best:
            continue  # no history, or bodyweight logged at 0: nothing to seed from
        age = (today - when).days
        factor = 1.0 if age <= max_age_days else decay
        val = best * factor
        old = store.get_state(lift, "e1rm_kg")
        reason = (f"historical best e1RM {val / factor:.1f} kg on {when}"
                  + (f", {age} days old: x{decay:g} decay" if factor != 1 else ", recent: taken as is"))
        a = Adjustment("seed_from_history", lift, "e1rm_kg", old, val, reason, (), 0)
        store.set_state(lift, "e1rm_kg", val)
        out.append(a)
    store.add_adjustments(out)
    return out
