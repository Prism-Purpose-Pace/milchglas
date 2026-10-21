# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Keep one fact in one place: the spec's config keys and its numeric thresholds.

Reads the documents under --root (default: the current directory) and checks:

(a) config keys: the key set K is the backticked keys in the `**Config (`config.json`,
    non-secret):**` paragraph of docs/spec.md (calendars[] {href, name, enabled} also
    yields the nested keys href, name, enabled). CLAUDE.md's `config.json` key list must
    equal K (a missing and an extra key are both findings). docs/architecture.md and
    docs/threat-model.md, where present, must not name a config key outside K. A document
    "names a config key" when a backticked lowercase identifier is
    - a member of a key list: a run of backticked identifiers joined only by commas,
      "and"/"or" or a "(default)" note, with at least two members in K; or
    - written next to the noun key, field or setting ("a plain `token` key").
    A bare container or tool name (`web`, `refresher`) matches neither shape. Residual:
    a key named alone, without the noun, is not recognisable by shape and not caught.
(b) placeholder lint: docs/spec.md must not say "stated bound/score/threshold/value"; an
    acceptance criterion states its number.

Absent docs/architecture.md and docs/threat-model.md are skipped with a notice (they live
on another branch until it merges). The disk is read, not the index; the pre-commit hook
runs after pre-commit stashed unstaged changes, so there the two are the same.

Exit codes: 0 clean, 1 findings (`path:line: reason`), 2 a required file or the spec
anchor is missing (a missing anchor must never pass silently).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

SPEC = "docs/spec.md"
AGENT_GUIDE = "CLAUDE.md"
OPTIONAL_DOCS = ("docs/architecture.md", "docs/threat-model.md")
ANCHOR = "**Config (`config.json`, non-secret):**"
PLACEHOLDER = re.compile(r"stated (bound|score|threshold|value)", re.IGNORECASE)
SPAN = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
# `tz`, `calendars[]`, `calendars[] {href, name, enabled}`: a top-level key, optionally
# followed by the keys nested under it.
KEY = re.compile(r"([a-z][a-z0-9_]*)(?:\[\])?(?:\s*\{([^{}]*)\})?")
LIST_SEPARATOR = re.compile(r"\s*(?:\([^()]*\)\s*)?(?:,\s*(?:(?:and|or)\s+)?|(?:and|or)\s+)")
NOUN_NEXT = re.compile(r"`([a-z][a-z0-9_]*)`\s+(?:key|field|setting)s?\b")
NOUN_BEFORE = re.compile(r"\b(?:key|field|setting)s?\s+`([a-z][a-z0-9_]*)`")
MIN_LIST_MEMBERS = 2


class AnchorMissingError(Exception):
    """A file or text the check is anchored on is absent: the check cannot run."""


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def parse_key(span: str) -> tuple[str, list[str]] | None:
    """Return (key, nested keys) when a backtick span has the shape of a config key."""
    found = KEY.fullmatch(span.strip())
    if found is None:
        return None
    nested = [name.strip() for name in (found.group(2) or "").split(",") if name.strip()]
    return found.group(1), nested


def config_keys(spec: str) -> tuple[int, set[str], set[str]]:
    """Return (anchor line, top-level keys, nested keys) from the spec's Config paragraph."""
    start = spec.find(ANCHOR)
    if start < 0:
        msg = f"{SPEC}: anchor {ANCHOR!r} not found"
        raise AnchorMissingError(msg)
    end = spec.find("\n\n", start)
    top: set[str] = set()
    nested: set[str] = set()
    for span in SPAN.finditer(spec[start + len(ANCHOR) : end if end >= 0 else len(spec)]):
        parsed = parse_key(span.group(1))
        if parsed:
            top.add(parsed[0])
            nested.update(parsed[1])
    if not top:
        msg = f"{SPEC}: no backticked key after the Config anchor"
        raise AnchorMissingError(msg)
    return line_of(spec, start), top, nested


