"""The HTTP service: JSON views over a fixture-fed store, the app shell, and the token gate."""

from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from onemore import engine, web
from onemore.cli import import_strong_text
from onemore.config import Config
from onemore.exercises import Catalog
from onemore.program.programs import PROGRAMS, comeback
from onemore.program.spec import Day, LiftSpec, Pct, Program, Sets, Slot, Week, WeekKind
from onemore.rules import DEFAULT_RULES
from onemore.store import Store

FIX = Path(__file__).parent / "fixtures"
CAT = Catalog.load()


@pytest.fixture
def cfg(tmp_path):
    (tmp_path / "imports").mkdir()
    return Config(db=tmp_path / "onemore.db", unit="lb", fallback_step_lb=5.0, token="secret",
                  imports_dir=tmp_path / "imports")


def _flex(days: int = 4) -> Program:
    """A test-only program whose day count is a parameter. `comeback` is four days only, so
    the API's `days` plumbing needs some program that accepts another count to be tested."""
    slot = Slot("leg_press", (Sets(1, 5, Pct(0.8), amrap=True),))
    return Program("flex", {"leg_press": LiftSpec("leg_press")},
                   [Week(1, WeekKind.WORK, tuple(Day(f"D{i}", (slot,)) for i in range(days)))],
                   list(DEFAULT_RULES), days_per_week=days)


@pytest.fixture
def flex(monkeypatch):
    monkeypatch.setitem(PROGRAMS, "flex", _flex)


@pytest.fixture
def seeded(cfg):
    """The machine-lift fixture in a store, and a plan started the day after its last session."""
    store = Store(cfg.db)
    import_strong_text(store, CAT, (FIX / "strong_machines.csv").read_text(), "lb", "fixture")
    last = store.sessions()[-1].date
    prog = comeback.build(4)
    engine.seed_from_history(store, prog, "lb")
    engine.start_plan(store, prog, last + timedelta(days=1))
    yield store
    store.close()


@pytest.fixture
def server(cfg, seeded):
    seeded.close()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(cfg))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def call(url, method="GET", body=None, token=None, ctype="application/json"):
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = Request(url, data=data, method=method)
    if token is not None:
        req.add_header("X-Token", token)
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urlopen(req) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


# -- the JSON views, called directly ----------------------------------------------------


def test_status_reports_the_history_and_the_plan(cfg, seeded):
    st = web.api_status(seeded, cfg, CAT, today=date(2026, 9, 6))
    assert st["sessions"] == 4 and st["unit"] == "lb" and st["writable"]
    assert st["plan"]["program"] == "comeback" and st["plan"]["current_week"] == 1
    ids = {r["id"] for r in st["lifts"]}
    assert "leg_press" in ids and "chest_press" in ids
    lp = next(r for r in st["lifts"] if r["id"] == "leg_press")
    assert lp["main"] and lp["step"] == 5.0 and lp["ceiling"] is None
    assert st["unmapped"] == [], "every fixture name resolves"


def test_the_week_carries_rounded_loads_warmups_and_last_actuals(cfg, seeded):
    wk = web.api_week(seeded, cfg, CAT, None)
    assert wk["number"] == 1 and wk["kind"] == "calibration" and wk["is_current"]
    assert len(wk["days"]) == 4 and len(wk["weeks"]) == 5
    lp = next(s for d in wk["days"] for s in d["slots"] if s["lift"] == "leg_press")
    top = lp["prescribed"][0]
    assert top["amrap"] and top["sets"] == 1 and top["reps"] == "5"
    assert top["load"] is not None and top["load"] % lp["step"] == 0, "rounded on the lift's step"
    assert top["rest_s"] == 180
    assert lp["warmup"] and all(w["load"] < top["load"] for w in lp["warmup"])
    assert lp["last"]["sets"], "the previous session's work sets ride along"
    assert all(s["type"] == "work" for s in lp["last"]["sets"])
    assert wk["missing"] == []


def test_a_lift_without_history_is_prescribed_by_how_not_load(cfg, seeded):
    wk = web.api_week(seeded, cfg, CAT, 2)
    # hip_abductor: a comeback accessory the fixture never logged.
    fp = next(s for d in wk["days"] for s in d["slots"] if s["lift"] == "hip_abductor")
    assert fp["prescribed"][0]["load"] is None
    assert "no e1rm yet" in fp["prescribed"][0]["how"]


