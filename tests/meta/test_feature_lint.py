"""Feature files keep the form the requirements step asks for.

Catalogue GATE-22.

GATE-22 binds every scenario to its catalogue ID (`test_feature_traceability`). This module
adds the form rules of novibe's `.gherkin-lintrc` and its requirements step, plus three that
behave-lint and gherkin-lint share, on top of `gherkin-official`, the parser pytest-bdd runs
the same files with:

- parse: a file that does not parse fails.
- no-scenario: a file that holds no scenario fails.
- feature-id, dupe-feature-id: the feature carries exactly one `@id:<issue>` tag, and no
  other feature carries the same one (novibe: the plan refers to a feature by its id).
- feature-description: the feature says who gains what, and why (novibe's Example Mapping).
- tag-allowed: a tag is `@id:<issue>`, `@backlog`, `@long-running` or one catalogue ID.
- step-count, when-count, then-required, keyword-order: a scenario has at most five steps
  of its own, exactly one `When`, a `Then`, and Given, When, Then in this order. `And`, `But`
  and `*` count as the keyword before them. Background steps count for the keywords and the
  order, as pytest-bdd runs them first, but not for the five: novibe caps a Background at four
  steps of its own, which five steps in total would leave no room for.
- background-form: a Background holds one to four steps, all of them Given.
- rule-scenarios: a Rule holds two scenarios or more (novibe: add a Rule once two or more
  scenarios illustrate it); a single scenario stands without a Rule.
- restricted-pattern: no name, description or step text names a screen element, a protocol or
  a data format; novibe's linter (gherkin-lint-plus) reads all of them.
- outline-without-examples, unused-example-column, undefined-variable: an outline has
  `Examples` with rows, every column is used by a step, and every `<variable>` of a step has a
  column in each `Examples` block. A variable counts in step text, doc string and data table,
  where pytest-bdd substitutes it (`pytest_bdd.parser.PARAM_RE`), and a background step counts.
  empty-examples: an `Examples` block without rows next to one with rows.
- no-comments: a `#` line is a comment and fails; the reason goes into a scenario description.
- dupe-feature-name, dupe-scenario-name: a feature name is unique across the files, a
  scenario name within its feature, rules included (pytest-bdd looks a scenario up by name).
- use-and: a Given, When or Then never follows a step of the same keyword; `And` goes there.
- no-duplicate-tags: a tag stands once on a node; pytest-bdd keeps tags as a set, so a doubled
  ID tag would pass GATE-22's one-ID check unseen.
- synthetic-world: every e-mail domain, URL host and IP address in a name, description, step,
  doc string or table cell is a documentation one (RFC 2606 names, RFC 5737 and RFC 3849
  networks, loopback), so a feature names nothing real (novibe: the World is synthetic).
  Shortcut: a bare host name without a scheme or `@`, and a person's name, are not read here.
- id-stable: a feature keeps the `@id` it had where this branch left main (the merge base
  with `origin/main`, else `main`; neither fails). Features are matched by their scenarios'
  catalogue IDs, so a move, a rename, a split and a deletion pass. Shortcut: renumbering the
  catalogue IDs together with the `@id` passes; GATE-17 shows the row change in review.

Every finding names file, line and rule. A rule fails on its own bad case and stays silent
on its near-miss, so a check that cannot fail would show here.

Limits, kept on purpose: whether a scenario states an outcome, whether a `Then` can be seen
from outside, and whether an Examples cell is a value rather than a phrase are prose; the
judges of D-18 read them (`scripts/judge_features.py`, rubric `tests/meta/judges.md`); `@long-running` passes tag-allowed but is a pytest marker that
`pyproject.toml` does not register yet.
"""

import contextlib
import ipaddress
import os
import re
import subprocess
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple, cast, override

import pytest
from gherkin.dialect import DIALECTS
from gherkin.errors import CompositeParserException
from gherkin.parser import Parser
from gherkin.parser_types import Feature, GherkinDocument, Scenario, Step
from pytest_bdd.parser import PARAM_RE

from tests.conftest import CATALOGUE_ID
from tests.meta.test_catalogue_traceability import REPO, tree
from tests.meta.test_feature_traceability import FEATURES

