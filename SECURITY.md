# Security

## Reporting a vulnerability

Please report security problems privately, through GitHub's private
vulnerability reporting: the repository's **Security** tab, then **Report a
vulnerability**. Don't open a public issue for them.

## What counts

`onemore serve` runs locally and is meant to be reached only from the machine
it runs on, or from a private overlay network you control — it holds your
training and health history, so anything that lets someone else reach or
read past that is in scope:

- **`onemore serve` binds `127.0.0.1` by default.** A way to reach it from
  off the machine without deliberately binding it to a non-loopback address,
  or a way to read or write outside its own data directory through the API,
  is a vulnerability.
- **The token gate.** Every write (`/import/strong`, `/import/health`,
  `/api/start`, `/api/advance`) is meant to require `ONEMORE_TOKEN` as
  `X-Token`. A way to write without it is a vulnerability.
- **The data directory boundary.** Everything onemore reads or writes
  resolves under `ONEMORE_DATA`. A way to make it read or write a path
  outside that directory is a vulnerability.

Not in scope: anything that needs an attacker to already run code as you,
and a non-loopback `--host` used to expose the app deliberately — GET routes
carry no authentication at all, so that bind is unsupported and the docs say
so (`docs/deploy.md`).