def test_a_main_lift_with_no_tm_shows_a_provisional_load_from_recent_sets(cfg, seeded):
    """A main lift that joins a running plan has no TM until its first week closes; the
    week must still show a weight, and say where it came from. Seated row 130x10 on
    08-31 is e1RM 173.3, so the provisional TM is 156 and the top set 0.82 of it."""
    wk = web.api_week(seeded, cfg, CAT, 2)
    row = next(s for d in wk["days"] for s in d["slots"] if s["lift"] == "seated_row")
    assert row["tm"] is None, "provisional is render-only: nothing is stored"
    top, back = row["prescribed"]
    assert top["load"] == 130.0 and back["load"] == 105.0
    assert "provisional tm" in top["how"]
    assert any(n.startswith("no TM yet: provisional TM 156 lb") for n in row["why"])
    assert row["warmup"], "a provisional top set gets a ramp like any other"


def test_a_provisional_tm_never_reaches_past_the_recent_window_or_over_a_real_tm(cfg, seeded):
    """Old history is not evidence of what the elbow takes now: with nothing logged in the
    window the slot stays blank. And a stored TM always wins."""
    wk = web.api_week(seeded, cfg, CAT, 14)
    row = next(s for d in wk["days"] for s in d["slots"] if s["lift"] == "seated_row")
    assert row["prescribed"][0]["load"] is None and "no tm yet" in row["prescribed"][0]["how"]
    seeded.set_state("seated_row", "tm_kg", 50.0)
    wk = web.api_week(seeded, cfg, CAT, 2)
    row = next(s for d in wk["days"] for s in d["slots"] if s["lift"] == "seated_row")
    assert "provisional" not in row["prescribed"][0]["how"]
    assert not any("provisional" in n for n in row["why"])


def test_an_imported_session_checks_off_its_day_and_only_the_lifts_it_trained(cfg, seeded):
    """The plan starts 09-01. A Strong session on 09-02 that opens with the leg press is
    the day whose main lift that is; its other slots stay open, every other day stays
    unlogged, and the next week is untouched -- the same matching the rules count with."""
    csv = ("Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,"
           "Seconds,Notes,Workout Notes,RPE\n"
           '2026-09-02 17:00:00,"Legs",50m,"Leg Press",1,180.0,8.0,0,0.0,"","",\n')
    import_strong_text(seeded, CAT, csv, "lb", "test")
    wk = web.api_week(seeded, cfg, CAT, 1)
    logged = [d for d in wk["days"] if d["logged"]]
    assert len(logged) == 1
    day = logged[0]
    assert day["slots"][0]["lift"] == "leg_press"
    assert day["logged"] == {"date": "2026-09-02", "title": "Legs"}
    assert day["slots"][0]["logged"]
    assert not any(s["logged"] for s in day["slots"][1:])
    assert not any(s["logged"] for d in wk["days"] if not d["logged"] for s in d["slots"])
    assert not any(d["logged"] for d in web.api_week(seeded, cfg, CAT, 2)["days"])


def test_a_week_is_closed_only_once_the_plan_has_advanced_past_it(cfg, seeded):
    """A week whose dates have ended but which is still current may yet get its export, so
    only an advanced-past week is final -- the page marks its unlogged days missed."""
    assert not web.api_week(seeded, cfg, CAT, 1)["closed"]
    p = seeded.get_plan("plan")
    seeded.set_plan("plan", {**p, "current_week": 2})
    assert web.api_week(seeded, cfg, CAT, 1)["closed"]
    assert not web.api_week(seeded, cfg, CAT, 2)["closed"]


def test_weeks_past_the_definition_cycle_the_body(cfg, seeded):
    wk = web.api_week(seeded, cfg, CAT, 14)
    assert wk["number"] == 14 and wk["kind"] == "work"


def test_lift_detail_has_a_series_and_recent_sets(cfg, seeded):
    d = web.api_lift(seeded, cfg, CAT, "leg_press", today=date(2026, 9, 6))
    assert d["name"] == "Leg Press" and d["sessions"] == len(d["series"]) == 2
    p = d["series"][-1]
    assert p["e1rm"] and p["top_w"] and p["sets"] >= 1
    assert d["recent"][0]["date"] == p["date"]
    assert any(a["rule"] == "seed_from_history" for a in d["adjustments"])
    assert web.api_lift(seeded, cfg, CAT, "no_such_lift") is None


