"""Every scenario of a feature file runs, under the catalogue ID it carries.

Catalogue GATE-22.

pytest-bdd runs a scenario only when a test function binds it with `@scenario`, so a
scenario nobody binds is skipped without a word, and its ID tag reaches the checks of
GATE-17 only through the name of that function. Four checks close that, for every
scenario under `tests/features/`:

- tags: exactly one catalogue-shaped tag among its own, its rule's and its feature's tags
  (pytest-bdd applies all three), and that tag is a row ID.
- unbound: a function under `tests/` binds it as `@scenario("<path>", "<name>")`, both
  arguments literal strings and the path relative to `tests/features/`; a scenario tagged
  `@backlog` (specified, not built yet) may stay unbound; when bound, the hook expects it to
  fail, strictly, so a built scenario that keeps the tag fails the run.
- bound_twice: no second function binds it.
- misnamed: the binding function is `test_<id>` or `test_<id>_…`, the ID lower-cased with
  dashes as underscores, so pytest collects it and GATE-17 counts it as a citation.

A binding the check cannot read (`scenarios()`, a computed path) leaves its scenario
unbound, so the gap is reported, never hidden. The hook in `tests/conftest.py` keeps the
ID tags and the feature's `@id:<ticket>` out of the markers; any other tag still meets
`--strict-markers`.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd.parser import FeatureParser

from tests.conftest import CATALOGUE_ID, pytest_bdd_apply_tag
from tests.meta.test_catalogue_traceability import CATALOGUE, REPO, parse_catalogue, tree

FEATURES = Path("tests/features")

type Key = tuple[str, str]  # (path under tests/features/, scenario name)
type Problems = dict[str, list[str]]


def scenario_tags(root: Path) -> dict[Key, set[str]]:
    """The tags of every scenario, its rule's and its feature's included."""
    base = root / FEATURES
    found: dict[Key, set[str]] = {}
    for path in sorted(base.rglob("*.feature")):
        relative = path.relative_to(base).as_posix()
        feature = FeatureParser(str(base), relative).parse()
        for name, template in feature.scenarios.items():
            rule = template.rule.tags if template.rule else set()
            found[relative, name] = template.tags | rule | feature.tags
    return found


def bindings(root: Path) -> list[tuple[Key, str]]:
    """Each `@scenario("<path>", "<name>")` under tests/ with the function it decorates."""
    found: list[tuple[Key, str]] = []
    for path in sorted((root / "tests").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                match decorator:
                    case ast.Call(
                        func=ast.Name(id="scenario"),
                        args=[
                            ast.Constant(value=str() as feature),
                            ast.Constant(value=str() as name),
                        ],
                    ):
                        found.append(((feature, name), node.name))
                    case _:
                        pass  # not a readable binding: its scenario stays unbound
    return found


def problems(root: Path) -> Problems:
    rows = parse_catalogue((root / CATALOGUE).read_text(encoding="utf-8"))
    tags = scenario_tags(root)
    ids = {
        key: sorted(t for t in found if CATALOGUE_ID.fullmatch(t)) for key, found in tags.items()
    }
    bound: dict[Key, list[str]] = {key: [] for key in ids}
    for key, function in bindings(root):
        if key in bound:  # a binding to no scenario: pytest-bdd itself refuses it at import
            bound[key].append(function)

    def label(key: Key) -> str:
        return f"{key[0]}: {key[1]}"

    def leads_with_id(key: Key, function: str) -> bool:
        name = "test_" + ids[key][0].lower().replace("-", "_")
        return function == name or function.startswith(f"{name}_")

    return {
        "tags": [
            label(key) for key, found in ids.items() if len(found) != 1 or found[0] not in rows
        ],
        "unbound": [
            label(key)
            for key, functions in bound.items()
            if not functions and "backlog" not in tags[key]
        ],
        "bound_twice": [label(key) for key, functions in bound.items() if len(functions) > 1],
        "misnamed": [
            f"{label(key)}: {function}"
            for key, functions in bound.items()
            if len(ids[key]) == 1
            for function in functions
            if not leads_with_id(key, function)
        ],
    }


# --- the real tree -----------------------------------------------------------------------


def test_every_scenario_runs_under_its_id() -> None:
    assert problems(REPO) == {"tags": [], "unbound": [], "bound_twice": [], "misnamed": []}


# --- the checks on synthetic features and bindings ---------------------------------------
# The areas ALPHA and BETA are not in the real catalogue, so these strings are no citation.

FEATURE = """\
Feature: Sample

  Rule: One rule

    @ALPHA-1
    Scenario: First
      Given nothing

    @BETA-SUB-1
    Scenario: Second
      Given nothing
"""

BINDINGS = """\
@scenario("area/sample.feature", "First")
def test_alpha_1_first() -> None: ...


