# CLAUDE.md

Guidance for AI coding agents (Claude Code and similar) working in this repository.
Human contributors: [CONTRIBUTING.md](CONTRIBUTING.md) holds the same rules.

Milchglas reads CalDAV calendars read-only, reduces every event to anonymous time
intervals and publishes a busy-only ICS feed. Spec: [docs/spec.md](docs/spec.md).
**Status: pre-feature** — package skeleton and toolchain in place (`src/milchglas/`,
`tests/`); no pipeline code yet. Toolchain rationale: [TOOLING.md](TOOLING.md).

## Stack

- Python 3.12 (container image `python:3.12-slim` for deployment option B), managed with **uv**.
- Runtime dependencies (`[project.dependencies]` in `pyproject.toml`) stay **pure Python**
  (NFR-O3) so every deployment option shares one codebase.

## Commands (canonical — do not infer alternatives)

| Purpose | Command |
|---|---|
| Install | `uv sync` |
| Test | `uv run pytest` (branch coverage ≥ 90 %; `contract` tests excluded) · single: `uv run pytest --no-cov tests/unit/test_package.py` · contract only: `uv run pytest -m contract --no-cov` |
| Lint / format | `uv run ruff check` · `uv run ruff format` |
| Type-check | `uv run mypy` (strict, blocking) · advisory: `uv run ty check` |
| Run (planned) | `uv run python -m milchglas refresh` (one idempotent run) · `--loop --interval 900` (refresher) |
| Gates | commit stage `python3 scripts/gates.py` · push stage `python3 scripts/gates.py run --hook-stage pre-push --all-files` — green means both |

## Spec markers (binding)

- **[DECIDED D-n]** — do not re-decide silently.
- **[OPEN Q-n]** — implement the stated default, keep it configurable.
- **[VERIFY V-n]** — do not build irreversibly on it before its check passes.
- **MVP vs LATER** — build only the MVP column of spec §6; backlog items (spec §12) need
  an explicit maintainer decision first.

## Architecture

One-directional pipeline of pure functions (spec §8):

```
fetch (CalDAV calendar-query + server-side expand) → filter → reduce → clip → round → merge → emit → atomic write
```

Planned layout: `src/milchglas/sources/` (CalDAV client, parsing), `core/` (model,
reduce, emit — pure, no I/O; ruff bans I/O imports there), `web/` (WSGI app serving
`/f/<token>.ics` and `/healthz`), `refresh.py` (orchestration), `state.py` (last success
/ last error); `deploy/<option>/`; `docs/`.

- Non-secret config: one `config.json` (`tz`, `window_days`, `grid_minutes`, `summary`,
  `ttl_seconds`, `allday_mode`, `tentative_mode`, `owner_emails`, `calendars[]`,
  `token_sha256`, `uid_salt`); changes apply on the next refresh without restart. Only
  the SHA-256 of the feed token is stored, never the token itself (spec D-14).
- Secrets and paths only via environment: `CALDAV_URL`, `CALDAV_USER`, `CALDAV_SECRET`,
  `MILCHGLAS_VAR_DIR`, `MILCHGLAS_LOG_LEVEL`.

## Invariants that are easy to break

- **No private content anywhere.** Titles, descriptions, locations and attendees never
  reach disk, logs, metrics, exception messages or test output. Reduce each event to
  `(start, end, tentative, allday)` immediately after parsing. Tests grep the feed and
  every log line for fixture titles.
- **Redaction lives only in Milchglas.** Never rely on the server's `CLASS`; a
  `CLASS:PRIVATE` event that reaches Milchglas still produces a block (the read-only
  service user never receives one; confidential ones arrive stripped, spec D-3).
- **Exclude** `STATUS:CANCELLED`, `TRANSP:TRANSPARENT` on timed events (all-day events:
  spec Q-12), and events where a configured owner e-mail has `PARTSTAT=DECLINED`.
- **Rounding** in the configured local time zone: start floored, end ceiled to the grid;
  then merge overlapping **and adjacent** intervals — no two output blocks may touch.
- **Output:** only `UID, DTSTAMP, DTSTART, DTEND, SUMMARY, TRANSP, STATUS`; timed
  blocks in UTC (no `VTIMEZONE`), all-day as `VALUE=DATE`, `TRANSP:OPAQUE`, RFC 5545
  line folding.
- **Determinism:** `UID = sha256(salt|start|end)[:32]@milchglas`; `DTSTAMP` is the last
  content change, never "now". Unchanged source ⇒ byte-identical feed.
- **Never overwrite the last good feed on failure:** atomic replace only on full success;
  on error keep the old file and record the error in state.
- **Web surface:** a wrong token and any unknown path return an identical 404 (same body,
  constant-time compare); the right token gets `200 text/calendar; charset=utf-8` with
  `ETag`, `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`. Tokens never appear in
  logs.
- **Health:** only `/healthz` (200 if the last success is < 60 min old and `token_sha256` is
  readable, else 503, spec Q-23; no body
  data). One stdout log stream, SIGTERM finishes the current write before exit.

## Working agreements

- Smallest change that serves the task; tests first (see CONTRIBUTING.md § Tests).
- Conventional commits; never push, never `--no-verify`.
- `.claude/` and `.local/` are git-ignored maintainer space: never add files from there
  (the public-tree guard rejects them in pre-commit and CI).
