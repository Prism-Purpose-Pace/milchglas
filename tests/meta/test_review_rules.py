"""The review rules in REVIEW.md and AGENTS.md must say the same thing.

Catalogue GATE-19.

REVIEW.md defines every check once, as a bullet `- **RV-<area>-<n>** (<level>) ...`. AGENTS.md is
what Codex reads, and Codex shows only P0 and P1, so it lists every `BLOCK` rule inline under its
priority. Nothing else ties the two files together: a rule could be added, renamed or re-levelled
in one and go unnoticed in the other. Four checks close that:

- rules: every rule in REVIEW.md has a unique ID and one of the levels `BLOCK P0`, `BLOCK P1`,
  `WARN`, `INFO`; a file without a rule is an error, so the scan cannot go silently empty;
- undefined: every rule ID that REVIEW.md or AGENTS.md cites is defined in REVIEW.md;
- priorities: AGENTS.md lists exactly the `BLOCK` rules, each under the priority that is its
  level (P0 for `BLOCK P0`, P1 for `BLOCK P1`), and lists no `WARN` or `INFO` rule;
- gates: every test-catalogue ID that REVIEW.md names is a row with status `exists`, so a
  `Gate:` claim cannot point at a test that is only planned.

Known limit: the two files are compared by ID and level, not by wording.
"""

import re
from pathlib import Path

import pytest

from tests.meta.test_catalogue_traceability import CATALOGUE, parse_catalogue, resolve

REPO = Path(__file__).resolve().parents[2]
LEVELS = frozenset({"BLOCK P0", "BLOCK P1", "WARN", "INFO"})
RULE = r"RV-(?:[A-Z]+-)?\d+"
DEFINITION = re.compile(rf"^- \*\*({RULE})\*\* \(([^)]*)\)", re.MULTILINE)
CITATION = re.compile(rf"(?<![\w-])({RULE})(?![\w-])")
HEADING = re.compile(r"#{2,3} (.*)")
PRIORITY = re.compile(r"(P[01])\b")
EXPECTED = {"BLOCK P0": "P0", "BLOCK P1": "P1"}

type Problems = dict[str, list[str]]


def parse_rules(review: str) -> dict[str, str]:
    """Rule ID to default level; a duplicate ID or an unknown level is an error."""
    rules: dict[str, str] = {}
    for rule_id, level in DEFINITION.findall(review):
        if rule_id in rules or level not in LEVELS:
            msg = f"{rule_id}: duplicate ID or level {level!r}"
            raise ValueError(msg)
        rules[rule_id] = level
    if not rules:
        msg = "no rules in the review file"
        raise ValueError(msg)
    return rules


def listed(agents: str) -> dict[str, str]:
    """Rule ID to priority, for every ID under a `P0` or `P1` heading of the agents file."""
    listing: dict[str, str] = {}
    priority: str | None = None
    for line in agents.splitlines():
        if heading := HEADING.fullmatch(line):
            found = PRIORITY.match(heading[1])
            priority = found[1] if found else None
        elif priority:
            for rule_id in CITATION.findall(line):
                if listing.setdefault(rule_id, priority) != priority:
                    msg = f"{rule_id}: listed under two priorities"
                    raise ValueError(msg)
    return listing


def problems(review: str, agents: str, rows: dict[str, str]) -> Problems:
    rules = parse_rules(review)
    listing = listed(agents)
    expected = {i: EXPECTED[level] for i, level in rules.items() if level in EXPECTED}
    unresolved, gates = resolve(rows, review)
    cited = {*CITATION.findall(review), *CITATION.findall(agents)}
    return {
        "undefined": sorted(cited - rules.keys()),
        "missing": sorted(expected.keys() - listing.keys()),
        "wrong_priority": sorted(i for i in expected if i in listing and listing[i] != expected[i]),
        "not_blocking": sorted(i for i in listing if i in rules and i not in expected),
        "gates": [*unresolved, *sorted(i for i in gates if rows[i] != "exists")],
    }


NONE: Problems = {
    "undefined": [],
    "missing": [],
    "wrong_priority": [],
    "not_blocking": [],
    "gates": [],
}

# --- the real files ------------------------------------------------------------------------


def test_review_and_agents_files_agree() -> None:
    rows = parse_catalogue((REPO / CATALOGUE).read_text(encoding="utf-8"))
    review = (REPO / "REVIEW.md").read_text(encoding="utf-8")
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert problems(review, agents, rows) == NONE


# --- the checks on synthetic files ---------------------------------------------------------
# The areas ALPHA and BETA are not in the real catalogue, so these strings are no citation.

ROWS = {"ALPHA-1": "exists", "ALPHA-2": "planned"}
REVIEW = """\
- **RV-1** (BLOCK P1) First. Gate: ALPHA-1.
- **RV-CORE-1** (BLOCK P0) Second.
- **RV-CORE-2** (WARN) Third.
"""
AGENTS = """\
## Code Review Rules

### P0: report at once

- Second. (RV-CORE-1)

### P1: report

- First. (RV-1)

### Not worth a finding

- Third (RV-CORE-2) is a warning and may be named here.
"""


def check(
    review: str = REVIEW, agents: str = AGENTS, rows: dict[str, str] | None = None
) -> Problems:
    return problems(review, agents, ROWS if rows is None else rows)


def test_consistent_files_pass() -> None:
    assert check() == NONE


def test_a_rule_without_a_unique_id_and_a_known_level_is_an_error() -> None:
    for review in (
        REVIEW + "- **RV-1** (WARN) Again.\n",
        REVIEW + "- **RV-CORE-3** (BLOCK P2) Level.\n",
        "no rules here\n",
    ):
        with pytest.raises(ValueError, match=r"duplicate|no rules"):
            check(review)


def test_an_id_that_is_cited_but_not_defined_is_found() -> None:
    assert check(agents=AGENTS + "- Other (RV-WEB-9)\n")["undefined"] == ["RV-WEB-9"]
    assert check(review=REVIEW + "See RV-DOC-9.\n")["undefined"] == ["RV-DOC-9"]


def test_a_blocking_rule_missing_from_the_agents_file_is_found() -> None:
    agents = AGENTS.replace("- First. (RV-1)\n", "")
    assert check(agents=agents)["missing"] == ["RV-1"]


def test_a_rule_under_the_wrong_priority_is_found() -> None:
    agents = AGENTS.replace("- Second. (RV-CORE-1)\n", "").replace("(RV-1)", "(RV-1, RV-CORE-1)")
    assert check(agents=agents)["wrong_priority"] == ["RV-CORE-1"]


def test_a_rule_under_two_priorities_is_an_error() -> None:
    with pytest.raises(ValueError, match="two priorities"):
        check(agents=AGENTS.replace("(RV-1)", "(RV-1, RV-CORE-1)"))


def test_a_warning_listed_as_p0_or_p1_is_found() -> None:
    agents = AGENTS.replace("(RV-1)", "(RV-1, RV-CORE-2)")
    assert check(agents=agents)["not_blocking"] == ["RV-CORE-2"]


def test_a_gate_must_be_an_existing_catalogue_row() -> None:
    assert check(review=REVIEW.replace("ALPHA-1", "ALPHA-2"))["gates"] == ["ALPHA-2"]
    assert check(review=REVIEW.replace("ALPHA-1", "ALPHA-3"))["gates"] == ["ALPHA-3"]