ID_TAG = re.compile(r"id:\d+")
ALLOWED_TAG = re.compile(rf"{ID_TAG.pattern}|backlog|long-running|{CATALOGUE_ID.pattern}")
MAX_STEPS = 5
MAX_BACKGROUND = 4
MIN_RULE_SCENARIOS = 2
ORDER = {"Context": 0, "Action": 1, "Outcome": 2}  # Given, When, Then
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
EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://(\[[^\]]+\]|[^/\s:?#\"'<>|]+)", re.IGNORECASE)
IP = re.compile(r"[0-9A-Fa-f:.]*[:.][0-9A-Fa-f:.]+")  # a candidate; ipaddress decides
RESERVED_NAME = re.compile(
    r"(?:.+\.)?(?:example\.(?:com|net|org)|example|test|invalid|localhost)", re.IGNORECASE
)
DOCUMENTATION = [
    ipaddress.ip_network(network)
    for network in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
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


def parts(feature: Feature, key: str) -> list[Any]:
    """The rules or the backgrounds of a feature, a rule's background included."""
    children: list[Any] = feature["children"]
    rules = [child["rule"] for child in children if "rule" in child]
    return [child[key] for node in [feature, *rules] for child in node["children"] if key in child]


def tagged(feature: Feature) -> Iterator[Any]:
    """The feature, its rules, scenarios and examples: every node that carries tags."""
    yield feature
    yield from parts(feature, "rule")
    for scenario, _ in cases(feature["children"], []):
        yield scenario
        yield from scenario["examples"]


def kinds(steps: list[Step]) -> list[str]:
    """The keyword type of each step; And, But and * take the type of the step before."""
    found: list[str] = []
    for step in steps:
        kind = step["keywordType"]
        found.append(found[-1] if found and kind in {"Conjunction", "Unknown"} else kind)
    return found


def restricted(at: partial[Finding], line: int, text: str) -> Iterator[Finding]:
    for pattern in RESTRICTED:
        if found := pattern.search(text):
            yield at(line, "restricted-pattern", f"names {found[0]!r}")


def repeats(at: partial[Finding], steps: list[Step]) -> Iterator[Finding]:
    """A Given, When or Then right after a step of the same keyword, where And belongs."""
    for step, before in zip(steps[1:], kinds(steps), strict=False):
        if step["keywordType"] == before and before in ORDER:
            yield at(step["location"]["line"], "use-and", f"{step['keyword'].strip()!r}: use And")


def texts(feature: Feature) -> Iterator[tuple[int, str]]:
    """Every name, description, step text, doc string and table cell, with its line."""
    scenarios = [scenario for scenario, _ in cases(feature["children"], [])]
    backgrounds = parts(feature, "background")
    for node in [feature, *parts(feature, "rule"), *backgrounds, *scenarios]:
        yield node["location"]["line"], f"{node['name']}\n{node['description']}"
    tables: list[Any] = [examples for scenario in scenarios for examples in scenario["examples"]]
    for step in [step for node in [*backgrounds, *scenarios] for step in node["steps"]]:
        yield step["location"]["line"], step["text"]
        if "docString" in step:
            yield step["docString"]["location"]["line"], step["docString"]["content"]
        tables.append({"tableBody": step.get("dataTable", {}).get("rows", [])})
    for table in tables:
        rows = [*([table["tableHeader"]] if "tableHeader" in table else []), *table["tableBody"]]
        yield from (
            (cell["location"]["line"], cell["value"]) for row in rows for cell in row["cells"]
        )


def real(value: str) -> bool:
    """True unless `value` is a documentation name or address, or loopback."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return not RESERVED_NAME.fullmatch(value.rstrip("."))
    return not (address.is_loopback or any(address in network for network in DOCUMENTATION))


def world(at: partial[Finding], feature: Feature) -> Iterator[Finding]:
    """The e-mail domains, URL hosts and IP addresses that point somewhere real."""
    for line, text in texts(feature):
        found = [m[1] for m in EMAIL.finditer(text)]
        found += [m[1].strip("[]") for m in URL.finditer(text)]
        for candidate in IP.finditer(text):
            with contextlib.suppress(ValueError):
                found.append(str(ipaddress.ip_address(candidate[0].rstrip("."))))
        for value in found:
            if real(value):
                message = f"{value!r} is real: use an RFC 2606 name or RFC 5737/3849 address"
                yield at(line, "synthetic-world", message)


def shape(at: partial[Finding], scenario: Scenario, steps: list[Step]) -> Iterator[Finding]:
    """The size, the When/Then form and the order of one scenario and its background steps."""
    line, kind = scenario["location"]["line"], kinds(steps)
    if len(scenario["steps"]) > MAX_STEPS:
        yield at(line, "step-count", f"{len(scenario['steps'])} steps, at most {MAX_STEPS}")
    if kind.count("Action") != 1:
        yield at(line, "when-count", f"{kind.count('Action')} When steps, exactly 1")
    if "Outcome" not in kind:
        yield at(line, "then-required", "no Then step")
    highest = 0
    for step, position in zip(steps, [ORDER.get(k, -1) for k in kind], strict=True):
        if 0 <= position < highest:
            yield at(step["location"]["line"], "keyword-order", "Given, When, Then in this order")
        highest = max(highest, position)
    yield from repeats(at, scenario["steps"])
    for step in steps:
        yield from restricted(at, step["location"]["line"], step["text"])


def variables(step: Step) -> set[str]:
    """The <variables> of a step, where pytest-bdd substitutes them: text, doc string, table."""
    texts = [step["text"]]
    if "docString" in step:
        texts.append(step["docString"]["content"])
    if "dataTable" in step:
        texts += [cell["value"] for row in step["dataTable"]["rows"] for cell in row["cells"]]
    return {found[1] for text in texts for found in PARAM_RE.finditer(text)}


def outline(
    at: partial[Finding], scenario: Scenario, steps: list[Step], keywords: list[str]
) -> Iterator[Finding]:
    """Examples with rows, a step for every column and a column for every variable."""
    blocks = [examples for examples in scenario["examples"] if examples.get("tableBody")]
    if not blocks:
        if scenario["keyword"] in keywords or scenario["examples"]:
            yield at(scenario["location"]["line"], "outline-without-examples", "no Examples rows")
        return
    empty = [examples for examples in scenario["examples"] if examples not in blocks]
    yield from (at(e["location"]["line"], "empty-examples", "no rows") for e in empty)
    used = {name for step in steps for name in variables(step)}
    columns = [{cell["value"] for cell in block["tableHeader"]["cells"]} for block in blocks]
    for block in blocks:
        for cell in block["tableHeader"]["cells"]:
            if cell["value"] not in used:
                yield at(cell["location"]["line"], "unused-example-column", f"{cell['value']!r}")
    for step in steps:
        for name in sorted(variables(step)):
            if not all(name in block for block in columns):
                yield at(step["location"]["line"], "undefined-variable", f"<{name}> has no column")


def repeated_scenarios(at: partial[Finding], feature: Feature) -> Iterator[Finding]:
    """The scenarios, rules included, whose name an earlier scenario of the feature uses."""
    seen: dict[str, int] = {}
    for scenario, _ in cases(feature["children"], []):
        name, line = scenario["name"], scenario["location"]["line"]
        if name in seen:
            yield at(line, "dupe-scenario-name", f"{name!r} is also the name of line {seen[name]}")
        seen.setdefault(name, line)


def repeated(
    features: dict[str, Feature], rule: str, key: Callable[[Any], list[str]]
) -> Iterator[Finding]:
    """The features, by file in order, that repeat a name or id an earlier file uses."""
    seen: dict[str, str] = {}
    for file, feature in features.items():
        for value in key(feature):
            first = seen.setdefault(value, file)
            if first != file:
                yield Finding(file, feature["location"]["line"], rule, f"{value!r} also in {first}")


def ids(feature: Feature) -> list[str]:
    return [
        tag["name"] for tag in feature["tags"] if ID_TAG.fullmatch(tag["name"].removeprefix("@"))
    ]


def head(at: partial[Finding], feature: Feature) -> Iterator[Finding]:
    """The id and tag rules, and the rule that a feature holds a scenario."""
    line = feature["location"]["line"]
    if not list(cases(feature["children"], [])):
        yield at(line, "no-scenario", "the Feature holds no scenario")
    if len(ids(feature)) != 1:
        yield at(
            line, "feature-id", f"{len(ids(feature))} @id:<issue> tags on the Feature, exactly 1"
        )
    if not feature["description"].strip():
        yield at(line, "feature-description", "no description: who gains what, and why")
    for node in tagged(feature):
        for index, tag in enumerate(node["tags"]):
            if tag["name"] in [earlier["name"] for earlier in node["tags"][:index]]:
                yield at(tag["location"]["line"], "no-duplicate-tags", f"{tag['name']} twice")
            if not ALLOWED_TAG.fullmatch(tag["name"].removeprefix("@")):
                allowed = "@id:<issue>, @backlog, @long-running or a catalogue ID"
                yield at(
                    tag["location"]["line"], "tag-allowed", f"{tag['name']} is none of {allowed}"
                )


def body(at: partial[Finding], feature: Feature) -> Iterator[Finding]:
    """Rules that hold scenarios, backgrounds that hold only a few Givens, and plain names."""
    for rule in parts(feature, "rule"):
        count = sum("scenario" in child for child in rule["children"])
        if count < MIN_RULE_SCENARIOS:
            message = f"holds {count}, needs 2; a single scenario stands without a Rule"
            yield at(rule["location"]["line"], "rule-scenarios", message)
    for background in parts(feature, "background"):
        steps = background["steps"]
        if len(steps) > MAX_BACKGROUND or set(kinds(steps)) != {"Context"}:  # empty: set()
            message = f"{len(steps)} steps; 1 to {MAX_BACKGROUND} Given steps"
            yield at(background["location"]["line"], "background-form", message)
        yield from repeats(at, steps)
    nodes = [feature, *parts(feature, "rule"), *parts(feature, "background")]
    nodes += [scenario for scenario, _ in cases(feature["children"], [])]
    for node in nodes:
        for text in (node["name"], node["description"]):
            yield from restricted(at, node["location"]["line"], text)


def check(file: str, document: GherkinDocument) -> Iterator[Finding]:
    at = partial(Finding, file)
    for comment in document["comments"]:
        yield at(
            comment["location"]["line"],
            "no-comments",
            "move the reason into a scenario description",
        )
    feature = cast("Feature | None", document.get("feature"))  # absent from an empty file
    if feature is None:
        yield at(1, "no-scenario", "no Feature")
        return
    yield from head(at, feature)
    yield from body(at, feature)
    yield from world(at, feature)
    yield from repeated_scenarios(at, feature)
    keywords = DIALECTS[feature["language"]]["scenarioOutline"]
    for scenario, background in cases(feature["children"], []):
        steps = [*background, *scenario["steps"]]
        yield from shape(at, scenario, steps)
        yield from outline(at, scenario, steps, keywords)


def lint(root: Path) -> list[Finding]:
    """Every rule broken in any feature file under tests/features/, by file and line."""
    findings: list[Finding] = []
    features: dict[str, Feature] = {}
    for path in sorted((root / FEATURES).rglob("*.feature")):
        file = path.relative_to(root).as_posix()
        document = read(path)
        if isinstance(document, tuple):
            findings.append(Finding(file, document[0], "parse", document[1]))
            continue
        findings += check(file, document)
        if "feature" in document:
            features[file] = document["feature"]
    names = repeated(features, "dupe-feature-name", lambda feature: [feature["name"]])
    return sorted({*findings, *names, *repeated(features, "dupe-feature-id", ids)})


def numbered(texts: list[str]) -> Iterator[tuple[list[str], set[str]]]:
    """Each feature's `@id` tags and the catalogue ID tags it holds; unparsed text is skipped."""
    for text in texts:
        try:
            feature = cast("Feature | None", Parser().parse(text).get("feature"))
        except CompositeParserException:
            continue  # the form rules report it
        if feature is not None:
            tags = {tag["name"] for node in tagged(feature) for tag in node["tags"]}
            yield ids(feature), {tag for tag in tags if CATALOGUE_ID.fullmatch(tag[1:])}


def renumbering(before: list[str], now: list[str]) -> list[str]:
    """The `@id` tags of `before` that no feature of `now` holding their scenarios carries.

    A feature is found by its scenarios' catalogue IDs, not its path, so a move or a rename
    passes, and so does a feature deleted with its scenarios or split into two.
    """
    holders: dict[str, set[str]] = {}
    for found, tags in numbered(now):
        for tag in tags:
            holders.setdefault(tag, set()).update(found)
    changes: list[str] = []
    for found, tags in numbered(before):
        kept = sorted(tags & holders.keys())
        carried = set().union(*(holders[tag] for tag in kept))
        lost = [was for was in found if kept and was not in carried]
        changes += [
            f"{was} became {', '.join(sorted(carried))} ({', '.join(kept)})" for was in lost
        ]
    return changes


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def renumbered(root: Path) -> list[str]:
    """The `@id` changes since this branch left main (the merge base with origin/main or main)."""
    for ref in ("origin/main", "main"):
        if (fork := git(root, "merge-base", "HEAD", ref)).returncode == 0:
            break
    else:
        msg = "neither origin/main nor main to compare with: fetch main (CI: fetch-depth: 0)"
        raise LookupError(msg)
    base = fork.stdout.strip()
    listed = git(root, "ls-tree", "-r", "--name-only", base, "--", FEATURES.as_posix()).stdout
    paths = [path for path in listed.splitlines() if path.endswith(".feature")]
    before = [git(root, "show", f"{base}:{path}").stdout for path in paths]
    now = [
        path.read_text(encoding="utf-8") for path in sorted((root / FEATURES).rglob("*.feature"))
    ]
    return renumbering(before, now)


# --- the real tree -----------------------------------------------------------------------


def test_feature_files_keep_the_form() -> None:
    assert list((REPO / FEATURES).rglob("*.feature")), "no feature file: the check would be vacuous"
    assert [str(finding) for finding in lint(REPO)] == []


# --- the rules on synthetic features -----------------------------------------------------

FILE = "tests/features/area/sample.feature"

GOOD = """\
@id:80
Feature: Sample
  A sample.
  Rule: One rule

    @ALPHA-1
    Scenario: First
      Given a thing
      When it runs
      Then it is done

    @ALPHA-2
    Scenario: Second
      Given another thing
      When it stops
      Then it is over
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
    "parse-docstring": (GOOD + '      """\n      open\n', [(19, "parse")]),
    "parse-language": ("# language: xx\n" + GOOD, [(1, "parse")]),
    "no-scenario-empty": ("", [(1, "no-scenario")]),
    "no-scenario-comment-only": ("# nothing\n", [(1, "no-comments"), (1, "no-scenario")]),
    "no-scenario-misspelt": (
        GOOD.replace("    @ALPHA-1\n    Scenario:", "    Scenaro:").replace(
            "    @ALPHA-2\n    Scenario:", "    Scenaro:"
        ),
        [(2, "no-scenario"), (4, "rule-scenarios")],
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
        GOOD.replace("Scenario: First", "Scenario Outline: First")
        .replace("a thing\n", "<x>\n")
        .replace(
            "Then it is done\n",
            "Then it is done\n\n      @wip\n      Examples:\n        | x |\n        | 1 |\n",
        ),
        [(12, "tag-allowed")],
    ),
    "step-count": (
        GOOD.replace(
            "Given a thing\n", "Given a thing\n      And a second\n      And a third\n"
        ).replace("Then it is done\n", "Then it is done\n      And more\n"),
        [(7, "step-count")],
    ),
    "when-missing": (GOOD.replace("      When it runs\n", ""), [(7, "when-count")]),
    "when-twice": (
        GOOD.replace("When it runs\n", "When it runs\n      When it runs again\n"),
        [(7, "when-count"), (10, "use-and")],
    ),
    "use-and-given": (
        GOOD.replace("Given a thing\n", "Given a thing\n      Given a second\n"),
        [(9, "use-and")],
    ),
    "use-and-then": (
        GOOD.replace("Then it is done\n", "Then it is done\n      Then it is clean\n"),
        [(11, "use-and")],
    ),
    "use-and-after-and": (
        GOOD.replace("Given a thing\n", "Given a thing\n      And a second\n      Given a third\n"),
        [(10, "use-and")],
    ),
    "use-and-in-background": (
        GOOD.replace("  Rule:", "  Background:\n    Given a base\n    Given a second\n\n  Rule:"),
        [(6, "use-and")],
    ),
    "duplicate-tag-on-a-scenario": (
        GOOD.replace("@ALPHA-1", "@ALPHA-1 @ALPHA-1"),
        [(6, "no-duplicate-tags")],
    ),
    "duplicate-tag-on-the-feature": (
        GOOD.replace("@id:80", "@id:80 @id:80"),
        [(1, "no-duplicate-tags"), (2, "feature-id")],
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
        [
            (4, "background-form"),
            (10, "when-count"),
            (11, "keyword-order"),
            (16, "when-count"),
            (17, "keyword-order"),
        ],
    ),
    "feature-description-missing": (
        GOOD.replace("  A sample.\n", "\n"),
        [(2, "feature-description")],
    ),
    "then-before-when": (
        GOOD.replace("When it runs\n", "Then it is ready\n      When it runs\n"),
        [(10, "keyword-order")],
    ),
    "given-after-when": (
        GOOD.replace("When it runs\n", "When it runs\n      Given a second thing\n"),
        [(10, "keyword-order")],
    ),
    "then-in-the-background": (
        GOOD.replace("  Rule:", "  Background:\n    Then it was ready\n\n  Rule:"),
        [
            (4, "background-form"),
            (11, "keyword-order"),
            (12, "keyword-order"),
            (17, "keyword-order"),
            (18, "keyword-order"),
        ],
    ),
    "background-of-five-steps": (
        GOOD.replace(
            "  Rule:",
            "  Background:\n    Given a base\n    And a second\n    And a third\n"
            "    And a fourth\n    And a fifth\n\n  Rule:",
        ),
        [(4, "background-form")],
    ),
    "empty-background": (
        GOOD.replace("  Rule:", "  Background:\n\n  Rule:"),
        [(4, "background-form")],
    ),
    "rule-background-with-when": (
        GOOD.replace("    @ALPHA-1\n", "    Background:\n      When it starts\n\n    @ALPHA-1\n"),
        [
            (6, "background-form"),
            (10, "when-count"),
            (11, "keyword-order"),
            (16, "when-count"),
            (17, "keyword-order"),
        ],
    ),
    "rule-without-scenario": (GOOD + "\n  Rule: Empty rule\n", [(18, "rule-scenarios")]),
    "rule-with-one-scenario": (
        GOOD.split("\n\n    @ALPHA-2", maxsplit=1)[0] + "\n",
        [(4, "rule-scenarios")],
    ),
    "rule-with-only-a-background": (
        GOOD + "\n  Rule: Empty rule\n\n    Background:\n      Given a base\n",
        [(18, "rule-scenarios")],
    ),
    "restricted-in-the-feature-name": (
        GOOD.replace("Sample", "Sample JSON"),
        [(2, "restricted-pattern")],
    ),
    "restricted-in-the-feature-description": (
        GOOD.replace("A sample.", "A sample one clicks."),
        [(2, "restricted-pattern")],
    ),
    "restricted-in-a-rule-name": (
        GOOD.replace("One rule", "One HTTP rule"),
        [(4, "restricted-pattern")],
    ),
    "restricted-in-a-scenario-name": (
        GOOD.replace("First", "First button"),
        [(7, "restricted-pattern")],
    ),
    "restricted-in-a-scenario-description": (
        GOOD.replace("    Scenario: First\n", "    Scenario: First\n      Via the endpoint.\n"),
        [(7, "restricted-pattern")],
    ),
    "restricted-in-a-background-name": (
        GOOD.replace("  Rule:", "  Background: the SQL base\n    Given a base\n\n  Rule:"),
        [(4, "restricted-pattern")],
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
    "background-steps-do-not-count": GOOD.replace(
        "  Rule:",
        "  Background:\n    Given a base\n    And a second\n    And a third\n    And a fourth\n\n  Rule:",
    ).replace("Given a thing\n", "Given a thing\n      And a second\n"),
    "rule-background-steps-do-not-count": GOOD.replace(
        "    @ALPHA-1\n",
        "    Background:\n      Given a base\n      And a second\n      And a third\n\n    @ALPHA-1\n",
    ),
    "but-after-given": GOOD.replace("Given a thing\n", "Given a thing\n      But not another\n"),
    "same-tag-on-feature-and-scenario": GOOD.replace("@id:80", "@id:80 @backlog").replace(
        "@ALPHA-1", "@backlog @ALPHA-1"
    ),
}


@pytest.mark.parametrize("text", SILENT.values(), ids=SILENT.keys())
def test_near_miss_is_silent(tmp_path: Path, text: str) -> None:
    assert found(tmp_path, text) == []


@pytest.mark.parametrize("tag", ["wip", "alpha-1", "ALPHA", "ALPHA-1x", "id", "id:", "backlogged"])
def test_tag_outside_the_allowlist_is_reported(tmp_path: Path, tag: str) -> None:
    assert found(tmp_path, GOOD.replace("@ALPHA-1", f"@ALPHA-1 @{tag}")) == [(6, "tag-allowed")]


# An outline that is right: the bad cases below each break one thing.
OUTLINE = """\
@id:80
Feature: Sample
  A sample.
  @ALPHA-1
  Scenario Outline: First
    Given a <thing>
    When it runs
    Then it is <state>

    Examples:
      | thing | state |
      | cat   | done  |
"""

OUTLINE_BAD = {
    "no-examples": (
        OUTLINE.split("\n    Examples:", maxsplit=1)[0] + "\n",
        [(5, "outline-without-examples")],
    ),
    "template-keyword-no-examples": (
        OUTLINE.split("\n    Examples:", maxsplit=1)[0].replace("Outline", "Template") + "\n",
        [(5, "outline-without-examples")],
    ),
    "examples-without-rows": (
        OUTLINE.replace("      | cat   | done  |\n", ""),
        [(5, "outline-without-examples")],
    ),
    "examples-without-table": (
        OUTLINE.split("      | thing", maxsplit=1)[0],
        [(5, "outline-without-examples")],
    ),
    "scenario-keyword-with-empty-examples": (
        OUTLINE.replace("Scenario Outline", "Scenario").replace("      | cat   | done  |\n", ""),
        [(5, "outline-without-examples")],
    ),
    "german-keyword-no-examples": (
        (
            "# language: de\n@id:80\nFunktionalität: Sample\n  Ein Beispiel.\n  @ALPHA-1\n"
            "  Szenariogrundriss: First\n"
            "    Gegeben sei a <thing>\n    Wenn it runs\n    Dann it is done\n"
        ),
        [(6, "outline-without-examples")],
    ),
    "unused-column": (
        OUTLINE.replace("| state |", "| state | extra |").replace("| done  |", "| done  | 1 |"),
        [(11, "unused-example-column")],
    ),
    "column-used-only-in-the-name": (
        OUTLINE.replace("First", "First <state>").replace("it is <state>", "it is done"),
        [(11, "unused-example-column")],
    ),
    "unused-column-in-the-second-block": (
        OUTLINE + "\n    Examples:\n      | thing | state | extra |\n      | dog   | done  | 1 |\n",
        [(15, "unused-example-column")],
    ),
    "variable-without-column": (
        OUTLINE.replace("a <thing>", "a <thing> and <other>"),
        [(6, "undefined-variable")],
    ),
    "variable-without-column-in-the-second-block": (
        OUTLINE + "\n    Examples:\n      | thing |\n      | dog   |\n",
        [(8, "undefined-variable")],
    ),
    "empty-second-examples-block": (
        OUTLINE + "\n    Examples:\n      | thing | state |\n",
        [(14, "empty-examples")],
    ),
    "variable-in-the-doc-string-without-column": (
        OUTLINE.replace(
            "Then it is <state>", 'Then it is <state>\n      """\n      <other>\n      """'
        ),
        [(8, "undefined-variable")],
    ),
}


@pytest.mark.parametrize(("text", "expected"), OUTLINE_BAD.values(), ids=OUTLINE_BAD.keys())
def test_bad_outline_is_reported_with_line_and_rule(
    tmp_path: Path, text: str, expected: list[tuple[int, str]]
) -> None:
    assert found(tmp_path, text) == expected


OUTLINE_SILENT = {
    "outline": OUTLINE,
    "scenario-keyword-with-examples": OUTLINE.replace("Scenario Outline", "Scenario"),
    "two-blocks": OUTLINE + "\n    Examples:\n      | thing | state |\n      | dog   | done  |\n",
    "variable-only-in-a-doc-string": OUTLINE.replace(
        "Then it is <state>", 'Then it is done\n      """\n      <state>\n      """'
    ),
    "variable-only-in-a-data-table": OUTLINE.replace(
        "Then it is <state>", "Then it is done\n      | <state> |"
    ),
    "variable-only-in-the-background": OUTLINE.replace(
        "  @ALPHA-1", "  Background:\n    Given the <state>\n\n  @ALPHA-1"
    ).replace("Then it is <state>", "Then it is done"),
    "angle-brackets-in-a-scenario-without-examples": GOOD.replace("a thing", "an <answer> element"),
}


@pytest.mark.parametrize("text", OUTLINE_SILENT.values(), ids=OUTLINE_SILENT.keys())
def test_good_outline_is_silent(tmp_path: Path, text: str) -> None:
    assert found(tmp_path, text) == []


SECOND = "\n    @ALPHA-2\n    Scenario: First\n      Given a thing\n      When it runs\n      Then it is done\n"


@pytest.mark.parametrize(
    ("text", "line"),
    [
        (GOOD + SECOND, 19),
        (GOOD + "\n  Rule: Other rule\n" + SECOND + SECOND.replace("First", "Third"), 21),
    ],
    ids=["same-rule", "other-rule"],
)
def test_scenario_name_used_twice_is_reported_on_the_second(
    tmp_path: Path, text: str, line: int
) -> None:
    assert found(tmp_path, text) == [(line, "dupe-scenario-name")]


def test_scenario_names_that_differ_or_sit_in_two_files_are_silent(tmp_path: Path) -> None:
    other = GOOD + SECOND.replace("First", "Third")
    root = tree(
        tmp_path,
        {
            "tests/features/a/one.feature": other,
            "tests/features/b/two.feature": GOOD.replace("Sample", "Other").replace("80", "81"),
        },
    )
    assert lint(root) == []


def test_feature_name_used_in_two_files_is_reported_in_the_second(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "tests/features/a/one.feature": GOOD,
            "tests/features/b/two.feature": GOOD.replace("@id:80", "@id:81"),
        },
    )
    [finding] = lint(root)
    assert (finding.file, finding.line, finding.rule) == (
        "tests/features/b/two.feature",
        2,
        "dupe-feature-name",
    )
    assert "tests/features/a/one.feature" in finding.message


