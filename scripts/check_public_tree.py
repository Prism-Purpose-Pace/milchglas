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
- --message-files: the paths are commit-message files; only their content is term-scanned.
- --pre-push: the pre-push hook. Scans the pushed commit, not HEAD or the working tree: its
  tree as git holds it (path guard, file names, blob content), its commits not yet on
  origin/main (message, author, committer) and the pushed ref names. pre-commit exports the
  pushed ref (PRE_COMMIT_TO_REF, else PRE_COMMIT_LOCAL_BRANCH); outside a push it is HEAD.
  A push whose ref cannot be resolved is refused. pre-commit hands hooks only the first
  ref of a multi-ref push, so push one ref per `git push`. Without a denylist the push is
  refused (exit 2) when PRE_COMMIT_REMOTE_URL names the canonical repository; to any other
  remote, or in a manual run, the term scan is skipped with a notice.

Residual: matching is per line, so a term split across lines, encoded (base64, UTF-16
without BOM) or spelled with homoglyphs from another script is not detected.

Exit codes: 0 clean, 1 findings, 2 denylist missing or without patterns (with
--require-denylist, or with --pre-push to the canonical repository) or invalid.
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

# Sibling script (this directory is sys.path[0] when run as a script): one rule for
# "which commit is being pushed" in both pre-push hooks.
from check_push_ancestry import git_resolve, pushed_commit

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
# --pre-push: commits below this ref are published and cannot be rewritten.
PUSH_BASE = "origin/main"
# Only writers can push to this repository (contributors push to forks), so a --pre-push to
# it without a denylist must refuse: the skip would publish unscanned, with no CI before it.
CANONICAL_REPOSITORY = "Prism-Purpose-Pace/milchglas"
# Matched on the path tail, whatever the scheme, host, user, token or port: an URL form
# nobody listed must refuse, not skip. Case-insensitive like GitHub's owner/name.
CANONICAL_URL = re.compile(
    rf"[:/]{re.escape(CANONICAL_REPOSITORY)}(\.git)?/?\Z",
    re.IGNORECASE,
)
# What pre-commit exports about a push (pre-commit commands/hook_impl.py); any of these
# marks a push, so an unresolvable pushed ref there is refused rather than read as HEAD.
PUSH_VARIABLES = ("PRE_COMMIT_REMOTE_NAME", "PRE_COMMIT_TO_REF", "PRE_COMMIT_LOCAL_BRANCH")
# Ref names are published too; reports name the variable's role, never the ref itself.
REF_VARIABLES = (
    ("PRE_COMMIT_LOCAL_BRANCH", "local branch"),
    ("PRE_COMMIT_REMOTE_BRANCH", "remote branch"),
)


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
    """Prefer the environment (CI secret), fall back to the local file, else None.

    A source that parses to zero patterns counts as absent: an empty list would pass
    --require-denylist and skip the term scan without a word, so a mangled secret
    (whitespace, comments only) would turn the guard off while CI stays green.
    """
    if env.get(ENV_VAR, "").strip():
        return parse_denylist(env[ENV_VAR]) or None
    if file.is_file():
        return parse_denylist(file.read_text(encoding="utf-8")) or None
    return None


def main_checkout_denylist() -> Path | None:
    """The default denylist of the main checkout, also when run in a linked worktree.

    The denylist is git-ignored, so a linked worktree has no copy; without this lookup
    the term scan was skipped there behind a passing hook.
    """
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(common).parent / DEFAULT_DENYLIST


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


def run(
    paths: Sequence[str],
    patterns: Sequence[re.Pattern[str]] | None,
    root: Path,
    *,
    message_files: bool = False,
) -> list[str]:
    private = [] if message_files else path_violations(paths)
    report = [f"{p}: private path must not be tracked in the public repo" for p in private]
    if patterns is None:
        return report
    for path in paths:
        if path in private:
            continue
        if not message_files:
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


def tree_entries(commit: str) -> list[tuple[str, str, str]]:
    """(type, object id, path) of every blob and gitlink in the tree of `commit`."""
    out = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", commit],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    entries = []
    for record in out.split("\0"):
        if record:
            meta, _, path = record.partition("\t")  # "<mode> <type> <oid>" TAB path
            _mode, kind, oid = meta.split(" ")
            entries.append((kind, oid, path))
    return entries


