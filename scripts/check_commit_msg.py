# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Commit-message convention gate — stdlib replacement for gitlint.

Runs at the pre-commit `commit-msg` stage:
    uv run --script scripts/check_commit_msg.py <COMMIT_MSG_FILE>

Zero install (uv is already a repo dependency) and no isolated env build — unlike the
upstream gitlint hook whose `pip install .` breaks in the sandbox (and even outside it).

Parity with the former gitlint setup (.gitlint + gitlint 0.19.1 active defaults). Every
active gitlint rule is reproduced; every dropped rule is justified below.

  BLOCKING (exit 1)
    T1  title-max-length            len <= 72
    T8  title-min-length            len >= 5
    T2  title-trailing-whitespace
    T6  title-leading-whitespace
    T3  title-trailing-punctuation  last char not in  . ? ! , ; :
    T4  title-hard-tab
    T5  title-must-not-contain-word wip / tmp / TODO / FIXME (whole word, case-insensitive)
    CT1 conventional-commits        <type>(scope)?!?: <desc>, type in TYPES
    B1  body-max-line-length        len <= 80
    B2  body-trailing-whitespace
    B3  body-hard-tab
    B4  body-first-line-empty       blank line between title and body

  BYPASS (exit 0 — gitlint's ignore-*-commits INTENT, deliberately not its predicate)
    A title whose LOWERCASED form starts with one of BYPASS_PREFIXES. Every prefix ends
    in a SPACE, and that space is the word boundary: `Merge branch 'x'` bypasses while
    `merged the thing` stays linted. A colon form (`merge: …`) is NOT a bypass — it is
    linted like any other commit, and CT1 then carries an explaining hint.

    Measured divergence from gitlint 0.19.1 (gitlint-core/gitlint/git.py:206-222 uses a
    case-SENSITIVE startswith with no trailing space), 2026-07-29:
      `merge branch main`  -> bypassed here, linted upstream
      `Merged the thing`   -> linted here, bypassed upstream
    Edge-only: zero of this repo's 1053 commit titles are judged differently by the two.
    Rejected alternatives: widen the predicate, adopt gitlint's exactly, add `merge` to
    TYPES.

  ADDED (CONTRIBUTING.md § Commits — WARN only, never blocks)
    breaking marker (`type!:` or a `BREAKING CHANGE:` footer) needs explicit approval
    scope missing on an otherwise-valid conventional title (narrow-scope nudge)

  DROPPED (justified)
    B5 body-min-length / B6 body-is-missing  — in gitlint `ignore` list (kept off)
    T7 / B8 / I1-I4 match-regex              — regex=None upstream, no-op
    B7 body-changed-file-mention             — no files configured, no-op
    M1 author-valid-email                    — author identity is a git-config property,
        not a message property; it is validated at the git/commit layer. A pure message
        linter would need a subprocess for ~zero real coverage (any configured git user
        matches `^[^@ ]+@[^@ ]+\\.[^@ ]+`). Intentionally not reproduced.

  VERIFIED PARITY — matrix-scoped, and no longer re-runnable
    Exit-code identical to gitlint 0.19.1 across the 19-fixture migration matrix — T5
    word-boundary matching, scissors / `--verbose` diff stripping, and every bypass mode
    included. The claim is scoped to that matrix, NOT universal: the bypass predicate
    above diverges outside it by design (see BYPASS). Treat this as a dated migration
    record rather than a live check — the oracle cannot be re-run here, because gitlint
    is not installed and pypi is blocked in-sandbox.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = ("feat", "fix", "refactor", "docs", "test", "chore", "perf", "ci", "build", "style")
TITLE_MAX = 72
TITLE_MIN = 5
BODY_MAX = 80
FORBIDDEN_WORDS = ("wip", "tmp", "todo", "fixme")
TRAILING_PUNCT = ".?!,;:"

COMMENT_CHAR = "#"
SCISSORS = "# ------------------------ >8 ------------------------"
BYPASS_PREFIXES = ("merge ", "revert ", "fixup! ", "squash! ", "amend! ")

# A title that LOOKS like a merge/revert but missed the bypass above gets told why:
# without it the only diagnostic is CT1, which names Conventional Commits rather than
# the real cause, and a half-completed merge is a poor state to hand over.
BYPASS_LOOKALIKES = ("merge", "revert", "fixup", "squash", "amend")
BYPASS_HINT = (
    " — a merge/revert title bypasses only in git's own form (`Merge …`, `Revert …`);"
    " `merge: …` is linted like any other commit"
)

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>" + "|".join(TYPES) + r")"
    r"(?P<scope>\([^()\r\n]+\))?"
    r"(?P<breaking>!)?"
    r": (?P<desc>.+)$"
)
BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def message_lines(raw: str) -> list[str]:
    """Normalize a raw commit message the way gitlint does before linting.

    Cuts the `git commit --verbose` diff (everything from the scissors marker on),
    drops git comment lines, and strips leading blank lines.
    """
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.rstrip() == SCISSORS:
            lines = lines[:i]
            break
    lines = [ln for ln in lines if not ln.startswith(COMMENT_CHAR)]
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def check(raw: str) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Non-empty errors => the commit is rejected."""
    lines = message_lines(raw)
    if not lines:
        return (["empty commit message"], [])

    title = lines[0]
    if title.lower().startswith(BYPASS_PREFIXES):
        return ([], [])

    errors: list[str] = []
    warnings: list[str] = []
    stripped = title.strip()

    # --- Title rules (T*) ---
    if title != title.rstrip():
        errors.append("T2 title has trailing whitespace")
    if title != title.lstrip():
        errors.append("T6 title has leading whitespace")
    if len(title) > TITLE_MAX:
        errors.append(f"T1 title too long ({len(title)}>{TITLE_MAX})")
    if len(stripped) < TITLE_MIN:
        errors.append(f"T8 title too short ({len(stripped)}<{TITLE_MIN})")
    if "\t" in title:
        errors.append("T4 title contains a hard tab")
    if stripped and stripped[-1] in TRAILING_PUNCT:
        errors.append(f"T3 title ends with punctuation ({stripped[-1]!r})")
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{word}\b", title, re.IGNORECASE):
            errors.append(f"T5 title contains forbidden word ({word})")

    # --- Conventional Commits (CT1) + repo-added scope/breaking nudges ---
    m = CONVENTIONAL_RE.match(title)
    if m is None:
        detail = f"<type>(scope)?: desc (type in {'|'.join(TYPES)})"
        if title.split()[0].rstrip(":!\"'").lower() in BYPASS_LOOKALIKES:
            detail += BYPASS_HINT
        errors.append(f"CT1 not Conventional Commits: {detail}")
    else:
        if m.group("scope") is None:
            warnings.append("scope missing — name the area, e.g. feat(parser): ...")
        if m.group("breaking"):
            warnings.append("breaking '!' marker — needs explicit approval (major bump)")

    # --- Body rules (B*) ---
    if len(lines) > 1:
        if lines[1].strip():
            errors.append("B4 no blank line between title and body")
        for n, line in enumerate(lines[1:], start=2):
            if len(line) > BODY_MAX:
                errors.append(f"B1 body line {n} too long ({len(line)}>{BODY_MAX})")
            if line != line.rstrip():
                errors.append(f"B2 body line {n} has trailing whitespace")
            if "\t" in line:
                errors.append(f"B3 body line {n} contains a hard tab")

    if BREAKING_FOOTER_RE.search(raw):
        warnings.append("BREAKING CHANGE footer — needs explicit approval (major bump)")

    return (errors, warnings)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_commit_msg.py <commit-msg-file>", file=sys.stderr)
        return 2
    raw = Path(argv[1]).read_text(encoding="utf-8")
    errors, warnings = check(raw)
    for w in warnings:
        print(f"commit-msg: warning: {w}", file=sys.stderr)
    if errors:
        print("commit-msg: rejected —", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print("  (convention: CONTRIBUTING.md § Commits)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))  # pragma: no cover
