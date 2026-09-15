# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Commit-size gate — WARN on soft caps, BLOCK on hard caps (shared-index sweep guard).

Runs at the pre-commit stage (`verbose: true`, `always_run: true`):
    uv run --script scripts/check_commit_size.py

Enforces the deterministic half of CONTRIBUTING.md § Commits ("Keep commits small and
coherent ..."). Two tiers:

  - SOFT caps (5 files / 100 LOC) -> WARN, exit 0. "Bundle only when causally inseparable"
    is a judgment the hook cannot make, so the soft tier only advises.
  - HARD caps (20 files / 800 LOC) -> BLOCK, exit 1. A staged change this large is almost
    always a pathless sweep across workstreams — the shared-index hazard when parallel
    agents share one working tree, where `git add -A` / `git commit -a` in one session
    absorbs another session's staged files. Split per concern, or set COMMIT_SIZE_OK=1 for
    a deliberate large commit (bulk rename, generated files, vendoring).
  - MERGE commits are EXEMPT from BOTH tiers, detected as `$GIT_DIR/MERGE_HEAD` existing
    while `git commit` runs. The caps exist to keep AUTHORED diffs reviewable; a merge is
    reconciliation, not authored content, and it cannot be split, so "split per concern" is
    advice nobody can act on. Where a same-day merge-back of a busy trunk is mandated, every
    such merge would otherwise need the override for a purely mechanical reason — measured on
    one real merge-back: 41 files / 4982 LOC after the trunk had moved 33 commits.

    The discriminator is "is this commit a merge", never "is this commit big". Still BLOCKED
    by construction, because none of them writes MERGE_HEAD: `git merge --squash`, rebase
    (REBASE_HEAD), cherry-pick and revert (their own heads). Each lands an AUTHORED diff.

    `check_commit_msg.py` bypasses merges too, but by commit-message TITLE PREFIX: it runs at
    the commit-msg stage and is handed the message, while this gate runs at the pre-commit
    stage and never sees one. Two differently-shaped merge tests are a consequence of that
    stage split, not drift.

Counting (parity with the rule's carve-outs):
  - Pure renames / mode-only changes (numstat `0  0`) are EXEMPT from the file cap.
  - Binary files count as one file, zero LOC.
  - LOC = added + removed across text files.

The rule's third dimension ("2 distinct change-types") is intentionally NOT checked:
change-type is semantic (it lives in the commit message, unavailable at this stage).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FILE_CAP = 5
LOC_CAP = 100
BLOCK_FILE_CAP = 20
BLOCK_LOC_CAP = 800
OVERRIDE_ENV = "COMMIT_SIZE_OK"
MERGE_HEAD = "MERGE_HEAD"


def analyze(numstat: str) -> tuple[int, int, list[str], list[str]]:
    """Parse `git diff --cached --numstat -M` -> (files, loc, warnings, blockers)."""
    files = 0
    loc = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_s, removed_s = parts[0], parts[1]
        if added_s == "-" or removed_s == "-":  # binary file
            files += 1
            continue
        added, removed = int(added_s), int(removed_s)
        if added == 0 and removed == 0:  # pure rename / mode-only — exempt
            continue
        files += 1
        loc += added + removed

    warnings: list[str] = []
    if files > FILE_CAP:
        warnings.append(f"{files} files staged (> {FILE_CAP}) — split per concern")
    if loc > LOC_CAP:
        warnings.append(f"{loc} LOC staged (> {LOC_CAP}) — split per concern")

    blockers: list[str] = []
    if files > BLOCK_FILE_CAP:
        blockers.append(f"{files} files staged (> {BLOCK_FILE_CAP} hard cap)")
    if loc > BLOCK_LOC_CAP:
        blockers.append(f"{loc} LOC staged (> {BLOCK_LOC_CAP} hard cap)")
    return (files, loc, warnings, blockers)


def merge_head_present(git_dir: str | Path) -> bool:
    """True when `<git_dir>/MERGE_HEAD` exists as a file — git is mid-merge.

    Pure: the caller resolves the directory, which keeps this testable against a plain
    temporary directory. A fixture repository is deliberately NOT an option — pre-commit
    exports GIT_DIR into hook processes, and a `git init` that inherits it re-initialises
    the real repository.
    """
    return (Path(git_dir) / MERGE_HEAD).is_file()


def staged_numstat() -> str:  # pragma: no cover
    """Thin git I/O wrapper (kept separate so analyze() stays pure and testable)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--numstat", "-M"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def in_merge() -> bool:  # pragma: no cover
    """Thin git I/O wrapper: is THIS worktree mid-merge?

    `--git-dir`, never `--git-common-dir`: MERGE_HEAD is a per-worktree file, so a linked
    worktree's merge lives under `.git/worktrees/<name>/` while the common dir stays clean.
    Reading the common dir would miss exactly the worktree merge-back this exemption exists
    for.

    A non-zero exit means "unknown", and unknown must not open a gate — it degrades to False
    so the caps still apply.

    `pragma: no cover` marks this untraceable in-process, NOT untested. Every in-process case
    monkeypatches this function, so the resolution above would go unexecuted and the suite
    would certify a DISARMED gate green — measured, not feared: an unconditional True, a
    `--git-common-dir` read, and a dropped `.strip()` each passed at "100% line coverage".
    The suite therefore also runs this script as a subprocess against a hand-built gitdir
    carrying a `commondir` file, which is what makes the two rev-parse forms resolve apart.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return merge_head_present(result.stdout.strip())


def main() -> int:
    if in_merge():
        print(
            "commit-size: merge commit (MERGE_HEAD present) — size caps do not apply.",
            file=sys.stderr,
        )
        return 0
    _files, _loc, warnings, blockers = analyze(staged_numstat())
    for w in warnings:
        print(f"commit-size: warning: {w}", file=sys.stderr)
    if warnings:
        print(
            "  (CONTRIBUTING.md § Commits — bundle only if causally inseparable; renames exempt)",
            file=sys.stderr,
        )
    if not blockers:
        return 0
    if os.environ.get(OVERRIDE_ENV) == "1":
        print(
            f"commit-size: hard cap exceeded but {OVERRIDE_ENV}=1 set — allowing.", file=sys.stderr
        )
        return 0
    for b in blockers:
        print(f"commit-size: BLOCKED: {b}", file=sys.stderr)
    print(
        "  Likely a pathless sweep across workstreams (shared-index hazard) — split",
        file=sys.stderr,
    )
    print(f"  per concern, or set {OVERRIDE_ENV}=1 for a deliberate large commit.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())  # pragma: no cover
