"""`onemore` CLI: import | import-health | status | start | plan | advance | explain |
serve | demo."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import secrets
import sys
import tempfile
from datetime import date, timedelta
from ipaddress import ip_address
from pathlib import Path

from . import engine, estimate, vitals
from .config import Config
from .exercises import Catalog
from .program.programs import DEFAULT_PROGRAM, PROGRAMS
from .program.render import render_week, to_text
from .sources.apple_health import import_health_text
from .sources.apple_health_xml import import_health_export
from .sources.strong_csv import StrongCsvSource
from .store import Store
from .units import from_kg


def _open(cfg: Config) -> Store:
    cfg.db.parent.mkdir(parents=True, exist_ok=True)
    return Store(cfg.db)


def import_strong_text(store: Store, catalog: Catalog, text: str, unit: str,
                       filename: str = "-") -> tuple[int, int]:
    src = StrongCsvSource(text, catalog, weight_unit=unit)
    new = seen = 0
    for s in src.fetch_sessions():
        seen += 1
        if store.upsert_session(s):
            new += 1
    store.drop_rest_timers()
    store.record_import("strong", filename, hashlib.sha256(text.encode()).hexdigest(), new, seen)
    return new, seen


def cmd_import(a, cfg: Config) -> int:
    store = _open(cfg)
    catalog = Catalog.load()
    text = Path(a.path).read_bytes().decode("utf-8-sig")
    new, seen = import_strong_text(store, catalog, text, a.unit or cfg.unit, a.path)
    print(f"{seen} sessions in file, {new} new")
    moves = store.remap_exercise_ids(catalog)
    if moves:
        print(f"{len(moves)} exercise names re-resolved against the catalog:")
        for (raw, o), n in sorted(moves.items()):
            print(f"  {raw!r:38s} {o} -> {n}")
    for src, names in catalog.unmapped.items():
        print(f"{len(names)} {src} exercise names not in the catalog (see `onemore status --unmapped`)")
    return 0


def cmd_import_health(a, cfg: Config) -> int:
    """Health Auto Export JSON, or the zip / export.xml Apple Health itself produces."""
    store = _open(cfg)
    if a.path.lower().endswith((".zip", ".xml")):
        new, seen = import_health_export(store, a.path)
    else:
        text = Path(a.path).read_bytes().decode("utf-8-sig")
        new, seen = import_health_text(store, text, a.path)
    print(f"{seen} readings in file, {new} new")
    for name, n in store.metric_names():
        print(f"  {name:36s} {n}")
    return 0


def _vitals_text(store: Store, cfg: Config) -> str:
    return vitals.to_text(vitals.summary(store, date.today(), cfg.unit), vitals.last_workout(store))


def _program(store: Store):
    st = engine.plan_status(store)
    if st is None:
        return None, None
    return PROGRAMS[st.program](st.days), st


def cmd_status(a, cfg: Config) -> int:
    store = _open(cfg)
    catalog = Catalog.load()
    sessions = store.sessions()
    if not sessions:
        print("no sessions imported")
        return 0
    print(f"{len(sessions)} sessions, {sessions[0].date} to {sessions[-1].date}")
    for imp in store.imports()[-3:]:
        print(f"  import {imp['received_at']} {imp['filename']}: {imp['sessions_new']} new / "
              f"{imp['sessions_seen']} seen")
    if a.unmapped:
        print("\nexercise ids not in the catalog (raw Strong name, entries):")
        for eid, raw, n in store.unmapped_names():
            if catalog.get(eid) is None:
                print(f"  {eid:40s} {raw!r:45s} {n}")
        return 0
    prog, st = _program(store)
    if prog is None:
        # No plan yet: show what `onemore start` would seed, i.e. the default program's
        # lifts. (The catalog marks nothing as main; main is program config.)
        prog = PROGRAMS[DEFAULT_PROGRAM]()
        print(f"\nthe lifts below are {prog.name}'s, as `onemore start` would seed them")
    print(f"\n{'lift':22s} {'best e1RM':>12s} {'when':>11s} {'21d e1RM':>10s} {'TM':>8s}")
    today = date.today()
    for lid in prog.lifts:
        sets = store.sets_for(lid)
        best, when = estimate.historical_best(sets)
        roll, _ = estimate.rolling_e1rm(sets, today)
        tm = store.get_state(lid, "tm_kg")
        f = lambda kg: f"{from_kg(kg, cfg.unit):.0f}" if kg is not None else "-"
        print(f"{catalog.name(lid):22s} {f(best):>12s} {when or '-'!s:>11s} {f(roll):>10s} {f(tm):>8s}")
    if st:
        s, e = engine.week_window(st, st.current_week)
        print(f"\nplan {st.program} ({st.days} days/wk), week {st.current_week}: {s} to {e}"
              + (" — deload next" if st.deload_next else ""))
    else:
        print("\nno plan started (`onemore start`)")
    v = _vitals_text(store, cfg)
    if v:
        print(f"\n{v}")
    return 0


def cmd_start(a, cfg: Config) -> int:
    store = _open(cfg)
    prog = PROGRAMS[a.program](a.days)
    on = date.fromisoformat(a.on) if a.on else date.today()
    seeded = engine.seed_from_history(store, prog, cfg.unit)
    st = engine.start_plan(store, prog, on)
    for adj in seeded:
        print(f"seed {adj.lift}: {adj.reason}")
    print(f"started {prog.name}, {prog.days_per_week} days/week, week 1 begins {st.started_on}")
    return 0


def _previous_text(store: Store, prog, cfg: Config) -> dict[str, str]:
    out = {}
    for lid in prog.lifts:
        sets = store.sets_for(lid)
        if not sets:
            continue
        last_day = sets[-1][0]
        todays = [s for d, s in sets if d == last_day and s.set_type == "work"]
        if not todays:
            continue
        parts = []
        for s in todays:
            w = f"{from_kg(s.weight_kg, cfg.unit):g}" if s.weight_kg is not None else "bw"
            parts.append(f"{w}x{s.reps}" + (f"@{s.rpe:g}" if s.rpe else ""))
        out[lid] = f"{last_day} " + " ".join(parts)
    return out


def cmd_plan(a, cfg: Config) -> int:
    store = _open(cfg)
    catalog = Catalog.load()
    prog, st = _program(store)
    if prog is None:
        print("no plan started (`onemore start`)")
        return 1
    n = a.week or st.current_week
    week = engine.effective_week(prog, st, n)
    prov = engine.provisional_tms(store, prog, st, n)
    rw = render_week(week, store.all_state(), catalog, cfg.unit, cfg.fallback_step_lb,
                     {k: tm for k, (tm, _) in prov.items()})
    notes = {}
    for adj in store.adjustments(week=n - 1):
        if adj.lift != "*" and adj.field in ("tm_kg", "sets_delta", "reps_delta"):
            notes.setdefault(adj.lift, []).append(f"{adj.rule}: {adj.reason}")
    for lift, (tm, e1) in prov.items():
        notes.setdefault(lift, []).append(
            engine.provisional_note(tm, e1, prog.lifts[lift].tm_factor, cfg.unit))
    print(to_text(rw, _previous_text(store, prog, cfg), notes,
                  vitals.to_line(vitals.summary(store, date.today(), cfg.unit))))
    s, e = engine.week_window(st, n)
    print(f"\n({s} to {e})")
    missing = prog.unavailable(catalog)
    if missing:
        print(f"\nWARNING: {len(missing)} of these need equipment this gym does not have: "
              + ", ".join(catalog.name(m) for m in missing)
              + "\n         The loads above are arithmetic, not a workout you can do.")
    return 0


def cmd_advance(a, cfg: Config) -> int:
    store = _open(cfg)
    prog, _st = _program(store)
    if prog is None:
        print("no plan started (`onemore start`)")
        return 1
    try:
        fired, new = engine.advance(store, prog, cfg.unit, force=a.force,
                                    asof=date.fromisoformat(a.asof) if a.asof else None)
    except RuntimeError as e:
        print(e)
        return 1
    _print_adjustments(fired, cfg)
    print(f"\nnow week {new.current_week}" + (" (deload next)" if new.deload_next else ""))
    return 0


def _print_adjustments(adjs, cfg: Config) -> None:
    if not adjs:
        print("no rule fired")
    for adj in adjs:
        change = ""
        if adj.field in ("tm_kg", "e1rm_kg") and adj.new is not None:
            o = f"{from_kg(adj.old, cfg.unit):.0f}" if adj.old is not None else "-"
            change = f" {o} -> {from_kg(adj.new, cfg.unit):.0f} {cfg.unit}"
        elif adj.old != adj.new:
            change = f" {adj.old} -> {adj.new}"
        print(f"[w{adj.week}] {adj.rule:24s} {adj.lift:22s} {adj.field}{change}\n"
              f"      {adj.reason}")


def cmd_explain(a, cfg: Config) -> int:
    store = _open(cfg)
    _print_adjustments(store.adjustments(week=a.week), cfg)
    return 0


def _is_loopback_host(host: str) -> bool:
    """True for 127.0.0.1, ::1, "localhost", and anything else `ipaddress` calls loopback.
    A hostname `ipaddress` can't parse is treated as NOT loopback: the warning is meant to
    fire on doubt, not only on a confirmed non-loopback address."""
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _warn_if_not_loopback(host: str) -> None:
    """web.py's docstring: GET carries no auth at all, so a non-loopback bind hands
    anyone who can reach it the training history — every rendered week, every logged set."""
    if not _is_loopback_host(host):
        print(f"WARNING: --host {host} is not loopback. Every GET is unauthenticated, so "
              f"the training history is readable by anyone who can reach {host}.",
              file=sys.stderr)


def cmd_serve(a, cfg: Config) -> int:
    from .web import serve

    _warn_if_not_loopback(a.host)
    serve(cfg, host=a.host, port=a.port)
    return 0


# -- demo ---------------------------------------------------------------------------

# Two made-up training days, each a handful of that program's own lifts, so the split
# looks like a real log without needing to know the program's actual day layout.
_DEMO_DAY_NAMES = ("Day A", "Day B")
_DEMO_WEEKS = 6
_DEMO_REPS = (8, 8, 6)  # three work sets, the last one a bit harder


def demo_strong_csv(catalog: Catalog, program, weeks: int = _DEMO_WEEKS) -> str:
    """A synthetic Strong CSV: `weeks` of history for every lift `program` prescribes,
    split across two alternating days, loads progressing one catalog step per week. Built
    entirely from the catalog and the program's own lift ids — no file on disk is read, so
    this works the same from an installed package as from a checkout, and it can never
    leak real data because it never opens any."""
    lift_ids = [lid for lid in program.lifts if catalog.get(lid) is not None
                and catalog.get(lid).aliases.get("strong")]
    if not lift_ids:
        raise ValueError(f"no catalog lift in {program.name!r} has a Strong alias")
    half = (len(lift_ids) + 1) // 2
    groups = (lift_ids[:half], lift_ids[half:] or lift_ids[:half])

    header = ("Date", "Workout Name", "Duration", "Exercise Name", "Set Order",
              "Weight", "Reps", "Distance", "Seconds", "Notes", "Workout Notes", "RPE")
    rows = [header]
    today = date.today()
    start = today - timedelta(weeks=weeks)
    for w in range(weeks):
        for day_idx, (name, group) in enumerate(zip(_DEMO_DAY_NAMES, groups)):
            d = start + timedelta(weeks=w, days=day_idx * 3 + 1)
            if d > today:
                continue
            timestamp = f"{d.isoformat()} 17:{'00' if day_idx else '30'}:00"
            for lid in group:
                ex = catalog.get(lid)
                strong_name = ex.aliases["strong"][0]
                step = ex.step_lb or 5.0
                weight = step * 6 + step * w  # progresses one step a week, plausibly light
                for set_no, reps in enumerate(_DEMO_REPS, start=1):
                    rows.append((timestamp, name, "45m", strong_name, str(set_no),
                                f"{weight:g}", str(reps), "0", "0", "", "", ""))

    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue()


def cmd_demo(a, cfg: Config) -> int:
    data_dir = Path(a.dir) if a.dir else Path(tempfile.mkdtemp(prefix="onemore-demo-"))
    data_dir.mkdir(parents=True, exist_ok=True)
    imports_dir = data_dir / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    demo_cfg = Config(db=data_dir / "onemore.db", unit=cfg.unit,
                      fallback_step_lb=cfg.fallback_step_lb, token=secrets.token_hex(16),
                      imports_dir=imports_dir)

    store = _open(demo_cfg)
    catalog = Catalog.load()
    program = PROGRAMS[DEFAULT_PROGRAM]()
    text = demo_strong_csv(catalog, program)
    new, seen = import_strong_text(store, catalog, text, demo_cfg.unit, "demo.csv")
    print(f"{seen} sessions in file, {new} new (synthetic — no real data)")
    seeded = engine.seed_from_history(store, program, demo_cfg.unit)
    for adj in seeded:
        print(f"seed {adj.lift}: {adj.reason}")
    st = engine.start_plan(store, program, date.today())
    print(f"started {program.name}, {program.days_per_week} days/week, week 1 begins {st.started_on}")
    store.close()
    print(f"demo data directory: {data_dir}")

    if a.no_serve:
        return 0

    from .web import serve

    _warn_if_not_loopback(a.host)
    print(f"onemore demo on http://{a.host}:{a.port}  token={demo_cfg.token}")
    serve(demo_cfg, host=a.host, port=a.port)
    return 0


def main(argv=None) -> int:
    cfg = Config.from_env()
    p = argparse.ArgumentParser(prog="onemore")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("import", help="import a Strong CSV export")
    s.add_argument("path")
    s.add_argument("--unit", choices=["lb", "kg"])
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("import-health", help="import Apple Health: the Health app's export zip/xml, or Health Auto Export JSON")
    s.add_argument("path")
    s.set_defaults(fn=cmd_import_health)
    s = sub.add_parser("status", help="history, estimates, plan position, vitals")
    s.add_argument("--unmapped", action="store_true", help="list exercise names not in the catalog")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("start", help="start a program at week 1")
    s.add_argument("--program", default=DEFAULT_PROGRAM, choices=sorted(PROGRAMS))
    s.add_argument("--days", type=int, default=4)
    s.add_argument("--on", help="YYYY-MM-DD week 1 starts (default today)")
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("plan", help="render a week")
    s.add_argument("--week", type=int)
    s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("advance", help="close the current week and run the rules")
    s.add_argument("--force", action="store_true")
    s.add_argument("--asof", help="pretend today is YYYY-MM-DD")
    s.set_defaults(fn=cmd_advance)
    s = sub.add_parser("explain", help="show which rules fired and why")
    s.add_argument("--week", type=int)
    s.set_defaults(fn=cmd_explain)
    s = sub.add_parser("serve", help="webhook ingest + phone page")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8790)
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("demo", help="throwaway synthetic data: import, start, serve")
    s.add_argument("--dir", help="use this directory instead of a fresh tempdir (not deleted)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8790)
    s.add_argument("--no-serve", action="store_true",
                   help="build and import only, then exit; for tests and scripting")
    s.set_defaults(fn=cmd_demo)
    a = p.parse_args(argv)
    return a.fn(a, cfg)


if __name__ == "__main__":
    sys.exit(main())
