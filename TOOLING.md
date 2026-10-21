# Tooling — `python` stack

**Single version source:** every Python tool (ruff, mypy, ty, pytest, pytest-cov,
hypothesis) is an entry of the `dev` dependency group, pinned by `uv.lock`. Hooks and CI
call them via `uv run --frozen`, so hook, terminal and CI run the identical version.
Bump with `uv lock --upgrade-package <tool>`, never via a hook `rev:`. Remote `rev:`
pins remain only for the non-Python tools below (`pre-commit autoupdate`); Dependabot
bumps `uv.lock` and the SHA-pinned GitHub Actions weekly.

## Local gates (pre-commit)

| Gate | Stage | Tool (version source) |
|------|-------|------------|
| Hygiene (eof, trailing-ws, large-file, merge-conflict, case, symlinks, yaml/json/toml) | pre-commit | pre-commit-hooks v6.0.0 |
| Private-key detection (catches PuTTY, SSH2, OpenVPN and partial keys that gitleaks misses) | pre-commit | pre-commit-hooks v6.0.0 |
| Lint (`select = ALL`; TID251 bans I/O imports in `src/milchglas/core/`, PTH123 flags builtin `open()`; a dynamic `__import__` is review-only) + format | pre-commit | ruff (`uv.lock`) |
| Lock in sync with `pyproject.toml` | pre-commit + pre-push | `uv lock --check` |
| Workflow schema validation | pre-commit | check-jsonschema 0.37.4 |
| Fast secret scan (staged diff) | pre-commit | gitleaks v8.30.1 |
| Public-tree guard (private paths; private terms in file names, content, commit messages and identities when a denylist is present; a push to the canonical repository requires it; every pushed ref through `pre-push.legacy`) | pre-commit + pre-push | `scripts/check_public_tree.py` (stdlib) |
| Push guard installed (maintainer clone: `.git/hooks/pre-push.legacy` present and current, pre-commit's hook passes `--hook-dir`) | pre-commit | `scripts/install_push_guard.py --check` (stdlib) |
| Pushed ref descends from the public root commit | pre-push | `scripts/check_push_ancestry.py` (stdlib) |
| Commit size (warn 5/100, block 20/800) | pre-commit | `scripts/check_commit_size.py` (stdlib) |
| PEP 723 script-deps CVE audit | pre-commit (warn) + pre-push (block) | `scripts/audit_script_deps.py` (stdlib) |
| Commit message convention (title ≤72, body ≤80/line) | commit-msg | `scripts/check_commit_msg.py` (stdlib) |
| Type-check (`--strict` + extra error codes, spec AC-12) | pre-push | mypy (`uv.lock`) |
| Unit tests + branch coverage ≥ 90 % (marker `contract` excluded) | pre-push | pytest + pytest-cov (`uv.lock`) |
| Deep secret scan (full history, verified) | pre-push | trufflehog (installed binary; `rev:` informational) |
| Dependency CVE scan (blocking) | pre-push | osv-scanner v2.3.8 |

- **Advisory, not a gate:** `uv run ty check` — a fast second opinion; ty is pre-1.0.
- **Not used:** bandit — ruff `S` implements 73 of its 75 checks; B613 (trojan source)
  is covered by ruff `PLE2502`, the rest (pytorch, huggingface, django) do not apply.

Install once:

```bash
uv tool install pre-commit --with pre-commit-uv
brew install gitleaks trufflehog osv-scanner
pre-commit install --install-hooks
```

Run the gates through `python3 scripts/gates.py`, which picks a writable cache directory
before handing off to `uv run --frozen pre-commit`. This repository configures no cache
path anywhere, so a fresh clone works on any host: the script prefers an absolute value
already in the environment, then `~/.cache/<tool>`, then the repo-local
`.claude/.cache/<tool>`, then the system temp directory. It runs on plain `python3`
because `uv` needs that cache before it can run anything, and it discards a relative
value — relative paths are resolved by the process that reads them, with that process's
CWD, which is how pre-commit's `uv venv` child once failed with `Operation not
permitted`.

## CI (GitHub Actions)

Every action is pinned to a full commit SHA; every workflow starts from empty token
permissions and grants per job only what it needs.

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | push to `main`, pull requests | `lint`, `typecheck`, `test`, `public-guard`, `secret-scan`, `osv-scan`, `dependency-review` (PRs), `zizmor` (workflow security lint) — all required checks |
| `codeql.yml` | push, pull requests, weekly | CodeQL for Python and Actions; the `main` ruleset blocks a merge on an alert of severity error or a security alert of high or above |
| `pr-triage.yml` | pull requests from this repository | path labels (`.github/labeler.yml`) and the author as assignee; Dependabot does the same through `dependabot.yml`, fork PRs are triaged by hand |
| `scorecard.yml` | push to `main`, weekly | OpenSSF Scorecard, results to code scanning + badge |
| `release-please.yml` | push to `main` | release PR with changelog and version bump from conventional commits; on a release, sdist and wheel with their provenance (`.sigstore.json`, `.intoto.jsonl`) as release assets |

`public-guard` reads the maintainer's private denylist from the `PUBLIC_DENYLIST`
secret (stored as Actions secret and as Dependabot secret) and reports only file, line
and pattern number — never the matched text; a file-name hit prints the path, which
holds the term, but CI runs after the push, so that path is already public. Without the secret the job fails, except
on pull requests from forks, which check paths only; the full check runs again on the
push to `main`. Commit messages and identities are scanned for the range a change adds
(`base..head` on a pull request, `before..sha` on a push), never the whole history:
commits GitHub creates itself carry the account's display name, and one such commit
(`a995e8f`) would otherwise keep every later run red. Every commit GitHub writes takes the
merging account's **profile name**: a squash commit as its author, a rebased commit as its
committer. That profile name must therefore be the maintainer's full name, or the push run
after each merge fails the guard. Merges use rebase, which keeps each commit's own author.

Repository settings that files cannot express (security features, rulesets, labels,
project board, actions that must be pinned to a full commit SHA, approval of every
outside contributor's fork workflows) are applied with `uv run --script
scripts/github_bootstrap.py --owner <owner> --repo <repo>` (`--dry-run` to preview).
For an organization owner it first reads the organization's Actions policy and stops
before any write when the organization withholds pull-request creation from GitHub
Actions: the repository setting cannot override it, and release-please could not open
release PRs.

## Maintainer operations (`gh`)

Commands only the maintainer runs; agents never push or merge. `N` is a pull request
number, `ID` a workflow run id, `<owner>` the account or organization.

Merge your own pull request once every required check is green. `--admin` uses the
bypass of the `review` ruleset and skips only the approval; the `main` ruleset has no
bypass, so the checks still bind.

```bash
gh pr merge N --rebase --admin
```

A release PR is opened with `GITHUB_TOKEN`, so its checks do not start on their own.
Close and reopen it to run them, wait for the required checks, then merge it:

```bash
gh pr close N && gh pr reopen N
gh pr checks N --required --watch
gh pr merge N --rebase --admin
```

Re-run only the failed jobs of a run:

```bash
gh run list --repo <owner>/milchglas --limit 5
gh run rerun ID --failed
```

After the repository moves to another owner, point the remote at it, re-apply the
settings (reading the organization policy needs `admin:org`), check that the
`PUBLIC_DENYLIST` secret survived for both apps, then drop the extra scope again.
"Auto-add to project" on the project board has no API; enable it in the web UI.

```bash
git remote set-url origin https://github.com/<owner>/milchglas.git
gh auth refresh -h github.com -s admin:org,project
uv run --script scripts/github_bootstrap.py --owner <owner> --repo milchglas
gh secret list --repo <owner>/milchglas
gh secret list --repo <owner>/milchglas --app dependabot
gh auth refresh -h github.com -r admin:org
```

Verifying a release asset: see [SECURITY.md](SECURITY.md).

## Residual risk (read once)

- Local gates are bypassable by design, not only via `--no-verify`: the environment can
  re-configure the tools a hook runs (`COVERAGE_RCFILE` lowers the coverage floor,
  `UV_ENV_FILE` injects pytest options), and `# pragma: no cover` excludes code in a
  review-visible way. The push hook unsets `PYTEST_ADDOPTS` to stop the most common
  accident, not as enforcement — CI plus the `main` ruleset (required checks, no
  force-push) is the enforcer.
- The public-tree guard matches line by line after Unicode normalisation (NFKD, control,
  format, separator and combining characters removed); a term split across lines,
  encoded (base64, UTF-16 without BOM) or written with homoglyphs from another script is
  not detected — review covers that residual.
- The pre-push ancestry hook requires the public root to be the ONLY root of a pushed
  ref, so a merge that pulls in older history is refused. It sees one ref per push:
  pre-commit evaluates only the first ref of a multi-ref push (`--all`, `--mirror`,
  `--tags`). The protection against publishing pre-public history is that maintainer
  clones hold none — this repository contains no other history to tag.
- The pre-push public-tree guard scans what the push transfers, not HEAD: every commit of
  the pushed ref that no remote-tracking ref of the remote holds (`git rev-list <commit>
  --not --remotes=<remote>`, pre-commit's rule for "new"), with its message, identities and
  every path and blob it adds or changes, plus the ref names. A term added and removed
  again inside the push is found; content the remote already holds is not rescanned.
  pre-commit hands hooks only the first ref of a multi-ref push and none for a push whose
  refs carry no new commit (a branch or tag name, or an annotated tag's own message, would
  be published unscanned). So every pushed ref is also scanned through the legacy entry:
  `scripts/install_push_guard.py` writes `.git/hooks/pre-push.legacy`, which pre-commit's
  generated hook runs first with git's argv and its full stdin, and
  `check_public_tree.py --pre-push-refs` reads each line (ref names, each tag object,
  what the peeled commit transfers); a non-zero exit stops the push. The shim is per clone
  and unversioned, so a commit-stage preflight (`install_push_guard.py --check`) fails in a
  maintainer clone that lacks it, and when pre-commit's hook stops passing `--hook-dir`:
  run as a git config hook (git 2.54+), pre-commit skips the legacy hook
  (`hook_impl._run_legacy`), and the route would go silent. That failure is the cue to move
  the guard to its own git config hook (`hook.<name>.event = pre-push`), which git hands every
  ref line as well. pre-commit's classic hook passes the flag on any git version.
  The `--pre-push` hook stays as the first-ref fallback. The ancestry hook above still sees
  one ref: push one ref per `git push` there.
  Known limits: the every-ref scan runs only while `pre-push.legacy` exists. It is gone after
  `pre-commit install -f` (pre-commit suggests that flag when it finds the legacy file), and it
  is not demanded in a clone without the denylist or the private repo. A tree whose guard
  predates `--pre-push-refs` cannot push through the shim. So push from the main checkout,
  with `install_push_guard.py --check` at exit 0, and rerun the installer after every
  `pre-commit install`.
- The `tags` ruleset freezes every tag: nobody moves or deletes one, and nobody holds
  a bypass (an admin disables the ruleset to repair a wrong tag). Creating a tag stays
  open to writers, because release-please tags with `GITHUB_TOKEN` and GitHub rejects
  GitHub Actions as a bypass actor — on a user account and in this organization alike
  (HTTP 422). So anyone with write access can still create a tag; the mitigation is the
  absent pre-public history above, not a rule.
- Two rulesets guard `main`. `main` (no bypass) holds the required checks, linear
  history and the pull-request requirement for everyone, admins included; `review`
  requires one approval of the last push and is the only ruleset admins may bypass,
  because a solo maintainer cannot approve their own pull requests. A bypass skips every
  unmet rule of its ruleset, so keeping the checks in a ruleset without bypass is what
  keeps them binding.
- Release PRs are opened with `GITHUB_TOKEN` and trigger no CI; the maintainer closes and
  reopens one to run the required checks, then approves and merges it. `GITHUB_TOKEN`
  also keeps the release tag attributable to the workflow rather than to a person's
  token.
