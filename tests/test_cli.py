"""`onemore demo` (a throwaway synthetic Strong history, imported and planned with no
`--serve`) and the warning on a non-loopback `--host`
(`docs/public-release-plan.md` § Phase 3)."""

from __future__ import annotations

import io

from onemore import cli, engine, web
from onemore.exercises import Catalog
from onemore.program.programs import PROGRAMS
from onemore.program.render import render_week
from onemore.store import Store

CAT = Catalog.load()


def test_demo_strong_csv_is_a_parseable_strong_export():
    program = PROGRAMS["comeback"]()
    text = cli.demo_strong_csv(CAT, program, weeks=3)
    from onemore.sources.strong_csv import StrongCsvSource

    sessions = list(StrongCsvSource(text, CAT, weight_unit="lb").fetch_sessions())
    assert sessions, "the synthetic CSV produced no sessions"
    # Every lift the program prescribes shows up somewhere in the synthetic history.
    seen = {e.exercise_id for s in sessions for e in s.entries}
    assert seen & set(program.lifts)
    # Loads progress: the same lift's last logged weight beats its first.
    by_lift: dict[str, list[float]] = {}
    for s in sessions:
        for e in s.entries:
            for st in e.sets:
                by_lift.setdefault(e.exercise_id, []).append(st.weight_kg)
    weights = next(iter(by_lift.values()))
    assert weights[-1] > weights[0]


def test_demo_no_serve_starts_a_plan_and_a_week_renders(tmp_path):
    data_dir = tmp_path / "demo"
    rc = cli.main(["demo", "--dir", str(data_dir), "--no-serve"])
    assert rc == 0
    assert (data_dir / "onemore.db").exists()

    store = Store(data_dir / "onemore.db")
    st = engine.plan_status(store)
    assert st is not None, "demo did not start a plan"
    program = PROGRAMS[st.program](st.days)
    week = engine.effective_week(program, st, st.current_week)
    prov = engine.provisional_tms(store, program, st, st.current_week)
    rw = render_week(week, store.all_state(), CAT, "lb", 5.0,
                     {k: tm for k, (tm, _) in prov.items()})
    assert rw.days, "the rendered week has no days"
    assert any(slot.prescribed for day in rw.days for slot in day.slots), \
        "the rendered week prescribes no sets"


def test_demo_writes_nothing_outside_its_directory(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    data_dir = tmp_path / "elsewhere" / "demo"
    rc = cli.main(["demo", "--dir", str(data_dir), "--no-serve"])
    assert rc == 0
    assert list(cwd.iterdir()) == [], "demo left files in the cwd instead of --dir"


def test_demo_default_dir_is_a_tempdir(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    rc = cli.main(["demo", "--no-serve"])
    assert rc == 0
    assert list(cwd.iterdir()) == []
    last_line = [ln for ln in buf.getvalue().splitlines() if ln][-1]
    assert last_line.startswith("demo data directory: ")


def test_loopback_host_is_not_warned_about(capsys):
    for host in ("127.0.0.1", "::1", "localhost"):
        cli._warn_if_not_loopback(host)
        assert capsys.readouterr().err == ""


def test_non_loopback_host_prints_a_warning_naming_what_is_exposed(capsys):
    for host in ("0.0.0.0", "192.0.2.50", "10.0.0.5"):
        cli._warn_if_not_loopback(host)
        err = capsys.readouterr().err
        assert "WARNING" in err
        assert host in err
        assert "unauthenticated" in err


def test_serve_warns_before_binding_a_non_loopback_host(monkeypatch, capsys, tmp_path):
    from onemore.config import Config

    monkeypatch.setattr(web, "serve", lambda cfg, host, port: None)
    cfg = Config(db=tmp_path / "onemore.db", unit="lb", fallback_step_lb=5.0, token="",
                imports_dir=tmp_path / "imports")

    class Args:
        host = "0.0.0.0"
        port = 8790

    rc = cli.cmd_serve(Args(), cfg)
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARNING" in err and "0.0.0.0" in err


def test_demo_warns_before_binding_a_non_loopback_host(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(web, "serve", lambda cfg, host, port: None)

    class Args:
        dir = str(tmp_path / "demo")
        host = "0.0.0.0"
        port = 8790
        no_serve = False

    from onemore.config import Config

    rc = cli.cmd_demo(Args(), Config.from_env())
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARNING" in err and "0.0.0.0" in err
