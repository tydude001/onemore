"""HTTP service: the JSON API, the single-page app that reads it, and the ingest webhooks.

  GET  /                    the app (also /week/<n>, /lifts, /log, /rules, /vitals, /program)
  GET  /static/<file>       app assets, served from the package
  GET  /api/status          history span, imports, plan position, per-lift estimates, vitals
  GET  /api/week[/<n>]      a rendered week: loads rounded per machine, rest, warm-ups,
                            last actuals, the rule notes that changed it
  GET  /api/lifts           every lift with history, with an e1RM sparkline
  GET  /api/lift/<id>       one lift: per-session e1RM series, state, rule log, recent sets
  GET  /api/sessions        the log, newest first (?limit=&before=YYYY-MM-DD)
  GET  /api/adjustments     the rule audit trail (?week=)
  GET  /api/vitals          Health metrics: tiles plus daily series (?days=)
  GET  /api/program         the program map: every week, every slot's scheme, the rules
  GET  /health
  POST /import/strong       body = the CSV (raw or multipart), header X-Token: <ONEMORE_TOKEN>
  POST /import/health       body = the Health app's export zip (or its export.xml, or
                            Health Auto Export JSON), same header. A zip answers 202 and
                            parses on a worker thread — it takes minutes.
  POST /api/start           {program, days, on?, force?}  seed from history and start week 1
  POST /api/advance         {force?, asof?}               close the week, run the rules

Every POST needs the token; an empty ONEMORE_TOKEN disables them all. There is no auth on
GET at all, so this must never be reachable from the LAN: on the NAS it binds loopback and
the tailnet reaches it from there (DEPLOY.md), while on a PC that means --host <tailnet ip>.
Stdlib only, and the app loads nothing from a CDN, because the NAS is reachable only over
the tailnet.
"""

from __future__ import annotations

import hmac
import inspect
import json
import mimetypes
import re
import threading
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, unquote, urlsplit

from . import engine, estimate, vitals
from .cli import import_strong_text
from .config import Config
from .exercises import Catalog
from .model import Adjustment, Session, Set, SetType
from .program.programs import DEFAULT_PROGRAM, PROGRAMS
from .program.render import RenderedWeek, fmt_reps, render_week, warmup_steps
from .program.spec import Abs, Bodyweight, Pct, Program, Rpe, Sets
from .sources.apple_health import import_health_text
from .sources.apple_health_xml import import_health_export
from .store import Store
from .units import from_kg, round_load

APP_ROUTES = ("/", "/week", "/lifts", "/lift", "/log", "/rules", "/vitals", "/program",
              "/explain", "/settings")

# One Health export parses at a time: a 1.1 GB `export.xml` is minutes of CPU and the
# whole point of the lock is that a re-tapped share sheet cannot start a second one.
_health_parse = threading.Lock()
_health_thread: threading.Thread | None = None  # the last one, so tests can join it


def _health_kind(body: bytes) -> str:
    """zip | xml | json, from the bytes. Not from Content-Type: a Shortcuts File body
    arrives as octet-stream or with no type at all."""
    if body[:4] == b"PK\x03\x04":
        return "zip"
    head = body[:200].lstrip()
    if head[:1] == b"<":
        return "xml"
    return "json"
VITAL_SERIES = ("bodyweight", "resting HR", "HRV", "sleep h", "steps", "body fat %")


def _extract_csv(body: bytes, content_type: str) -> str:
    if content_type.startswith("multipart/form-data"):
        m = re.search(r"boundary=([^;]+)", content_type)
        if m:
            boundary = m.group(1).strip('"').encode()
            for part in body.split(b"--" + boundary):
                if b"\r\n\r\n" in part and b"Date" in part:
                    return part.split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n-").decode("utf-8-sig")
    return body.decode("utf-8-sig")


# -- JSON views ---------------------------------------------------------------------------
# Plain dicts over the same engine calls the CLI makes. Loads leave here in `cfg.unit`,
# rounded on the lift's own step where a plan is being shown and unrounded where history is.


def _r(kg: float | None, unit: str, nd: int = 1) -> float | None:
    return None if kg is None else round(from_kg(kg, unit), nd)


