"""Adaptation rules. Each is a function Context -> list[Adjustment]. Order matters."""

from .base import Context, Rule
from .ceiling import dumbbell_ceiling
from .progression import (
    calibrate_new_lift,
    calibrate_tm,
    e1rm_ceiling,
    e1rm_refresh,
    tm_progress,
)
from .recovery import recovery_deload
from .schedule import deload_after_reductions, missed_week_repeat
from .volume import accessory_volume

DEFAULT_RULES: tuple[Rule, ...] = (
    e1rm_refresh,
    missed_week_repeat,
    calibrate_tm,
    tm_progress,
    calibrate_new_lift,
    e1rm_ceiling,
    dumbbell_ceiling,
    accessory_volume,
    deload_after_reductions,
    recovery_deload,
)

__all__ = ["DEFAULT_RULES", "Context", "Rule"]
