# onemore — plan (2026-09-06)

Answer to the handoff brief: evaluation of wger and Liftosaur, the architecture,
the program model, and the repo layout. This file is the architecture owner;
what is built is § What is built.

The full research reports with citations are in `docs/research/`; the original
brief is `docs/BRIEF.md`. Everything marked *unverified* is a gap the
research could not close without installing something or logging in.

---

## 1. Evaluation

### Liftosaur

- **Not self-hostable in practice.** The client is a Preact PWA you can run
  locally offline-only. The backend is AWS Lambda + DynamoDB + S3, deployed with
  CDK into your own AWS account, with hand-created Secrets Manager entries and
  domain coupling to liftosaur.com. No Docker image. (README.)
- **API is premium.** REST API and MCP server need the paid tier ($4.99/mo,
  $39.99/yr, $99.99 lifetime). History comes back as a text DSL ("Liftoscript
  Workouts") you would have to parse. Free tier has manual JSON/CSV export only.
- **Single maintainer**, very active (3,344 of ~3,427 commits, pushes daily).
  AGPL-3.0. App Store 4.9★ over 386 ratings. Apple Watch app since Feb 2026.
- **As a logger:** same manual-export friction as Strong, worse UX than Strong,
  paid API. Rejected.
- **As prior art for the program DSL: excellent.** See §3. Grammars are in the
  repo (`src/pages/planner/plannerExercise.grammar`,
  `src/liftohistory/liftohistory.grammar`), evaluator in
  `src/liftoscriptEvaluator.ts`, function table in `src/liftoscriptFns.ts`,
  examples in `src/generated/liftoscriptExamples.ts`.

### wger

- **Deploy:** seven containers (web/gunicorn, nginx, postgres, redis, celery
  worker, celery beat, **powersync**). amd64 + arm64 images, ~358 MB. First
  boot needs `manage.py setup-powersync-storage`. Config is one `prod.env`.
  NAS has the headroom (x86_64, ~10 GB RAM, 7 GB free as of today).
- **Synology pain, specific:** wger must run on its own (sub)domain, not a
  subpath, and the mobile app's sync path `/ps/` needs response buffering off,
  Upgrade/Connection headers passed and long timeouts. DSM's built-in reverse
  proxy is the likely failure point; the one DSM report on GitHub (#67) closed
  without a fix. Would want Caddy or direct Tailscale-IP access. *Unverified*
  whether the iOS app accepts plain http on a Tailscale IP.
- **API:** `/api/v2/`, token or JWT, OpenAPI at `/api/v2/schema`. The 2025
  "flexible routines" rewrite (Routine → Day → Slot → SlotEntry → per-field
  config rows) is fully writable, so a generator can push a plan, but it is
  five-plus POSTs per exercise and there is no nested/bulk create. Per-set logs
  carry `weight`/`reps`/`rir` plus `*_target` twins, so planned-vs-actual is
  native. Official Python client `wger-api-client` exists. No webhooks; poll
  `workoutlog/?date__gte=`.
- **Breaking API changes every release** (2.5 removed endpoints, 2.6 moved to
  UUIDs and dropped login endpoints, 2.7 on 2026-09-03 changed session fields
  and deprecated `weightentry`). One maintainer does ~98% of commits. AGPL.
- **Data model gaps:** RiR only, no RPE; notes per session, not per set; CSV
  import/export exists for body weight only; no Strong/Hevy importer.
- **Mobile logging:** official Flutter app on the App Store with a self-hosted
  URL field. App ≥2.0.3 hard-requires PowerSync ("Sync service unreachable"
  otherwise). Offline mode since 2.6. App Store has 2 ratings; no substantive
  gym-floor UX reports found. Against the Strong bar this is the weak point.

### Strong (re-examined, because you love it)

- CSV export is free, full history every time, three taps plus the share sheet.
  So it does **not** need to happen after every workout. Export whenever you
  want the plan to adapt.
- Header (verified from real exports):
  `Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE`
  plus a 10-column "without notes" variant. Date is local `YYYY-MM-DD HH:MM:SS`,
  duration is `2h 38m`, no unit column (bare numbers in the app's unit), warm-up
  sets appear as `Set Order = W`. A semicolon/`Weight (kg)` locale variant is
  reported but not seen verbatim; detect it defensively.
- No Shortcuts action reads workouts, no URL scheme, nothing per-set in Apple
  Health. Two reverse-engineered backend clients exist; Strong asked one author
  to take his down. Not worth the account.
- Strong Pro adds nothing about data. Export is free.

### Hevy (the "later" path)

- API is Pro-only ($2.99/mo, $23.99/yr, $74.99 lifetime). `api-key` header.
  `GET /v1/workouts` paged at max 10 per page; `GET /v1/workouts/events?since=`
  is the incremental-sync primitive; a webhook fires on workout creation.
  Set shape: `{index, type: normal|warmup|dropset|failure, weight_kg, reps,
  distance_meters, duration_seconds, rpe}`. Routines are POST/PUT-able with
  exercises, sets, `rep_range`, `rest_seconds`. Exercise names must be mapped to
  opaque `exercise_template_id`s first.
- Imports Strong CSV natively. UX is the closest thing to Strong that has an
  API; reports call it "slightly busier" with a social feed.

### Verdict

Between the two the brief asked about: **wger**, because Liftosaur cannot be
self-hosted without an AWS account and its API is paid. But I would not deploy
either first. Neither logger clears the Strong bar, and the thing you would own
by self-hosting wger is a worse notebook with an API that breaks quarterly.

**Recommendation: keep Strong as the logger. Feed the repo from its CSV export
on the adaptation cadence, which is weekly, not per workout.** Make the export
a single share-sheet action into the NAS so it survives past week three:

1. Strong → Export Strong Data → share sheet → an iOS Shortcut that POSTs the
   file to a webhook on the NAS over Tailscale. Four taps, no file management.
   Fallback: share to Synology Drive and let a folder watcher pick it up.
2. Full-history export + idempotent dedupe on
   (date, workout name, exercise, set order) means a missed week costs nothing.

If that cadence fails in practice, the upgrade is **Hevy lifetime**, not wger:
same shape of app as Strong, API + webhook, Strong importer for history. wger
stays the "zero subscriptions, total ownership" option and the adapter layer
keeps it reachable. Liftosaur is prior art only.

### The open question: who owns the program?

**The repo owns the program. The logging app is a notebook.**

- Adaptation rules must be inspectable and versioned. That means code in a
  repo with tests, not progression settings inside an app.
- Every candidate app can *display* a routine. Only Liftosaur can *run* rules.
  Keeping rules in the repo is what makes the app swappable.
- With Strong there is no routine push at all: the repo renders the week and
  you read it off a phone-sized page while logging in Strong, exactly the
  college-spreadsheet workflow. Hevy/wger adapters add `push_plan` later.
- Consequence: in-workout autoregulation (Liftosaur's `update:` blocks) stays
  in your head. The engine implements only post-workout, block-level rules
  (Liftosaur's `progress:`), evaluated when an export lands. That is the right
  granularity for a rebuild program anyway.

---

## 2. Architecture

```
  Strong CSV ─┐                                        ┌─ CLI: plan / status / explain
  Hevy API  ──┤  sources/   →  canonical  →  store   ─┤
  wger API  ──┤  (adapters)     model        (sqlite)  ├─ engine: estimate → rules → next week
  Health Auto Export JSON ┘  (optional enrichment)     └─ outputs: phone card, Hevy/wger push
```

### Canonical model (`onemore/model.py`)

- `Session(id, source, source_key, started_at, duration, notes, bodyweight?)`
- `ExerciseEntry(session, exercise_id, order, notes)`
- `Set(entry, index, set_type: work|warmup|drop|failure, weight_kg, reps,
  rpe?, rir?, completed, source_ref)`
- `Exercise(id, name, aliases{source: name}, movement pattern, muscle groups,
  is_main_lift)`. Aliases are a data file; Strong's `Bench Press (Barbell)`,
  Hevy's template id and wger's exercise id all resolve to `bench_press`.
- `Prescription` and `Adjustment` (see §3) are stored too, so planned-vs-actual
  and the rule audit trail live in the same DB.
- Store kg internally, render in the user's unit. Rounding to plates happens
  only at render time.

### Sources (`onemore/sources/`)

```python
class Source(Protocol):
    name: str
    def fetch_sessions(self, since: datetime | None) -> Iterable[Session]: ...

class Sink(Protocol):            # optional capability
    def push_plan(self, week: RenderedWeek) -> None: ...
```

- `strong_csv.py` — parses all header variants, sniffs delimiter, takes the
  unit from config, maps `W` set order to warm-up, drops `Rest Timer` rows (a rest,
  not a set), dedupes on the natural key.
  Used for the one-time history import **and** the ongoing weekly feed.
- `hevy.py` — `workouts/events?since=` polling plus the creation webhook;
  implements `Sink` via `POST /v1/routines`. Written against the Swagger spec
  now, exercised only when a key exists.
- `wger.py` — `workoutlog/?date__gte=`; `Sink` via the routine/day/slot/config
  POST chain. Stub until wger is actually deployed.
- `apple_health.py` — accepts Health Auto Export's JSON (metrics and workouts)
  on `POST /import/health` or from a file. Every reading becomes a `Metric`
  row; `vitals.py` turns them into latest / 7-day / 28-day rows for `status`
  and a one-line header on the plan. Enrichment only, never required. Format
  verified against the vendor's pages 2026-09-06
  (`docs/research/strong-data-out.md` § Apple Health).
- `apple_health_xml.py` — the Health app's own "Export All Health Data" zip,
  no third-party app needed. A streaming parse of `export.xml` (1.1 GB, 2.3 M
  records for a first export) that keeps bodyweight, body fat, lean mass,
  resting HR, HRV, VO2 max, respiratory rate, daily steps (largest source per
  day, since phone and Watch both count), one sleep row per night from the
  stage intervals, and the strength workouts' HR and calories — computed from
  raw samples where the older Watch workouts carry no statistics. Same metric
  names as the JSON path, so `onemore import-health` takes either by extension.
  The same zip also POSTs to `/import/health` straight from the share sheet, which
  is how it is fed: the request answers 202 and the parse runs on a worker thread,
  because it is far longer than a phone will wait (`DEPLOY.md` § 6). No app and no
  subscription — Health Auto Export's JSON remains a second, paid way in.

### Estimation (`onemore/estimate.py`)

- e1RM per set: Epley for reps ≤ 10, RPE-adjusted via an RPE → %1RM table
  (Liftosaur's `rpeMultiplier`) when RPE is logged.
- Rolling e1RM per lift: best e1RM from work sets over the last 21 days.
- Training max = 0.9 × rolling e1RM (5/3/1 convention).
- **Cold start (no current maxes):** week 1 is the seeded week. `onemore start`
  seeds every program lift's e1RM from its historical best, decayed ×0.8 past
  180 days; week 1 prescribes off that e1RM with a 5+ top set, and
  `calibrate_tm` sets the TM from what the top set actually did. Percentages of
  TM start in week 2. § The seeded week and the ceiling. A main lift that joins a
  running plan (comeback's machine pulldown, 2026-09-21) is calibrated the same way
  from its first work week by `calibrate_new_lift`. Until then the page shows a
  render-only provisional TM, the same 0.9 × best e1RM from the 21 days before the
  week (`engine.provisional_tms`); with nothing logged in that window it stays blank.

### Engine (`onemore/engine.py`)

`advance(program, state, history) -> (next_week_plan, adjustments)`. Pure
function over stored data; the CLI and the web service both call it. Every
`Adjustment` records rule name, lift, field, old → new, and the set ids that
were the evidence. `onemore explain --week N` prints them.

### Deploy

Python 3.13, uv, src layout, pytest, ruff (house conventions). CLI first.

The HTTP service — webhook ingest plus the week as a phone page — runs as a
container on a home server, bound to loopback and reached only over a private
network from the phone: the inbound localhost proxy is what makes it reachable
from nowhere else. Procedure, `.env` keys and the iOS Shortcut: [DEPLOY.md](DEPLOY.md).

**There is no Dockerfile, and that is the design.** `dependencies = []` and a
stdlib-only `web.py` mean stock `python:3.13-slim` plus `PYTHONPATH=/app/src` *is*
the image, so nothing holds the code: the deploy clone is mounted read-only and
a sync script pulls it and recreates the container. Adding a dependency ends
that and needs a real `build:`. SQLite and the archived imports live outside
the clone, since the sync force-resets it on an interval, and are on the
regular backup list. The compose entry, the sync line and the two backup lines
are in a separate deploy repo, outside this one.

---

## 3. Program model

### What to take from Liftoscript

- Prescribed arrays vs completed arrays (`reps` vs `completedReps`) as
  first-class, side by side.
- Per-exercise persistent state (`rm1`, counters) that rules mutate.
- Two hook points: post-workout `progress:` and intra-workout `update:`. We
  implement the first only (see §1).
- Load expressed as `%` of a state variable, absolute, or `@RPE`; `+` for
  AMRAP; set variations for stage-cycling (GZCLP's 5x3 → 6x2 → 10x1).
- Reuse across weeks by restating only what changed.
- Plate-aware rounding as a library function, not baked into rules.

### What not to take

Liftosaur needs a *text* DSL because users edit programs inside an app. We
have one user and a repo, so **programs are Python modules** built from a small
set of dataclasses. Rules are plain functions with a docstring and a `reason`.
No parser to maintain, and pytest is the inspector.

### The program as written

`src/onemore/program/programs/rebuild.py` was the first program — **retired 2026-09-21**,
superseded by `comeback` (§ `comeback` supersedes `rebuild`) and carrying the Epley ratchet
fault in its accessories; it survives in git history. Its design, in outline:

- `Sets(n, reps | (lo, hi), load, amrap=False)` renders to concrete loads.
  `load` is one of `Pct(x, of="tm"|"e1rm")`, `Rpe(x)`, `Abs(kg)`, `Bodyweight`;
  `rebuild` uses only `Pct` and `Bodyweight`.
- Thirteen weeks: the seeded week, then three blocks of three work weeks and a
  deload. `Program.week()` cycles the body after that.
- Main lifts run the DUP sheet's wave: 5RM / 1RM / 3RM top sets at
  85 / 95 / 90 % of TM with 4x12 / 4x4 / 4x8 backoffs at 65 / 85 / 75 %,
  the two days of a twice-weekly lift phase-offset,
  and +1.5 / +1.0 points per block as template progression. The sheet's
  percentages were of a true 1RM; against a TM of 0.9 × e1RM they start about
  ten percent more conservative, deliberately, and `tm_progress` closes the gap.
- Accessories are a rep range at a fraction of the lift's own e1RM with the
  last set AMRAP; `e1rm_refresh` is their progression.
- Every set carries a rest (`Sets.rest_s`: 3:00 after a top set, 2:00 backoffs,
  1:15 accessories) and every top-set slot a warm-up ramp (`Slot.warmup`:
  50 / 70 / 85 % of the top set for 8 / 5 / 3), Liftoscript's `warmup:` with
  percentages of the first working set. The renderer rounds the ramp on the
  lift's step and drops a rung that rounds to nothing, repeats the previous one
  or reaches the working load. Logged as warm-up sets in Strong they are
  invisible to every rule.

### Initial rule set (all explicit, each emits an Adjustment with evidence)

This table matches `src/onemore/rules/`, in `DEFAULT_RULES` order (`rules/__init__.py`); it
replaces the design-time sketch this section originally held. `calibrate_tm` and
`calibrate_new_lift` share one factor, `LiftSpec.tm_factor` (0.9 by default); `tm_progress`
is one function emitting four different adjustment names depending on outcome.

| Rule | Fires when | Effect |
|---|---|---|
| `e1rm_refresh` | any lift's best work set in the rolling 21-day window changes its estimated max | sets the lift's rolling e1RM |
| `missed_week_repeat` | fewer than 2 of the planned days logged (each session matches at most one planned day: the one whose main lift it reaches first) | repeat the week, do not advance |
| `calibrate_tm` | the seeded (calibration) week closes | TM = tm_factor × that week's best e1RM |
| `tm_progress` | all top-set reps hit and AMRAP ≥ target + 2 | TM += lift's load step |
| `tm_hold` | reps hit, AMRAP < target + 2 | TM unchanged, note why |
| `tm_reduce` | top set missed two weeks running; a week whose top-set day was not logged is not judged | TM −10% |
| `tm_pain_hold` | top set short of target and the week's Strong note on the lift says it hurt | TM unchanged; not a miss, streak untouched |
| `calibrate_new_lift` | a main lift with no TM is trained in a work week (it joined a running plan after the seeded week) | TM = tm_factor × that week's best e1RM, same as `calibrate_tm`; runs after `tm_progress` so the same week is not also judged |
| `e1rm_ceiling` | TM > rolling 21-day e1RM | TM clamped to the e1RM (the clamp is 1.0 × e1RM, not 0.9× — § The seeded week and the ceiling) |
| `dumbbell_ceiling` | load cannot rise — rack or stack is at its known ceiling and every set there hit the prescribed rep range | +1 rep, then (past `REP_CAP`) converts to +1 set; a TM above the ceiling is clamped down to it |
| `accessory_volume` | mean logged RPE on a non-main lift > 9 two weeks running / < 7 two weeks running | −1 / +1 set, bounded; almost always silent — 3 of 2532 logged sets carry an RPE (§ RPE is not logged) |
| `deload_after_reductions` | `tm_reduce` cut two or more main lifts' TM in the same week | inserts a deload before continuing |
| `recovery_deload` | Apple Health resting heart rate: this week's mean sits `ONEMORE_RHR_THRESHOLD` (default +5.0 bpm, measured) above the 28-day mean | inserts a deload; silent before week 4, in a deload week, or with fewer than 4 daily readings in the closing week |

### Rendering a week

`onemore plan --week 5` prints per day, per slot: exercise, sets × reps, load
rounded on the lift's own step, the rest, the warm-up ramp, the rule notes that
changed anything since last week, and the previous session's actuals for that
slot. A vitals line (bodyweight with its 7- and 28-day means, resting HR,
sleep) heads the week when Health data has landed. The same renderer feeds
`/api/week`, which the web app draws (README § Web app).

---

## 4. Repo layout

```
onemore/
  pyproject.toml            uv, python 3.13, ruff, pytest
  CLAUDE.md  README.md  PLAN.md (this file)
  src/onemore/
    model.py                canonical dataclasses
    store.py                sqlite, idempotent upsert
    exercises.py + exercises.toml   catalog and per-source aliases
    sources/
      base.py               Source / Sink protocols
      strong_csv.py
      hevy.py  wger.py     planned (build order step 5); not written
      apple_health.py       Health Auto Export JSON
      apple_health_xml.py   the Health app's own export zip / export.xml
    vitals.py               latest / 7-day / 28-day summary of the metrics table
    estimate.py             e1RM, training max, RPE table
    program/
      spec.py               Program / Week / Day / Slot / Sets / loads
      render.py             per-exercise rounding, text + HTML week
      programs/rebuild.py    the shipped default (retired 2026-09-21, restored 2026-09-28)
      programs/comeback.py   opt-in via ONEMORE_PROGRAM=comeback (§ `rebuild` restored)
    rules/
      base.py               Rule protocol, Adjustment, Context (carries the catalog)
      progression.py  volume.py  schedule.py  ceiling.py
    engine.py               advance()
    cli.py                  onemore ingest | plan | status | explain
    web.py                  JSON API + webhooks; serves static/ (the app)
    static/                 index.html app.js app.css — no build step, no CDN
      pale.css              the Pale design tokens (docs/design.md); app.css uses only these
      fonts/                the three faces those tokens name, vendored — the CDN rule wins
  scripts/                  analyses against the real export; never tests
    derive_increments.py    per-exercise load steps from every logged load
    replay_rules.py         replay the rules over the imported history, read-only
  tests/
    fixtures/strong_12col.csv  strong_10col.csv  hevy_workout.json
  docker/Dockerfile  compose.yml   planned (build order step 4); not written
  data/                     gitignored: onemore.db, imports/ (Strong CSVs, the Health zip)
```

### Build order

1. **Strong import + store + `onemore status`.** Needs one real export from
   your phone. Validates the CSV variant and gives e1RM history per lift.
2. **Program spec + renderer + calibration week.** `onemore plan --week 1`.
3. **Rules + `explain`.** Replay against the imported history to check the
   rules fire the way you expect before they touch a live plan.
4. **Webhook ingest + phone page, NAS container.** iOS Shortcut on the phone.
5. **Hevy adapter** when and if a key exists; wger adapter if ever deployed.

### Direction questions — answered 2026-09-06

**What the export showed.** 224 sessions, 2022-05-16 to 2025-01-03, almost
entirely machines and dumbbells: leg press, machine shoulder press, machine
curls, dumbbell bench, lat pulldown, chest press. Barbell squat, bench,
deadlift and overhead press do not appear at all; the only squat and deadlift
rows are Smith-machine, 16 sets each.

1. **Equipment: Planet Fitness.** No barbells, no squat or power racks, no
   platforms. Smith machine, selectorized machines, dumbbells (typically to
   60–80 lb), cardio. No chalk, no dropping weight.
2. **Starting point: dissolved by 1.** The 2022–2025 history is on this same
   equipment, so it is representative rather than a gap — it seeds the
   movements the program will actually use.
3. **Export cadence: still open**, and the only one left. § Client below.
4. **Days per week: 4.** Provisional — "4 sounds fair", not a commitment, so
   the spec keeps 3 reachable.

**Consequence: the draft `rebuild` program is dead.** It is built on barbell
squat / bench / deadlift / press, none of which exist at Planet Fitness. The
program, the exercise catalog and the `Lift` increments are rebuilt around
Smith and selectorized movements. Estimation and the rule engine are
unaffected — they only ever read sets, reps, load and RPE.

What that changes, concretely:

- The main lifts become machines, not the Smith — see § Which movements are
  main. The Smith bar's tare varies by machine and is a per-branch catalog
  field, not a rule.
- Dumbbells step by the rack (usually 5 lb) and stop where the rack stops;
  machines step by the pin. Both are catalog data, per exercise, not constants.
- `dumbbell_ceiling` is the new rule the equipment forces: when load cannot
  rise, progress becomes reps and then sets, never a load bump. It fits the
  existing contract as-is — `Adjustment.field` is a free string, so `sets` is
  as expressible as `tm`, and the reps-then-sets counter lives in the per-lift
  state `Context.states` already carries.
- e1RM on a Smith or a machine is never compared to a barbell e1RM, only to
  itself over time. The `e1rm_ceiling` clamp still applies within a lift.

### Client — no native iOS app (decided 2026-09-06)

Strong stays the logger; the repo renders the week to a read-only home-screen
PWA over a private network (build order step 4). The toolchain is not the
reason: EAS Build compiles and signs iOS on hosted macOS workers, so no Mac is
needed and there is none in the house. The reasons are that a $75 Hevy lifetime buys the same
escape from the weekly export ritual, and the two things native would add — a
rest timer that fires with the screen off, and a Watch app — are wants, not
needs, for a program that adapts weekly.

### What is built (2026-09-06)

- **Verified, tested:** Strong CSV parser (all three header variants plus the
  `1,301h 4m` unquoted-thousands duration row seen in the real export), SQLite
  store with idempotent import, e1RM / RPE-table estimation.
- **Equipment-correct and tested (2026-09-06, second pass):** the exercise
  catalog, per-exercise load steps and rounding, `dumbbell_ceiling`, and the
  engine's guard against unpersisted rule state.
- **The `rebuild` program (2026-09-06, third pass; retired 2026-09-21):** machine main lifts, the
  DUP wave and block creep, no RPE anywhere, and a seeded first week — § The
  program as written. Tested for shape (`tests/test_rebuild.py`), and the
  progression rules and `advance()` now have tests of their own
  (`tests/test_progression.py`, `tests/test_engine.py`), which is what found the
  three defects in § The seeded week and the ceiling. `onemore plan` still warns
  about any prescribed lift the gym does not have; for `rebuild` the list is empty.
- **Rest, warm-ups and Apple Health (2026-09-06, fourth pass):** rest and ramps
  in the spec and renderer; the Health Auto Export adapter, the native Health
  export parser, the `metrics` table and the vitals summary, all tested on
  synthetic exports and the native one run against a real 1.1 GB export
  (§ What the Health export showed).
- **The recovery rule (2026-09-07, sixth pass):** the export cleared the
  precondition above — 1,784 resting-HR readings over 1,776 days — so
  `recovery_deload` is written: a week whose mean resting HR sits +5.0 bpm above
  the 28-day mean sets `deload_next`. The threshold is the 92nd percentile of
  the weeks actually trained, not of all 274 — measuring against every
  week, trained or not, made +4.0 look twice as rare as it is
  (`scripts/recovery_threshold.py`). Sleep and HRV were the obvious inputs and are
  not usable — the watch is not worn to bed, so HRV is waking spot checks. The
  rule is silent before week 4, in a deload week, and whenever the closing week
  holds fewer than four daily readings; the windows are the training week's, so a
  Health export must land before Advance to be read.

- **The web app (2026-09-06, fifth pass):** `web.py` grew from the one phone page
  into a JSON API over the engine and a static single-page app (README § Web
  app), tested over HTTP on a synthetic machine-lift fixture
  (`tests/test_web.py`, `tests/fixtures/strong_machines.csv`) and looked at
  against the real database at phone and desktop widths in both themes. Writes
  (import, start, advance) sit behind the same token as the webhooks.
- **Not started:** the Hevy / wger adapters (build order step 5). The NAS
  container and the iOS Shortcut that feeds it are done (`DEPLOY.md`). Nothing
  in the plan has yet seen a live training week.

#### The equipment pass, concretely

- **The catalog is the sole owner of load arithmetic.** 64 entries, every one
  carrying `equipment`, `step_lb` and `available`; all 47 previously unmapped
  Strong names resolve, so `onemore status --unmapped` is empty against the real
  export. An import re-resolves the ids of sessions it already holds
  (`Store.remap_exercise_ids`), or a catalog edit never reaches the history —
  the import skips a session it has seen, so the ids would stay frozen at
  whatever the catalog said that day. `LiftSpec.inc_kg` defaults to None meaning "the catalog's step", and
  `Config.fallback_step_lb` is only what an exercise with no catalog step falls
  back to — there is no global rounding constant.
- **The steps are measured from the export**, not assumed: each is the modal
  difference between an exercise's consecutive distinct logged loads. Leg press
  5 lb, machine curl 2.5, pulldown 10. Method, per-exercise numbers and every
  merge between two Strong names: `scripts/derive_increments.py`.
- **`ceiling_lb` is set only for the dumbbell rack, `smith_tare_lb` nowhere.**
  A machine's heaviest logged load is a floor on its stack top, not the stack
  top; Strong logs a Smith's added load, and the bar's counterweight varies by
  machine. Both are gym errands — read the stack tops, weigh the bar — and until
  they are done `dumbbell_ceiling` stays silent on machines rather than stalling
  a lift with room left, and a Smith e1RM compares only to itself.
- **`dumbbell_ceiling` adds reps, then a set, never load**, and each rung is
  earned at the rep range the plan actually printed. It reads the catalog
  through `Context` (`ctx.step_kg`, `ctx.ceiling_kg`) and writes a `reps_delta`
  the renderer applies — a rule whose state nothing reads is a plan changed
  silently.
- **A rule may only write state in `engine.PERSISTED_STATE`**; `_apply` raises
  otherwise, naming the rule and the field.

#### Replay against the real history

`scripts/replay_rules.py` walks the 224 imported sessions a week at a time and
prints every `Adjustment` with its evidence. It is a read-only dry run over an
in-memory copy, and it is a script rather than a test because tests use the
synthetic fixtures and never the real export.

138 weeks replay without an error. What it showed:

- `dumbbell_ceiling` never fires on this history, and should not: the heaviest
  dumbbell bench ever logged is 50 lb against an 80 lb rack.
- `accessory_volume` never fires: 3 of 2532 sets have an RPE. The rule is
  documented to stay silent without RPE rather than guess, and it does. **This
  is a live constraint on the program** — every RPE-prescribed accessory
  depends on RPE actually being logged in Strong.
- `missed_week_repeat` fires in all 138 weeks, so nothing downstream is ever
  reached — hence the script's `--ignore-missed` diagnostic flag. Mostly the
  replay scaffold, which assigns one main lift per day where the real sessions
  are machine circuits hitting several at once. Worth a look anyway: the rule
  counts *distinct planned days whose main lift was trained*, which undercounts
  a week where one session covers three of them.

### Which movements are main — machines (decided 2026-09-06)

The § Direction questions answers pointed at Smith squat / bench / OHP / RDL.
The export does not support them: Smith squat 4 sessions / 15 sets / best 60 lb
and last touched 2024-04, Smith deadlift 5 sessions all in 2022, Smith bench 1.
Against leg press 49 / 165 / 280 lb, machine shoulder press 47, lat pulldown 45,
leg curl 44.

A main lift needs a load history, because its training max is seeded from that
history and then progressed off the top set's reps. On the Smith there is none
to seed from, and the stall rules would be firing on noise. So the machines
carry the load. **The Smith squat stays as an accessory with its own slow
progression** — it is the one pattern the machines do not give, it costs
nothing to carry, and `main_lifts()` is program config, so promoting it once it
has a history is a one-line change.

The objection that machine strength is a leverage artifact does not bite here:
`rolling_e1rm` only ever compares a lift to itself, on one machine, and nothing
in the engine compares across machines.

### The seeded week and the ceiling (decided 2026-09-06)

Writing the layouts without RPE exposed a gap the earlier sections left open:
week 1 existed because there is no training max yet, and it was prescribed by
RPE because there was nothing else to prescribe by. Now:

- **Week 1 is seeded, not calibrated by feel.** `onemore start` runs
  `seed_from_history` over every lift in the program — accessories too, since
  they are prescribed off their own e1RM — taking each lift's best historical
  e1RM at face value inside 180 days and ×0.8 beyond. The last logged session is
  2025-01-03, so today everything is decayed. Week 1 prescribes the main lifts at
  72 % of that e1RM for a 5+ top set (0.8 × the TM the e1RM implies) and
  `calibrate_tm` sets the TM at 0.9 × whatever e1RM the top set actually
  produced. A flat 0.8 for twenty months off is a guess; the point of the AMRAP
  is that it only has to be a safe one, because the TM is re-derived from the
  set a week later.

- **The e1RM ceiling is the e1RM, not 0.9 of it.** Writing the engine test
  showed the 0.9 clamp from § Initial rule set undoing every earned step:
  calibration puts the TM at exactly 0.9 × e1RM, and a 5+ at 85 % of TM that
  beats its target by two implies, by Epley, an e1RM *below* the one it was
  prescribed from (85 % of TM is 76.5 % of e1RM, a nine-rep load, so seven reps
  reads as a worse day). With the clamp at 1.0 the TM has the ten percent of
  headroom calibration built in and the ceiling fires only when reps fall while
  the TM climbs — the runaway guard it was meant to be.

- **The rolling e1RM really is rolling now.** `e1rm_refresh` documented a
  21-day window and read only the week's sets. The engine now hands rules the
  previous 21 days as `Context.history`, so a week whose top set is a heavy
  single does not re-derive the max from the single. Rules judging *this
  week's* performance still read only the week.

- **`tm_progress` judges the heaviest prescribed top set.** With two
  phase-offset days the week holds two AMRAPs at different loads and targets;
  the heaviest logged set is compared to the heaviest prescribed one's target.
  A week whose heaviest set sits more than a load step under that prescribed
  load is a miss whatever its reps — a skipped top set must not let four
  backoffs of twelve read as progress.
- **A set stopped for pain is not a miss (2026-09-21).** `comeback` tells the
  lifter to end a set when the elbow hurts; counting that as a miss would cut
  the TM for following the program. The only place a logged set can say why it
  stopped is Strong's per-exercise note, so `tm_progress` reads it for pain
  words (`PAIN_WORDS`). First case: week 2's shoulder press, 50 lb x4 against a
  target of 10, noted "began to hurt", applied as a miss before this existed.

### RPE is not logged, so nothing may read it (decided 2026-09-06)

Three of the 2532 imported sets carry an RPE, and the author does not use the term.
A program cannot depend on a signal that is not in the data and would be guessed
at if demanded, so the dependency goes rather than the habit changing.

Everything RPE-prescribed moves to percent-of-TM plus a last-set AMRAP: a rep
count, which Strong records on every set, feeding the same progression. Done in
`rebuild` (main lifts off TM, accessories off their own e1RM, the seeded week
off the decayed historical e1RM). `accessory_volume` stays in the rule set,
reads nothing but RPE, and fires zero times across the 138 replayed weeks; it
wakes up only if RPE ever gets logged. `Rpe` stays in the DSL — the estimator's
RPE table is how a logged RPE becomes an e1RM, and that is still right for the
sets that have one.

### `comeback` supersedes `rebuild` (decided 2026-09-06)

A left radial head fracture, nonoperative and cleared for a gradual return, makes
`rebuild` the wrong program: it prescribes pressing, curls, triceps isolation and a loaded
Smith bar without reference to an elbow. `comeback` is the program for that return.
The clinical reasoning, the biomechanics with citations and every movement kept or dropped
because of them are in `docs/research/radial-head-return.md`; the design note is the
module docstring, per the § What not to take convention. In outline:

- **Two speeds in one program.** The legs are uninjured, so `leg_press` and `leg_curl`
  run a real 8/5/3 wave; the four upper machines run one fixed light scheme. `rebuild`
  couples them and cannot express this.
- **The upper lifts are main lifts anyway**, which is not obvious — see below.
- **Block 1 is five weeks and ends on a scheduled clinical re-evaluation.**
  Upper-body block 2 is deliberately unwritten rather than planned across a scheduled
  reassessment.
- No template creep, no maximal singles, no direct arm work, and a printed
  stop-short-of-lockout note on every press slot.

#### The Epley ratchet — a defect in `rebuild`, found while writing this

`estimate.e1rm` returns `None` above 12 reps, so the best e1RM a single set at `f × e1RM`
can measure is `f × e1RM × 1.4`. That beats the stored e1RM only when **`f > 0.714`**.
Every `rebuild` accessory is prescribed at 0.60–0.70, so `e1rm_refresh` can only ratchet
those lifts *down* — the load shrinks, lagged by the 21-day best-of window, indefinitely.
Only `smith_squat` at 0.75 can rise. Reproduced with `estimate.e1rm` directly; asserted in
`tests/test_comeback.py::test_epley_ratchet_floor_is_what_the_docstring_claims`.

Consequences, all of which shaped `comeback` (`rebuild` was never fixed; it was retired
2026-09-21 instead):

- **Accessories belong at 0.75**, where twelve reps measure 1.05 and eight measure 0.95,
  so the slot self-corrects instead of decaying. `comeback` uses 0.75 throughout and a
  test enforces a 0.71 floor.
- **An accessory-shaped upper body cannot progress at all**, which is why the upper
  machines here are main lifts driven by `tm_progress` (rep counts, never Epley) rather
  than the accessory path that would otherwise be the natural way to hold them back.
- **The same arithmetic sets a floor on top-set percentages.** `e1rm_ceiling` clamps the
  TM to the rolling e1RM, so a top set at `f × TM` with `TM = 0.9 × e1RM` needs
  `f × 0.9 × (1 + reps/30) > 1`, i.e. `f > 0.79` at 12 reps. The upper top set is 0.82 —
  a "safer" 0.70 would have decayed the e1RM and let the ceiling eat every earned step,
  which is § The seeded week and the ceiling recurring at a different percentage.
  **Safety comes from the calibration seed, not the percentage:** week 1 prescribes the
  upper lifts at 0.50 of the decayed historical e1RM, and `calibrate_tm` turns whatever
  that light AMRAP actually does into the TM everything after it hangs off.

Verified by driving `advance()` over five synthetic weeks: the TM is monotone
non-decreasing at one catalog step per week per lift, and `e1rm_ceiling` fires only as a
1–2 lb trim rather than clawing steps back. Rendered against a copy of the real database;
`unavailable()` is empty.

### `rebuild` restored as the shipped default (2026-09-28)

The retirement above stood until the public-release plan (`docs/public-release-plan.md`
§ Phase 3) pointed out that a release whose only program assumes the reader's injury helps
nobody. `rebuild` is restored from before 3cdf86d with its accessories moved to 0.75 of
their own e1RM — the same fix § The Epley ratchet gave `comeback` — and registered as
`SHIPPED_DEFAULT` in `src/onemore/program/programs/__init__.py`. `comeback` is not gone: it
stays in `PROGRAMS`, and `ONEMORE_PROGRAM=comeback` (or `--program comeback`, or
`onemore start --program comeback`) selects it, including for `onemore serve`'s Start
button. A plan already stored under one program name keeps loading under that name either
way — `default_program()` only fills in a name when none was given. `rebuild`'s exercise
selection is unchanged from the version retired above; only the accessory percentage moved.