def _set(s: Set, unit: str) -> dict:
    return {"type": str(s.set_type), "w": _r(s.weight_kg, unit), "r": s.reps, "rpe": s.rpe,
            "done": s.completed, "ref": s.source_ref}


def _adj(a: Adjustment, unit: str) -> dict:
    kg_field = a.field in ("tm_kg", "e1rm_kg")
    return {"week": a.week, "rule": a.rule, "lift": a.lift, "field": a.field,
            "old": _r(a.old, unit, 1) if kg_field else a.old,
            "new": _r(a.new, unit, 1) if kg_field else a.new,
            "reason": a.reason, "evidence": list(a.evidence), "kg": kg_field}


def _session(s: Session, catalog: Catalog, unit: str) -> dict:
    entries = []
    volume = 0.0
    n_sets = 0
    for e in s.entries:
        sets = [_set(st, unit) for st in e.sets]
        n_sets += len(sets)
        for st in e.work_sets():
            if st.weight_kg and st.reps:
                volume += st.weight_kg * st.reps
        entries.append({"lift": e.exercise_id, "name": catalog.name(e.exercise_id),
                        "notes": e.notes, "sets": sets})
    return {"key": s.source_key, "date": s.date.isoformat(),
            "time": s.started_at.strftime("%H:%M"), "title": s.title, "notes": s.notes,
            "duration_s": int(s.duration.total_seconds()) if s.duration else None,
            "exercises": len(entries), "sets": n_sets, "volume": round(from_kg(volume, unit)),
            "entries": entries}


def _plan(st: engine.PlanStatus | None) -> dict | None:
    if st is None:
        return None
    start, end = engine.week_window(st, st.current_week)
    return {"program": st.program, "days": st.days, "started_on": st.started_on.isoformat(),
            "current_week": st.current_week, "deload_next": st.deload_next,
            "window": [start.isoformat(), end.isoformat()]}


def _vital(v: vitals.Vital) -> dict:
    return {"label": v.label, "unit": v.unit, "latest": round(v.latest, v.decimals),
            "on": v.latest_on.isoformat(),
            "mean_7d": None if v.mean_7d is None else round(v.mean_7d, v.decimals),
            "mean_28d": None if v.mean_28d is None else round(v.mean_28d, v.decimals),
            "decimals": v.decimals}


def _program(store: Store) -> tuple[Program | None, engine.PlanStatus | None]:
    st = engine.plan_status(store)
    if st is None:
        return None, None
    return PROGRAMS[st.program](st.days), st


def _lift_series(sets: list[tuple[date, Set]], unit: str) -> list[dict]:
    """Per session: best e1RM, the heaviest work set, volume and set count."""
    by_day: dict[date, list[Set]] = {}
    for d, s in sets:
        if s.set_type == SetType.WORK and s.completed:
            by_day.setdefault(d, []).append(s)
    out = []
    for d, ss in sorted(by_day.items()):
        e1s = [(estimate.e1rm(s), s) for s in ss]
        e1s = [(v, s) for v, s in e1s if v is not None]
        loaded = [s for s in ss if s.weight_kg]
        top = max(loaded, key=lambda s: (s.weight_kg, s.reps or 0)) if loaded else None
        best = max(e1s, key=lambda t: t[0]) if e1s else None
        out.append({"date": d.isoformat(),
                    "e1rm": _r(best[0], unit) if best else None,
                    "best_w": _r(best[1].weight_kg, unit) if best else None,
                    "best_r": best[1].reps if best else None,
                    "top_w": _r(top.weight_kg, unit) if top else None,
                    "top_r": top.reps if top else None,
                    "volume": round(from_kg(sum((s.weight_kg or 0) * (s.reps or 0) for s in ss),
                                            unit)),
                    "sets": len(ss)})
    return out


