from datetime import timedelta
from pathlib import Path

import pytest

from onemore.cli import import_strong_text
from onemore.exercises import Catalog
from onemore.model import Set, SetType
from onemore.sources.strong_csv import StrongCsvSource, parse_duration
from onemore.store import Store
from onemore.units import to_kg

FIX = Path(__file__).parent / "fixtures"


def load(name, unit="lb"):
    cat = Catalog.load()
    src = StrongCsvSource.from_path(FIX / name, cat, weight_unit=unit)
    return list(src.fetch_sessions()), cat


def test_12col_sessions_entries_sets():
    sessions, cat = load("strong_12col.csv")
    assert [s.title for s in sessions] == ["Day A", "Day B"]
    a = sessions[0]
    assert a.duration == timedelta(hours=1, minutes=5)
    assert a.notes == "felt ok"
    assert [e.exercise_id for e in a.entries] == ["back_squat", "bench_press", "some_new_machine"]
    squat = a.entries[0]
    assert [s.set_type for s in squat.sets] == [SetType.WARMUP, SetType.WORK, SetType.WORK]
    assert squat.sets[1].weight_kg == pytest.approx(to_kg(225, "lb"))
    assert squat.sets[1].rpe == 7 and squat.sets[2].rpe == 8
    assert a.entries[1].notes == "paused"
    assert cat.unmapped == {"strong": {"Some New Machine"}}


def test_10col_variant_and_float_reps():
    sessions, _ = load("strong_10col.csv")
    row = sessions[0].entries[0]
    assert row.exercise_id == "barbell_row"
    assert [s.reps for s in row.sets] == [13, 12]
    assert sessions[0].duration == timedelta(minutes=35)


def test_thousands_separator_duration_row_is_repaired():
    sessions, _ = load("strong_thousands_duration.csv")
    s = sessions[0]
    assert s.duration == timedelta(hours=1301, minutes=4)
    e = s.entries[0]
    assert e.source_name == "Mts Chest Press"
    assert [x.set_type for x in e.sets] == [SetType.WARMUP, SetType.WORK]
    assert e.sets[1].weight_kg == pytest.approx(to_kg(50, "lb"))


def test_semicolon_kg_header_overrides_config_unit():
    sessions, _ = load("strong_semicolon_kg.csv", unit="lb")
    st = sessions[0].entries[0].sets[0]
    assert st.weight_kg == pytest.approx(100.0)
    assert st.reps == 5 and st.rpe == 8


def test_rest_timer_rows_are_not_sets():
    sessions, _ = load("strong_rest_timer.csv")
    curl, ext = sessions[0].entries
    assert [(s.set_type, s.weight_kg, s.reps) for s in curl.sets] == [
        (SetType.WARMUP, pytest.approx(to_kg(30, "lb")), 8),
        (SetType.WORK, pytest.approx(to_kg(60, "lb")), 7),
        (SetType.WORK, pytest.approx(to_kg(55, "lb")), 5),
    ]
    assert [s.index for s in curl.sets] == [1, 1, 2]
    assert len(ext.sets) == 1
    assert not any("Rest Timer" in s.source_ref for e in sessions[0].entries for s in e.sets)


def test_import_clears_rest_timers_already_in_the_db():
    """A session held from before the parser skipped rest timers is never re-imported, so
    the import has to clear its rows in place — and only those."""
    sessions, cat = load("strong_rest_timer.csv")
    old = sessions[0]
    curl = old.entries[0]
    curl.sets.insert(2, Set(index=3, set_type=SetType.WORK, weight_kg=0.0, reps=0,
                            source_ref=f"strong:{old.source_key}:{curl.source_name}:Rest Timer:r4"))
    store = Store(":memory:")
    store.upsert_session(old)
    assert len(store.sets_for("leg_curl")) == 4
    new, seen = import_strong_text(store, cat, (FIX / "strong_rest_timer.csv").read_text(), "lb")
    assert (new, seen) == (0, 1)
    assert [(s.weight_kg, s.reps) for _, s in store.sets_for("leg_curl")] == [
        (pytest.approx(to_kg(30, "lb")), 8), (pytest.approx(to_kg(60, "lb")), 7),
        (pytest.approx(to_kg(55, "lb")), 5)]
    assert store.drop_rest_timers() == 0


def test_parse_duration():
    assert parse_duration("2h 38m") == timedelta(hours=2, minutes=38)
    assert parse_duration("57m") == timedelta(minutes=57)
    assert parse_duration("1h 5m 30s") == timedelta(hours=1, minutes=5, seconds=30)
    assert parse_duration("") is None


def test_store_import_is_idempotent(tmp_path):
    sessions, _ = load("strong_12col.csv")
    store = Store(tmp_path / "t.db")
    assert [store.upsert_session(s) for s in sessions] == [True, True]
    assert [store.upsert_session(s) for s in sessions] == [False, False]
    back = store.sessions()
    assert len(back) == 2
    assert back[0].entries[0].sets[1].source_ref.startswith("strong:")
    squat_sets = store.sets_for("back_squat")
    assert len(squat_sets) == 3
