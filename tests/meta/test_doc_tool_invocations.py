"""Contributor-facing docs must invoke Python dev tools through the lock.

A bare `ruff` / `mypy` / `basedpyright` / `pytest` / `ty` / `mutmut` command resolves to
whatever binary is on PATH, not the uv.lock version the hooks and CI run, so a contributor
(human or AI agent) who follows such a doc reintroduces version drift.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LOCKED_TOOLS = frozenset({"ruff", "mypy", "basedpyright", "pytest", "ty", "mutmut"})
OWNED_DOCS = ("README.md", "CONTRIBUTING.md", "CLAUDE.md", "TOOLING.md")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
COMMAND_SEPARATOR = re.compile(r"&&|\|\||;|\|")


def _starts_with_locked_tool(segment: str) -> bool:
    words = segment.split()
    # A lone word is a tool *name* (e.g. "`ruff`"), not a command.
    return len(words) > 1 and words[0] in LOCKED_TOOLS


def bare_tool_invocations(text: str) -> list[str]:
    """Return every inline-code command segment that starts with a locked tool."""
    return [
        segment.strip()
        for span in CODE_SPAN.findall(text)
        for segment in COMMAND_SEPARATOR.split(span)
        if _starts_with_locked_tool(segment)
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("run `uv run ruff check --fix x`", []),
        ("run `ruff check --fix x`", ["ruff check --fix x"]),
        ("`uv run ruff check x && ruff format x`", ["ruff format x"]),
        ("`uv run --frozen mypy`", []),
        ("the `mypy-strict` hook", []),
        ("`pytest -m contract`", ["pytest -m contract"]),
        ("the tool name `ruff` alone", []),
    ],
)
def test_bare_tool_invocations_discriminates(text: str, expected: list[str]) -> None:
    assert bare_tool_invocations(text) == expected


@pytest.mark.parametrize("doc", OWNED_DOCS)
def test_owned_docs_invoke_python_tools_through_uv(doc: str) -> None:
    assert bare_tool_invocations((REPO / doc).read_text(encoding="utf-8")) == []