def _lift_row(store: Store, catalog: Catalog, lid: str, unit: str, today: date,
              spec=None) -> dict:
    sets = store.sets_for(lid)
    best, when = estimate.historical_best(sets)
    roll, _ = estimate.rolling_e1rm(sets, today)
    ex = catalog.get(lid)
    series = _lift_series(sets, unit)
    return {"id": lid, "name": catalog.name(lid),
            "equipment": ex.equipment if ex else "", "pattern": ex.pattern if ex else "",
            "available": ex.available if ex else True,
            "step": from_kg(catalog.step_kg(lid), unit),
            "ceiling": _r(catalog.ceiling_kg(lid), unit, 0),
            "in_program": spec is not None, "main": bool(spec and spec.main),
            "best_e1rm": _r(best, unit), "best_on": when.isoformat() if when else None,
            "rolling_e1rm": _r(roll, unit),
            "tm": _r(store.get_state(lid, "tm_kg"), unit),
            "e1rm": _r(store.get_state(lid, "e1rm_kg"), unit),
            "sessions": len(series), "last_on": series[-1]["date"] if series else None,
            "spark": [p["e1rm"] for p in series[-24:]]}


def api_status(store: Store, cfg: Config, catalog: Catalog, today: date | None = None) -> dict:
    today = today or date.today()
    sessions = store.sessions()
    prog, st = _program(store)
    seed_program = prog or PROGRAMS[DEFAULT_PROGRAM]()
    lifts = [_lift_row(store, catalog, lid, cfg.unit, today, spec)
             for lid, spec in seed_program.lifts.items()]
    unmapped = [{"id": eid, "name": raw, "entries": n}
                for eid, raw, n in store.unmapped_names() if catalog.get(eid) is None]
    return {
        "unit": cfg.unit, "today": today.isoformat(), "writable": bool(cfg.token),
        "sessions": len(sessions),
        "first": sessions[0].date.isoformat() if sessions else None,
        "last": sessions[-1].date.isoformat() if sessions else None,
        "sets": sum(len(e.sets) for s in sessions for e in s.entries),
        "imports": [{"at": r["received_at"], "source": r["source"], "file": r["filename"],
                     "new": r["sessions_new"], "seen": r["sessions_seen"]}
                    for r in store.imports()],
        "plan": _plan(st), "program": seed_program.name,
        "programs": sorted(PROGRAMS),
        "lifts": lifts,
        "missing": [catalog.name(m) for m in seed_program.unavailable(catalog)],
        "unmapped": unmapped,
        "vitals": [_vital(v) for v in vitals.summary(store, today, cfg.unit)],
        "last_workout": vitals.last_workout(store),
    }


def _previous(store: Store, lifts, unit: str) -> dict[str, dict]:
    """The last logged session's work sets for each lift the plan prescribes."""
    out = {}
    for lid in lifts:
        sets = store.sets_for(lid)
        if not sets:
            continue
        last_day = sets[-1][0]
        todays = [s for d, s in sets if d == last_day and s.set_type == SetType.WORK]
        if todays:
            out[lid] = {"date": last_day.isoformat(), "sets": [_set(s, unit) for s in todays]}
    return out


def _scheme(sets: tuple[Sets, ...]) -> list[dict]:
    out = []
    for s in sets:
        load = s.load
        if isinstance(load, Pct):
            how = f"{load.value:.0%} {load.of.upper() if load.of == 'tm' else 'e1RM'}"
        elif isinstance(load, Rpe):
            how = f"RPE {load.value:g}"
        elif isinstance(load, Abs):
            how = f"{load.kg:g} kg"
        elif isinstance(load, Bodyweight):
            how = "bodyweight"
        else:
            how = ""
        out.append({"sets": s.n, "reps": fmt_reps(s.reps), "amrap": s.amrap, "how": how,
                    "rest_s": s.rest_s})
    return out


def _rendered(rw: RenderedWeek, previous: dict, notes: dict, catalog: Catalog,
              states: dict, mains: frozenset[str] = frozenset()) -> list[dict]:
    days = []
    for d in rw.days:
        slots = []
        for s in d.slots:
            step = rw.step(s.lift)
            pres = []
            for p in s.prescribed:
                pres.append({
                    "sets": p.sets, "reps": fmt_reps(p.reps), "amrap": p.amrap,
                    "load": round_load(p.load_kg, rw.unit, step) if p.load_kg else None,
                    "rpe": p.rpe_target, "how": p.how, "rest_s": p.rest_s,
                })
            top = s.prescribed[0].load_kg if s.prescribed else None
            ex = catalog.get(s.lift)
            st = states.get(s.lift, {})
            slots.append({
                "lift": s.lift, "name": s.name, "note": s.note, "step": step,
                "main": s.lift in mains,
                "equipment": ex.equipment if ex else "",
                "available": ex.available if ex else True,
                "prescribed": pres,
                "warmup": [{"load": v, "reps": r}
                           for v, r in warmup_steps(s.warmup, top, rw.unit, step)],
                "last": previous.get(s.lift),
                "why": notes.get(s.lift, []),
                "tm": _r(st.get("tm_kg"), rw.unit), "e1rm": _r(st.get("e1rm_kg"), rw.unit),
                "reps_delta": int(st.get("reps_delta") or 0),
                "sets_delta": int(st.get("sets_delta") or 0),
            })
        days.append({"name": d.name, "slots": slots})
    return days


