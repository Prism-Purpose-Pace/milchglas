"""Feature files keep the form the requirements step asks for.

Catalogue GATE-22.

GATE-22 binds every scenario to its catalogue ID (`test_feature_traceability`). This module
adds the form rules of novibe's `.gherkin-lintrc` and its requirements step, on top of
`gherkin-official`, the parser pytest-bdd runs the same files with:

- parse: a file that does not parse fails.
- no-scenario: a file that holds no scenario fails.
- feature-id: the feature carries exactly one `@id:<issue>` tag.
- tag-allowed: a tag is `@id:<issue>`, `@backlog`, `@long-running` or one catalogue ID.
- step-count, when-count, then-required: a scenario has at most five steps, exactly one
  `When` and a `Then`. `And`, `But` and `*` count as the keyword before them, and the
  background steps count, because pytest-bdd runs them as part of the scenario.
- restricted-pattern: no step text names a screen element, a protocol or a data format.

Every finding names file, line and rule. A rule fails on its own bad case and stays silent
on its near-miss, so a check that cannot fail would show here.
"""

import re
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple, cast, override

import pytest
from gherkin.errors import CompositeParserException
from gherkin.parser import Parser
from gherkin.parser_types import Feature, GherkinDocument, Scenario, Step

from tests.conftest import CATALOGUE_ID
from tests.meta.test_catalogue_traceability import REPO, tree
from tests.meta.test_feature_traceability import FEATURES

ID_TAG = re.compile(r"id:\d+")
ALLOWED_TAG = re.compile(rf"{ID_TAG.pattern}|backlog|long-running|{CATALOGUE_ID.pattern}")
MAX_STEPS = 5
# novibe's `.gherkin-lintrc` (Global): screen elements and protocols say how, not what.
# gherkin-lint compiles them case-insensitively.
RESTRICTED = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(click|tap|press)(s|es|ed)?\b",
        r"\b(button|dropdown|checkbox|text ?field)s?\b",
        r"\bendpoints?\b",
        r"\bstatus code\b",
        r"\bHTTP\b",
        r"\bJSON\b",
        r"\bSQL\b",
    )
]


class Finding(NamedTuple):
    file: str  # relative to the repository root
    line: int
    rule: str
    message: str

    @override
    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}: {self.message}"


