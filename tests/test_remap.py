"""Catalog edits must reach sessions already imported.

`upsert_session` skips a session it already holds, so without a remap step an id resolved
by an older catalog stays frozen in the db and every catalog lookup misses on real history.
"""

from __future__ import annotations

from pathlib import Path

from onemore.cli import import_strong_text
from onemore.exercises import Catalog, Exercise
from onemore.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "strong_12col.csv"


def _empty_catalog() -> Catalog:
    c = Catalog.__new__(Catalog)
    c._by_id, c._alias, c.unmapped = {}, {}, {}
    return c


def _catalog_with(eid: str, strong_name: str) -> Catalog:
    c = _empty_catalog()
    ex = Exercise(id=eid, name=eid.replace("_", " ").title(), equipment="machine",
                  aliases={"strong": [strong_name]})
    c._by_id[eid] = ex
    c._alias[("strong", strong_name.casefold())] = eid
    return c


def test_remap_moves_entries_state_and_adjustments_to_the_new_id():
    text = FIXTURE.read_text()
    store = Store(":memory:")
    stale = _empty_catalog()  # knows nothing: every name slugifies
    import_strong_text(store, stale, text, "lb", str(FIXTURE))
    before = {r[0] for r in store.db.execute("SELECT DISTINCT exercise_id FROM entries")}
    assert before, "fixture produced no entries"

    old = min(before)
    raw = store.db.execute(
        "SELECT source_name FROM entries WHERE exercise_id=?", (old,)).fetchone()[0]
    store.set_state(old, "tm_kg", 60.0)

    moves = store.remap_exercise_ids(_catalog_with("canonical_lift", raw))
    assert moves[(raw, old)] == "canonical_lift"
    ids = {r[0] for r in store.db.execute("SELECT DISTINCT exercise_id FROM entries")}
    assert "canonical_lift" in ids and old not in ids
    # State follows the movement, or the lift's training max is orphaned on a dead id.
    assert store.get_state("canonical_lift", "tm_kg") == 60.0


def test_remap_is_a_no_op_when_the_catalog_already_agrees():
    text = FIXTURE.read_text()
    store = Store(":memory:")
    cat = Catalog.load()
    import_strong_text(store, cat, text, "lb", str(FIXTURE))
    assert store.remap_exercise_ids(Catalog.load()) == {}


def test_one_stale_id_covering_several_names_splits_instead_of_collapsing():
    """The real db held a single `bicep_curl` for the barbell, dumbbell and hammer curls.
    A catalog that gives each its own id must move each name to its own id, not drag all
    three onto whichever the last row happened to resolve to."""
    store = Store(":memory:")
    for i, raw in enumerate(["Bicep Curl (Barbell)", "Hammer Curl (Dumbbell)"]):
        store.db.execute(
            "INSERT INTO sessions(source, source_key, started_at) VALUES ('strong', ?, ?)",
            (f"k{i}", f"2024-01-0{i + 1}T10:00:00"))
        store.db.execute(
            "INSERT INTO entries(session_id, exercise_id, ord, source_name)"
            " VALUES (?, 'bicep_curl', 0, ?)", (store.db.execute(
                "SELECT id FROM sessions WHERE source_key=?", (f"k{i}",)).fetchone()[0], raw))

    cat = _empty_catalog()
    for eid, raw in [("barbell_curl", "Bicep Curl (Barbell)"),
                     ("dumbbell_curl", "Hammer Curl (Dumbbell)")]:
        cat._by_id[eid] = Exercise(id=eid, name=eid, equipment="barbell",
                                   aliases={"strong": [raw]})
        cat._alias[("strong", raw.casefold())] = eid

    store.remap_exercise_ids(cat)
    got = dict(store.db.execute("SELECT source_name, exercise_id FROM entries"))
    assert got == {"Bicep Curl (Barbell)": "barbell_curl",
                   "Hammer Curl (Dumbbell)": "dumbbell_curl"}


def test_the_pulldown_split_moves_the_machine_and_leaves_the_tm_with_the_cable():
    """2026-09-21: `lat_pulldown` covered both Strong pulldowns. Split, the cable keeps the
    bare id and the machine gets its own. The TM already stored under `lat_pulldown` was set
    off the cable, so it must stay there and the machine must start with none -- a TM
    carried onto the other load scale would prescribe the wrong weight."""
    store = Store(":memory:")
    for i, raw in enumerate(["Lat Pulldown (Cable)", "Lat Pulldown (Machine)"]):
        store.db.execute(
            "INSERT INTO sessions(source, source_key, started_at) VALUES ('strong', ?, ?)",
            (f"k{i}", f"2026-09-0{i + 1}T10:00:00"))
        store.db.execute(
            "INSERT INTO entries(session_id, exercise_id, ord, source_name)"
            " VALUES (?, 'lat_pulldown', 0, ?)", (store.db.execute(
                "SELECT id FROM sessions WHERE source_key=?", (f"k{i}",)).fetchone()[0], raw))
    store.set_state("lat_pulldown", "tm_kg", 40.0)

    moves = store.remap_exercise_ids(Catalog.load())
    assert moves == {("Lat Pulldown (Machine)", "lat_pulldown"): "machine_lat_pulldown"}
    got = dict(store.db.execute("SELECT source_name, exercise_id FROM entries"))
    assert got == {"Lat Pulldown (Cable)": "lat_pulldown",
                   "Lat Pulldown (Machine)": "machine_lat_pulldown"}
    assert store.get_state("lat_pulldown", "tm_kg") == 40.0
    assert store.get_state("machine_lat_pulldown", "tm_kg") is None
