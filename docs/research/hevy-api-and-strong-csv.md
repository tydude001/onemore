# Hevy API shape and Strong CSV format — research report (2026-09-06)

Agent-gathered, web sources cited inline. Nothing was installed.

## Task A — Hevy public API shape

**Access / auth.** Pro-only: the spec's own intro says "Currently, this API is only available to Hevy Pro users. You can get your key on our web app at https://hevy.com/settings?developer." Every endpoint takes a header `api-key: <uuid>`. No OAuth. Base URL `https://api.hevyapp.com`. The docs page (https://api.hevyapp.com/docs/) is a Swagger UI; the spec is embedded in https://api.hevyapp.com/docs/swagger-ui-init.js. Third-party copies: https://github.com/chrisdoc/hevy-mcp/blob/main/openapi-spec.json, https://github.com/ewright3/hevy-py (swaggerDoc.json — the copy that includes webhooks).

**Endpoints (all `/v1`)**
- `GET/POST workouts`, `GET workouts/count`, `GET workouts/events?since=<ISO>`, `GET/PUT workouts/{id}`
- `GET/POST routines`, `GET/PUT routines/{id}`
- `GET/POST exercise_templates`, `GET exercise_templates/{id}`
- `GET/POST routine_folders`, `GET routine_folders/{id}`
- `GET exercise_history/{exerciseTemplateId}?start_date&end_date`
- `GET/POST body_measurements`, `GET/PUT body_measurements/{date}`
- `GET user/info`
- `POST/GET/DELETE webhook-subscription`
- **No DELETE for workouts/routines/templates/folders** (hevy-mcp README states this explicitly).

**Pagination:** `page` (>=1) and `pageSize` (default 5, **max 10** for workouts/routines/folders; max 100 for exercise_templates). Responses wrap as `{page, page_count, workouts[]}`. `workouts/events` returns `{page, page_count, events[]}` where each event is `{type:"updated", workout}` or `{type:"deleted", id, deleted_at}` — this is the incremental-sync primitive.

**Workout JSON**
```
Workout { id, title, routine_id, description, start_time, end_time, updated_at, created_at, exercises[] }
Exercise { index, title, notes, exercise_template_id, supersets_id|null, sets[] }
Set { index, type: "normal"|"warmup"|"dropset"|"failure",
      weight_kg|null, reps|null, distance_meters|null, duration_seconds|null,
      rpe|null (enum 6,7,7.5,8,8.5,9,9.5,10), custom_metric|null }
```
Note the field is `type`, not `set_type`; weight is always kg, distance always meters.

**POST workouts body:** `{workout:{title, description, start_time, end_time, is_private, exercises:[{exercise_template_id, superset_id, notes, sets:[Set fields]}]}}`. PUT `/workouts/{id}` replaces; `is_private` is required on update.

**Routines — POST and PUT with exercises and sets:**
```
{routine:{title, folder_id|null, notes, exercises:[
  {exercise_template_id, superset_id|null, rest_seconds|null, notes|null,
   sets:[{type, weight_kg, reps, distance_meters, duration_seconds, custom_metric,
          rep_range:{start,end}|null}]}]}}
```
Routine sets add `rep_range` and exercises add `rest_seconds`; there is no `rpe` on routine sets.

**ExerciseTemplate:** `{id, title, type, primary_muscle_group, secondary_muscle_groups[], is_custom}`. IDs are opaque strings; POST creates custom templates. Any importer must map exercise names to `exercise_template_id` first (strong2hevy makes this an explicit step).

**Webhooks:** `POST /v1/webhook-subscription {url, authToken}` — `authToken` is sent verbatim as the `Authorization` header. One subscription per account (`GET` returns `{url, auth_token}` or 404; `DELETE` removes). Fires **only on workout creation** with payload `{id, payload:{workoutId}}`; the endpoint must return 200 within 5 s or delivery is retried. Updates/deletes are not pushed — poll `workouts/events` for those.

Sources: https://api.hevyapp.com/docs/swagger-ui-init.js, https://raw.githubusercontent.com/ewright3/hevy-py/main/swaggerDoc.json, https://github.com/chrisdoc/hevy-mcp, https://github.com/chrisdoc/hevy-api-client

## Task B — Strong CSV export

