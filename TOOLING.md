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
| Public-tree guard (private paths; private terms in file names, content, commit messages and identities when a denylist is present) | pre-commit + pre-push | `scripts/check_public_tree.py` (stdlib) |
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

## CI (GitHub Actions)

Every action is pinned to a full commit SHA; every workflow starts from empty token
permissions and grants per job only what it needs.

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | push to `main`, pull requests | `lint`, `typecheck`, `test`, `public-guard`, `secret-scan` (required checks), `osv-scan`, `dependency-review` (PRs), `zizmor` (workflow security lint) |
| `codeql.yml` | push, pull requests, weekly | CodeQL for Python and Actions |
| `scorecard.yml` | push to `main`, weekly | OpenSSF Scorecard, results to code scanning + badge |
| `release-please.yml` | push to `main` | release PR with changelog and version bump from conventional commits |

`public-guard` reads the maintainer's private denylist from the `PUBLIC_DENYLIST`
secret (stored as Actions secret and as Dependabot secret) and reports only file, line
and pattern number — never the matched text. Without the secret the job fails, except
on pull requests from forks, which check paths only; the full check runs again on the
push to `main`.

Repository settings that files cannot express (security features, ruleset, labels,
project board) are applied with `uv run --script scripts/github_bootstrap.py --owner
<owner> --repo <repo>` (`--dry-run` to preview).

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
  `--tags`). The protection against
  publishing pre-public history is that maintainer clones hold none, plus the `tags`
  ruleset that lets only the release workflow create tags.
- Release PRs are opened with `GITHUB_TOKEN` and trigger no CI; the maintainer merges
  them through the admin bypass after review. A personal token is not an option: the
  `tags` ruleset would block the release tag it creates.