def test_feature_names_that_differ_are_silent(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "tests/features/a/one.feature": GOOD,
            "tests/features/b/two.feature": GOOD.replace("Sample", "Other").replace("80", "81"),
        },
    )
    assert lint(root) == []


def test_feature_id_used_in_two_files_is_reported_in_the_second(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "tests/features/a/one.feature": GOOD,
            "tests/features/b/two.feature": GOOD.replace("Sample", "Other"),
        },
    )
    [finding] = lint(root)
    assert (finding.file, finding.line, finding.rule) == (
        "tests/features/b/two.feature",
        2,
        "dupe-feature-id",
    )
    assert "tests/features/a/one.feature" in finding.message


def test_rule_id_used_in_two_files_is_silent(tmp_path: Path) -> None:
    sliced = GOOD.replace("  Rule:", "  @id:77\n  Rule:")
    root = tree(
        tmp_path,
        {
            "tests/features/a/one.feature": sliced,
            "tests/features/b/two.feature": sliced.replace("Sample", "Other").replace("80", "81"),
        },
    )
    assert lint(root) == []


COMMENT_BAD = {
    "above-the-feature": ("# note\n" + GOOD, [(1, "no-comments")]),
    "between-steps": (
        GOOD.replace("      When it runs\n", "      # why\n      When it runs\n"),
        [(9, "no-comments")],
    ),
    "at-the-end": (GOOD + "    # done\n", [(17, "no-comments")]),
    "in-an-examples-table": (
        OUTLINE.replace("      | cat   | done  |\n", "      # why\n      | cat   | done  |\n"),
        [(12, "no-comments")],
    ),
    "two-comments": ("# one\n" + GOOD + "# two\n", [(1, "no-comments"), (18, "no-comments")]),
}


