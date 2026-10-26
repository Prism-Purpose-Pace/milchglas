"""Milchglas never reads private event content, so none can leak.

Catalogue GATE-21.

A taint check follows private text from where it is read to where it could leak: a log
line, an exception message, a file, a response. This gate removes the source instead: no
string literal under src/ names a content-bearing iCalendar property, compared
case-insensitively as icalendar compares names. A property that is never read reaches no
sink, through however many helper functions, which a flow analysis that stops at a
function boundary cannot promise.

Two exceptions, each with its exact spelling: ATTENDEE in `_owner_replies` of
core/reduce.py, because the owner's PARTSTAT decides whether an event counts as declined
(FR-3), and the config key `summary` in config.py, which holds the feed's own fixed text.
Known limit: a name built at run time ("SUMM" + "ARY") and a loop over every property of an
event are not read; review covers both.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# RFC 5545 section 3.8 and RFC 7986: the event properties that carry text, people, places
# or links, plus the HTML description some clients add.
PRIVATE = frozenset(
    {
        "ATTACH",
        "ATTENDEE",
        "CATEGORIES",
        "COMMENT",
        "CONFERENCE",
        "CONTACT",
        "DESCRIPTION",
        "GEO",
        "IMAGE",
        "LOCATION",
        "ORGANIZER",
        "RELATED-TO",
        "RESOURCES",
        "STYLED-DESCRIPTION",
        "SUMMARY",
        "URL",
        "X-ALT-DESC",
    }
)
# (file under src/, function, literal as written): the names the spec requires.
ALLOWED = frozenset(
    {
        ("milchglas/core/reduce.py", "_owner_replies", "ATTENDEE"),
        ("milchglas/config.py", "", "summary"),
        ("milchglas/config.py", "parse", "summary"),
    }
)


def private_names(tree: ast.AST, function: str = "") -> list[tuple[str, int, str]]:
    """(enclosing function, line, literal) of every literal that names a private property."""
    found: list[tuple[str, int, str]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found += private_names(node, node.name)
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literal = node.value.strip()
            if literal.upper() in PRIVATE:
                found.append((function, node.lineno, literal))
        found += private_names(node, function)
    return found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('event.get("SUMMARY")', [("", 1, "SUMMARY")]),
        ('event["description"]', [("", 1, "description")]),
        ('def f(event):\n    return event.decoded(" Location ")', [("f", 2, "Location")]),
        (
            'def outer():\n    def inner(event):\n        return event["ATTENDEE"]',
            [("inner", 3, "ATTENDEE")],
        ),
        ('LINE = f"SUMMARY:{text}"', []),
        ('event.get("DTSTART")', []),
        ('"""SUMMARY and DESCRIPTION never reach the feed."""', []),
    ],
)
def test_private_property_names_are_found(
    source: str, expected: list[tuple[str, int, str]]
) -> None:
    assert private_names(ast.parse(source)) == expected


def test_src_names_no_private_property_beyond_the_exceptions() -> None:
    found = {
        (path.relative_to(SRC).as_posix(), function, literal): line
        for path in sorted(SRC.rglob("*.py"))
        for function, line, literal in private_names(ast.parse(path.read_text(encoding="utf-8")))
    }
    assert {key: line for key, line in found.items() if key not in ALLOWED} == {}
    # A stale exception would let the next read there pass unseen; it also proves the
    # scan reached the package.
    assert found.keys() >= ALLOWED
