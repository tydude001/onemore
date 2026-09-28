# onemore — repo notes for Claude

Deviations from the global conventions only; everything else is inherited. When
`home/CLAUDE.md` exists, read it too: it is the private half, git-ignored here.

- `PLAN.md` owns the architecture. Read it before changing structure.
- `docs/research/*.md` are dated research records with citations. Append new
  findings with a date; do not rewrite old ones to match later decisions.
- Loads are stored in kg and rounded only at render time, per exercise, to the catalog's
  `step_lb` — stored in lb because that is how the plates and pin stacks are marked.
  `round_load` converts to the render unit first and rounds there.
- Adaptation rules must emit an `Adjustment` with rule name and evidence set
  ids. A rule that changes a plan silently is a bug.
- The Strong CSV adapter is both the one-time history import and the ongoing weekly feed;
  keep it idempotent. One session is (date, workout name) and an import skips a session it
  already holds — so a catalog edit reaches old history only through
  `Store.remap_exercise_ids`, which every import runs. Without it the ids stay frozen at
  whatever the catalog said on import day and every catalog lookup silently misses.
- Stack: Python 3.13, uv, src layout, pytest, ruff.
- `data/` is gitignored; a real Strong export lives at `data/imports/`. Tests use the
  synthetic fixtures under `tests/fixtures/` and never real training data — checks against a
  real export are scripts under `scripts/`, never tests.
- The shipped catalog is a Planet Fitness: Smith machine, selectorized machines, dumbbells
  to ~80 lb. No barbell, no rack. Steps and ceilings are per-exercise catalog data in
  `exercises.toml`, measured from a Strong export (`scripts/derive_increments.py`), never
  constants; `$ONEMORE_DATA/exercises.toml` overlays it for another gym. A program is
  checked against the gym with `Catalog.unavailable()`.
- `ceiling_lb` and `smith_tare_lb` are set only where the number is actually known — a
  machine's heaviest logged load is a floor on its stack top, not the stack top. A rule
  with no ceiling stays silent rather than inventing one.
- Nothing may depend on RPE: 3 of 2532 logged sets carry one. Prescribe percent-of-TM
  plus a last-set AMRAP instead (PLAN.md § RPE is not logged). The one qualitative input a
  rule reads is Strong's per-exercise note: a short top set whose note says it hurt is
  `tm_pain_hold`, not a miss.
- `rebuild` is the shipped default; `ONEMORE_PROGRAM` overrides it, and no caller names a
  program literally (`programs/__init__.py`). `comeback`'s exercise selection is medical,
  not taste — a lifter returning from a radial head fracture. Do not add a movement back
  because the gym has it; read `docs/research/radial-head-return.md` and the module
  docstring first. `tests/test_comeback.py` holds the tripwires.
- An accessory prescribed below ~0.71 of its own e1RM can only ratchet *down*: Epley is
  capped at 12 reps, so `e1rm_refresh` never measures a rise. Every program's accessories
  sit at 0.75, and a test over `PROGRAMS` enforces the floor (PLAN.md § The Epley ratchet).
- A rule may only write state in `engine.PERSISTED_STATE`; `_apply` raises otherwise. And
  state a rule writes must be read by the renderer, or the rule changes nothing.
- Health metrics (`metrics` table, `vitals.py`) are enrichment: no rule may require them.
  `recovery_deload` is the only rule that reads any, and its +5.0 bpm default is a measured
  percentile, not a chosen number; `scripts/recovery_threshold.py` measures it from your own
  export and prints the `ONEMORE_RHR_THRESHOLD` to set — re-measure rather than tune by
  feel. Sleep and HRV are not usable inputs and the docstring says why. What the export holds is in
  `docs/research/strong-data-out.md`.
- `web.py` and `static/` stay stdlib and CDN-free: the app runs on private networks with no
  internet assumed. Every write goes through the `X-Token` gate; GET is unauthenticated, so
  it must never be reachable from a network you don't trust. `serve` binds loopback by
  default and warns on any other `--host`; in a container the *published* port is what
  confines it (`docs/deploy.md`). A POST that fails auth must drain the body before
  answering, or the caller gets a dead socket instead of the error (`test_web.py`).
  Try writes (start, advance, import) against a copy of a database, never the real one.
  A Health export posted to `/import/health` answers 202 and parses on a worker thread —
  making that synchronous would look tidier and would time the phone out.
- The page is used as an iOS home-screen shortcut, which runs it standalone and
  edge-to-edge (`viewport-fit=cover`, `black-translucent`), so fixed chrome pays
  `env(safe-area-inset-*)` — the topbar's top, the nav's bottom. Every desktop browser
  reports those insets as 0, so a missing one is invisible everywhere it can be tested — the
  phone is the only check. `black-translucent` stays: its forced-white clock and battery are
  legible over the light theme, checked on the phone.
- There is no Dockerfile and adding one would be a regression — `dependencies = []` is what
  lets a clone be mounted read-only into stock `python:3.13-slim` (`docs/deploy.md`), so a
  deploy is a pull plus an `up -d --force-recreate --no-deps onemore` with no image to go
  stale. Adding a dependency ends that and needs a real `build:`.
- `/health` is a static 200 that never opens the database; it is not a health check.
  The container's healthcheck and any Kuma monitor probe `/api/status`.
- The web UI's look is the `Pale` design system: `docs/design.md` is the spec and
  `static/pale.css` its tokens, generated from that export — don't hand-tune values in it.
  `static/app.css` may use only those variables: no literal hex, no hand-picked shadow, no
  font that isn't one of the three. Translucent values come from `color-mix` on a token.
  Spacing is a strict 4px unit and interactive controls take the 12px `--radius`. The three
  faces are vendored under `static/fonts/` because the CDN-free rule above outranks the
  export's Google Fonts `@import`. `--accent-ink`/`--good-ink`/`--bad-ink` exist because
  `--primary`, `--good` and `--bad` are fills: as *text* they measure 2.8:1 and fail the
  system's own contrast check, so text takes the step of the same ramp that passes and
  fills keep the 500.
- This repo is mirrored publicly. A commit message says what the program changed; *why*,
  when the why is clinical or personal, does not go in this repo. `tests/test_denylist.py`
  runs where a private denylist exists and skips everywhere else.
- The logo and every icon in `static/` (`icon*.png`, `apple-touch-icon.png`, `maskable-512.png`,
  `icon.svg`, `mark.svg`) are generated, not hand-edited: `docs/brand/build_mark.py` is the
  source of the geometry and `docs/brand/README.md` how the set was exported. The
  apple-touch icon stays a PNG — iOS ignores an SVG one.
