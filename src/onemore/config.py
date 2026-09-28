"""Runtime configuration from environment variables, with repo-local defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Config:
    db: Path
    unit: str
    # Fallback only, in lb: the load step is per-exercise catalog data, and this is what
    # an exercise the catalog has no step for rounds to. Not a global rounding constant.
    fallback_step_lb: float
    token: str  # webhook shared secret; empty disables POST
    imports_dir: Path

    @classmethod
    def from_env(cls) -> Config:
        root = Path(os.environ.get("ONEMORE_DATA", Path.cwd() / "data"))
        return cls(
            db=Path(os.environ.get("ONEMORE_DB", root / "onemore.db")),
            unit=os.environ.get("ONEMORE_UNIT", "lb"),
            fallback_step_lb=float(os.environ.get("ONEMORE_ROUND", "5")),
            token=os.environ.get("ONEMORE_TOKEN", ""),
            imports_dir=Path(os.environ.get("ONEMORE_IMPORTS", root / "imports")),
        )