def api_week(store: Store, cfg: Config, catalog: Catalog, n: int | None,
             today: date | None = None) -> dict | None:
    today = today or date.today()
    prog, st = _program(store)
    if prog is None:
        return None
    n = n or st.current_week
    week = engine.effective_week(prog, st, n)
    states = store.all_state()
    prov = engine.provisional_tms(store, prog, st, n)
    rw = render_week(week, states, catalog, cfg.unit, cfg.fallback_step_lb,
                     {k: tm for k, (tm, _) in prov.items()})
    notes: dict[str, list[str]] = {}
    for adj in store.adjustments(week=n - 1):
        if adj.lift != "*" and adj.field in ("tm_kg", "sets_delta", "reps_delta"):
            notes.setdefault(adj.lift, []).append(f"{adj.rule}: {adj.reason}")
    for lift, (tm, e1) in prov.items():
        notes.setdefault(lift, []).append(
            engine.provisional_note(tm, e1, prog.lifts[lift].tm_factor, cfg.unit))
    start, end = engine.week_window(st, n)
    lifts_in_week = {s.lift for d in week.days for s in d.slots}
    return {
        "number": rw.number, "kind": rw.kind, "label": rw.label, "unit": rw.unit,
        "window": [start.isoformat(), end.isoformat()],
        "is_current": n == st.current_week, "plan": _plan(st),
        "defined_weeks": len(prog.weeks),
        "weeks": [{"number": w.number, "kind": str(w.kind), "label": w.label}
                  for w in prog.weeks],
        "days": _rendered(rw, _previous(store, lifts_in_week, cfg.unit), notes, catalog,
                          states, frozenset(prog.main_lifts())),
        "missing": [catalog.name(m) for m in prog.unavailable(catalog)],
        "vitals": [_vital(v) for v in vitals.summary(store, today, cfg.unit)],
        "header": vitals.to_line(vitals.summary(store, today, cfg.unit)),
    }


def api_lifts(store: Store, cfg: Config, catalog: Catalog, today: date | None = None) -> dict:
    today = today or date.today()
    prog, _ = _program(store)
    prog = prog or PROGRAMS[DEFAULT_PROGRAM]()
    ids = list(prog.lifts) + [i for i in store.exercise_ids() if i not in prog.lifts]
    return {"unit": cfg.unit,
            "lifts": [_lift_row(store, catalog, lid, cfg.unit, today, prog.lifts.get(lid))
                      for lid in ids]}


def api_lift(store: Store, cfg: Config, catalog: Catalog, lid: str,
             today: date | None = None) -> dict | None:
    today = today or date.today()
    sets = store.sets_for(lid)
    ex = catalog.get(lid)
    if not sets and ex is None:
        return None
    prog, _ = _program(store)
    prog = prog or PROGRAMS[DEFAULT_PROGRAM]()
    row = _lift_row(store, catalog, lid, cfg.unit, today, prog.lifts.get(lid))
    row["series"] = _lift_series(sets, cfg.unit)
    row["adjustments"] = [_adj(a, cfg.unit) for a in store.adjustments() if a.lift == lid]
    by_day: dict[date, list[Set]] = {}
    for d, s in sets:
        by_day.setdefault(d, []).append(s)
    row["recent"] = [{"date": d.isoformat(), "sets": [_set(s, cfg.unit) for s in ss]}
                     for d, ss in sorted(by_day.items(), reverse=True)[:30]]
    row["aliases"] = sorted(n for names in (ex.aliases.values() if ex else ()) for n in names)
    return row


