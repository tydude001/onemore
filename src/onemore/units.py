"""Unit handling. Loads are stored in kg; rendering converts to the user's unit."""

from __future__ import annotations

KG_PER_LB = 0.45359237


def to_kg(value: float, unit: str) -> float:
    if unit == "kg":
        return float(value)
    if unit == "lb":
        return float(value) * KG_PER_LB
    raise ValueError(f"unknown unit {unit!r}")


def from_kg(kg: float, unit: str) -> float:
    if unit == "kg":
        return kg
    if unit == "lb":
        return kg / KG_PER_LB
    raise ValueError(f"unknown unit {unit!r}")


def round_to(value: float, step: float) -> float:
    """Round to the nearest multiple of `step` (a plate-pair increment, e.g. 5 lb)."""
    if step <= 0:
        return value
    return round(value / step) * step


def round_load(kg: float, unit: str, step: float) -> float:
    """Convert kg to `unit` and round to `step` **in that unit**.

    The order matters. The stacks and plates are marked in lb, so rounding has to happen
    on the lb value; rounding the kg value to a kg-converted 5 lb step and converting back
    lands between the pins. `step` is therefore always in `unit`, never in kg.
    """
    return round_to(from_kg(kg, unit), step)
