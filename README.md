# Milchglas

> Frosted glass for your calendar: others see *that* you are busy — never *what* you are doing.

[![CI](https://github.com/philippsied/milchglas/actions/workflows/ci.yml/badge.svg)](https://github.com/philippsied/milchglas/actions/workflows/ci.yml)
[![CodeQL](https://github.com/philippsied/milchglas/actions/workflows/codeql.yml/badge.svg)](https://github.com/philippsied/milchglas/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/philippsied/milchglas/badge)](https://scorecard.dev/viewer/?uri=github.com/philippsied/milchglas)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Milchglas (German for *frosted glass*) reads private CalDAV calendars — for example on
Nextcloud — strictly read-only, reduces every event to an anonymous time block and
publishes one busy-only ICS feed. Subscribe to that feed wherever your availability
matters — a work calendar, a booking tool — without handing it a single title,
location or attendee.

> [!IMPORTANT]
> **Status: pre-alpha.** The specification and toolchain are in place; the pipeline is
> being built. Do not use it in production yet. Progress: [docs/spec.md](docs/spec.md).

## Why

Calendar sharing is access control, not redaction. Once a consumer may read a calendar it
sees everything, and "private" flags are honoured inconsistently across servers and
clients. Milchglas does the redaction itself, before anything leaves your server, and
never writes to a source calendar.

## How it works

```mermaid
flowchart LR
    S[(CalDAV calendars<br/>read-only)] -->|calendar-query + expand| F[filter]
    F --> R[reduce] --> C[clip] --> G[round] --> M[merge] --> E[emit]
    E -->|atomic write| O[/busy-only ICS feed/]
    O -->|/f/&lt;token&gt;.ics| X[subscribers]
```

- **Filter** drops cancelled events, events marked free (`TRANSP:TRANSPARENT`) and
  invitations you declined.
- **Reduce** keeps only start, end, tentative and all-day — immediately after parsing.
- **Clip, round, merge** limit the feed to a time window, round to a 15-minute grid in
  local time and merge overlapping and adjacent blocks.
- **Emit** writes minimal events (`UID`, `DTSTAMP`, `DTSTART`, `DTEND`, `SUMMARY`,
  `TRANSP`, `STATUS`) in UTC. Output is deterministic: an unchanged source yields a
  byte-identical feed, so subscribers never see duplicates.
- **Fail-safe:** if a source is unreachable, the last good feed stays in place; an
  outage never produces an empty feed.

## Target consumers

| Consumer | Integration |
|---|---|
| OX App Suite (e.g. mailbox.org) | iCal feed subscription as a second calendar |
| meetergo | read-only ICS calendar for conflict checks |
| Any RFC 5545 client | subscribe to the feed URL |

Compatibility is being verified; the open items are tracked in
[docs/spec.md §11](docs/spec.md#11-verification-plan-for-assumptions).

## Configuration (planned)

Non-secret settings live in one `config.json` and take effect on the next refresh:

| Key | Default | Meaning |
|---|---|---|
| `tz` | `Europe/Berlin` | time zone for grid rounding |
| `window_days` | `28` | feed horizon from today |
| `grid_minutes` | `15` | rounding grid |
| `summary` | `Blocker Privat` | title of every busy block |
| `ttl_seconds` | `900` | refresh interval hint |
| `allday_mode`, `tentative_mode` | see spec | how all-day and tentative events are shown |
| `owner_emails` | — | addresses whose declined invitations are skipped |
| `calendars[]` | — | `{href, name, enabled}` per source calendar |
| `token` | — | secret part of the feed URL |

Secrets and paths come only from the environment: `CALDAV_URL` (DAV root),
`CALDAV_USER`, `CALDAV_SECRET` (an app password with read access), `MILCHGLAS_VAR_DIR`,
`MILCHGLAS_LOG_LEVEL`.

## Deployment (planned)

One host-independent Python core, several ways to run it
([docs/spec.md §9](docs/spec.md#9-deployment-options)): **B** Docker containers
(`web` + `refresher`, the default), **A** systemd on a VPS, **C** shared Python web
hosting, **D** a PHP port that must produce byte-identical feeds.

## Development

```bash
uv sync
uv run pytest
pre-commit install --install-hooks
```

Everything else — gates, conventions, the privacy rules for contributions — is in
[CONTRIBUTING.md](CONTRIBUTING.md) and [TOOLING.md](TOOLING.md).

## Security

The feed URL contains a secret token; treat it like a password. Wrong tokens and unknown
paths get an identical `404`. Please report vulnerabilities privately — see
[SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Philipp Sieder
