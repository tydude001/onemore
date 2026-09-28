# Liftosaur — research report (2026-09-06)

Agent-gathered, web sources cited inline. Nothing was installed.

## 1. What it is / architecture

- **Self-description:** "Open-source powerful weight lifting tracker PWA for coders." Preact/TypeScript PWA (~200 KB, service-worker cached) with a custom Redux-like state manager; CodeMirror for the program editor, uPlot for graphs. The iOS and Android apps are described as "thin" native wrappers around the PWA with some native features added. — https://github.com/astashov/liftosaur (README)
- **Backend:** "AWS Lambdas + DynamoDB + S3 + a bunch of other AWS services," deployed with AWS CDK. The author admits DynamoDB "is not a great choice for this app." — README.
- **Self-hosting reality:** The README gives a *client-only* local run (`npm install && npm start` → `localhost:8080/app`, offline-only, no backend). Running "the server" means: your own AWS account, IAM permissions across ~11 services (SecretsManager, DynamoDB, ECR, S3, CloudFront, SES, API Gateway, SSM, Route53, CloudFormation, Lambda), hand-created Secrets Manager entries listed in `liftosaur-cdk.ts`, then `npm cdk-deploy`. The README notes the deployment is coupled to the `liftosaur.com` domain and CDK files need editing. So: the source is fully open, but "self-host" in practice means "deploy your own AWS stack," not a Docker container. Repo tree also shows `lambda/api` and `lambda/mcp` directories (server code is in-repo). — README; https://github.com/astashov/liftosaur/tree/master/lambda
- **License:** AGPL-3.0 (GitHub API `license.spdx_id`). — https://api.github.com/repos/astashov/liftosaur

## 2. Liftoscript — the program DSL

Source: https://www.liftosaur.com/docs/liftoscript (all syntax below), plus the shipped examples file https://raw.githubusercontent.com/astashov/liftosaur/master/src/generated/liftoscriptExamples.ts.