def blank_fences(text: str) -> str:
    """Blank fenced code blocks (keeping line breaks) so their backticks cannot pair up."""
    return FENCE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def key_lists(text: str) -> list[list[tuple[int, str]]]:
    """Return runs of backticked key-shaped identifiers joined as a list, as (offset, key)."""
    runs: list[list[tuple[int, str]]] = []
    previous_end = -1
    for span in SPAN.finditer(text):
        parsed = parse_key(span.group(1))
        if parsed is None:
            continue  # its backticks sit in the next gap, which then cannot be a separator
        between = text[previous_end : span.start()]
        joined = previous_end >= 0 and "\n\n" not in between and LIST_SEPARATOR.fullmatch(between)
        if not joined:
            runs.append([])
        runs[-1].append((span.start(), parsed[0]))
        previous_end = span.end()
    return runs


def named_keys(text: str, known: set[str]) -> list[tuple[int, str]]:
    """Return (line, key) for every config key outside `known` that `text` names."""
    text = blank_fences(text)
    found = {
        (line_of(text, offset), name)
        for run in key_lists(text)
        if sum(name in known for _, name in run) >= MIN_LIST_MEMBERS
        for offset, name in run
    }
    for pattern in (NOUN_NEXT, NOUN_BEFORE):
        found.update((line_of(text, m.start(1)), m.group(1)) for m in pattern.finditer(text))
    return sorted((line, name) for line, name in found if name not in known)


def guide_keys(guide: str) -> tuple[int, list[tuple[int, str]]]:
    """Return the CLAUDE.md `config.json` bullet's line and its (line, key) members."""
    start = guide.find("`config.json`")
    if start < 0:
        return 1, []
    stop = re.search(r"\n\s*\n|\n- ", guide[start:])
    block = guide[start : start + stop.start()] if stop else guide[start:]
    members = [
        (line_of(guide, start + span.start(1)), parsed[0])
        for span in SPAN.finditer(block)
        if (parsed := parse_key(span.group(1)))
    ]
    return line_of(guide, start), members


def key_findings(spec_line: int, top: set[str], nested: set[str], root: Path) -> list[str]:
    report: list[str] = []
    guide = (root / AGENT_GUIDE).read_text(encoding="utf-8", errors="replace")
    guide_line, members = guide_keys(guide)
    listed = {name for _, name in members}
    report.extend(
        f"{AGENT_GUIDE}:{guide_line}: config key `{name}` is in the spec"
        f" ({SPEC}:{spec_line}) but not in this list"
        for name in sorted(top - listed)
    )
    report.extend(
        f"{AGENT_GUIDE}:{line}: config key `{name}` is not in the spec's key list"
        f" ({SPEC}:{spec_line})"
        for line, name in members
        if name not in top
    )
    for doc in OPTIONAL_DOCS:
        path = root / doc
        if not path.is_file():
            print(f"skipped: {doc} not in tree", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        report.extend(
            f"{doc}:{line}: config key `{name}` is not in the spec's key list ({SPEC}:{spec_line})"
            for line, name in named_keys(text, top | nested)
        )
    return report


def placeholder_findings(spec: str) -> list[str]:
    return [
        f'{SPEC}:{line_of(spec, m.start())}: placeholder "{m.group(0)}": state the number'
        for m in PLACEHOLDER.finditer(spec)
    ]


def run(root: Path) -> list[str]:
    for required in (SPEC, AGENT_GUIDE):
        if not (root / required).is_file():
            msg = f"{required}: required file not found under {root}"
            raise AnchorMissingError(msg)
    spec = (root / SPEC).read_text(encoding="utf-8", errors="replace")
    spec_line, top, nested = config_keys(spec)
    return key_findings(spec_line, top, nested, root) + placeholder_findings(spec)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One fact, one place: spec drift check.")
    parser.add_argument("--root", type=Path, default=Path(), help="tree to check (default: .)")
    try:
        report = run(parser.parse_args(argv).root)
    except AnchorMissingError as exc:
        print(f"check-spec-drift: {exc}", file=sys.stderr)
        return 2
    for line in report:
        print(line, file=sys.stderr)
    if report:
        print(f"check-spec-drift: {len(report)} finding(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
