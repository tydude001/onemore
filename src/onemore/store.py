"""SQLite store. Idempotent on (source, source_key) so any adapter can be re-run freely."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .model import Adjustment, ExerciseEntry, Metric, Session, Set, SetType

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  source_key TEXT NOT NULL,
  started_at TEXT NOT NULL,
  duration_s INTEGER,
  title TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  bodyweight_kg REAL,
  UNIQUE(source, source_key)
);
CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  exercise_id TEXT NOT NULL,
  ord INTEGER NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  source_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sets (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  set_type TEXT NOT NULL,
  weight_kg REAL,
  reps INTEGER,
  rpe REAL,
  rir REAL,
  completed INTEGER NOT NULL DEFAULT 1,
  source_ref TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sets_entry ON sets(entry_id);
CREATE INDEX IF NOT EXISTS entries_session ON entries(session_id);
CREATE INDEX IF NOT EXISTS entries_exercise ON entries(exercise_id);
CREATE TABLE IF NOT EXISTS lift_state (
  lift TEXT NOT NULL,
  key TEXT NOT NULL,
  value REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (lift, key)
);
CREATE TABLE IF NOT EXISTS plan_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS adjustments (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  week INTEGER,
  rule TEXT NOT NULL,
  lift TEXT NOT NULL,
  field TEXT NOT NULL,
  old REAL,
  new REAL,
  reason TEXT NOT NULL,
  evidence TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS metrics (
  source TEXT NOT NULL,
  name TEXT NOT NULL,
  at TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (source, name, at)
);
CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY,
  received_at TEXT NOT NULL,
  source TEXT NOT NULL,
  filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  sessions_new INTEGER NOT NULL,
  sessions_seen INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # -- sessions -----------------------------------------------------------------

    def upsert_session(self, s: Session) -> bool:
        """Insert a session; return True if new. An existing (source, source_key) is skipped."""
        row = self.db.execute(
            "SELECT id FROM sessions WHERE source=? AND source_key=?", (s.source, s.source_key)
        ).fetchone()
        if row:
            return False
        cur = self.db.execute(
            "INSERT INTO sessions(source, source_key, started_at, duration_s, title, notes,"
            " bodyweight_kg) VALUES (?,?,?,?,?,?,?)",
            (
                s.source,
                s.source_key,
                s.started_at.isoformat(),
                int(s.duration.total_seconds()) if s.duration else None,
                s.title,
                s.notes,
                s.bodyweight_kg,
            ),
        )
        sid = cur.lastrowid
        for e in s.entries:
            ecur = self.db.execute(
                "INSERT INTO entries(session_id, exercise_id, ord, notes, source_name)"
                " VALUES (?,?,?,?,?)",
                (sid, e.exercise_id, e.order, e.notes, e.source_name),
            )
            eid = ecur.lastrowid
            self.db.executemany(
                "INSERT INTO sets(entry_id, idx, set_type, weight_kg, reps, rpe, rir, completed,"
                " source_ref) VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (eid, st.index, st.set_type, st.weight_kg, st.reps, st.rpe, st.rir,
                     int(st.completed), st.source_ref)
                    for st in e.sets
                ],
            )
        self.db.commit()
        return True

    def sessions(self, since: date | None = None, until: date | None = None) -> list[Session]:
        q = "SELECT * FROM sessions"
        args: list = []
        conds = []
        if since:
            conds.append("started_at >= ?")
            args.append(since.isoformat())
        if until:
            conds.append("started_at < ?")
            args.append((until + timedelta(days=1)).isoformat())
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY started_at"
        out = []
        for r in self.db.execute(q, args):
            out.append(self._hydrate(r))
        return out

    def _hydrate(self, r: sqlite3.Row) -> Session:
        s = Session(
            source=r["source"],
            source_key=r["source_key"],
            started_at=datetime.fromisoformat(r["started_at"]),
            duration=timedelta(seconds=r["duration_s"]) if r["duration_s"] is not None else None,
            title=r["title"],
            notes=r["notes"],
            bodyweight_kg=r["bodyweight_kg"],
        )
        for e in self.db.execute(
            "SELECT * FROM entries WHERE session_id=? ORDER BY ord", (r["id"],)
        ):
            entry = ExerciseEntry(
                exercise_id=e["exercise_id"], order=e["ord"], notes=e["notes"],
                source_name=e["source_name"],
            )
            for st in self.db.execute("SELECT * FROM sets WHERE entry_id=? ORDER BY idx", (e["id"],)):
                entry.sets.append(
                    Set(
                        index=st["idx"], set_type=SetType(st["set_type"]),
                        weight_kg=st["weight_kg"], reps=st["reps"], rpe=st["rpe"], rir=st["rir"],
                        completed=bool(st["completed"]), source_ref=st["source_ref"],
                    )
                )
            s.entries.append(entry)
        return s

    def sets_for(self, exercise_id: str, since: date | None = None) -> list[tuple[date, Set]]:
        q = (
            "SELECT s.started_at, st.* FROM sets st JOIN entries e ON st.entry_id=e.id"
            " JOIN sessions s ON e.session_id=s.id WHERE e.exercise_id=?"
        )
        args: list = [exercise_id]
        if since:
            q += " AND s.started_at >= ?"
            args.append(since.isoformat())
        q += " ORDER BY s.started_at, e.ord, st.idx"
        out = []
        for r in self.db.execute(q, args):
            out.append(
                (
                    datetime.fromisoformat(r["started_at"]).date(),
                    Set(
                        index=r["idx"], set_type=SetType(r["set_type"]), weight_kg=r["weight_kg"],
                        reps=r["reps"], rpe=r["rpe"], rir=r["rir"], completed=bool(r["completed"]),
                        source_ref=r["source_ref"],
                    ),
                )
            )
        return out

    def exercise_ids(self) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT exercise_id FROM entries GROUP BY exercise_id ORDER BY COUNT(*) DESC")]

    def unmapped_names(self) -> list[tuple[str, str, int]]:
        """(source, raw name, count) for entries whose exercise_id is not in the catalog.
        The catalog check is the caller's; this returns every distinct (exercise_id, name)."""
        return [
            (r[0], r[1], r[2])
            for r in self.db.execute(
                "SELECT exercise_id, source_name, COUNT(*) FROM entries"
                " GROUP BY exercise_id, source_name ORDER BY 3 DESC"
            )
        ]

    def remap_exercise_ids(self, catalog) -> dict[tuple[str, str], str]:
        """Re-resolve every entry's exercise_id from the raw source name it was imported with.

        `upsert_session` skips a session it already holds, so a catalog edit made after an
        import never reaches the rows already in the db — the ids stay frozen at whatever the
        catalog said that day, and every catalog-driven lookup (step, ceiling, availability)
        silently misses on the real history. Called on every import so the catalog stays the
        one owner of the mapping.

        Keyed on (raw name, old id), not on the old id alone: one id routinely covers several
        source names (a single `bicep_curl` held the barbell, dumbbell and hammer curls), and
        a catalog that splits them must not drag all three onto whichever landed last.

        Returns the {(raw name, old id): new id} moves it made.
        """
        moves: dict[tuple[str, str], str] = {}
        rows = self.db.execute(
            "SELECT DISTINCT s.source, e.exercise_id, e.source_name FROM entries e"
            " JOIN sessions s ON s.id = e.session_id WHERE e.source_name != ''"
        ).fetchall()
        for source, old, raw in rows:
            new = catalog.resolve(source, raw)
            if new != old:
                moves[(raw, old)] = new
        if not moves:
            return moves
        for (raw, old), new in moves.items():
            self.db.execute(
                "UPDATE entries SET exercise_id=? WHERE exercise_id=? AND source_name=?",
                (new, old, raw))
        # Per-lift state and adjustments are keyed by id with no source name to disambiguate,
        # so they can only follow an id that moved as a whole. A split id leaves them where
        # they are rather than guessing which half they belonged to.
        whole = {old: new for (_, old), new in moves.items()
                 if len({n for (_, o), n in moves.items() if o == old}) == 1
                 and not self.db.execute(
                     "SELECT 1 FROM entries WHERE exercise_id=? LIMIT 1", (old,)).fetchone()}
        for old, new in whole.items():
            self.db.execute("UPDATE OR REPLACE lift_state SET lift=? WHERE lift=?", (new, old))
            self.db.execute("UPDATE adjustments SET lift=? WHERE lift=?", (new, old))
        self.db.commit()
        return moves

    def drop_rest_timers(self) -> int:
        """Delete Strong "Rest Timer" rows imported as sets before the adapter skipped them.
        `upsert_session` never revisits a held session, so the parser fix alone leaves them
        in place for good. Matched on the source_ref the adapter wrote, which carries the Set
        Order verbatim (`strong:<key>:<exercise>:Rest Timer:r<row>`). Returns rows deleted."""
        cur = self.db.execute(
            "DELETE FROM sets WHERE source_ref LIKE 'strong:%:Rest Timer:r%'"
            " AND COALESCE(weight_kg, 0) = 0 AND COALESCE(reps, 0) = 0")
        self.db.commit()
        return cur.rowcount

    # -- state --------------------------------------------------------------------

    def get_state(self, lift: str, key: str) -> float | None:
        r = self.db.execute(
            "SELECT value FROM lift_state WHERE lift=? AND key=?", (lift, key)
        ).fetchone()
        return r[0] if r else None

    def set_state(self, lift: str, key: str, value: float | None) -> None:
        self.db.execute(
            "INSERT INTO lift_state(lift, key, value, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(lift, key) DO UPDATE SET value=excluded.value,"
            " updated_at=excluded.updated_at",
            (lift, key, value, datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()

    def all_state(self) -> dict[str, dict[str, float | None]]:
        out: dict[str, dict[str, float | None]] = {}
        for r in self.db.execute("SELECT lift, key, value FROM lift_state ORDER BY lift, key"):
            out.setdefault(r[0], {})[r[1]] = r[2]
        return out

    def get_plan(self, key: str, default=None):
        r = self.db.execute("SELECT value FROM plan_state WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_plan(self, key: str, value) -> None:
        self.db.execute(
            "INSERT INTO plan_state(key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self.db.commit()

    # -- adjustments ----------------------------------------------------------------

    def add_adjustments(self, adjs: list[Adjustment]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.db.executemany(
            "INSERT INTO adjustments(created_at, week, rule, lift, field, old, new, reason,"
            " evidence) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (now, a.week, a.rule, a.lift, a.field, a.old, a.new, a.reason,
                 json.dumps(list(a.evidence)))
                for a in adjs
            ],
        )
        self.db.commit()

    def adjustments(self, week: int | None = None) -> list[Adjustment]:
        q = "SELECT * FROM adjustments"
        args: list = []
        if week is not None:
            q += " WHERE week=?"
            args.append(week)
        q += " ORDER BY id"
        return [
            Adjustment(
                rule=r["rule"], lift=r["lift"], field=r["field"], old=r["old"], new=r["new"],
                reason=r["reason"], evidence=tuple(json.loads(r["evidence"])), week=r["week"],
            )
            for r in self.db.execute(q, args)
        ]

    # -- metrics ------------------------------------------------------------------

    def upsert_metrics(self, metrics: list[Metric]) -> int:
        """Insert readings; return how many were new. A reading already held for the same
        (source, name, instant) is replaced, so a re-export with a corrected value wins."""
        before = self.db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        self.db.executemany(
            "INSERT INTO metrics(source, name, at, value, unit) VALUES (?,?,?,?,?)"
            " ON CONFLICT(source, name, at) DO UPDATE SET value=excluded.value,"
            " unit=excluded.unit",
            [(m.source, m.name, m.at.isoformat(), m.value, m.unit) for m in metrics],
        )
        self.db.commit()
        return self.db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] - before

    def metrics(self, name: str, since: date | None = None) -> list[Metric]:
        q = "SELECT source, name, at, value, unit FROM metrics WHERE name=?"
        args: list = [name]
        if since is not None:
            q += " AND substr(at, 1, 10) >= ?"
            args.append(since.isoformat())
        q += " ORDER BY at"
        return [Metric(r[0], r[1], datetime.fromisoformat(r[2]), r[3], r[4])
                for r in self.db.execute(q, args)]

    def metric_names(self) -> list[tuple[str, int]]:
        return [(r[0], r[1]) for r in self.db.execute(
            "SELECT name, COUNT(*) FROM metrics GROUP BY name ORDER BY name")]

    def record_import(self, source: str, filename: str, sha256: str, new: int, seen: int) -> None:
        self.db.execute(
            "INSERT INTO imports(received_at, source, filename, sha256, sessions_new,"
            " sessions_seen) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), source, filename, sha256, new, seen),
        )
        self.db.commit()

    def imports(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM imports ORDER BY id"))
