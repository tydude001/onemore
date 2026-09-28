"""The catalog owns load arithmetic, so its invariants are worth asserting."""

from __future__ import annotations

import pytest

from onemore.exercises import Catalog
from onemore.units import to_kg

CAT = Catalog.load()

# Exercise names Strong emits for this gym's equipment. Not an export: a hand-written
# list of the names the adapter has to recognise, one per catalog entry that matters.
PF_NAMES = [
    "Seated Leg Press (Machine)", "Shoulder Press (Machine)", "Seated Leg Curl (Machine)",
    "Seated Row (Machine)", "Bicep Curl (Machine)", "Arnold Press (Dumbbell)",
    "Chest Press (Machine)", "Triceps Extension (Machine)", "Triceps Extension",
    "Iso-Lateral Chest Press (Machine)", "Chest Fly (Dumbbell)", "MTS Shoulder Press",
    "Preacher Curl (Machine)", "Knee Raise (Captain's Chair)", "Tricep Press Machine",
    "Hammer Curl (Cable)", "Incline Bench Press (Dumbbell)", "Skullcrusher (Barbell)",
    "Crunch (Machine)", "MTS Row", "Chest Fly", "Mts Chest Press", "Front Raise (Cable)",
    "Leg Extension (Machine)", "Seated Row (Cable)", "Sitting Bike",
    "Deadlift (Smith Machine)", "Decline Crunch", "Seated French Press",
    "Squat (Smith Machine)", "Tricep Pressdown (Cable)", "Calf Press on Leg Press",
    "Front Pulldown", "Seated Hammer Curl", "Mts Front Pulldown", "Mts Incline Press",
    "Bench Press (Smith Machine)", "Bicep Curl (Cable)", "Calf Press on Seated Leg Press",
    "Elliptical Machine", "Hip Abductor (Machine)", "Lat Pulldown - Wide Grip (Cable)",
    "MTS Abdominal Crunch", "Mts Rows Machine", "Push Up",
    "Standing Calf Raise (Dumbbell)", "Standing Calf Raise (Smith Machine)",
]


def test_every_planet_fitness_name_maps_to_a_catalog_entry():
    cat = Catalog.load()
    for name in PF_NAMES:
        eid = cat.resolve("strong", name)
        assert cat.get(eid) is not None, f"{name!r} slugified to {eid!r} instead of mapping"
    assert cat.unmapped == {}


def test_alias_collisions_are_refused_rather_than_silently_resolved():
    """Last-write-wins on a duplicate alias would route a name by TOML ordering."""
    from onemore.exercises import Exercise

    dup = {
        "a": Exercise(id="a", name="A", aliases={"strong": ("Same Name",)}),
        "b": Exercise(id="b", name="B", aliases={"strong": ("Same Name",)}),
    }
    with pytest.raises(ValueError, match="claimed by both"):
        Catalog(dup)


def test_every_loaded_exercise_has_a_step_unless_it_carries_no_load():
    for ex in Catalog.load()._by_id.values():
        if ex.equipment in ("cardio",) or (ex.bodyweight and ex.step_lb is None):
            continue
        assert ex.step_lb is not None, f"{ex.id} has no step_lb"
        assert ex.step_lb > 0


def test_ceilings_are_set_only_where_the_limit_is_actually_known():
    """The dumbbell rack is known; a pin stack's top is not. An invented machine ceiling
    would stall a lift that had room left, so absence here is the correct state."""
    for ex in Catalog.load()._by_id.values():
        if ex.ceiling_lb is not None:
            assert ex.equipment == "dumbbell", f"{ex.id} claims a ceiling it cannot know"


def test_steps_are_lb_and_convert_to_kg_not_the_other_way():
    assert CAT.step_kg("leg_press") == pytest.approx(to_kg(5, "lb"))
    assert CAT.step_kg("machine_bicep_curl") == pytest.approx(to_kg(2.5, "lb"))
    assert CAT.step_kg("lat_pulldown") == pytest.approx(to_kg(10, "lb"))


def test_unknown_id_falls_back_instead_of_raising():
    """An unmapped Strong name must still render a number."""
    assert CAT.step_kg("no_such_exercise", default_lb=5) == pytest.approx(to_kg(5, "lb"))
    assert CAT.ceiling_kg("no_such_exercise") is None


def test_barbell_movements_are_present_but_marked_unavailable():
    """Kept so old history resolves; marked so a program can be checked against the gym."""
    assert CAT.unavailable(["back_squat", "deadlift", "bench_press"]) == [
        "back_squat", "deadlift", "bench_press"]
    assert CAT.unavailable(["leg_press", "smith_squat", "dumbbell_bench_press"]) == []


def test_the_cable_and_machine_pulldowns_are_separate_lifts():
    """Two load scales, two training maxes (split 2026-09-21)."""
    assert CAT.resolve("strong", "Lat Pulldown (Cable)") == "lat_pulldown"
    assert CAT.resolve("strong", "Lat Pulldown - Wide Grip (Cable)") == "lat_pulldown"
    assert CAT.resolve("strong", "Lat Pulldown (Machine)") == "machine_lat_pulldown"
    assert CAT.get("lat_pulldown").equipment == "cable"
    assert CAT.get("machine_lat_pulldown").equipment == "machine"
    assert CAT.step_kg("machine_lat_pulldown") == pytest.approx(to_kg(10, "lb"))


# -- $ONEMORE_DATA/exercises.toml overlay --------------------------------------------


def test_with_no_overlay_file_the_catalog_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEMORE_DATA", str(tmp_path))
    cat = Catalog.load()
    assert cat.get("leg_press") == CAT.get("leg_press")
    assert set(cat._by_id) == set(CAT._by_id)


def test_overlay_field_override_keeps_the_rest_of_the_table(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEMORE_DATA", str(tmp_path))
    (tmp_path / "exercises.toml").write_text(
        '[leg_press]\nceiling_lb = 400\n'
    )
    cat = Catalog.load()
    ex = cat.get("leg_press")
    assert ex.ceiling_lb == 400
    # Everything the overlay did not mention survives from the shipped table.
    assert ex.name == "Leg Press"
    assert ex.pattern == "squat"
    assert ex.equipment == "machine"
    assert ex.step_lb == 5
    assert ex.aliases == {"strong": ("Seated Leg Press (Machine)", "Leg Press")}


def test_overlay_can_add_a_new_exercise(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEMORE_DATA", str(tmp_path))
    (tmp_path / "exercises.toml").write_text(
        '[my_home_gym_row]\n'
        'name = "Home Gym Row"\n'
        'equipment = "cable"\n'
        'step_lb = 5\n'
    )
    cat = Catalog.load()
    ex = cat.get("my_home_gym_row")
    assert ex is not None
    assert ex.name == "Home Gym Row"
    assert ex.equipment == "cable"
    # The shipped catalog is still there alongside it.
    assert cat.get("leg_press") is not None