def api_sessions(store: Store, cfg: Config, catalog: Catalog, limit: int = 60,
                 before: date | None = None) -> dict:
    sessions = store.sessions(until=before) if before else store.sessions()
    if before:
        sessions = [s for s in sessions if s.date < before]
    sessions = list(reversed(sessions))
    page = sessions[:limit]
    return {"unit": cfg.unit, "total": len(sessions) if not before else None,
            "sessions": [_session(s, catalog, cfg.unit) for s in page],
            "more": len(sessions) > limit}


def api_adjustments(store: Store, cfg: Config, week: int | None = None) -> dict:
    return {"unit": cfg.unit, "adjustments": [_adj(a, cfg.unit) for a in store.adjustments(week)]}


def api_vitals(store: Store, cfg: Config, days: int | None = 365,
               today: date | None = None) -> dict:
    today = today or date.today()
    series = {}
    for label in VITAL_SERIES:
        unit, pts = vitals.series(store, label, today, days, cfg.unit)
        if pts:
            series[label] = {"unit": unit,
                             "points": [[d.isoformat(), round(v, 2)] for d, v in pts]}
    workouts = []
    for part in ("hr_avg", "hr_max", "kcal", "minutes"):
        for m in store.metrics(f"workout/{part}"):
            workouts.append((m.at.isoformat(), part, m.value))
    by_at: dict[str, dict] = {}
    for at, part, v in workouts:
        by_at.setdefault(at, {"at": at})[part] = round(v)
    return {"unit": cfg.unit, "today": today.isoformat(), "days": days,
            "tiles": [_vital(v) for v in vitals.summary(store, today, cfg.unit)],
            "series": series,
            "workouts": sorted(by_at.values(), key=lambda w: w["at"], reverse=True)[:40]}


def api_program(store: Store, cfg: Config, catalog: Catalog, name: str | None = None,
                days: int | None = None) -> dict:
    prog, st = _program(store)
    if name or days or prog is None:
        prog = PROGRAMS[name or (st.program if st else DEFAULT_PROGRAM)](days or (st.days if st else 4))
    mains = set(prog.main_lifts())
    weeks = []
    for w in prog.weeks:
        weeks.append({"number": w.number, "kind": str(w.kind), "label": w.label,
                      "days": [{"name": d.name,
                                "slots": [{"lift": s.lift, "name": catalog.name(s.lift),
                                           "equipment": catalog.get(s.lift).equipment
                                           if catalog.get(s.lift) else "",
                                           "main": s.lift in mains,
                                           "scheme": _scheme(s.sets), "note": s.note,
                                           "warmup": bool(s.warmup)}
                                          for s in d.slots]}
                               for d in w.days]})
    rules = []
    for r in prog.rules:
        doc = inspect.getdoc(r) or ""
        rules.append({"name": r.__name__, "summary": doc.split("\n\n")[0].replace("\n", " "),
                      "doc": doc})
    return {"name": prog.name, "days": prog.days_per_week, "programs": sorted(PROGRAMS),
            "lifts": [{"id": lid, "name": catalog.name(lid), "main": spec.main,
                       "step": from_kg(catalog.step_kg(lid), cfg.unit)}
                      for lid, spec in prog.lifts.items()],
            "weeks": weeks, "rules": rules,
            "doc": inspect.getmodule(PROGRAMS[prog.name]).__doc__ or "",
            "missing": [catalog.name(m) for m in prog.unavailable(catalog)]}


def _week_arg(path: str) -> int | None:
    m = re.fullmatch(r"/api/week/(\d+)", path)
    return int(m.group(1)) if m else None


# -- the server ---------------------------------------------------------------------------



def _parse_export(cfg: Config, path) -> None:
    """Worker for a Health export. Its own Store, because the connection cannot be shared
    across threads, and it keeps the zip only until it is parsed — 52 MB an import, the
    metrics table is the record, and the phone can make another whenever."""
    store = Store(cfg.db)
    try:
        new, seen = import_health_export(store, path)
        print(f"health export {path.name}: {new} new of {seen} readings")
        path.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001 — nobody is listening on the socket any more
        print(f"health export {path.name} failed: {e!r}")
    finally:
        store.close()
        _health_parse.release()


