# Deploying `onemore serve`

A generic recipe for running the web app as a container on a machine you
control, reached only over a private network (a tailnet, a WireGuard mesh, or
just the loopback interface on your own laptop) — never a public or LAN
address. `web.py`'s GET routes carry no authentication at all; only POST is
behind `X-Token`. Exposing this on an untrusted network puts your whole
training history out unauthenticated.

## There is no Dockerfile, on purpose

`pyproject.toml` declares `dependencies = []`, and `web.py` is stdlib-only
(`http.server`, `sqlite3`, `json`), so there is nothing to install: the image
is stock `python:3.13-slim`, and a clone of this repo is mounted **read-only**
into it. Package data — `exercises.toml` and `static/` — is read through
`importlib.resources`, which resolves fine from a source tree on the path.

The consequence is the good part: there is no image holding the code, so
there is nothing to go stale. Deploying a change is a `git pull` on the host
plus a container recreate — no image rebuild.

If a dependency is ever added to `pyproject.toml`, this stops being true and
the service needs a real `build:`. That is the moment to write a Dockerfile,
not before.

## 1. Clone the repo

```bash
git clone https://github.com/tydude001/onemore.git onemore
```

## 2. Make a data directory

Writable state lives **outside** the clone, so a hard reset of the clone
(a redeploy) never touches it.

```bash
mkdir -p ./data/imports
```

It will be mounted at `/data`, a sibling of `/app` — not nested inside it —
so nothing writable ever lands in the read-only clone.

## 3. `docker-compose.yml`

```yaml
services:
  onemore:
    image: python:3.13-slim
    working_dir: /app
    volumes:
      - ./onemore:/app:ro
      - ./data:/data
    environment:
      PYTHONPATH: /app/src
      ONEMORE_DATA: /data
      ONEMORE_TOKEN: ${ONEMORE_TOKEN}
      TZ: ${TZ:-UTC}
    command: python -m onemore.cli serve --host 0.0.0.0 --port 8790
    ports:
      - "127.0.0.1:8790:8790"
    healthcheck:
      test: ["CMD", "python3", "-c",
             "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8790/api/status', timeout=3).status == 200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

- **The published port is the confinement.** The container binds `0.0.0.0`
  internally so the healthcheck and any reverse proxy on the same host can
  reach it, but `"127.0.0.1:8790:8790"` means only the host itself, or
  whatever a tailnet's userspace proxy delivers to `127.0.0.1`, can reach
  it — not the LAN. Publish on a private-network interface address instead
  only if you understand that everything under `/api/*` is then reachable
  from that network, unauthenticated, for GET.
- **`ONEMORE_TOKEN`** is the shared secret every write needs, sent as
  `X-Token`: `/import/strong`, `/import/health`, `/api/start`,
  `/api/advance`. Leave it unset and writes are disabled — reads still work.
  Generate one with `openssl rand -hex 24`.
- **`TZ`** matters: `python:3.13-slim` ships tzdata and honours it, and
  without a timezone set the container runs UTC, which can roll the training
  week's day boundary early or late relative to where you actually train.
- **Check `/api/status`, not `/health`.** `/health` answers a static 200
  without ever opening the database; `/api/status` is what actually proves
  the app can read its data, and it's what the healthcheck above probes.

## 4. Start it

```bash
export ONEMORE_TOKEN=$(openssl rand -hex 24)
docker compose up -d
docker compose ps                 # running (healthy) shortly after start
curl -s http://127.0.0.1:8790/api/status | head -c 200
```

To carry existing history over instead of starting empty, copy a database
into place before the first start:

```bash
cp /path/to/your/onemore.db ./data/onemore.db
```

## 5. The iOS Shortcut that feeds it: Strong

Build it on the phone — there is nothing to install on the server.

**Shortcuts → new shortcut → Info → "Show in Share Sheet"**, accept type
*Files*. Turning that on adds the `Receive … from Share Sheet` block itself.

| Step | Setting |
|------|---------|
| Get Contents of URL | `http://<your host>:8790/import/strong` |
| ↳ Method | `POST` |
| ↳ Headers | `X-Token` = your `ONEMORE_TOKEN` |
| ↳ Request Body | **File** → the Shortcut Input |
| Show | **Contents of URL** — so a failure is legible instead of silent |

In Strong: **Settings → Export Data → share → your shortcut.** The response
is `{"sessions": N, "new": N, "saved": "...", "remapped": N}`.

The import is idempotent — a session is `(date, workout name)`, and a re-post
of the same export answers `"new": 0` — so sending the whole history every
time is fine and is the intended use.

## 6. The second Shortcut: Apple Health

The Health app already makes the export file; `/import/health` takes it
whole. Same shape as § 5 with a different URL:

| Step | Setting |
|------|---------|
| Get Contents of URL | `http://<your host>:8790/import/health` |
| ↳ Method | `POST` |
| ↳ Headers | `X-Token` = your `ONEMORE_TOKEN` |
| ↳ Request Body | **File** → the Shortcut Input |
| Show | **Contents of URL** |

Name it so the two are distinguishable in the share sheet — both accept
files.

On the phone: **Health → your photo, top right → Export All Health Data →
share → your shortcut.** The export answers **202**, not 200, on purpose:
it can be well over a gigabyte, and the parse runs on a worker thread so the
request answers immediately rather than timing the phone's share sheet out.
Progress shows up in `/api/status` once the parse finishes.

Re-sending the same export is free: readings are keyed on name and instant,
so a full export lands only what's new. Send one before you advance a
week — the recovery rule reads the closing week's own readings, not
whatever's latest on file, so an export that arrives after the week is
closed is never read by the rule that wanted it.

## Updating

```bash
git pull
docker compose up -d --force-recreate --no-deps onemore
```

Nothing else needs rebuilding — the clone is the image's content, mounted
read-only.