@pytest.mark.parametrize(("text", "expected"), COMMENT_BAD.values(), ids=COMMENT_BAD.keys())
def test_comment_is_reported_on_its_line(
    tmp_path: Path, text: str, expected: list[tuple[int, str]]
) -> None:
    assert found(tmp_path, text) == expected


COMMENT_SILENT = {
    "hash-in-a-doc-string": GOOD.replace(
        "Then it is done", 'Then it is done\n      """\n      # not a comment\n      """'
    ),
    "hash-inside-a-step": GOOD.replace("a thing", "a thing #1"),
    "hash-in-a-table-cell": GOOD.replace("Then it is done", "Then it is done\n      | # |"),
    "description-instead": GOOD.replace(
        "    Scenario: First\n", "    Scenario: First\n      Why: it is the first.\n\n"
    ),
}


@pytest.mark.parametrize("text", COMMENT_SILENT.values(), ids=COMMENT_SILENT.keys())
def test_hash_that_is_no_comment_is_silent(tmp_path: Path, text: str) -> None:
    assert found(tmp_path, text) == []


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


# Addresses that point somewhere real, and the documentation ones a synthetic World uses.
REAL_ADDRESSES = [
    "owner@mail.acme.de",
    "owner@example.com.acme.de",
    "https://cloud.acme.de/remote.php/dav",
    "https://nas.home.arpa",
    "10.0.0.7",
    "the server 10.0.0.7.",
    "fd00::7",
    "https://[fd00::7]/dav",
]