**Structure.** A program is Markdown-ish text: `# Week N` / `## Day N` headings, one exercise per line, sections separated by `/`:
`Exercise[, Equipment] / <sets> / <weight> / progress: ... / update: ... / warmup: ... / superset: A / id: tags(...)`. `// text` is a user-visible description; `/// text` a hidden comment; a line ending in `\` continues.

**Sets.** `3x8`, `3x8-12` (range), `1x5, 1x3, 1x1, 5x5` (mixed), `1x5+` (AMRAP). Weight: `60kg`/`60lb` absolute, `80%` (of the exercise's 1RM, `rm1`), `@8` RPE (app derives weight from an RPE table), `@8+` (log actual RPE), `100lb+` (prompt for actual weight). Timers: `60s` rest; `60s|30s` active|rest; `60s+|30s` manual-stop active; `auto` auto-advance. Set labels: `4x5 (Main), 1x5+ (AMRAP)`. Multiple set *variations* separated by `/` (`5x3 / 6x2 / 10x1`), current one marked `!` or chosen via `setVariationIndex`. Exercise *variations* with `|` (`Split Squat | Bulgarian Split Squat / 3x8`) share progress logic.

**Reuse.** `Squat / ...Bench Press` copies another exercise's sections; `...Bench Press[2]` = day 2 this week, `[2:1]` = week 2 day 1. `Bench Press[1-4] / 3x8` repeats across weeks 1–4; a later week can restate just the changed line. Templates: `T1 / used: none / ... ` defines a non-scheduled exercise others `...T1`. Labels (`main: Squat`, `accessory: Squat`) let the same lift carry two progressions. `id: tags(1, 100)` exposes an exercise's state to others via `state[1].rating = 10`.

**Warmups/supersets.** `warmup: 1x5 45lb, 1x5 135lb, 1x3 80%` (percentages are of the *first working set*, not 1RM); `warmup: none`; `superset: A` on two lines alternates them.

**State & progress.** `progress:` is one of:
- `lp(inc, successesNeeded, successCounter, dec, failuresNeeded, failureCounter)` — linear; e.g. `lp(2.5lb, 1, 0, 10%, 1, 0)` (the shipped "Basic Beginner" example shows a *percentage* decrease is allowed). Success = all sets hit prescribed reps.
- `dp(inc, minReps, maxReps)` — double progression: reps climb in the range, then weight bumps and reps reset. No deload path.
- `sum(threshold, inc)` — add weight if total completed reps > threshold.
- `custom(var: default, ...) {~ script ~}` — state variables declared in the parens persist per exercise and are read/written as `state.var`; `var+: default` prompts the user. Script has math/comparison/logical ops, ternary, `if/else`, `for (var.i in array)`, temporary `var.x`.

Read-only vars in scripts (1-indexed arrays): `weights[n]`/`w`, `completedWeights[n]`/`cw`, `reps`/`r`, `minReps`, `completedReps[n]`/`cr`, `RPE`, `completedRPE`, `rm1`, `bodyweight`, `day`, `week`, `dayInWeek`, `numberOfSets`/`ns`, `completedNumberOfSets`, `setVariationIndex`, `descriptionIndex`, `amraps/logrpes/askweights[n]`, `setTime[]`. Writable: `weights`, `reps`, `minReps`, `RPE`, `timers`, `amraps`, `logrpes`, `askweights`, `rm1`, `setVariationIndex`, `descriptionIndex`, `numberOfSets`; addressable as `weights[week:day:setvariation:set]` or `weights[5]`. Bare `completedReps >= reps` compares whole arrays.

**Adaptation semantics.** Progress scripts run once when a workout is *finished* and mutate the exercise's state / next prescriptions ("after you finish a workout the app would try to extract the new values into overrides"). Decisions are expressed against *logged* values — `completedReps`, `completedWeights`, `completedRPE` — not prescribed ones; the REST API doc confirms `POST /workout/finish` "runs progressions, advances training day" server-side too.

**`update:` blocks** run *during* the workout, before/after each set (`setIndex` = 0 on initial run), e.g. adding a set when the first is easy: `update: custom() {~ if (setIndex == 1 && completedReps[1] >= reps[1]) { numberOfSets = 4 } ~}`. Helper `sets(fromIdx, toIdx, minReps, maxReps, isAmrap, weight, timer, rpe, logRpe)` rewrites a block of sets.

**Built-in functions** (authoritative list in `src/liftoscriptFns.ts`): `roundWeight`, `roundConvertWeight`, `calculateTrainingMax`, `calculate1RM` (Epley), `rpeMultiplier`, `floor`, `ceil`, `round`, `sum`, `min`, `max`, `zeroOrGte`, `print`, `increment`/`decrement` (plate-aware), `sets`. — https://raw.githubusercontent.com/astashov/liftosaur/master/src/liftoscriptFns.ts

**Rendering.** The web editor (`/planner`) and app render each week as days with concrete weights already resolved from `%`/RPE/state and rounded to the user's gym's plates; descriptions persist across weeks until overwritten. (From docs text; the editor was not run.)

**Verbatim examples** (from `liftoscriptExamples.ts`):

5/3/1 BBB (weeks 2–4 restate only `main`):
```
# Week 1
## Day 1
main / used: none / 1x5 58%, 1x5 67%, 1x5+ 76%, 5x10 50% / progress: custom(increment: 5lb) {~
  if (week % 3 == 0) { rm1 += state.increment }
~}
Overhead Press[1-4] / ...main
Chin Up[1-4] / 5x10 / 0lb / warmup: none
## Day 2
Deadlift[1-4] / ...main / progress: custom(increment: 10lb) { ...main }
# Week 2
## Day 1
main / 1x3 63%, 1x3 72%, 1x3+ 81%, 5x10 50%
# Week 3
## Day 1
main / 1x5 67%, 1x3 76%, 1x1+ 85%, 5x10 50%
```
GZCLP T1 (stage-cycling via set variations):
```
t1 / used: none / 4x3, 1x3+ / 5x2, 1x2+ / 9x1, 1x1+ / 1x5 (5RM Test) / 75% / progress: custom(increase: 10lb) {~
  if (setVariationIndex == 4) {
    setVariationIndex = 1
    weights = completedWeights[1] * 0.85
    rm1 = completedWeights[1] / rpeMultiplier(5, 10)
  } else if (completedReps >= reps) {
    weights = completedWeights[ns] + state.increase
  } else { setVariationIndex += 1 }
~}
t1: Squat / ...t1
```
Basic beginner: `Squat / 2x5, 1x5+ / 45lb / progress: lp(5lb, 1, 0, 10%, 1, 0)`.

## 3. Data access / export

- **In-app (free, no gate seen in code):** Settings menu has "Export data to JSON file" (full storage dump), "Export history to CSV file", "Export all programs to text file", "Import history from other apps", and a Liftosaur-CSV importer with an example zip. — `src/components/screenSettings.tsx`, `importerLiftosaurCsv.tsx`
- **Third-party import:** the "other apps" modal offers exactly one option, "Upload CSV file from Hevy" (`Thunk_importHevyData`, client-side). **No Strong import** found. — `src/components/modalImportFromOtherApps.tsx`
- **REST API (premium only):** `https://www.liftosaur.com/api/v1`, Bearer `lftsk_…` keys. Full CRUD on programs and history, live-workout endpoints (`/workout/start|set|sets|finish`), measurements, gyms. History records come back as `{id, text}` where `text` is the "Liftoscript Workouts" format, e.g. `2026-03-01T10:00:00Z / program: "5/3/1" / ... / exercises: { Bench Press, Barbell / 3x5 185lb, 1x3 185lb / target: 3x5 185lb 120s }`. Pagination `limit` (max 200) + `cursor`. — https://www.liftosaur.com/docs/api. A grammar/serializer for this format is in `src/liftohistory/liftohistory.grammar`.
- **MCP server (premium):** `https://www.liftosaur.com/mcp`, OAuth 2.1 or API key, 30+ tools. — https://www.liftosaur.com/docs/mcp
- Community: `liftosaur-garmin-uploader` consumes either the CSV export or the API. — https://github.com/mhballin/liftosaur-garmin-uploader

