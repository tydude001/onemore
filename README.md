<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/onemore-horizontal-mono-cd7ba4.svg">
    <img alt="onemore" src="docs/brand/onemore-horizontal-mono-ae4278.svg" width="280">
  </picture>
</h1>

[![CI](https://github.com/tydude001/onemore/actions/workflows/ci.yml/badge.svg)](https://github.com/tydude001/onemore/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

onemore doesn't replace your logger. Strong stays the logging app — onemore
reads its CSV export, renders a multi-week program with loads rounded to
your gym's real plates and pin stacks, and adjusts the next week through
rules that each leave an audit trail. No RPE, no dependencies, one phone
page.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/week-dark.png">
    <img alt="the week view: loads rounded per machine, the rule that produced each one" src="docs/screenshots/week-light.png" width="260">
  </picture>
  <img alt="the rules view: every adjustment with its evidence" src="docs/screenshots/rules.png" width="260">
</p>

<p align="center"><sub>From <code>onemore demo</code> — synthetic training history, nothing real.</sub></p>

## Quick start

```bash
git clone https://github.com/tydude001/onemore.git
cd onemore
uv sync
uv run onemore demo       # a synthetic training history, a plan, and the web app — nothing real, nothing kept
```

To use it for real:

```bash
uv run onemore import path/to/your_strong_export.csv
uv run onemore status                 # history and estimated maxes per lift
uv run onemore start --days 4         # seeds training maxes from history, week 1 starts today
uv run onemore plan --week 1          # the week, loads rounded per machine
uv run onemore advance                # after the week's export lands: run the rules, move on
uv run onemore explain --week 1       # which rules fired, on which sets, and why
uv run onemore serve                  # the web app and the import webhooks — see docs/deploy.md
```

`uv run onemore status --unmapped` lists any exercise name Strong logged
that isn't in the catalog yet — a gym's equipment is data
(`exercises.toml`), not code, and `$ONEMORE_DATA/exercises.toml` overlays
the shipped one so your own steps and ceilings don't need a fork.
`ONEMORE_RHR_THRESHOLD` overrides the resting-heart-rate margin
`recovery_deload` reads before it inserts a deload (default +5.0 bpm,
measured — see the rules table below).

## The rules

Every adaptation rule writes an `Adjustment` — its name, what changed, and
the evidence set ids behind it — so nothing moves a number silently and
`onemore explain` can show exactly why.

| Rule | Reads | Effect |
|---|---|---|
| `e1rm_refresh` | your best logged set per lift, rolling window | updates the lift's estimated max |
| `calibrate_tm` / `calibrate_new_lift` | the seeding week's, or a newly-added lift's, best set | sets a training max where none exists yet |
| `tm_progress` | the week's top AMRAP set against its target reps | progresses, holds, or (after two misses) cuts the training max 10%; a Strong note that a set hurt holds it instead of counting a miss |
| `e1rm_ceiling` | training max against the rolling estimated max | clamps the training max so it can't outrun demonstrated strength |
| `dumbbell_ceiling` | load against a lift's known ceiling | once the load can't go up, adds reps, then a set |
| `missed_week_repeat` | days logged this week | repeats the week instead of advancing |
| `deload_after_reductions` | this week's training-max cuts | inserts a deload after two lifts drop in the same week |
| `recovery_deload` | Apple Health resting heart rate, if you send it | inserts a deload when the week's mean sits well above your own 28-day baseline |
| `accessory_volume` | logged RPE, if your export carries any | trims or adds a set on non-main lifts; most exports carry none, so this one is usually silent |

No rule needs RPE, sleep, or HRV to run the plan — Strong logs almost none
of the first and the other two are enrichment at best. Health data is
optional everywhere it's read.

## Privacy

Everything onemore reads or writes lives in one SQLite file and the CSV or
export you gave it, all under your own data directory. Nothing is sent
anywhere, ever — there's no network call in the whole program, `onemore
serve` included, beyond answering requests you send it yourself.

`onemore serve` binds `127.0.0.1` by default. Running it on any address
other than loopback, or a private network you control, is unsupported —
its GET routes carry no authentication at all. See `docs/deploy.md` and
`SECURITY.md`.

## Programs

`rebuild`: the shipped default. A general 4-day upper/lower return-to-training
program on machines and dumbbells — no injury assumed. Main lifts run a
three-week wave of 5RM / 1RM / 3RM top sets against a training max, accessories
sit at 0.75 of their own e1RM with a last-set AMRAP, and week 1 is seeded from
whatever history is on file (`src/onemore/program/programs/rebuild.py`).

`comeback`: a program for returning from a radial head fracture, not
medical advice. Opt in with `--program comeback` or `ONEMORE_PROGRAM=comeback`
— either one also switches which program `onemore serve`'s Start button
offers.

## Not affiliated

onemore is not affiliated with, endorsed by, or officially connected to
Strong, Apple, or Planet Fitness. It's an independent tool that reads a CSV
export and a health export you already have.

## Contributing

See `CONTRIBUTING.md` for the rules a pull request is checked against, and
`SECURITY.md` to report a vulnerability privately.
