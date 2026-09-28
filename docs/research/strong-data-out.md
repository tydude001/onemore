# Getting per-set data out of Strong (iOS) — research report (2026-09-06)

Agent-gathered, web sources cited inline. Nothing was installed.

## 1. Official export

- **Path and cost.** Profile tab → settings gear → "Export Strong Data" (iOS wording) → confirm. Three taps plus the share sheet. Free-tier and Pro both get it; no export frequency limit. ([Strong help](https://help.strongapp.io/article/235-export-workout-data), [Taper guide](https://thetaperapp.com/articles/how-to-export-strong-data/)). The App Store listing says "Export all of your data to Notes or Email in CSV format" — it goes through the iOS share sheet, so "Save to Files" (an iCloud Drive folder) works too. ([App Store](https://apps.apple.com/us/app/strong-workout-tracker-gym-log/id464254577))
- **Scope.** Full history every time, one row per set — so periodic re-export + dedupe on (Date, Workout Name, Exercise Name, Set Order) is viable. Body measurements export separately, one CSV per metric. Strong cannot re-import its own CSV.
- **Exact header** (verified from a real export on GitHub): `Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE`. Sample row: `2020-12-30 18:51:52,"Evening Workout",2h 38m,"Snatch (Barbell)",1,40.0,3,0,0,"","",`. Date is local `YYYY-MM-DD HH:MM:SS`, Duration is `2h 38m`, Weight has no unit column (whatever the app is set to). ([sample CSV](https://github.com/AlexandrosKyriakakis/StrongAppAnalytics/blob/main/Data/strong.csv)). Set type (warm-up/drop/failure) is **not** a column in that sample; see hevy-api-and-strong-csv.md for the `Set Order = W` warm-up marker strong2hevy handles.
- **Share workout.** "More (…)" on a workout → Share → share sheet. The help article says a link/URL is generated and, "If you share a Workout via text message, the contents of the Workout will also be included by default." The link format changed in 6.0 and is not backward compatible. Neither article shows the text layout; no documented example of the summary text was found. ([share article](https://help.strongapp.io/article/109-share-workout-or-template), [6.x links](https://help.strongapp.io/article/255-share-links))

## 2. iOS Shortcuts / automation

- The App Store listing carries only Apple's generic "Use this app with Siri to help you get things done" line, and strong.app lists "Siri Shortcuts" as a feature with no detail. The only concrete action found referenced is adding a body measurement (via Profile widgets). **No documented action reads or exports workouts**, and no `strong://` scheme appears in the community URL-scheme reference. ([strong.app](https://www.strong.app/), [URL-scheme list](https://github.com/organicaudio/useful-code-snippets/blob/main/docs/ios/Reference:%20iOS%20App%20URL%20Scheme%20Names%20&%20Paths%20for%20Shortcuts.md)) — unverified: the Shortcuts app's action list for Strong was not inspected directly; worth a 30-second check on the phone.
- Practical automation is therefore a human-in-the-loop "Export → share sheet" done every so often. Shortcuts can't drive Strong's UI, but a Shortcut *can* be the share-sheet target and POST the file to a webhook.

## 3. Apple Health

- Strong writes **Workouts** (with Activity ring credit), **Active Energy**, and **Weight**; it reads nutrition/measurements. Only new workouts sync; nothing retroactive. Heart rate comes from the Watch app. ([sync article](https://help.strongapp.io/article/147-sync-with-apple-health), [permissions](https://help.strongapp.io/article/212-apple-health-permissions))
- **Per-exercise/per-set data is not in HealthKit** in any documented form; no source mentions metadata keys. The workout activity type (Traditional vs Functional Strength Training) is not documented by Strong — unverified.
- **Health Auto Export** (Lybron/HealthyApps): Premium ($5.99/yr, $24.99 lifetime) adds scheduled REST-API automations with "Since Last Sync" windows, JSON or CSV, custom headers. Caveats: iOS decides when it actually runs, and the phone must be unlocked. Workout v2 JSON: `{"data":{"workouts":[{id,name,start,end,duration,activeEnergyBurned{qty,units},heartRate{min,avg,max},heartRateData[],metadata{},…}]}}` — `name` is the activity type; per-set fields have nowhere to live. ([REST API](https://help.healthyapps.dev/en/health-auto-export/automations/rest-api/), [workouts format](https://help.healthyapps.dev/en/health-auto-export/export-format/workouts/), [FAQ/pricing](https://help.healthyapps.dev/en/health-auto-export/faq/)). Conclusion: HealthKit is good for session timestamps/HR/calories only.

## 4. Unofficial / reverse-engineered

- **dmzoneill/strongapp-api** — documented Strong's old **Parse Server** backend: `POST https://ws13.strongapp.co/parse/login` with `x-parse-application-id`, then `POST /parse/classes/ParseWorkout` (`_method: GET`) returning `parseSetGroups[].parseSetsDictionary[]` with `reps, kilograms, expectedKilograms, rpe, tagsValue, isChecked, isPersonalRecord`. Author states Strong asked him not to publish it; he "accept[ed] the termination", cancelled Pro and moved to Hevy; README says use it only "if you plan on getting your account terminated." Headers reference app v2.7.9 (Android), so this is the pre-6.0 API; repo still gets pushes (2026-09-03) but is marked reference-only. ([repo](https://github.com/dmzoneill/strongapp-api), [login.md](https://github.com/dmzoneill/strongapp-api/blob/main/api/login.md))
- **tolik518/strong-api-workout-sync** — Rust service against the **current** backend (client build 600013): `POST auth/login` (`usernameOrEmail`/`password` → `access_token`/`refresh_token`), `GET api/users/{id}?include=log,…`, `GET api/logs/{user_id}`. Data model: Log → cellSetGroup[] → cellSets[] (`isCompleted`) → cells[] (`cellType`, `value`), i.e. per-set. Stores to ClickHouse for Grafana. Active (commits through May 2026), 8 stars, but the base URL is withheld: "not entirely public and because of possible legal implications" — you'd have to capture it yourself via a proxy. ([repo](https://github.com/tolik518/strong-api-workout-sync))
- **Account risk:** documented precedent of Strong objecting; ToS reportedly silent at the time. Treat as real risk to the account holding your history.
- **Local database from an iPhone backup:** no thread or write-up documents Strong's on-device schema. Strong's GitHub org shows a Swift/ObjC stack (SwiftUIX, Charts, Sentry) but no Realm/Core Data hint. iMazing-style raw extraction would work in principle; the file format and schema are unverified.

## 5. Strong vs Hevy

- **Hevy public API exists** (`api.hevyapp.com/v1/workouts`, `api-key` header), Pro-only ($2.99/mo, $23.99/yr, $74.99 lifetime), with Python/MCP/Home Assistant clients — this is the decisive difference for automation. ([Hevy API docs](https://api.hevyapp.com/docs/))
- **Importer:** Profile → Settings → Export & Import Data → Import Strong CSV; Strong must be set to English before exporting. One migrator lost ~5–10 of ~900 workouts. ([Hevy help](https://help.hevyapp.com/hc/en-us/articles/38001424401943), [blog](https://blog.ayjc.net/posts/migrate-strong-hevy-app/))
- **UX reports** (Reddit was blocked to the crawler; these are from comparison writeups that cite r/strongapp/r/fitness): Strong = "gym's notebook", previous sets in gray, fewer animations, "gets out of the way", better Apple Watch app (phone-free logging), quicker access to warm-up/AMRAP set types, more flexible notes. Hevy = "gym's Instagram", busier, social feed, supersets/drop sets/RIR handled more cleanly, PR color-coding, watch app lags on stability. Strong loyalists call Hevy "slightly busier"; Hevy users call Strong "sparse". ([sensai](https://www.sensai.fit/blog/hevy-vs-strong-2026), [aitoolsbakery](https://aitoolsbakery.com/blog/hevy-vs-strong-app/), [setgraph](https://setgraph.app/ai-blog/hevy-vs-strong-app-comparison-2026))

## 6. Strong Pro

- App Store IAPs: $4.99/mo, $19.99/6 mo, $29.99/yr, Forever $79.99–$99.99 (both prices listed). Pro = unlimited templates, measurements, all charts, plate/warm-up calculators, themes. **Nothing about data/export** — CSV export is free. No official API statement or roadmap found anywhere; the only signal is the takedown request above. ([App Store](https://apps.apple.com/us/app/strong-workout-tracker-gym-log/id464254577), [Pro article](https://help.strongapp.io/article/132-strong-pro))

## Bottom line

Zero-friction extraction from Strong does not exist. Lowest-friction legitimate path: 3-tap CSV export to a share-sheet target (Shortcut → webhook, or a synced folder) every N workouts, with a watcher that dedupes. Zero-friction requires either the undocumented backend (account risk) or moving to Hevy for its API while keeping the Strong history via the importer.

## Addendum 2026-09-06 — Health Auto Export JSON, verified against the vendor's format pages

Re-read for the adapter (`src/onemore/sources/apple_health.py`); the §3 summary above was
from memory of the format and is confirmed with two corrections.

- **Metrics** live under `data.metrics[]` as `{name, units, data[]}`. A plain reading is
  `{"date": "2024-02-06 14:30:00 -0800", "qty": 8500}`. Multi-valued readings carry their
  parts as sibling keys: `heart_rate` has `Min`/`Avg`/`Max`, `blood_pressure` has
  `systolic`/`diastolic`, and the aggregated `sleep_analysis` (units `hr`) has a bare
  `"date": "2024-02-06"` with `totalSleep`, `asleep`, `core`, `deep`, `rem` (the page also
  shows `inBed` in older exports). Names are snake_case; the page renders body mass as
  `weight_&_body_mass`, which may be the display name rather than the key, so the
  adapter normalises every name (`&`, spaces, camelCase → `_`). Confirmed names:
  `step_count`, `active_energy`, `resting_heart_rate`, `sleep_analysis`. Not shown on the
  page, assumed by analogy: `heart_rate_variability`, `body_fat_percentage`, `vo2_max`.
  ([metrics format](https://help.healthyapps.dev/en/health-auto-export/export-format/health-metrics/))
- **Workouts** live under `data.workouts[]`: `id`, `name`, `start`/`end`
  (`yyyy-MM-dd HH:mm:ss Z`), `duration` in **seconds**, and quantity objects `{qty, units}`
  for `activeEnergyBurned`, `totalEnergy`, `distance`, …; `heartRate` is an object with
  `min`/`avg`/`max`. Time-series arrays carry a `source` (e.g. "Apple Watch").
  ([workouts format](https://help.healthyapps.dev/en/health-auto-export/export-format/workouts/))
- **REST automation**: HTTP POST, `application/json` for JSON exports (multipart for CSV),
  custom headers supported ("Each header key must have a corresponding value"), so the
  repo's `X-Token` works as-is. Windows: Default (previous full day plus today so far),
  Since Last Sync, Today, Yesterday, Previous 7 Days. Runs only while the phone is
  unlocked ("Apps are not allowed to access health data while iPhone is locked"). The
  page does not state whether Premium is required; §3 above says it is, from the FAQ.
  ([REST API](https://help.healthyapps.dev/en/health-auto-export/automations/rest-api/))

## Addendum 2026-09-06 — the Health app's native export, measured

The author exported straight from Apple Health (profile → Export All Health Data) instead of
installing Health Auto Export. What that gives, from the file itself:

- **A 52 MB zip holding a 1.1 GB `export.xml`** of about 2.3 million `<Record>` elements
  plus `<Workout>` elements and a `workout-routes/` folder of GPX files. Records come
  first in the file, workouts after, so a single streaming pass has to hold the raw
  heart-rate samples until the workouts arrive. Parsed with `iterparse`, clearing the
  root as it goes, in a few minutes; `scripts`-free, it is the `apple_health_xml` adapter.
- **Records are not in date order**, so a first-seen date in a single pass is not a
  series' start (the first census here got that wrong). Real ranges, from the imported
  table: body mass 2018-12-03 to 2026-04-04; body fat and lean mass 2023-01-20 to
  2026-04-04; resting HR and HRV 2021-02-03 to the export day; VO2 max 2021-05 to
  2026-05-16; steps 2020-10 onward; raw heart rate is dense only from 2025-05.
- **Body composition is a Withings scale**, 112 of 192 body-mass records, plus
  MyFitnessPal (67), Lose It! (11), Strong (1). Body fat (91) and lean mass (92) are
  Withings only, last reading **2026-04-04** — nothing since April, so the scale has not
  been used in five months. Body fat is written as a fraction (`0.204`) under a `%`
  unit; the adapter stores the percentage.
- **Sleep is thin.** Phone-only `InBed` blocks 2020-10 to 2024-09 (1041 nights), but
  Watch stage intervals (`AsleepCore` / `Deep` / `REM` / `Awake` / `AsleepUnspecified`)
  on only 73 nights, 2021-02 to 2026-07-05, most of them 2022-09 to 2025-05. The Watch
  is evidently not worn to bed, so a sleep-based recovery signal has nothing to read.
  Two stray numeric values (`8`, `8.5`) are a sleep goal, ignored.
- **Workouts:** 261 Traditional Strength Training, 30 walks, 22 cycling, 9 yoga, a few
  others. Only 63 workouts carry a `HeartRate` `WorkoutStatistics` row (the newer ones);
  321 carry `ActiveEnergyBurned`. The adapter fills the missing HR from raw samples inside
  each workout window, which exist from 2025-05 onward — so the 2022–2024 Strong sessions
  get calories but no heart rate.
- **Steps double-count** across the phone (61k records) and the watch
  (72k): the app dedupes on display, the export does not. Per day, the adapter keeps the
  larger source.

## Addendum 2026-09-06 — re-verified, and the migration is one-way

- **Re-checked, no change.** No official Strong API has appeared. `tolik518/strong-api-workout-sync` still withholds its base URL for the reasons §4 records ([repo](https://github.com/tolik518/strong-api-workout-sync)), and the help centre still documents CSV export as the supported way out ([Strong help](https://help.strongapp.io/article/235-export-workout-data)).
- **The consequence §5 never draws.** §1 records that Strong cannot re-import its own CSV. So a move to Hevy is **one-way**: the history goes in through Hevy's Strong importer, and nothing comes back if the app turns out to be wrong. Weigh that against a $74.99 lifetime before buying, not after.