## 4. Logging UX

Offline-first PWA (README; API doc describes idempotent client-generated set IDs for offline writes). Rest timers, plate calculator, RPE logging, set-timers/EMOM/Tabata. **Apple Health + Google Health Connect** shipped Oct 2024 (discussion #117). **Apple Watch app** shipped Feb 2026 ("Apple Watch is done", discussion #118; `src/watch/index.ts` in repo); Wear OS still open as of Jul 2026. — https://github.com/astashov/liftosaur/discussions/117 , /118

## 5. Project health

- Effectively a single maintainer: astashov 3,344 of ~3,427 commits; next contributor 32. — https://api.github.com/repos/astashov/liftosaur/contributors
- Very active: last push 2026-09-05, daily commits in the past week. No GitHub releases or tags. 700 stars, 107 forks, 223 open issues. — https://api.github.com/repos/astashov/liftosaur
- App Store: v7.11, "released 4 days ago", 4.9★ (386 ratings), developer Liftosaur, LLC. IAP: $4.99/mo, $39.99/yr, $99.99 lifetime. — https://apps.apple.com/us/app/liftosaur/id1661880849. Programs/logging/offline are free; graphs, cloud sync, REST API and MCP are premium.
- Google Play listing exists but its version/downloads could not be read — **unverified**.

## 6. Verdict-relevant

**(a) As a logging backend for an external analysis tool:** workable but with caveats. Free path = manual JSON/CSV export from the phone. Programmatic path = REST API, paid, and the history payload is a *text DSL* (Liftoscript Workouts), so you'd parse it (grammar available in-repo to port). Self-hosting to escape the paywall means running your own AWS/CDK stack — not lightweight.

**(b) As prior art for a Python program DSL:** strong. The design is well factored: text program → parser → evaluator producing resolved per-day sets; explicit split between *prescribed* and *completed* arrays; per-exercise persistent state; `progress` (post-workout) vs `update` (intra-workout) hooks; templates/reuse; tags for cross-exercise state. Published spec artifacts:
- Lezer grammars: `src/pages/planner/plannerExercise.grammar` (program syntax, `@top Program { expression* }`, `SetPart { Rep Plus? "x" (RepRange | Rep) Plus? }`, `Weight`, `Rpe { "@" ... }`), `src/liftohistory/liftohistory.grammar` (workout records); a `liftoscript.grammar` for the script language is referenced by the generated `src/generated/liftoscriptGrammar.ts` but the source file was not located at `src/liftoscript.grammar` (404).
- Evaluators: `src/liftoscriptEvaluator.ts`, `src/pages/planner/plannerExerciseEvaluator.ts`; function table `src/liftoscriptFns.ts`; docs source `src/docs/content/docs.md`; examples `src/generated/liftoscriptExamples.ts`.

**Could not verify:** Play Store metadata; whether AMRAP sets count toward `lp()` success (docs silent); exact CSV column set; that in-app import/export is truly ungated (inferred from absence of a check in `screenSettings.tsx`).
