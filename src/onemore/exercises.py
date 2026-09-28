"""Exercise catalog: canonical ids, display names, and per-source alias resolution."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .units import to_kg


@dataclass(frozen=True, slots=True)
class Exercise:
    """One movement on one piece of equipment.

    `step_lb` and `ceiling_lb` are in lb, not kg, on purpose: the plates and pin stacks
    are marked in lb, and rounding a kg load to a kg-converted 5 lb step and converting
    back does not land on the stack. `round_load` converts first and rounds in the target
    unit, so the step belongs in the unit the equipment exists in.

    `ceiling_lb` is None wherever the true limit is unknown, which is every machine —
    the export's heaviest logged load is a floor on the stack top, not the stack top.
    """

    id: str
    name: str
    pattern: str = ""
    main: bool = False
    bodyweight: bool = False
    equipment: str = ""
    step_lb: float | None = None
    ceiling_lb: float | None = None
    smith_tare_lb: float | None = None
    available: bool = True
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def step_kg(self, default_lb: float = 5.0) -> float:
        return to_kg(self.step_lb if self.step_lb is not None else default_lb, "lb")

    def ceiling_kg(self) -> float | None:
        return None if self.ceiling_lb is None else to_kg(self.ceiling_lb, "lb")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "unknown"


def _overlay_path() -> Path:
    """Where a user's catalog overlay would live, resolved the same way as
    Config.from_env resolves ONEMORE_DATA (config.py): the env var, or `./data`."""
    root = Path(os.environ.get("ONEMORE_DATA", Path.cwd() / "data"))
    return root / "exercises.toml"


def _merge_tables(base: dict, overlay: dict) -> dict:
    """Nested dict merge: a table's fields merge recursively table by table; a list
    (e.g. `aliases.strong`) is replaced outright rather than merged element-wise."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_tables(merged[key], value)
        else:
            merged[key] = value
    return merged


class Catalog:
    def __init__(self, exercises: dict[str, Exercise]):
        self._by_id = exercises
        self._alias: dict[tuple[str, str], str] = {}
        for ex in exercises.values():
            for source, names in ex.aliases.items():
                for n in names:
                    key = (source, n.casefold())
                    if key in self._alias and self._alias[key] != ex.id:
                        # Last-write-wins here would silently route a source name to
                        # whichever id TOML ordering happened to put second.
                        raise ValueError(
                            f"{source} name {n!r} is claimed by both "
                            f"{self._alias[key]!r} and {ex.id!r}")
                    self._alias[key] = ex.id
        self.unmapped: dict[str, set[str]] = {}

    @classmethod
    def load(cls, path=None) -> Catalog:
        if path is None:
            data = resources.files("onemore").joinpath("exercises.toml").read_bytes()
        else:
            data = Path(path).read_bytes()
        raw = tomllib.loads(data.decode())
        if path is None:
            overlay = _overlay_path()
            if overlay.is_file():
                raw = _merge_tables(raw, tomllib.loads(overlay.read_text()))
        exercises = {}
        for eid, body in raw.items():
            aliases = {k: tuple(v) for k, v in body.get("aliases", {}).items()}
            exercises[eid] = Exercise(
                id=eid,
                name=body.get("name", eid),
                pattern=body.get("pattern", ""),
                main=bool(body.get("main", False)),
                bodyweight=bool(body.get("bodyweight", False)),
                equipment=body.get("equipment", ""),
                step_lb=body.get("step_lb"),
                ceiling_lb=body.get("ceiling_lb"),
                smith_tare_lb=body.get("smith_tare_lb"),
                available=bool(body.get("available", True)),
                aliases=aliases,
            )
        return cls(exercises)

    def get(self, exercise_id: str) -> Exercise | None:
        return self._by_id.get(exercise_id)

    def name(self, exercise_id: str) -> str:
        ex = self._by_id.get(exercise_id)
        return ex.name if ex else exercise_id.replace("_", " ").title()

    def main_lifts(self) -> list[Exercise]:
        return [e for e in self._by_id.values() if e.main]

    def step_kg(self, exercise_id: str, default_lb: float = 5.0) -> float:
        """The smallest load jump for this exercise, in kg. Unknown ids take the default
        rather than raising: an unmapped Strong name should still render a number."""
        ex = self._by_id.get(exercise_id)
        return ex.step_kg(default_lb) if ex else to_kg(default_lb, "lb")

    def ceiling_kg(self, exercise_id: str) -> float | None:
        ex = self._by_id.get(exercise_id)
        return ex.ceiling_kg() if ex else None

    def unavailable(self, exercise_ids) -> list[str]:
        """Which of these the gym does not have. A program is checked against this."""
        return [i for i in exercise_ids
                if (ex := self._by_id.get(i)) is not None and not ex.available]

    def resolve(self, source: str, name: str) -> str:
        """Map a source's exercise name to a canonical id.

        Unknown names slugify to a stable id and are recorded in `unmapped` so they can be
        reviewed and added to exercises.toml; they are never dropped.
        """
        eid = self._alias.get((source, name.strip().casefold()))
        if eid:
            return eid
        eid = slugify(name)
        self.unmapped.setdefault(source, set()).add(name)
        return eid