@pytest.mark.parametrize("address", REAL_ADDRESSES)
def test_real_address_in_a_step_is_reported(tmp_path: Path, address: str) -> None:
    text = GOOD.replace("a thing", f"a calendar at {address}")
    assert found(tmp_path, text) == [(8, "synthetic-world")]


@pytest.mark.parametrize(
    "address",
    [
        "owner@example.com",
        "https://dav.example.org/calendars",
        "https://dav.test",
        "https://localhost:8080/f/feed.ics",
        "192.0.2.7",
        "2001:db8::1",
        "https://[2001:db8::1]/dav",
        "127.0.0.1",
        "09:00 to 10:30:00",
        "version 1.7 on 2026-10-25",
    ],
)
def test_documentation_address_or_time_is_silent(tmp_path: Path, address: str) -> None:
    assert found(tmp_path, GOOD.replace("a thing", f"a calendar at {address}")) == []


ADDRESS_PLACES = {
    "feature-description": (GOOD.replace("  A sample.", "  Mail owner@mail.acme.de."), 2),
    "scenario-name": (GOOD.replace("Scenario: First", "Scenario: First at 10.0.0.7"), 7),
    "background-step": (
        GOOD.replace("  Rule:", "  Background:\n    Given the server 10.0.0.7\n\n  Rule:"),
        5,
    ),
    "doc-string": (
        GOOD.replace(
            "Given a thing\n",
            'Given a thing\n        """\n        owner@mail.acme.de\n        """\n',
        ),
        9,
    ),
    "data-table": (GOOD.replace("Given a thing\n", "Given a thing\n        | 10.0.0.7 |\n"), 9),
    "examples-cell": (OUTLINE.replace("| cat   | done  |", "| 10.0.0.7 | done |"), 12),
}


