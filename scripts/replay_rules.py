"""Replay the adaptation rules over the real imported history and print what fires.

Tests use the synthetic fixtures and never the real export, so this is the other half:
the check against real data that CLAUDE.md asks for. It builds a program out of the
exercises the history actually contains — leg press, machine shoulder press, seated row,
machine curls — so the rules have something to chew on, and walks a week at a time from
the first session to the last, printing every Adjustment with its evidence.

It is a read-only dry run: an in-memory copy of the store, nothing written back.

    uv run python -m scripts.replay_rules [path/to/onemore.db] [--weeks N]

Nothing here decides which movements the real program uses — that is the program's
business (PLAN.md § Which movements are main). The scaffold below only proves the rules
fire correctly on real sets; the real sessions are machine circuits that match no
program's day layout, so replaying a program itself would mostly show missed weeks.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from datetime import timedelta
from pathlib import Path

from onemore.engine import RECOVERY_METRIC
from onemore.exercises import Catalog
from onemore.program.spec import Day, LiftSpec, Program, Rpe, Sets, Slot, Week, WeekKind
from onemore.rules import DEFAULT_RULES
from onemore.rules.base import HISTORY_DAYS, Context
from onemore.store import Store

# The four most-logged exercises in the export, as main lifts, plus the accessories that
# ran alongside them. A scaffold for the replay, not a proposed program.
MAIN = ["leg_press", "machine_shoulder_press", "leg_curl", "seated_row"]
ACCESSORY = ["machine_bicep_curl", "chest_press", "triceps_extension_machine",
             "dumbbell_bench_press", "lat_pulldown", "arnold_press"]


def build_program() -> Program:
    lifts = {i: LiftSpec(i) for i in MAIN}
    lifts |= {i: LiftSpec(i, main=False) for i in ACCESSORY}
    top = Sets(1, 5, Rpe(8), amrap=True)
    days = tuple(
        Day(f"Day {n}", (Slot(m, (Sets(3, 5, Rpe(7)), top)),
                         Slot(ACCESSORY[n % len(ACCESSORY)], (Sets(3, (8, 12), Rpe(8)),))))
        for n, m in enumerate(MAIN))
    weeks = [Week(1, WeekKind.CALIBRATION, days, "calibration")]
    weeks += [Week(n, WeekKind.WORK, days, f"work {n}") for n in range(2, 6)]
    return Program("replay", lifts, weeks, list(DEFAULT_RULES), days_per_week=len(MAIN))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", nargs="?", default="data/onemore.db")
    ap.add_argument("--weeks", type=int, default=0, help="stop after N weeks (0 = all)")
    ap.add_argument("--ignore-missed", action="store_true",
                    help="keep running the later rules through a week missed_week_repeat "
                         "would have repeated. Diagnostic only — the engine really does "
                         "stop there — but without it no rule downstream is ever reached "
                         "on this history.")
    a = ap.parse_args()

    if not Path(a.db).exists():
        print(f"no database at {a.db}; run `onemore import` first")
        return 1
    # Copy the real db into an in-memory store: read-only by construction, so a replay
    # can never write state back into the file the CLI uses.
    store = Store(":memory:")
    src = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    src.backup(store.db)
    src.close()

    catalog = Catalog.load()
    program = build_program()
    missing = program.unavailable(catalog)
    if missing:
        print(f"program prescribes unavailable equipment: {missing}")
        return 2

    sessions = store.sessions()
    if not sessions:
        print(f"no sessions in {a.db}")
        return 1
    first, last = sessions[0].date, sessions[-1].date
    print(f"{len(sessions)} sessions, {first} to {last}\n")

    states: dict[str, dict[str, float | None]] = {}
    fired = Counter()
    week_no, start, silent = 1, first, 0
    while start <= last and (not a.weeks or week_no <= a.weeks):
        end = start + timedelta(days=7)
        wk = program.week(week_no)
        history = store.sessions(since=start - timedelta(days=HISTORY_DAYS),
                                 until=end - timedelta(days=1))
        ctx = Context(program=program, week_no=week_no, week=wk, start=start, end=end,
                      sessions=[s for s in history if s.date >= start],
                      states=states, catalog=catalog, history=history,
                      # the recovery rule reads these; without them the replay would
                      # report it silent for the one reason that proves nothing
                      metrics=store.metrics(RECOVERY_METRIC, since=end - timedelta(days=28)))
        adjs = []
        for rule in program.rules:
            ctx._cache["adjustments_so_far"] = adjs
            got = rule(ctx)
            adjs.extend(got)
            for adj in got:
                if adj.lift != "*":
                    states.setdefault(adj.lift, {})[adj.field] = adj.new
            if any(x.field == "week" for x in got) and not a.ignore_missed:
                break
        if adjs:
            print(f"── week {week_no} ({start} to {end - timedelta(days=1)}, "
                  f"{len(ctx.sessions)} sessions, {wk.kind})")
            for adj in adjs:
                fired[adj.rule] += 1
                ev = f"  [{len(adj.evidence)} sets]" if adj.evidence else ""
                print(f"   {adj.rule:22} {adj.lift:26} {adj.field:11} {adj.reason}{ev}")
            print()
        else:
            silent += 1
        week_no, start = week_no + 1, end

    print(f"{week_no - 1} weeks replayed, {silent} with nothing to say")
    print("\nrules fired:")
    for rule, n in fired.most_common():
        print(f"  {rule:24} {n}")
    never = [r.__name__ for r in program.rules if r.__name__ not in fired]
    if never:
        print(f"\nnever fired: {', '.join(never)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