def read(path: Path) -> GherkinDocument | tuple[int, str]:
    """The parsed file, or the line and reason it does not parse."""
    try:
        return Parser().parse(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        return 1, f"not UTF-8 ({error.reason})"
    except CompositeParserException as error:
        first = error.errors[0]
        return first.location["line"], first.args[0].partition("): ")[2]


def cases(children: list[Any], background: list[Step]) -> Iterator[tuple[Scenario, list[Step]]]:
    """Each scenario with the background steps that run before it, a rule's included."""
    for child in children:
        if "background" in child:
            background = [*background, *child["background"]["steps"]]
        elif "scenario" in child:
            yield child["scenario"], background
        elif "rule" in child:
            yield from cases(child["rule"]["children"], background)


def tagged(feature: Feature) -> Iterator[Any]:
    """The feature, its rules, scenarios and examples: every node that carries tags."""
    yield feature
    children: list[Any] = feature["children"]
    yield from (child["rule"] for child in children if "rule" in child)
    for scenario, _ in cases(children, []):
        yield scenario
        yield from scenario["examples"]


def kinds(steps: list[Step]) -> list[str]:
    """The keyword type of each step; And, But and * take the type of the step before."""
    found: list[str] = []
    for step in steps:
        kind = step["keywordType"]
        found.append(found[-1] if found and kind in {"Conjunction", "Unknown"} else kind)
    return found


def shape(at: partial[Finding], scenario: Scenario, steps: list[Step]) -> Iterator[Finding]:
    """The size and the When/Then form of one scenario, and the words its steps use."""
    line, kind = scenario["location"]["line"], kinds(steps)
    if len(steps) > MAX_STEPS:
        yield at(line, "step-count", f"{len(steps)} steps, at most {MAX_STEPS}")
    if kind.count("Action") != 1:
        yield at(line, "when-count", f"{kind.count('Action')} When steps, exactly 1")
    if "Outcome" not in kind:
        yield at(line, "then-required", "no Then step")
    for step in steps:
        for pattern in RESTRICTED:
            if found := pattern.search(step["text"]):
                yield at(step["location"]["line"], "restricted-pattern", f"step names {found[0]!r}")


def head(at: partial[Finding], feature: Feature) -> Iterator[Finding]:
    """The id and tag rules, and the rule that a feature holds a scenario."""
    line = feature["location"]["line"]
    if not list(cases(feature["children"], [])):
        yield at(line, "no-scenario", "the Feature holds no scenario")
    own = [tag for tag in feature["tags"] if ID_TAG.fullmatch(tag["name"].removeprefix("@"))]
    if len(own) != 1:
        yield at(line, "feature-id", f"{len(own)} @id:<issue> tags on the Feature, exactly 1")
    for node in tagged(feature):
        for tag in node["tags"]:
            if not ALLOWED_TAG.fullmatch(tag["name"].removeprefix("@")):
                allowed = "@id:<issue>, @backlog, @long-running or a catalogue ID"
                yield at(
                    tag["location"]["line"], "tag-allowed", f"{tag['name']} is none of {allowed}"
                )


def check(file: str, document: GherkinDocument) -> Iterator[Finding]:
    at = partial(Finding, file)
    feature = cast("Feature | None", document.get("feature"))  # absent from an empty file
    if feature is None:
        yield at(1, "no-scenario", "no Feature")
        return
    yield from head(at, feature)
    for scenario, background in cases(feature["children"], []):
        yield from shape(at, scenario, [*background, *scenario["steps"]])


def lint(root: Path) -> list[Finding]:
    """Every rule broken in any feature file under tests/features/, by file and line."""
    findings: list[Finding] = []
    for path in sorted((root / FEATURES).rglob("*.feature")):
        file = path.relative_to(root).as_posix()
        document = read(path)
        if isinstance(document, tuple):
            findings.append(Finding(file, document[0], "parse", document[1]))
        else:
            findings += check(file, document)
    return sorted(set(findings))


# --- the real tree -----------------------------------------------------------------------


def test_feature_files_keep_the_form() -> None:
    assert list((REPO / FEATURES).rglob("*.feature")), "no feature file: the check would be vacuous"
    assert [str(finding) for finding in lint(REPO)] == []


# --- the rules on synthetic features -----------------------------------------------------

FILE = "tests/features/area/sample.feature"

GOOD = """\
@id:80
Feature: Sample

  Rule: One rule

    @ALPHA-1
    Scenario: First
      Given a thing
      When it runs
      Then it is done
"""


def found(tmp_path: Path, text: str) -> list[tuple[int, str]]:
    """The (line, rule) of every finding on one feature file."""
    findings = lint(tree(tmp_path, {FILE: text}))
    assert {finding.file for finding in findings} <= {FILE}
    return [(finding.line, finding.rule) for finding in findings]


def test_good_feature_is_silent(tmp_path: Path) -> None:
    assert found(tmp_path, GOOD) == []


def test_finding_reads_file_line_rule_message() -> None:
    assert str(Finding("a.feature", 3, "parse", "boom")) == "a.feature:3: parse: boom"


# One bad case per rule: (feature text, the findings it must give).
BAD = {
    "parse-table": (
        GOOD.replace("Given a thing\n", "Given a thing\n      | a | b |\n      | c |\n"),
        [(10, "parse")],
    ),
    "parse-docstring": (GOOD + '      """\n      open\n', [(13, "parse")]),
    "parse-language": ("# language: xx\n" + GOOD, [(1, "parse")]),
    "no-scenario-empty": ("", [(1, "no-scenario")]),
    "no-scenario-comment-only": ("# nothing\n", [(1, "no-scenario")]),
    "no-scenario-misspelt": (
        GOOD.replace("    @ALPHA-1\n    Scenario:", "    Scenaro:"),
        [(2, "no-scenario")],
    ),
    "parse-misspelt-after-tag": (GOOD.replace("Scenario:", "Scenaro:"), [(7, "parse")]),
    "feature-id-missing": (GOOD.replace("@id:80\n", ""), [(1, "feature-id")]),
    "feature-id-twice": (GOOD.replace("@id:80", "@id:80 @id:81"), [(2, "feature-id")]),
    "feature-id-not-a-number": (
        GOOD.replace("@id:80", "@id:abc"),
        [(1, "tag-allowed"), (2, "feature-id")],
    ),
    "tag-feature": (GOOD.replace("@id:80", "@id:80 @wip"), [(1, "tag-allowed")]),
    "tag-rule": (GOOD.replace("  Rule:", "  @wip\n  Rule:"), [(4, "tag-allowed")]),
    "tag-scenario": (GOOD.replace("@ALPHA-1", "@ALPHA-1 @wip"), [(6, "tag-allowed")]),
    "tag-examples": (
        GOOD.replace("Scenario:", "Scenario Outline:").replace("a thing", "<x>")
        + "\n      @wip\n      Examples:\n        | x |\n        | 1 |\n",
        [(12, "tag-allowed")],
    ),
    "step-count": (
        GOOD.replace("Given a thing\n", "Given a thing\n      And a second\n      And a third\n")
        + "      And more\n",
        [(7, "step-count")],
    ),
    "step-count-with-feature-background": (
        GOOD.replace(
            "  Rule:",
            "  Background:\n    Given a base\n    And a second\n    And a third\n\n  Rule:",
        ),
        [(12, "step-count")],
    ),
    "step-count-with-rule-background": (
        GOOD.replace(
            "    @ALPHA-1\n",
            "    Background:\n      Given a base\n      And a second\n      And a third\n\n    @ALPHA-1\n",
        ),
        [(12, "step-count")],
    ),
    "when-missing": (GOOD.replace("      When it runs\n", ""), [(7, "when-count")]),
    "when-twice": (
        GOOD.replace("When it runs\n", "When it runs\n      When it runs again\n"),
        [(7, "when-count")],
    ),
    "and-after-when": (
        GOOD.replace("When it runs\n", "When it runs\n      And it runs again\n"),
        [(7, "when-count")],
    ),
    "but-after-when": (
        GOOD.replace("When it runs\n", "When it runs\n      But not twice\n"),
        [(7, "when-count")],
    ),
    "star-after-when": (
        GOOD.replace("When it runs\n", "When it runs\n      * it runs again\n"),
        [(7, "when-count")],
    ),
    "when-in-background": (
        GOOD.replace("  Rule:", "  Background:\n    When it starts\n\n  Rule:"),
        [(10, "when-count")],
    ),
    "then-missing": (GOOD.replace("      Then it is done\n", ""), [(7, "then-required")]),
    "then-only-by-and-after-when": (
        GOOD.replace("Then it is done", "And it is done"),
        [(7, "then-required"), (7, "when-count")],
    ),
}


@pytest.mark.parametrize(("text", "expected"), BAD.values(), ids=BAD.keys())
def test_bad_feature_is_reported_with_line_and_rule(
    tmp_path: Path, text: str, expected: list[tuple[int, str]]
) -> None:
    assert found(tmp_path, text) == expected


def test_finding_names_the_file(tmp_path: Path) -> None:
    [finding] = lint(tree(tmp_path, {FILE: ""}))
    assert str(finding).startswith(f"{FILE}:1: no-scenario: ")


def test_file_that_is_no_utf8_does_not_parse(tmp_path: Path) -> None:
    root = tree(tmp_path, {})
    (root / FILE).parent.mkdir(parents=True)
    (root / FILE).write_bytes(b"\xff\xfeFeature: x\n")
    assert [(f.line, f.rule) for f in lint(root)] == [(1, "parse")]


# Near-misses: each stays silent although it is next to a bad case.
SILENT = {
    "language-pragma": "# language: en\n" + GOOD,
    "id-on-the-rule": GOOD.replace("  Rule:", "  @id:77\n  Rule:"),
    "backlog": GOOD.replace("@ALPHA-1", "@backlog @ALPHA-1"),
    "long-running": GOOD.replace("@ALPHA-1", "@long-running @ALPHA-1"),
    "catalogue-id-with-area-segment": GOOD.replace("@ALPHA-1", "@BETA-SUB-12"),
    "five-steps": GOOD.replace("Given a thing\n", "Given a thing\n      And a second\n").replace(
        "Then it is done\n", "Then it is done\n      But not twice\n"
    ),
    "five-steps-with-background": GOOD.replace(
        "  Rule:", "  Background:\n    Given a base\n\n  Rule:"
    ).replace("Given a thing\n", "Given a thing\n      And a second\n"),
    "star-after-given": GOOD.replace("Given a thing\n", "Given a thing\n      * a second\n"),
    "and-after-then": GOOD.replace("Then it is done\n", "Then it is done\n      And more\n"),
}


@pytest.mark.parametrize("text", SILENT.values(), ids=SILENT.keys())
def test_near_miss_is_silent(tmp_path: Path, text: str) -> None:
    assert found(tmp_path, text) == []


@pytest.mark.parametrize("tag", ["wip", "alpha-1", "ALPHA", "ALPHA-1x", "id", "id:", "backlogged"])
def test_tag_outside_the_allowlist_is_reported(tmp_path: Path, tag: str) -> None:
    assert found(tmp_path, GOOD.replace("@ALPHA-1", f"@ALPHA-1 @{tag}")) == [(6, "tag-allowed")]


# Step texts that name how the system is used, not what it does: one per pattern of novibe's
# `.gherkin-lintrc`, upper case included because gherkin-lint matches them case-insensitively.
HOW_STEPS = [
    "the owner clicks the link",
    "the owner taps the link",
    "the owner presses a key",
    "the page shows a button",
    "the owner opens a dropdown",
    "the owner ticks a checkbox",
    "the owner fills a text field",
    "the client calls an endpoint",
    "the server sends a status code",
    "the server speaks HTTP",
    "the server speaks http",
    "the answer is JSON",
    "the owner runs SQL",
    "Click the link",
]


@pytest.mark.parametrize("step", HOW_STEPS)
def test_step_that_names_a_screen_element_or_protocol_is_reported(
    tmp_path: Path, step: str
) -> None:
    assert found(tmp_path, GOOD.replace("a thing", step)) == [(8, "restricted-pattern")]


def test_restricted_pattern_in_any_step_is_reported_on_its_line(tmp_path: Path) -> None:
    assert found(tmp_path, GOOD.replace("it is done", "the answer is JSON")) == [
        (10, "restricted-pattern")
    ]


@pytest.mark.parametrize(
    "step",
    [
        "a tape of the call",
        "the pressure rises",
        "a SQLite file",
        "an https address",
        "the server answers status 207",
        "the clicker rings",
        "a buttonhole",
    ],
)
def test_step_that_only_contains_a_pattern_as_part_of_a_word_is_silent(
    tmp_path: Path, step: str
) -> None:
    assert found(tmp_path, GOOD.replace("a thing", step)) == []
