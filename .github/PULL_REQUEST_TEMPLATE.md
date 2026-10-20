## What and why

<!-- One concern per pull request. Link the issue: "Closes #…" -->

## How it was verified

<!-- Commands you ran and what they showed; for a fix: the regression test and that it
failed before the change. -->

## Checklist

- [ ] Title follows Conventional Commits (`feat:`, `fix:`, `docs:` …) — it becomes the release note
- [ ] Tests added or updated; `uv run pytest` passes locally
- [ ] `python3 scripts/gates.py` passes (commit-stage gates; see CONTRIBUTING.md)
- [ ] `docs/spec.md` / README updated if behaviour or configuration changed
- [ ] No new runtime dependency, or it is pure Python and justified above

## Privacy checklist

- [ ] No real calendar data, feed URLs with tokens, hostnames or credentials in code, tests, fixtures, logs or this description
- [ ] Event content (title, description, location, attendees) cannot reach the feed, logs, errors or state