def make_handler(cfg: Config):
    static = resources.files("onemore").joinpath("static")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: str | bytes, ctype="text/html; charset=utf-8",
                  cache: bool = False):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if cache:
                self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, default=str), "application/json; charset=utf-8")

        def _static(self, name: str) -> None:
            # Flat, except for the vendored font directory: the app is CDN-free,
            # so the faces the design tokens name are served from here.
            head, _, tail = name.partition("/")
            if head == "fonts" and tail and "/" not in tail and not tail.startswith("."):
                name = f"fonts/{tail}"
            elif "/" in name or name.startswith("."):
                return self._send(404, "not found", "text/plain")
            f = static.joinpath(name)
            if not f.is_file():
                return self._send(404, "not found", "text/plain")
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if name.endswith(".webmanifest"):
                ctype = "application/manifest+json"
            if name.endswith(".woff2"):
                ctype = "font/woff2"
            if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype, cache=True)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            url = urlsplit(self.path)
            path, q = url.path, parse_qs(url.query)
            if path == "/health":
                return self._send(200, "ok", "text/plain")
            if path == "/manifest.webmanifest":
                return self._static("manifest.webmanifest")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if not path.startswith("/api/"):
                if path == "/" or path.rstrip("/") in APP_ROUTES or any(
                        path.startswith(r + "/") for r in APP_ROUTES if r != "/"):
                    return self._static("index.html")
                return self._send(404, "not found", "text/plain")
            store = Store(cfg.db)
            catalog = Catalog.load()
            try:
                if path == "/api/status":
                    return self._json(200, api_status(store, cfg, catalog))
                if path == "/api/week" or _week_arg(path):
                    out = api_week(store, cfg, catalog, _week_arg(path))
                    return self._json(200, out) if out else self._json(
                        404, {"error": "no plan started"})
                if path == "/api/lifts":
                    return self._json(200, api_lifts(store, cfg, catalog))
                if path.startswith("/api/lift/"):
                    out = api_lift(store, cfg, catalog, unquote(path[len("/api/lift/"):]))
                    return self._json(200, out) if out else self._json(
                        404, {"error": "unknown lift"})
                if path == "/api/sessions":
                    before = q.get("before", [None])[0]
                    return self._json(200, api_sessions(
                        store, cfg, catalog, min(int(q.get("limit", ["60"])[0]), 500),
                        date.fromisoformat(before) if before else None))
                if path == "/api/adjustments":
                    w = q.get("week", [None])[0]
                    return self._json(200, api_adjustments(store, cfg, int(w) if w else None))
                if path == "/api/vitals":
                    d = q.get("days", ["365"])[0]
                    return self._json(200, api_vitals(store, cfg, int(d) if d != "all" else None))
                if path == "/api/program":
                    days = q.get("days", [None])[0]
                    return self._json(200, api_program(
                        store, cfg, catalog, q.get("program", [None])[0],
                        int(days) if days else None))
                return self._json(404, {"error": "not found"})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            finally:
                store.close()

        def _authed(self) -> bool:
            token = self.headers.get("X-Token", "")
            return bool(cfg.token) and hmac.compare_digest(token, cfg.token)

        def _drain(self) -> None:
            # Read and discard the upload before an error response. The server speaks
            # HTTP/1.0, so the connection closes as soon as we answer; a client still
            # sending its body then meets a closed socket and reports a transport error
            # instead of the JSON it was handed. Measured 2026-09-07: a wrong X-Token on a
            # 214KB Strong export from a phone over the tailnet surfaced as "timed out",
            # while the server had already logged the 401 — so the one message naming the
            # actual fault was the one the client could not see. Loopback hides it, since
            # the socket buffer swallows 214KB whole; it takes ~4MB to fail locally.
            # Chunked rather than one read() because the token has not been checked yet.
            remaining = int(self.headers.get("Content-Length", "0"))
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in ("/import/strong", "/import/health", "/api/start", "/api/advance"):
                self._drain()
                return self._send(404, "not found", "text/plain")
            if not self._authed():
                self._drain()
                return self._json(401, {"error": "bad token" if cfg.token else
                                        "writes disabled: ONEMORE_TOKEN is not set"})
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            if path == "/import/health":
                return self._import_health(body)
            if path == "/import/strong":
                return self._import_strong(body)
            try:
                args = json.loads(body or b"{}")
            except ValueError:
                return self._json(400, {"error": "body must be JSON"})
            store = Store(cfg.db)
            try:
                if path == "/api/start":
                    return self._start(store, args)
                return self._advance(store, args)
            except (ValueError, KeyError) as e:
                return self._json(400, {"error": str(e)})
            finally:
                store.close()

        def _start(self, store: Store, args: dict):
            if engine.plan_status(store) and not args.get("force"):
                return self._json(409, {"error": "a plan is already running; pass force to "
                                                 "restart it at week 1"})
            prog = PROGRAMS[args.get("program", DEFAULT_PROGRAM)](int(args.get("days", 4)))
            on = date.fromisoformat(args["on"]) if args.get("on") else date.today()
            seeded = engine.seed_from_history(store, prog, cfg.unit)
            st = engine.start_plan(store, prog, on)
            return self._json(200, {"plan": _plan(st),
                                    "seeded": [_adj(a, cfg.unit) for a in seeded]})

        def _advance(self, store: Store, args: dict):
            prog, _st = _program(store)
            if prog is None:
                return self._json(409, {"error": "no plan started"})
            asof = date.fromisoformat(args["asof"]) if args.get("asof") else None
            try:
                fired, new = engine.advance(store, prog, cfg.unit, force=bool(args.get("force")),
                                            asof=asof)
            except RuntimeError as e:
                return self._json(409, {"error": str(e)})
            return self._json(200, {"plan": _plan(new),
                                    "fired": [_adj(a, cfg.unit) for a in fired]})

        def _import_strong(self, body: bytes):
            text = _extract_csv(body, self.headers.get("Content-Type", ""))
            cfg.imports_dir.mkdir(parents=True, exist_ok=True)
            fname = f"strong_{datetime.now():%Y-%m-%d_%H%M%S}.csv"
            (cfg.imports_dir / fname).write_text(text)
            store = Store(cfg.db)
            catalog = Catalog.load()
            try:
                new, seen = import_strong_text(store, catalog, text, cfg.unit, fname)
                moves = store.remap_exercise_ids(catalog)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            finally:
                store.close()
            return self._json(200, {"sessions": seen, "new": new, "saved": fname,
                                    "remapped": len(moves)})

        def _import_health(self, body: bytes):
            kind = _health_kind(body)
            cfg.imports_dir.mkdir(parents=True, exist_ok=True)
            fname = f"health_{datetime.now():%Y-%m-%d_%H%M%S}.{kind}"
            path = cfg.imports_dir / fname
            path.write_bytes(body)
            if kind == "json":
                store = Store(cfg.db)
                try:
                    new, seen = import_health_text(store, body.decode("utf-8-sig"), fname)
                except (ValueError, UnicodeDecodeError) as e:
                    return self._json(400, {"error": str(e)})
                finally:
                    store.close()
                return self._json(200, {"readings": seen, "new": new, "saved": fname})

            # The Health app's own export: 2.3M records, minutes of parsing. Answering
            # first is not politeness — the phone's Get Contents of URL times out long
            # before this finishes, and a timeout on the phone reads as "the NAS is down"
            # for an import that in fact succeeded.
            if not _health_parse.acquire(blocking=False):
                path.unlink(missing_ok=True)
                return self._json(409, {"error": "an export is already parsing"})
            global _health_thread
            _health_thread = threading.Thread(target=_parse_export, args=(cfg, path),
                                              name="health-export", daemon=False)
            _health_thread.start()
            return self._json(202, {"queued": fname, "note": "parsing; watch imports in "
                                                             "/api/status"})

        def log_message(self, fmt, *args):  # quieter default log
            print(f"{self.address_string()} {fmt % args}")

    return Handler


def serve(cfg: Config, host="127.0.0.1", port=8790) -> None:
    # The CLI's other commands go through `cli._open`, which makes this directory;
    # `serve` does not, and on a fresh deploy `data/` is gitignored and absent, so
    # sqlite3.connect would raise "unable to open database file" on the first
    # request that touches the store — a container that starts and 500s.
    cfg.db.parent.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((host, port), make_handler(cfg))
    print(f"onemore web on http://{host}:{port}  db={cfg.db}")
    srv.serve_forever()