**Free tier:** yes. Strong's help article only says "You can export your workout data to a spreadsheet friendly CSV format" (https://help.strongapp.io/article/235-export-workout-data); Taper's guide states "Exporting is available on both free and Strong Pro accounts" (https://thetaperapp.com/articles/how-to-export-strong-data/). The App Store listing confirms Pro gates routines (>3), not export, and that v6.2.0 added "Export data from Strong with/without timers and workout notes" (https://apps.apple.com/us/app/strong-workout-tracker-gym-log/id464254577). Export is one-way; Strong has no CSV import.

**Header variants actually observed**
1. Full, comma-delimited, 12 columns (verified in a 2020–2021 export, https://raw.githubusercontent.com/AlexandrosKyriakakis/StrongAppAnalytics/main/Data/strong.csv):
   `Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE`
2. Without notes, 10 columns (2024 export, https://raw.githubusercontent.com/DaKheera47/strong-statistics/main/data_sample/sample_strong.csv — matches the "without notes" export option):
   `Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,RPE`
3. Reported but not directly observed: semicolon-delimited with unit-suffixed headers. LiftShift's README: "LiftShift handles semicolon-delimited files, quoted fields, and unit-suffixed headers like `Weight (kg)`" (https://github.com/aree6/LiftShift); Strength Journeys says it handles "Strong's CSV quirks like semicolon delimiters and weight-unit headers" (https://www.strengthjourneys.xyz/import/strong). No verbatim header row for this variant was found — treat `Weight (kg)`/`Weight (lbs)` and `;` as an adapter case to detect, not a confirmed spec. Semicolon output is likely locale-driven (decimal-comma locales), which RepStack also warns about ("weights use decimal commas", https://rep-stack.com/import/strong-csv/).

**Sample rows (variant 1):**
```
2020-12-30 18:51:52,"Evening Workout",2h 38m,"Snatch (Barbell)",1,40.0,3,0,0,"","",""
2024-11-28 17:36:08,"B",35m,"Bent Over Row (Barbell)",1,10.0,13.0,0,0.0,
```
- **Date:** `YYYY-MM-DD HH:MM:SS`, local time, no timezone; repeated on every set row of a workout (strong2hevy parses with Go layout `2006-01-02 15:04:05` and requires a configured timezone).
- **Duration:** `2h 38m`, `57m`, `1h 5m 30s` — space-separated `h`/`m`/`s` tokens. Only per-workout; no per-set rest time.
- **Units:** in the comma variants there is no unit column and no unit in the header — Weight/Distance are bare numbers in whatever unit the app was set to. strong2hevy takes `weight_unit` (lb/kg) and `distance_unit` (mi/km/m) as config. Text fields are quoted; numeric fields are not. `Weight` always has one decimal (`40.0`); `Reps` may be `3` or `13.0` depending on version.
- **Set Order / set types:** normal sets are `1..n` resetting per exercise. Strong tags sets Warm Up / Failure / Drop Set; in the export, warmup appears as `Set Order = W` (strong2hevy maps `W` → Hevy `warmup`, case-insensitive; https://raw.githubusercontent.com/criccomini/strong2hevy/main/strong.go). No source confirms `D`/`F` markers — strong2hevy treats anything non-`W` as a work set and strong-statistics coerces non-numeric to NaN, so an adapter should accept `W`/`D`/`F` defensively and log unknowns. Neither sample file contained a non-numeric Set Order.
- **RPE:** blank or 6–10 (Strong allows 0.5 steps).

**Reference parsers**
- https://github.com/criccomini/strong2hevy — Go; Strong CSV → Hevy API with explicit exercise mapping and routine generation. Best reference for the Strong→Hevy field mapping.
- https://github.com/DaKheera47/strong-statistics — Python/pandas, `app/processors/strong_processor.py`; auto-detects delimiter (`sep=None, engine='python'`), parses `%Y-%m-%d %H:%M:%S`, has `sample_strong.csv` and `sample_strong_legacy.csv` fixtures.
- https://github.com/aree6/LiftShift — TypeScript; generic header-synonym parser, useful for the semicolon/unit-suffixed case.
- https://github.com/aimarchirico/gymruntohevy, https://github.com/rosenpin/fitnotes-converter, https://github.com/DrBushyTop/GarminToHevyConverter — all emit the Strong format because Hevy imports it natively (https://help.hevyapp.com/hc/en-us/articles/38001424401943-How-to-Import-Strong-App-CSV-Files-and-Export-Your-Data-in-Hevy).
- https://blog.ayjc.net/posts/strong-app-parsing/ — SQLite loading of variant 1; the companion post shows Hevy's own export header: `title,start_time,end_time,description,exercise_title,superset_id,exercise_notes,set_index,set_type,weight_lbs,reps,distance_miles,duration_seconds,rpe` with dates like `28 Mar 2025, 17:29` (https://blog.ayjc.net/posts/migrate-strong-hevy-app/).

## Addendum 2026-09-10 — Set Order "Rest Timer", measured

The author's exports from 2026-09-07 on carry a non-numeric Set Order the sources above never
mention, and it contradicts "no per-set rest time": a row after each set with
`Set Order = Rest Timer`, Weight `0`, Reps `0.0`, and the rest taken in **Seconds**
(60/90/120/150/180 — the values `comeback` prescribes). 50 such rows in the 2026-09-10
export, every one in a session logged 2026-09-06 or later; the 2022–2025 history has none.
Read literally they are 0×0 work sets, which is how they were first imported.
`strong_csv.py` now drops them.
