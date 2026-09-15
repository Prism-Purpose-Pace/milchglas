# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Keep private material out of the public tree.

Checks over the tracked (or given) files:

- path guard: no path inside a private directory (.claude/, .local/, .worktrees/ at any
  depth) or under docs/plans/ or docs/evidence/; case-insensitive and normalised, so
  `./.claude/x` or `Docs/Plans/x` do not slip through;
- term guard: no file name, symlink target, file line or commit (message, author,
  committer) matches a denylist regex. Content is decoded leniently (UTF-16 by BOM,
  otherwise UTF-8 with replacement), NFKD-normalised, and stripped of control, format,
  line-separator and combining characters (and Hangul fillers) before it is split into
  lines. The denylist itself is private: it comes from the PUBLIC_DENYLIST environment
  variable (a CI secret) or a local file (default .claude/context/public-denylist.txt).
  Reports name file, line and pattern index only - never the matched text - so public CI
  logs cannot leak what is guarded. Denylist patterns must be ASCII (enforced: exit 2).

Residual: matching is per line, so a term split across lines, encoded (base64, UTF-16
without BOM) or spelled with homoglyphs from another script is not detected.

Exit codes: 0 clean, 1 findings, 2 denylist missing (with --require-denylist) or invalid.
"""

from __future__ import annotations

import argparse
import codecs
import os
import posixpath
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

PRIVATE_DIRS = frozenset({".claude", ".local", ".worktrees"})
PRIVATE_PREFIXES = ("docs/plans/", "docs/evidence/")
PRIVATE_NAMES = frozenset({"claude.local.md"})
DEFAULT_DENYLIST = Path(".claude/context/public-denylist.txt")
ENV_VAR = "PUBLIC_DENYLIST"
# One record per commit, NUL-terminated (git refuses NUL in messages, so no body can
# forge a record boundary): sha, author and committer each on one line, then the body.
LOG_FORMAT = "%h%n%an <%ae>%n%cn <%ce>%n%B%x00"
# Characters that render as nothing (or as a line break) and could hide a term.
HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cn", "Cs", "Zl", "Zp", "Mn", "Mc", "Me"})
HANGUL_FILLERS = frozenset(map(chr, (0x115F, 0x1160, 0x3164, 0xFFA0)))
KEPT_CONTROLS = frozenset("\n\t")


class DenylistError(ValueError):
    """A denylist entry is not a valid regular expression."""


@dataclass(frozen=True)
class Hit:
    where: str
    line: int  # 0 = the file name itself
    pattern: int


def is_private(path: str) -> bool:
    parts = posixpath.normpath(path.replace("\\", "/")).casefold().split("/")
    return (
        any(part in PRIVATE_DIRS for part in parts[:-1])
        or "/".join(parts).startswith(PRIVATE_PREFIXES)
        or parts[-1] in PRIVATE_NAMES
    )


def path_violations(paths: Iterable[str]) -> list[str]:
    return [p for p in paths if is_private(p)]


def compile_patterns(sources: Iterable[str]) -> list[re.Pattern[str]]:
    patterns = []
    for number, source in enumerate(sources, start=1):
        if not source.isascii():
            # Matched text is NFKD-folded, so a non-ASCII pattern would silently never match.
            msg = f"denylist pattern #{number} must be ASCII"
            raise DenylistError(msg)
        try:
            patterns.append(re.compile(source, re.IGNORECASE))
        except re.error as exc:
            msg = f"denylist pattern #{number} is not a valid regex ({exc.msg})"
            raise DenylistError(msg) from exc
    return patterns


def parse_denylist(text: str) -> list[re.Pattern[str]]:
    # A byte-order mark (editor or UI paste) would otherwise glue onto pattern #1.
    lines = (line.strip() for line in text.removeprefix(codecs.BOM_UTF8.decode()).splitlines())
    return compile_patterns(line for line in lines if line and not line.startswith("#"))


def load_denylist(file: Path, env: Mapping[str, str]) -> list[re.Pattern[str]] | None:
    """Prefer the environment (CI secret), fall back to the local file, else None."""
    if env.get(ENV_VAR, "").strip():
        return parse_denylist(env[ENV_VAR])
    if file.is_file():
        return parse_denylist(file.read_text(encoding="utf-8"))
    return None


def decode(data: bytes) -> str:
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8", errors="replace")


def visible(text: str) -> str:
    """NFKD-normalise and drop every character that renders as nothing (keeps \\n, \\t)."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if ch in KEPT_CONTROLS
        or (unicodedata.category(ch) not in HIDDEN_CATEGORIES and ch not in HANGUL_FILLERS)
    )


def term_violations(where: str, text: str, patterns: Sequence[re.Pattern[str]]) -> list[Hit]:
    # Normalise BEFORE splitting: separators like \x1c or U+2028 must not cut a term.
    return [
        Hit(where, number, index)
        for number, line in enumerate(visible(text).split("\n"), start=1)
        for index, pattern in enumerate(patterns)
        if pattern.search(line)
    ]


def name_violations(path: str, patterns: Sequence[re.Pattern[str]]) -> list[Hit]:
    return [Hit(path, 0, index) for index, p in enumerate(patterns) if p.search(visible(path))]


def message_violations(
    messages: Iterable[tuple[str, str]], patterns: Sequence[re.Pattern[str]]
) -> list[Hit]:
    hits: list[Hit] = []
    for sha, body in messages:
        hits.extend(term_violations(f"commit {sha}", body, patterns))
    return hits


def format_hit(hit: Hit) -> str:
    if hit.line == 0:
        return f"{hit.where}: file name matches denylist pattern #{hit.pattern + 1}"
    return f"{hit.where}:{hit.line}: matches denylist pattern #{hit.pattern + 1}"


def run(paths: Sequence[str], patterns: Sequence[re.Pattern[str]] | None, root: Path) -> list[str]:
    private = path_violations(paths)
    report = [f"{p}: private path must not be tracked in the public repo" for p in private]
    if patterns is None:
        return report
    for path in paths:
        if path in private:
            continue
        report.extend(format_hit(hit) for hit in name_violations(path, patterns))
        file = root / path
        if file.is_symlink():
            text = str(file.readlink())  # git publishes the link text, not the target
        else:
            try:
                text = decode(file.read_bytes())
            except (FileNotFoundError, IsADirectoryError):
                continue  # deleted in the staged set, or a directory
            except OSError:
                report.append(f"{path}: unreadable, cannot be checked")  # fail closed
                continue
        report.extend(format_hit(hit) for hit in term_violations(path, text, patterns))
    return report


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True, text=True
    ).stdout
    return [path for path in out.split("\0") if path]


def parse_log(out: str) -> list[tuple[str, str]]:
    """Split `git log --format=LOG_FORMAT` output into (sha, identities + message)."""
    messages = []
    for record in out.split("\0"):
        sha, _, identities_and_body = record.lstrip("\n").partition("\n")
        if sha:
            messages.append((sha, identities_and_body))
    return messages


def commit_messages(rev: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", f"--format={LOG_FORMAT}", rev], check=True, capture_output=True, text=True
    ).stdout
    return parse_log(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep private material out of the public tree.")
    parser.add_argument("paths", nargs="*", help="files to check (default: git ls-files)")
    parser.add_argument("--denylist", type=Path, default=DEFAULT_DENYLIST)
    parser.add_argument(
        "--require-denylist", action="store_true", help="exit 2 when no denylist is available"
    )
    parser.add_argument(
        "--commit-messages",
        metavar="REV",
        help="also scan commit messages and identities reachable from REV",
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
