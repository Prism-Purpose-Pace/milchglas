# Contributing to Milchglas

Thanks for helping. Milchglas is small on purpose: one pipeline, one feed, no admin UI.
Contributions that keep it that way are the easiest to merge.

## Before you start

- **Bugs and features:** open an issue first (templates guide you). For anything larger
  than a typo, wait for a maintainer reply before investing time.
- **Security issues:** never in public — see [SECURITY.md](SECURITY.md).
- **Scope:** [docs/spec.md](docs/spec.md) is the source of truth. Build only the MVP
  column of its scope table; backlog items need a maintainer decision first. The spec
  marks settled decisions `[DECIDED D-n]` (do not re-decide silently), open product
  questions `[OPEN Q-n]` (implement the stated default, keep it configurable) and
  unverified assumptions `[VERIFY V-n]` (do not build irreversibly on them).

## Privacy rules for every contribution

Milchglas handles private calendars. These rules are not negotiable:

- Never paste real calendar data, feed URLs with live tokens, hostnames of your
  servers or credentials into issues, pull requests, tests or logs.
- Event content (titles, descriptions, locations, attendees) must never reach the feed,
  logs, exception messages, state files or test output. Reduce events to
  `(start, end, tentative, allday)` right after parsing.
- Fixtures are synthetic events, derived from real CalDAV server output (e.g. the
  Baïkal contract run) rather than hand-written in the parser's own dialect.

## Development setup

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and for the local gates
`pre-commit` plus gitleaks, trufflehog and osv-scanner.

```bash
uv sync
uv tool install pre-commit --with pre-commit-uv
pre-commit install --install-hooks
```

| Purpose | Command |
|---|---|
| Tests (branch coverage ≥ 90 %) | `uv run pytest` |
| Single test | `uv run pytest --no-cov tests/unit/test_package.py` |
| CalDAV contract tests (needs a Baïkal container) | `uv run pytest -m contract --no-cov` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |
| Type-check (strict, blocking) | `uv run mypy` |
| Type-check (advisory) | `uv run ty check` |
| All local gates (commit stage, then push stage) | `python3 scripts/gates.py` · `python3 scripts/gates.py run --hook-stage pre-push --all-files` |

Always call the Python tools through `uv run`: the lock file pins the exact versions
that the hooks and CI use. The one exception is `scripts/gates.py`, which runs on plain
`python3` because it picks the cache directory that `uv` itself needs — see its module
docstring. Gate details: [TOOLING.md](TOOLING.md).

## Tests

- Every `feat` ships at least one test; every `fix` ships a regression test that fails
  without the fix.
- Write the failing test first. Each gating assertion needs a case that must pass and
  one that must fail.
- Core behaviour gets golden tests: overlap and adjacency merge, grid rounding, DST
  transitions in Europe/Berlin, all-day, multi-day, tentative, cancelled, declined,
  RRULE with EXDATE and overridden instances, window clipping, UID determinism, line
  folding. Emitted ICS must re-parse with `icalendar`.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `feat|fix|refactor|docs|test|chore|perf|ci|build|style`,
imperative mood, subject ≤ 72 characters, body lines ≤ 80 explaining *why*. A local
`commit-msg` hook checks this. Keep commits small and coherent (the size gate warns
above 5 files / 100 lines). Release notes and version bumps are generated from these
messages by release-please, so the type matters: `feat` → minor, `fix` → patch.

## Pull requests

- Branch from `main`; one concern per pull request.
- All required checks must be green: lint, typecheck, test, public-guard, secret-scan,
  osv-scan, dependency-review and zizmor; CodeQL must report no new alert of severity
  error and no security alert of high or above.
- A pull request needs one approval of its last push; the maintainer reviews.
- Fill in the pull request template, including the privacy checklist.
- `main` is protected: pull requests are rebase-merged, history stays linear. Squash is
  disabled because a squash commit replaces the commits' authors with the merging
  account's profile name; a rebase keeps the authors but still records that profile
  name as committer, so the merging account needs its full name set.

## Licence

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE) of this project.
