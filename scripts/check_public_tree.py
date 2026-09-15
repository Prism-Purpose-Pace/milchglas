# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Keep private material out of the public tree.

Two checks over the tracked (or given) files:

- path guard: nothing under a private prefix (.claude/, .local/, docs/plans/, ...);
- term guard: no line matches a denylist regex. The denylist itself is private: it
  comes from the PUBLIC_DENYLIST environment variable (a CI secret) or a local file
  (default .claude/context/public-denylist.txt). Reports name file, line and pattern
  index only - never the matched text - so public CI logs cannot leak what is guarded.

Exit codes: 0 clean, 1 findings, 2 denylist missing (with --require-denylist) or invalid.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

PRIVATE_PREFIXES = (".claude/", ".local/", ".worktrees/", "docs/plans/", "docs/evidence/")
PRIVATE_NAMES = frozenset({"CLAUDE.local.md"})
DEFAULT_DENYLIST = Path(".claude/context/public-denylist.txt")
ENV_VAR = "PUBLIC_DENYLIST"


class DenylistError(ValueError):
    """A denylist entry is not a valid regular expression."""


@dataclass(frozen=True)
class Hit:
    where: str
    line: int
    pattern: int


def path_violations(paths: Iterable[str]) -> list[str]:
    return [p for p in paths if p.startswith(PRIVATE_PREFIXES) or Path(p).name in PRIVATE_NAMES]


def compile_patterns(sources: Iterable[str]) -> list[re.Pattern[str]]:
    patterns = []
    for number, source in enumerate(sources, start=1):
        try:
            patterns.append(re.compile(source, re.IGNORECASE))
        except re.error as exc:
            msg = f"denylist pattern #{number} is not a valid regex ({exc.msg})"
            raise DenylistError(msg) from exc
    return patterns


def parse_denylist(text: str) -> list[re.Pattern[str]]:
    lines = (line.strip() for line in text.splitlines())
    return compile_patterns(line for line in lines if line and not line.startswith("#"))


def load_denylist(file: Path, env: Mapping[str, str]) -> list[re.Pattern[str]] | None:
    """Prefer the environment (CI secret), fall back to the local file, else None."""
    if env.get(ENV_VAR, "").strip():
        return parse_denylist(env[ENV_VAR])
    if file.is_file():
        return parse_denylist(file.read_text(encoding="utf-8"))
    return None


def term_violations(where: str, text: str, patterns: Sequence[re.Pattern[str]]) -> list[Hit]:
    return [
        Hit(where, number, index)
        for number, line in enumerate(text.splitlines(), start=1)
        for index, pattern in enumerate(patterns)
        if pattern.search(line)
    ]


def message_violations(
    messages: Iterable[tuple[str, str]], patterns: Sequence[re.Pattern[str]]
) -> list[Hit]:
    hits: list[Hit] = []
    for sha, body in messages:
        hits.extend(term_violations(f"commit {sha}", body, patterns))
    return hits


def format_hit(hit: Hit) -> str:
    return f"{hit.where}:{hit.line}: matches denylist pattern #{hit.pattern + 1}"


def run(paths: Sequence[str], patterns: Sequence[re.Pattern[str]] | None, root: Path) -> list[str]:
    private = path_violations(paths)
    report = [f"{p}: private path must not be tracked in the public repo" for p in private]
    if patterns is None:
        return report
    for path in paths:
        if path in private:
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
            continue  # deleted in the staged set, a directory, or binary
        report.extend(format_hit(hit) for hit in term_violations(path, text, patterns))
    return report


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True, text=True
    ).stdout
    return [path for path in out.split("\0") if path]


def commit_messages(rev: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", "--format=%h%x00%B%x1e", rev], check=True, capture_output=True, text=True
    ).stdout
    messages = []
    for record in out.split("\x1e"):
        sha, _, body = record.lstrip("\n").partition("\0")
        if sha:
            messages.append((sha, body))
    return messages


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep private material out of the public tree.")
    parser.add_argument("paths", nargs="*", help="files to check (default: git ls-files)")
    parser.add_argument("--denylist", type=Path, default=DEFAULT_DENYLIST)
    parser.add_argument(
        "--require-denylist", action="store_true", help="exit 2 when no denylist is available"
    )
    parser.add_argument(
        "--commit-messages", metavar="REV", help="also scan commit messages reachable from REV"
    )
    args = parser.parse_args(argv)
    try:
        patterns = load_denylist(args.denylist, os.environ)
    except DenylistError as exc:
        print(f"check-public-tree: {exc}", file=sys.stderr)
        return 2
    if patterns is None:
        if args.require_denylist:
            print("check-public-tree: no denylist (PUBLIC_DENYLIST or --denylist)", file=sys.stderr)
            return 2
        print("check-public-tree: no denylist found, term scan skipped", file=sys.stderr)
    report = run(args.paths or tracked_files(), patterns, Path.cwd())
    if patterns is not None and args.commit_messages:
        messages = commit_messages(args.commit_messages)
        report.extend(format_hit(hit) for hit in message_violations(messages, patterns))
    for line in report:
        print(line, file=sys.stderr)
    if report:
        print(f"check-public-tree: {len(report)} finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
