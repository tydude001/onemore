# wger — research report (2026-09-06)

Agent-gathered, web sources cited inline. Nothing was installed.

## 1. Deploy story

**Official compose** (`wger-project/docker`, `docker-compose.yml`): seven services — `web` (`wger/server:latest`, gunicorn on :8000, healthcheck on `/api/v2/version/`), `nginx` (`nginx:stable`, publishes :80, serves static/media), `db` (Postgres, included from `services/postgres.yaml`), `cache` (Redis), `celery_worker`, `celery_beat` (both the wger image), and **`powersync`** (offline-sync service for the mobile app, added in 2.6). Source: https://raw.githubusercontent.com/wger-project/docker/master/docker-compose.yml. First start requires `docker compose up -d` then `docker compose exec web ./manage.py setup-powersync-storage` (https://github.com/wger-project/docker).

**Images**: Docker Hub `wger/server` tag `2.7`/`latest` ships **amd64 and arm64**, ~358 MB each (https://hub.docker.com/v2/repositories/wger/server/tags). RAM: not documented anywhere found; gunicorn default is `--workers 3 --threads 2` plus Celery concurrency 4, Postgres, Redis, PowerSync — expect well over 1 GB for the stack (estimate, not sourced).

**Config** is a single `config/prod.env` (https://raw.githubusercontent.com/wger-project/docker/master/config/prod.env). Must-change: `SECRET_KEY`, `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` (`manage.py generate-jwt-keys`), `SITE_URL`. Proxy/HTTPS knobs: `CSRF_TRUSTED_ORIGINS` (comma list, include port), `X_FORWARDED_PROTO_HEADER_SET=True`, `USE_X_FORWARDED_HOST=True`, `NUMBER_OF_PROXIES`. `ALLOWED_HOSTS` is not exposed in prod.env; the errors page instead has you forward `Host`/`X-Forwarded-Proto`/`X-Forwarded-Host` and set the two flags, then verify `/api/v2/exercise/?limit=1` returns pagination links with your scheme/host (https://wger.readthedocs.io/en/latest/administration/errors.html). Two hard constraints: wger must run on its **own (sub)domain, not a subpath**, and the `/ps/` path needs **response buffering off, Upgrade/Connection headers passed, and long timeouts** or the mobile app cannot sync (https://wger.readthedocs.io/en/latest/installation/docker.html, https://wger.readthedocs.io/en/latest/administration/powersync.html). A `Caddyfile.example` ships in the docker repo.

**Synology**: only one direct report found — DS923+ Container Manager, "container for service web is unhealthy" after the user changed volume paths; closed without a documented fix (https://github.com/wger-project/docker/issues/67). Generic DSM pitfalls apply: the compose uses relative `./config/prod.env` and `./config/nginx.conf` bind mounts, which Container Manager projects often mishandle. No working DSM walkthrough found; treat DSM as unverified territory, with the PowerSync `/ps/` streaming requirement through DSM's built-in reverse proxy as the likely trouble spot.

## 2. API surface

Base `/api/v2/`; JSON; `?limit=`, `?ordering=`, field filters. Auth: **permanent token** (`Authorization: Token …`, generated in the web UI) or **JWT** via `POST /allauth/app/v1/auth/login` (10-min access, 120-day rotating refresh; `/api/v2/token/refresh`). Old `/api/v2/login/` and `/api/v2/token/` were removed in 2.6. OpenAPI: `/api/v2/schema`, `/api/v2/schema/ui/` (Swagger), `/api/v2/schema/redoc/` (https://wger.readthedocs.io/en/latest/api/api.html).

**Routine model (the 2.3 "Flexible routines" rewrite, released 2025-04-05, PR #1827)**: `Routine → Day → Slot → SlotEntry`, with prescribed values living in separate **config objects** per field — `weight-config`, `repetitions-config`, `sets-config`, `rir-config`, `rest-config`, each with a `max-*` sibling for ranges. A config row has `iteration`, `operation` (`r`/`+`/`-`), `step` (`abs`/`percent`), `repeat`, and optional `requirements` (progress only if prior-iteration logs hit targets). Multiple entries in one slot = superset; `is_rest` days; `need_logs_to_advance`; max 120 days; `class_name` hooks to custom Python progression classes (https://wger.readthedocs.io/en/latest/api/routines.html). All of these are ordinary writable CRUD endpoints, confirmed on the live root at https://wger.de/api/v2/. So **an external generator can push a full plan** — but it is many POSTs (routine, each day, slot, slot-entry, then one config row per prescribed field); `routine/{id}/structure/` is **GET-only** (checked `wger/manager/api/views.py`).

Read-only computed endpoints: `routine/{id}/structure/`, `date-sequence-display/`, `date-sequence-gym/` (set-by-set, supersets interleaved), `logs/` (grouped by session), `stats/` (volume/sets/Brzycki intensity by day, ISO week, iteration; split by muscle/exercise).

**Reading per-set logs**: `GET /api/v2/workoutlog/` filters on `routine`, `session`, `exercise` (`in`), `date` (`gt/gte/lt/lte/date`), `iteration`, `weight`, `repetitions`, `rir` and their `_target` twins; `ordering=__all__` (https://raw.githubusercontent.com/wger-project/wger/master/wger/manager/api/filtersets.py). Nutrition: `nutritionplan`, `meal`, `mealitem`, `nutritiondiary`, `ingredient`.

**Stability**: 2.5 removed search/weightunit endpoints; 2.6 moved to UUID IDs and dropped login endpoints; 2.7 (2026-09-03) changed sessions to `datetime_start/end` (legacy fields still accepted) and deprecated `weightentry` in favour of `measurement` (https://api.github.com/repos/wger-project/wger/releases/tags/2.7). Expect a breaking change roughly every release.

## 3. Data model

`WorkoutLog` (`wger/manager/models/log.py`): UUID7 `id`, `date` (datetime), `user`, `session` (auto-created if omitted), `exercise`, `routine` (nullable), `slot_entry` (nullable), `iteration`, `next_log` (drop-set chaining), `repetitions` + `repetitions_target` + `repetitions_unit`, `weight` + `weight_target` + `weight_unit`, **`rir` + `rir_target`** (decimal, 1 dp), `rest` + `rest_target`. Validation: at least one of reps/weight. **RiR only — there is no RPE field.** `WorkoutSession` (`session.py`): `routine`, `day`, `datetime_start`, `datetime_end`, `notes`, `impression` (1 bad/2 neutral/3 good); multiple sessions per day allowed since 2.7. Body weight: `weightentry` still works but is a shim over `measurement` (`extra_data.unit` = kg/lb) as of 2.7.

## 4. Mobile logging

Official Flutter app on Google Play, F-Droid, **App Store (id6502226792, seller Peter Thaler, iOS 15+, v2.1.0 on 2026-09-03)** and Flathub (https://github.com/wger-project/flutter, https://apps.apple.com/us/app/wger-workout-manager/id6502226792). The login screen has a "Self-hosted / Connect to your own instance" option with a custom URL field and an "Allow self-signed certificates" toggle (strings in `lib/l10n/app_en.arb`). **Offline mode landed in 2.6** (local SQLite, PowerSync sync) — but app **2.0.3+ requires the PowerSync service**; without it users get "Sync service unreachable" (https://github.com/alexbelgium/hassio-addons/issues/2950, https://github.com/wger-project/flutter/issues/6). Gym mode logs weight/reps/RiR/rest per set with an elapsed timer and history scope (flutter releases 2.0.2–2.1.0, https://api.github.com/repos/wger-project/flutter/releases). Reviews are thin: US store 4.0/5 from 2 ratings, one complaint of "errors for training logs"; Canada store one 2-star "will not open". No substantive gym-floor UX reports found. Web UI on mobile: not verified.

## 5. Export/import

Built-in **CSV import/export exists only for body weight** (https://github.com/wger-project/wger/discussions/1202); routines export to PDF/iCal. No Strong/Hevy importer exists; the maintainer's answer is "use the API". Full-instance JSON export is an open request (https://github.com/wger-project/wger/issues/2300). Backup = stop containers, `pg_dumpall --clean`, restore into a fresh volume, then **drop `powersync_*` replication slots** or you get cryptic errors (https://wger.readthedocs.io/en/latest/administration/backup.html).

## 6. Project health

Latest **2.7, 2026-09-03**; 2.6 2026-06-17; 2.5 2026-04-15; 2.4 2026-01-18; 2.3 2025-04-05. Repo pushed 2026-09-06; ~6.9k stars, 1k forks, 247 open issues; **AGPL-3.0**. Effectively a one-maintainer project: rolandgeider has 7,269 commits vs 122 for the next human; 14 of the last 20 commits are his, 5 are Weblate (https://api.github.com/repos/wger-project/wger, .../contributors, .../commits).

## 7. Backend-fit notes

- **Planned vs actual is native**: every log carries `*_target` next to the actual, and `routine/{id}/logs/` + `stats/` compare them; conditional progression `requirements` even consume that comparison server-side.
- **Official Python client** `wger-api-client` (httpx, sync+async, generated from the OpenAPI spec, versioned to match the server, Apache-2.0) — https://github.com/wger-project/api-client.
- **No webhooks** (none in the API root or docs); polling `workoutlog/?date__gte=` is the mechanism. wger is an **OAuth2 provider** since 2.7 and exposes Prometheus metrics.
- Gaps: no RPE, no per-set notes (notes are per session), no bulk/nested routine POST, and the RiR/config split means a generator writes 5+ rows per exercise.

**Not verified**: RAM footprint, DSM-specific success stories, web-UI-on-phone quality, whether `workoutlog` CSV export exists in the React frontend.