def read_blobs(oids: Iterable[str]) -> dict[str, bytes]:
    """Content of each object from one `git cat-file --batch` ("<oid> <type> <size>" LF data LF)."""
    wanted = list(dict.fromkeys(oids))
    out = subprocess.run(
        ["git", "cat-file", "--batch"],
        input="".join(f"{oid}\n" for oid in wanted).encode(),
        check=True,
        capture_output=True,
    ).stdout
    blobs: dict[str, bytes] = {}
    pos = 0
    for oid in wanted:
        end = out.index(b"\n", pos)
        size = int(out[pos:end].split()[2])  # a missing object has no size: fails closed
        blobs[oid] = out[end + 1 : end + 1 + size]
        pos = end + size + 2
    return blobs


def tree_report(commit: str, patterns: Sequence[re.Pattern[str]] | None) -> list[str]:
    """`run` over the tree of `commit` as git holds it, not over the working tree."""
    entries = tree_entries(commit)
    private = path_violations(path for _, _, path in entries)
    report = [f"{p}: private path must not be tracked in the public repo" for p in private]
    if patterns is None:
        return report
    blobs = read_blobs(oid for kind, oid, path in entries if kind == "blob" and path not in private)
    for kind, oid, path in entries:
        if path in private:
            continue
        report.extend(format_hit(hit) for hit in name_violations(path, patterns))
        if kind == "blob":  # a symlink blob is its link text; a gitlink has no content here
            text = decode(blobs[oid])
            report.extend(format_hit(hit) for hit in term_violations(path, text, patterns))
    return report


def ref_violations(env: Mapping[str, str], patterns: Sequence[re.Pattern[str]]) -> list[str]:
    return [
        f"ref {label}: matches denylist pattern #{hit.pattern + 1}"
        for variable, label in REF_VARIABLES
        if env.get(variable)
        for hit in name_violations(env[variable], patterns)
    ]


def pre_push_report(
    env: Mapping[str, str], patterns: Sequence[re.Pattern[str]] | None
) -> list[str]:
    commit = pushed_commit(env, git_resolve)
    if commit is None:
        if any(variable in env for variable in PUSH_VARIABLES):
            return ["cannot determine the pushed ref, refusing"]  # HEAD would be another ref
        commit = "HEAD"  # a manual `pre-commit run --hook-stage pre-push`
    report = tree_report(commit, patterns)
    if patterns is not None:
        messages = commit_messages(f"{PUSH_BASE}..{commit}")
        report.extend(format_hit(hit) for hit in message_violations(messages, patterns))
        report.extend(ref_violations(env, patterns))
    return report


def pushes_to_canonical(env: Mapping[str, str]) -> bool:
    """Whether the remote pre-commit exports (PRE_COMMIT_REMOTE_URL) is the canonical repository."""
    return CANONICAL_URL.search(env.get("PRE_COMMIT_REMOTE_URL", "").strip()) is not None


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
    parser.add_argument(
        "--message-files",
        action="store_true",
        help="the paths are commit-message files: scan their content only (no path or name check)",
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="the pre-push hook: scan the pushed commit (tree, unpushed commits, ref names)",
    )
    args = parser.parse_args(argv)
    if args.pre_push and (args.paths or args.commit_messages or args.message_files):
        # Else they would be ignored silently, and the run would look like it checked them.
        parser.error("--pre-push scans the pushed ref and takes no paths or other scan flags")
    if args.message_files and not args.paths:
        # Else the tracked-files default would run with the path guard off.
        parser.error("--message-files needs at least one path")
    denylist = args.denylist
    if denylist == DEFAULT_DENYLIST and not denylist.is_file():
        denylist = main_checkout_denylist() or denylist
    try:
        patterns = load_denylist(denylist, os.environ)
    except DenylistError as exc:
        print(f"check-public-tree: {exc}", file=sys.stderr)
        return 2
    if patterns is None:
        if args.require_denylist:
            print("check-public-tree: no denylist (PUBLIC_DENYLIST or --denylist)", file=sys.stderr)
            return 2
        if args.pre_push and pushes_to_canonical(os.environ):
            print(
                "check-public-tree: a push to the canonical repository needs the denylist: "
                f"provide PUBLIC_DENYLIST or the main checkout's {DEFAULT_DENYLIST}",
                file=sys.stderr,
            )
            return 2
        print("check-public-tree: no denylist found, term scan skipped", file=sys.stderr)
    if args.pre_push:
        report = pre_push_report(os.environ, patterns)
    else:
        report = run(
            args.paths or tracked_files(), patterns, Path.cwd(), message_files=args.message_files
        )
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
