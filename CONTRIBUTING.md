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

## Issues and the backlog

Work is planned in issues on the Milchglas project board. Each issue has an issue type
(`Feature`, `Task` or `Bug`), a Priority, a milestone (`MVP`, `Pilot run` or `Later`) and,
once planned, a sprint. Labels name the area (`area: …`), cross-cutting concerns
(`security`, `ci`, `documentation`, `dependencies`) and two states: `maintainer-action`
for steps that need the maintainer's accounts or platform, and `later` for work outside
the MVP that waits for a maintainer decision. Priorities are not labels.

**Ready.** An issue enters a sprint only when all of these hold:

1. Type, Priority and milestone are set.
2. The context names the spec items it serves (FR, NFR, AC, D, Q, V) and whether they are
   MVP or later.
3. The scope lists what is in and what is out.
4. Every acceptance criterion is one checkbox that cites its ID in
   [docs/test-catalogue.md](docs/test-catalogue.md); new behaviour gets a `planned` row
   there first.
5. Dependencies are linked as "blocked by" or as a parent, not only named in the text.
6. A step that needs the maintainer's accounts, hands or platform carries
   `maintainer-action` and names the exact step.
7. It fits into one sprint; larger work is split into sub-issues.

**Done.** An issue is closed as completed only when all of these hold:

1. Every checkbox is ticked, and each cited test ID has the status `exists` in the
   catalogue; a manual ID has its record in `docs/consumers.md` or the runbook.
2. CI is green on `main`: lint, strict type check, tests with branch coverage of at
   least 90 %, the gates and the pure-wheel check.
3. No event content reaches the feed, a log line or test output (see below).
4. The pull request was rebase-merged after an approval of its last push.
5. `docs/spec.md`, the catalogue and the README match any changed behaviour.
6. A criterion that was not finished lives in a linked follow-up issue, and the unticked
   checkbox says where it moved.

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
uv run --script scripts/install_push_guard.py
```

The last line installs `.git/hooks/pre-push.legacy`: pre-commit hands a pre-push hook one
ref at most, so this entry reads git's own list and scans every ref of a push
([TOOLING.md](TOOLING.md)). A maintainer clone refuses commits until it is installed.

| Purpose | Command |
|---|---|
| Tests (branch coverage ≥ 90 %) | `uv run pytest` |
| Single test | `uv run pytest --no-cov tests/unit/test_package.py` |
| CalDAV contract tests (needs a Baïkal container) | `uv run pytest -m contract --no-cov` |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |
| Type-check (strict, blocking) | `uv run mypy` |
| Type-check (advisory) | `uv run ty check` |
| Mutation testing (advisory) | `uv run --group mutation mutmut run` · survivors: `uv run --group mutation mutmut results` |
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
- Test IDs live in `docs/test-catalogue.md`: a new behaviour gets its row there first,
  and its test cites the ID.
- A behaviour that reads as an example of use can be a Gherkin scenario under
  `tests/features/`, run by pytest-bdd. The scenario carries its row ID as its only ID
  tag (`@ORCH-FETCH-2`), and exactly one function binds it:
  `@scenario("<path>", "<name>")` on `test_<id>_…` (`test_orch_fetch_2_…`). A feature
  carries its issue as `@id:<number>`. A scenario that is specified but not built yet
  carries `@backlog`: it may stay unbound, and a bound one is skipped; the change that
  builds it removes the tag. Properties, fuzzing and gates stay plain pytest. GATE-22
  checks the binding and the form: a feature description, at most five steps, exactly one
  `When`, a `Then`, Given-When-Then in order, a Background of at most four Givens, a Rule
  only for two scenarios or more, no name or step that names a click, a button, an
  endpoint, HTTP, JSON or SQL, `Examples` that match the `<variables>` of an outline, no
  comment (put the reason in the scenario's description), only the tags `@id:<number>`, `@backlog`, `@long-running` (a marker:
  register it in `pyproject.toml` first) and row IDs. A failing scenario names file,
  line and rule: `uv run pytest tests/meta/test_feature_lint.py`.
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
- A pull request needs one approval of its last push; the maintainer reviews. The criteria
  for maintainers and automated reviewers are in [REVIEW.md](REVIEW.md).
- Fill in the pull request template, including the privacy checklist.
- `main` is protected: pull requests are rebase-merged, history stays linear. Squash is
  disabled because a squash commit replaces the commits' authors with the merging
  account's profile name; a rebase keeps the authors but still records that profile
  name as committer, so the merging account needs its full name set.

## Licence

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE) of this project.
