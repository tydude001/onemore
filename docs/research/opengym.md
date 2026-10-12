# openGym, and other 2026 self-hosted loggers — research report (2026-10-12)

Agent-gathered from GitHub (API metadata, READMEs and the source files named below).
Nothing was installed or run. A project's own claims are marked as such.

## Why this matters to onemore

onemore is not a logger: Strong stays the app you log in, and onemore reads its export
and writes next week's program (README). A new logger is therefore relevant in three
ways: as a possible *replacement for Strong* (the logging UX, judged against Strong's),
as a possible *feed* in place of the Strong CSV, and as prior art for the parts onemore
does own — reading a Strong export, and progression rules.

## openGym

<https://github.com/DuarteSantos8/openGym>, read at `5ec23d3` (2026-10-12).

**What it is.** A self-hosted gym and body-weight tracker: plan routines (per weekday or
as an A/B/C rotation), run guided workouts with a rest timer and pre-filled loads, log
sets, see PRs, e1RM curves and a muscle map. Multi-user with passkeys, synced across
devices, installable as a PWA, plus a Capacitor build for Android (signed APK, not on the
Play Store) and a build-it-yourself iOS app. — README.

**Stack and hosting.** React 19 + Vite (React Router, Zustand) frontend; the API is
plain `node:http` with two dependencies (`@simplewebauthn/server`, `web-push`); nginx
serves the build and proxies `/api` so passkeys get one origin. Storage is JSON files
under `./data`: `db.json` (profiles, public passkey data) and one `state-<user>.json` per
user holding plan, workouts, body weight and settings. Docker Compose with prebuilt
amd64/arm64 images on GHCR and GitLab. Passkeys need HTTPS on a real hostname
(`RP_ID`/`ORIGIN`). OpenAPI spec at `api/openapi.yaml`. — README.

**Sync** (README, "How sync works"): each profile is one document with a server
revision; a stale write gets a 409 plus the current document, and the client merges
field by field using per-field stamps, so the newest edit of each field wins and
deletions stick.

**Importers** (`frontend/src/lib/import-csv.js`, `docs/DATA_IMPORTS.md`). One CSV parser
for FitNotes (Android and iOS), Strong, Hevy and Gravl, detected by header (Strong =
`exercise name` + `set order`), with a generic header-alias table for anything else; Hevy
Pro also by API key. Apple Health `export.xml` for body weight only. Points of contact
with onemore's `sources/strong_csv.py`:

- Both sniff `;` vs `,` (openGym from the header line only, onemore with `csv.Sniffer`).
- openGym's code comments describe a *newer* Strong export that writes the workout's
  length as seconds in a `Duration (sec)` column and adds a `Workout #` session-number
  column (`durationSec` alias; the `#`→`no` header normalisation). onemore's docstring
  lists three variants, none with those headers. With them the duration would be lost
  before `parse_duration` is reached: `_header_map` strips only `(kg)`/`(lb)` suffixes, so
  `Duration (sec)` never maps to `duration`. **Not seen here:** all 11 exports the live app
  has saved, the newest from 2026-10-02, carry the old 12-column header. Re-check when a
  fresh export arrives; the fix would be a header alias, not a parser change.
- Session identity: openGym keys a Strong session on date + start time + workout name
  (its issue #505: two sessions on one day had merged); onemore keys on
  (Date, Workout Name), where Strong's `Date` already carries the start time
  (`2022-05-16 17:58:27`), so the merge in #505 cannot happen here.
- Ids of imported sessions are a hash of what they are (`importId`, cyrb53), so the same
  file imported on two devices before they sync merges to one copy. Re-import skips days
  that already hold a workout.
- Unit handling per row (lb→kg only where a row disagrees with the profile), and
  hostile-input tests (`import-csv.hostile.test.js`).

**Progression** (`frontend/src/lib/progression.js`). Named per-routine or per-exercise
policies: off, linear, Greyskull LP, double, triple (reps, then sets, then load), and
add-time. The next target is a pure function of history, recomputed whenever needed; no
counters are stored. A set not checked off, or fewer sets than prescribed, is a miss.
Deload after N misses (3; 1 for Greyskull) by a factor of 0.9 (configurable 0.5–0.95),
snapped to the dumbbells the user owns. The app shows the rule and the reason for every
target — the same stance as onemore's `Adjustment` with evidence, arrived at
independently. It is single-session and per-exercise: no multi-week program, no
training max, no AMRAP-driven TM.

**Muscle map / fatigue** (`frontend/src/lib/recovery.js`, `docs/dev/FATIGUE_SETS_MODEL.md`).
Three modes: volume, recovering, and detrained. Fatigue v2 counts *effective hard sets*
per muscle (secondary movers 0.4, capped at 12 per session, 8 sets = one unit), weighted
by `(load / session best)^1.5`, decayed with a per-muscle half-life — 24 h arms,
shoulders and core; 30 h chest and upper back; 48 h legs and lower back — and squashed
by `1 − exp(−v)`, with "fatigued"/"recovering" thresholds at 0.5/0.25. The design note
cites its sources and keeps two invariants under a probe script: rest never raises
fatigue, and deleting a workout never raises it. "Detrained" uses a separate strength
curve (full for 14 days, then a 28-day half-life to a 0.5 floor). These are modelling
choices, not measurements.

**Other features** (README claims, not checked in code): ~5,600 exercises with animated
demos, plate math including the Smith machine, per-side reps, RIR or RPE column, edit
history after the fact, progress photos, 19 languages, an opt-in AI coach (own provider
key) and a read-only local MCP server.

**Licence.** AGPL-3.0 for the code, with a CLA that lets the maintainer relicense. The
exercise stills and animations are **not** open: © Gym visual, licensed for openGym only
(README § License).

**Health.** Created 2026-07-18; 10.3k stars and 1.26k forks within twelve weeks; 126 open
issues; last push 2026-10-12 (all as of 2026-10-12). Releases every few days to two weeks (v1.4.1 on
2026-10-10). 75 contributors, but the owner has 1,297 commits against 96 for the next. The
README states the code is largely drafted with Claude Code. Its own roadmap table is
already stale (lists v1.4.0 for November; v1.4.1 is out).

### Against Strong, as the logger

Not judged here — that takes the phone. On paper it covers what onemore relies on Strong
for (per-set logging, warm-up/drop sets, notes, rest timer, a JSON export) and adds what
Strong lacks (self-hosting, an API, progression rules). Two catches for this setup: on
iPhone it is a PWA or a self-built Xcode app, not an App Store app, and the README
mentions no Apple Watch app. Strong's watch app is one of the reasons its users give for
staying (`strong-data-out.md` § 5).

### As a feed for onemore

Possible later, not now. Its per-user `state-<user>.json` and the JSON export hold
per-set history, and the API has a published OpenAPI spec, so a `sources/opengym.py`
would read a documented format rather than a CSV. But onemore's rules write state the
renderer shows; openGym would keep computing its own targets beside them, so two
progression engines would disagree on screen. Only worth doing if openGym replaces
Strong as the logger.

### Borrowable

- **Check the newer Strong headers** (`Duration (sec)`, `Workout #`) against each fresh
  export, and add them to the adapter's known variants if they appear (none by 2026-10-02).
- **Hostile-input tests** for the Strong adapter, as openGym has
  (`import-csv.hostile.test.js`). Import-twice is already covered
  (`test_store_import_is_idempotent`).
- **A per-muscle weekly hard-set count** on the week view, from the catalog plus a
  primary/secondary muscle map, as display only. The decayed fatigue score is a model of
  a model; onemore's rule for readiness is `recovery_deload` on measured resting HR, and
  the set count is the part that needs no constants.

Ideas only: openGym is AGPL and onemore is MIT, so no code or data files (the
exercise→muscle JSON included) are copied.

### Verdict

The most complete self-hosted logger found so far, and the first with a Strong importer
and a progression engine in the same app. It does not change onemore's design: the
program model (multi-week, TM-based, catalog-rounded, rules with evidence) has no
counterpart there. It is the strongest candidate yet if Strong ever has to be replaced
as the logger — that would be a phone-in-the-gym trial against Strong, not a code
decision.

## Others found the same day

Searched GitHub for workout loggers created in 2026, sorted by stars. Most results were
AI-coach apps, Android-only offline logs, or keyword-stuffed repositories with no code
licence; the two below are self-hosted and relevant.

**GymCoach** — <https://github.com/gymcoach-app/gymcoach>, read at `a150458`
(README only). Created 2026-05-27, 42 stars, MIT, two main authors. Next.js 15, Prisma,
Postgres 16, Docker; offline PWA; double-progression suggestions; runnable named
programs (StrongLifts 5×5, Madcow, PHUL, PHAT); TCX/GPX/FIT cardio import; **imports
Strong and Hevy CSV** with a dry-run preview; an MCP/ChatGPT connector that can write
programs when allowed. A heavier deploy than onemore's (Postgres, a build) for a similar
audience. Not read in code.

**lyftr** — <https://github.com/Cawlumm/lyftr> (README only). Created 2026-04-18,
358 stars, MIT, one author. Go/Gin + SQLite backend, React web, React Native/Expo mobile;
workouts and nutrition. Strong/Hevy import and the PWA are listed as *planned*. Not a
candidate until the importer exists.