def test_sessions_page_newest_first_with_a_cursor(cfg, seeded):
    page = web.api_sessions(seeded, cfg, CAT, limit=1)
    assert page["total"] == 4 and page["more"] and len(page["sessions"]) == 1
    first = page["sessions"][0]
    older = web.api_sessions(seeded, cfg, CAT, limit=10, before=date.fromisoformat(first["date"]))
    assert not older["more"] and all(s["date"] < first["date"] for s in older["sessions"])
    assert first["entries"][0]["sets"][0]["type"] in ("work", "warmup")
    assert first["volume"] > 0


def test_program_map_describes_every_slot(cfg, seeded, flex):
    p = web.api_program(seeded, cfg, CAT)
    assert p["name"] == "comeback" and p["days"] == 4 and len(p["weeks"]) == 5
    top = p["weeks"][1]["days"][0]["slots"][0]
    assert top["lift"] == "leg_press" and top["scheme"][0]["amrap"]
    assert top["scheme"][0]["how"] == "80% TM"
    assert [r["name"] for r in p["rules"]][:2] == ["e1rm_refresh", "missed_week_repeat"]
    assert web.api_program(seeded, cfg, CAT, name="flex", days=3)["days"] == 3


def test_vitals_view_is_empty_without_health_data(cfg, seeded):
    v = web.api_vitals(seeded, cfg, 365, today=date(2026, 9, 6))
    assert v["tiles"] == [] and v["series"] == {} and v["workouts"] == []


# -- over HTTP ----------------------------------------------------------------------------


def test_app_shell_is_served_for_every_app_route(server):
    for path in ("/", "/week/3", "/lifts", "/lift/leg_press", "/log", "/rules", "/vitals",
                 "/program", "/settings", "/explain"):
        code, ctype, body = call(server + path)
        assert code == 200 and ctype.startswith("text/html"), path
        assert b'src="/static/app.js"' in body
    code, ctype, _ = call(server + "/static/app.css")
    assert code == 200 and ctype.startswith("text/css")
    code, ctype, _ = call(server + "/manifest.webmanifest")
    assert code == 200 and ctype.startswith("application/manifest+json")
    assert call(server + "/static/../pyproject.toml")[0] == 404
    assert call(server + "/nothing/here")[0] == 404


def test_api_routes_answer_json(server):
    code, ctype, body = call(server + "/api/week")
    assert code == 200 and ctype.startswith("application/json")
    assert json.loads(body)["number"] == 1
    assert json.loads(call(server + "/api/week/5")[2])["number"] == 5
    assert json.loads(call(server + "/api/sessions?limit=1")[2])["more"]
    assert json.loads(call(server + "/api/adjustments?week=0")[2])["adjustments"]
    assert call(server + "/api/lift/nope")[0] == 404
    assert call(server + "/api/sessions?before=not-a-date")[0] == 400


def test_writes_need_the_token(server):
    assert call(server + "/api/advance", "POST", {})[0] == 401
    assert call(server + "/api/advance", "POST", {}, token="wrong")[0] == 401
    assert call(server + "/api/start", "POST", {}, token="wrong")[0] == 401
    assert call(server + "/import/strong", "POST", b"Date", token="wrong",
                ctype="text/csv")[0] == 401


def test_a_rejected_upload_still_gets_its_error_back(server):
    """A big body must not turn a 401 into a transport error the caller can't read.

    The four asserts above all post a handful of bytes, which fit in the socket buffer
    whatever the server does with them — so they passed while a real 214KB Strong export
    from a phone died as "timed out" and never showed the token message. The size here is
    well over any loopback buffer; at 4MB this raised URLError(Broken pipe) before
    `_drain`.
    """
    big = b"Date,Workout Name\n" + b"x" * 16_000_000
    code, _, body = call(server + "/import/strong", "POST", big, token="wrong",
                         ctype="text/csv")
    assert code == 401
    assert json.loads(body)["error"] == "bad token"

    # The 404 exit closes the connection the same way, and is reachable without a token.
    code, _, _ = call(server + "/import/nope", "POST", big, token="wrong", ctype="text/csv")
    assert code == 404


