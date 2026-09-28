import os

from . import comeback, rebuild

PROGRAMS = {"comeback": comeback.build, "rebuild": rebuild.build}

# The default anywhere a program is not named. `rebuild` is restored with its accessories at
# 0.75 (PLAN.md § The Epley ratchet) and ships as the default, because `comeback`'s exercise
# selection is medical, built around a fracture the reader probably does not have. An instance
# that is running `comeback` sets ONEMORE_PROGRAM=comeback, so its Start button keeps offering
# it. A plan already stored under `comeback` loads as `comeback` either way: the fallback in
# engine.py only catches a program name that is not in `PROGRAMS` at all.
# Single-sourced because it once was not: 0650bd7 changed the CLI's default and left five
# literal fallbacks in web.py, so the API and the CLI disagreed.
SHIPPED_DEFAULT = "rebuild"


def default_program(env: dict[str, str] | None = None) -> str:
    """`ONEMORE_PROGRAM` if set, else `SHIPPED_DEFAULT`. An unknown name fails at startup,
    not at the first Start press."""
    name = (os.environ if env is None else env).get("ONEMORE_PROGRAM") or SHIPPED_DEFAULT
    if name not in PROGRAMS:
        raise ValueError(f"ONEMORE_PROGRAM={name!r} is not one of {sorted(PROGRAMS)}")
    return name


DEFAULT_PROGRAM = default_program()