@scenario("area/sample.feature", "Second")
def test_beta_sub_1() -> None: ...
"""


def features(tmp_path: Path, feature: str = FEATURE, bindings: str = BINDINGS) -> Path:
    return tree(
        tmp_path,
        {"tests/features/area/sample.feature": feature, "tests/unit/test_sample.py": bindings},
    )


def test_bound_and_tagged_scenarios_are_silent(tmp_path: Path) -> None:
    assert problems(features(tmp_path)) == {
        "tags": [],
        "unbound": [],
        "bound_twice": [],
        "misnamed": [],
    }


def test_tag_inherited_from_the_rule_counts(tmp_path: Path) -> None:
    feature = FEATURE.replace("  Rule: One rule", "  @ALPHA-1\n  Rule: One rule")
    feature = feature.replace("    @ALPHA-1\n    Scenario: First", "    Scenario: First")
    feature = feature.replace("    @BETA-SUB-1\n    Scenario: Second", "    Scenario: Second")
    bindings = BINDINGS.replace("test_beta_sub_1", "test_alpha_1_second")
    assert problems(features(tmp_path, feature, bindings))["tags"] == []


@pytest.mark.parametrize(
    "feature",
    [
        FEATURE.replace("    @ALPHA-1\n", ""),
        FEATURE.replace("@ALPHA-1", "@ALPHA-1 @BETA-SUB-1"),
        FEATURE.replace("  Rule: One rule", "  @BETA-SUB-1\n  Rule: One rule"),
        FEATURE.replace("Feature: Sample", "@BETA-SUB-1\nFeature: Sample"),
        FEATURE.replace("@ALPHA-1", "@ALPHA-9"),
    ],
    ids=["no-id", "two-ids", "second-id-from-rule", "second-id-from-feature", "not-a-row"],
)
def test_scenario_without_exactly_one_row_id_is_reported(tmp_path: Path, feature: str) -> None:
    assert "area/sample.feature: First" in problems(features(tmp_path, feature))["tags"]


@pytest.mark.parametrize(
    "bindings",
    [
        BINDINGS.split("\n\n\n")[1],
        BINDINGS.replace('@scenario("area/sample.feature", "First")', "@scenario(PATH, 'First')"),
        BINDINGS.replace('"First")', '"Frist")'),
    ],
    ids=["no-binding", "computed-path", "other-name"],
)
def test_scenario_nobody_binds_is_reported(tmp_path: Path, bindings: str) -> None:
    assert problems(features(tmp_path, bindings=bindings))["unbound"] == [
        "area/sample.feature: First"
    ]


@pytest.mark.parametrize(
    "feature",
    [
        FEATURE.replace("    @ALPHA-1\n", "    @backlog @ALPHA-1\n"),
        FEATURE.replace("  Rule: One rule", "  @backlog\n  Rule: One rule"),
        FEATURE.replace("Feature: Sample", "@backlog\nFeature: Sample"),
    ],
    ids=["own-tag", "from-rule", "from-feature"],
)
def test_backlog_scenario_nobody_binds_is_silent(tmp_path: Path, feature: str) -> None:
    bindings = BINDINGS.split("\n\n\n")[1]
    assert problems(features(tmp_path, feature, bindings))["unbound"] == []


def test_ticket_tag_is_no_catalogue_id(tmp_path: Path) -> None:
    feature = FEATURE.replace("Feature: Sample", "@id:23\nFeature: Sample")
    assert problems(features(tmp_path, feature))["tags"] == []


def test_scenario_bound_twice_is_reported(tmp_path: Path) -> None:
    root = features(tmp_path)
    (root / "tests/unit/test_again.py").write_text(
        BINDINGS.split("\n\n\n", maxsplit=1)[0], encoding="utf-8"
    )
    assert problems(root)["bound_twice"] == ["area/sample.feature: First"]


@pytest.mark.parametrize(
    "name", ["test_alpha_10_first", "check_alpha_1_first", "test_first_alpha_1", "test_alpha_1x"]
)
def test_binding_whose_name_does_not_lead_with_the_id_is_reported(
    tmp_path: Path, name: str
) -> None:
    bindings = BINDINGS.replace("test_alpha_1_first", name)
    assert problems(features(tmp_path, bindings=bindings))["misnamed"] == [
        f"area/sample.feature: First: {name}"
    ]


# --- the marker hook ---------------------------------------------------------------------


def _bound() -> None: ...


@pytest.mark.parametrize("tag", ["ALPHA-1", "BETA-SUB-1", "AREA-12", "id:23"])
def test_id_tag_is_no_marker(tag: str) -> None:
    assert pytest_bdd_apply_tag(tag, _bound) is True
    assert not hasattr(_bound, "pytestmark")


def test_backlog_tag_expects_the_scenario_to_fail() -> None:
    def bound() -> None: ...

    assert pytest_bdd_apply_tag("backlog", bound) is True
    [mark] = getattr(bound, "pytestmark", [])
    assert (mark.name, mark.kwargs.get("strict")) == ("xfail", True)


BACKLOG_FEATURE = """\
Feature: Sample

  @backlog
  Scenario: Not built
    Given nothing yet

  @backlog
  Scenario: Built
    Given a thing
"""

BACKLOG_TESTS = """\
from pytest_bdd import given, scenario


@scenario("sample.feature", "Not built")
def test_not_built() -> None: ...


@scenario("sample.feature", "Built")
def test_built() -> None: ...


@given("a thing")
def _thing() -> None: ...
"""


def test_built_backlog_scenario_fails_the_run(tmp_path: Path) -> None:
    """A bound `@backlog` scenario whose steps pass fails; one with a missing step does not."""
    (tmp_path / "sample.feature").write_text(BACKLOG_FEATURE, encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(BACKLOG_TESTS, encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "from tests.conftest import pytest_bdd_apply_tag  # noqa: F401\n", encoding="utf-8"
    )
    run = subprocess.run(  # noqa: S603 - the interpreter running this suite
        [
            *(sys.executable, "-m", "pytest", "-c", os.devnull, "--rootdir", str(tmp_path)),
            *("-p", "no:cacheprovider", "-q", "-rX", str(tmp_path)),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ | {"PYTHONPATH": str(REPO)},
    )
    assert run.returncode == 1, run.stdout
    assert "XPASS(strict)" in run.stdout
    assert "1 failed, 1 xfailed" in run.stdout


@pytest.mark.parametrize("tag", ["slow", "alpha-1", "ALPHA", "ALPHA-1x", "id", "backlogged"])
def test_other_tag_stays_a_marker(tag: str) -> None:
    assert pytest_bdd_apply_tag(tag, _bound) is None