@pytest.mark.parametrize(("text", "line"), ADDRESS_PLACES.values(), ids=ADDRESS_PLACES.keys())
def test_real_address_anywhere_is_reported_on_its_line(
    tmp_path: Path, text: str, line: int
) -> None:
    assert found(tmp_path, text) == [(line, "synthetic-world")]


# --- id-stable: a feature keeps the @id it had on main -----------------------------------

RENUMBERED = GOOD.replace("@id:80", "@id:81")
# The second scenario moves to a feature of its own: the old feature keeps its id.
SPLIT = (
    GOOD.split("    @ALPHA-2", maxsplit=1)[0].replace("  Rule: One rule\n", ""),
    (
        "@id:90\nFeature: Other\n  Another.\n  @ALPHA-2\n  Scenario: Second\n"
        "    Given another thing\n    When it stops\n    Then it is over\n"
    ),
)


@pytest.mark.parametrize(
    ("before", "now", "expected"),
    [
        ([GOOD], [GOOD], []),
        ([GOOD], [RENUMBERED], ["@id:80 became @id:81 (@ALPHA-1, @ALPHA-2)"]),
        ([GOOD], [SPLIT[1]], ["@id:80 became @id:90 (@ALPHA-2)"]),
        ([GOOD], list(SPLIT), []),
        ([GOOD], [], []),
        ([], [GOOD], []),
        ([GOOD], ["Feature: x\n  | broken"], []),
        ([GOOD, ""], [GOOD, ""], []),
    ],
    ids=[
        "unchanged",
        "renumbered",
        "scenarios-moved-away",
        "split",
        "deleted",
        "new",
        "unparsed",
        "empty-file",
    ],
)
def test_feature_id_change_is_found_by_its_scenario_ids(
    before: list[str], now: list[str], expected: list[str]
) -> None:
    assert renumbering(before, now) == expected


def _git(root: Path, *args: str) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Dev",
        "GIT_AUTHOR_EMAIL": "dev@example.org",
        "GIT_COMMITTER_NAME": "Dev",
        "GIT_COMMITTER_EMAIL": "dev@example.org",
    }
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def test_feature_renumbered_since_main_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path, {FILE: GOOD})
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "switch", "-q", "-c", "topic")
    (root / FILE).write_text(RENUMBERED, encoding="utf-8")
    assert renumbered(root) == ["@id:80 became @id:81 (@ALPHA-1, @ALPHA-2)"]


def test_repository_without_main_fails_instead_of_passing(tmp_path: Path) -> None:
    root = tree(tmp_path, {FILE: GOOD})
    _git(root, "init", "-q", "-b", "topic")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")
    with pytest.raises(LookupError, match="fetch-depth"):
        renumbered(root)


def test_no_feature_changed_its_id_since_main() -> None:
    assert renumbered(REPO) == []