def test_advance_refuses_an_open_week_then_closes_it_when_forced(server, monkeypatch):
    # The plan starts the day after the fixture's last session (2026-08-31), so week 1 is
    # 2026-09-01..09-07 and "today" is pinned inside it: unpinned, the week closed on its
    # own on 2026-09-08 and this went red.
    class _Day(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 2)

    monkeypatch.setattr(engine, "date", _Day)
    code, _, body = call(server + "/api/advance", "POST", {}, token="secret")
    assert code == 409 and "force" in json.loads(body)["error"]
    code, _, body = call(server + "/api/advance", "POST", {"force": True}, token="secret")
    out = json.loads(body)
    assert code == 200
    # Nothing was logged inside the week window, so the week repeats rather than advancing.
    assert any(a["rule"] == "missed_week_repeat" for a in out["fired"])
    assert out["plan"]["current_week"] == 1


def test_start_guards_a_running_plan_unless_forced(server, flex):
    code, _, body = call(server + "/api/start", "POST", {"program": "flex"}, token="secret")
    assert code == 409
    code, _, body = call(server + "/api/start", "POST",
                         {"program": "flex", "days": 3, "on": "2026-09-07", "force": True},
                         token="secret")
    out = json.loads(body)
    assert code == 200 and out["plan"]["days"] == 3 and out["plan"]["started_on"] == "2026-09-07"
    assert out["seeded"], "seeding is recorded like any other rule"
    assert json.loads(call(server + "/api/program")[2])["days"] == 3


def test_strong_import_over_http_is_idempotent_and_saved(server, cfg):
    csv = (FIX / "strong_10col.csv").read_bytes()
    code, _, body = call(server + "/import/strong", "POST", csv, token="secret", ctype="text/csv")
    first = json.loads(body)
    assert code == 200 and first["sessions"] >= 1
    assert (cfg.imports_dir / first["saved"]).exists()
    code, _, body = call(server + "/import/strong", "POST", csv, token="secret", ctype="text/csv")
    assert json.loads(body)["new"] == 0, "the same file again adds nothing"
    code, _, body = call(server + "/import/strong", "POST", b"garbage", token="secret",
                         ctype="text/csv")
    assert code == 400


def test_health_import_over_http(server):
    payload = (FIX / "health_auto_export.json").read_bytes()
    code, _, body = call(server + "/import/health", "POST", payload, token="secret")
    out = json.loads(body)
    assert code == 200 and out["new"] > 0
    v = json.loads(call(server + "/api/vitals?days=all")[2])
    assert v["tiles"] and v["series"]


def test_health_export_zip_over_http(server, cfg):
    """The Health app's own export, posted as the zip it hands you: 202 now, readings after.

    The phone's Get Contents of URL cannot wait minutes for a 1.1 GB parse, so the request
    answers before the work; the test has to join the worker rather than assume it ran."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("apple_health_export/export.xml", (FIX / "apple_health_export.xml").read_text())
    code, _, body = call(server + "/import/health", "POST", buf.getvalue(), token="secret",
                         ctype="application/octet-stream")
    out = json.loads(body)
    assert code == 202 and out["queued"].endswith(".zip")

    web._health_thread.join(30)
    assert not web._health_thread.is_alive()
    store = Store(cfg.db)
    try:
        assert store.metrics("resting_heart_rate"), "the worker parsed nothing into the store"
    finally:
        store.close()
    assert not (cfg.imports_dir / out["queued"]).exists(), "the zip is dropped once parsed"
    v = json.loads(call(server + "/api/vitals?days=all")[2])
    assert v["tiles"]


def test_health_export_xml_over_http(server, cfg):
    """The same export unzipped. Content-Type is not consulted — Shortcuts sends none."""
    code, _, body = call(server + "/import/health", "POST",
                         (FIX / "apple_health_export.xml").read_bytes(), token="secret",
                         ctype="text/plain")
    assert code == 202 and json.loads(body)["queued"].endswith(".xml")
    web._health_thread.join(30)
    store = Store(cfg.db)
    try:
        assert store.metrics("resting_heart_rate")
    finally:
        store.close()
