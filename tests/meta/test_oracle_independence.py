"""A test oracle must not be copied from the code it checks.

A property that compares the implementation with its own pattern passes whenever the
pattern is wrong. Two shapes give the copy away, and both are read from the syntax tree:
a `re.compile` pattern literal in tests/ that appears verbatim as a string in src/, and a
test that imports a `_`-prefixed name from milchglas.core (it then tests the internals,
not the contract). Known limit: attribute access through a module alias
(`import milchglas.core.emit as e; e._x`) and a pattern built in pieces are not read.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
TESTS = REPO / "tests"


def _trees(root: Path) -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"))) for path in sorted(root.rglob("*.py"))
    ]


def string_literals(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def compiled_patterns(tree: ast.AST) -> set[str]:
    """The first argument of every `re.compile(...)` call, when it is a plain literal."""
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) == "re.compile"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def private_core_imports(tree: ast.AST) -> list[str]:
    return [
        f"from {node.module} import {alias.name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.level == 0
        and (node.module or "").split(".")[:2] == ["milchglas", "core"]
        for alias in node.names
        if alias.name.startswith("_")
    ]


@pytest.mark.parametrize(
    ("test_source", "src_source", "expected"),
    [
        ('re.compile(r"[a-z]+")', 'PATTERN = r"[a-z]+"', ["[a-z]+"]),
        ('re.compile(r"[a-z]+")', 'PATTERN = re.compile(r"[a-z]+")', ["[a-z]+"]),
        ('re.compile(r"[a-z]+")', 'PATTERN = r"[a-z0-9]+"', []),
        ('re.compile(rf"{x}")', 'PATTERN = r"{x}"', []),
        ('other.compile(r"[a-z]+")', 'PATTERN = r"[a-z]+"', []),
        ("re.compile(NAME)", 'NAME = "NAME"', []),
    ],
)
def test_pattern_copy_is_detected(test_source: str, src_source: str, expected: list[str]) -> None:
    copied = compiled_patterns(ast.parse(test_source)) & string_literals(ast.parse(src_source))
    assert sorted(copied) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from milchglas.core.emit import _duration",
            ["from milchglas.core.emit import _duration"],
        ),
        ("from milchglas.core import emit, _UNSAFE", ["from milchglas.core import _UNSAFE"]),
        ("from milchglas.core.emit import emit, uid", []),
        ("from milchglas.sources import _client", []),
        ("from other.milchglas.core import _x", []),
    ],
)
def test_private_core_import_is_detected(source: str, expected: list[str]) -> None:
    assert private_core_imports(ast.parse(source)) == expected


def test_no_test_pattern_is_a_copy_of_the_source() -> None:
    in_src = set().union(*(string_literals(tree) for _, tree in _trees(SRC)))
    copies = {
        str(path.relative_to(REPO)): sorted(compiled_patterns(tree) & in_src)
        for path, tree in _trees(TESTS)
        if compiled_patterns(tree) & in_src
    }
    assert copies == {}


def test_no_test_imports_a_private_name_from_core() -> None:
    imports = {
        str(path.relative_to(REPO)): found
        for path, tree in _trees(TESTS)
        if (found := private_core_imports(tree))
    }
    assert imports == {}
