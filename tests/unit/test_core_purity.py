"""src/milchglas/core must stay pure: no I/O, no clock, no imports from outside core.

The feed has to be byte-identical for unchanged source, so the pipeline core computes and
never observes: no filesystem, network or environment access, and no reading of the
current time (DTSTAMP is the last content change, which the caller passes in).

A denylist of I/O modules cannot enumerate the standard library, so purity is checked as
an allowlist property: every import in core/ is on the list below, relative imports never
climb out of core, calls that read a clock are rejected, and core stays a package so the
tree scan cannot go silently empty. The ruff TID251 ban in pyproject.toml gives the same
feedback in the editor; this test is the gate.

Known limits: the import rule reads the module graph, so deliberate obfuscation
(`_imp = __import__`, `__builtins__["open"]`) passes. The clock rule matches calls, so a
clock passed as a value (`field(default_factory=datetime.now)`) and ambient-timezone
reads (`astimezone()` without an argument, `zoneinfo.reset_tzpath`) are not caught; it is
also receiver-blind, so a pure `clock.now()` parameter method is flagged. Until core/
holds code the tree scan is empty and the case table below carries the proof.
"""

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "src" / "milchglas" / "core"
# Pure computation only. Extend deliberately, in review, when core needs a module
# (icalendar / dateutil once reduce and emit land).
ALLOWED_MODULES = frozenset(
    {
        "__future__",
        "bisect",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "hashlib",
        "itertools",
        "math",
        "milchglas.core",
        "operator",
        "re",
        "typing",
        "zoneinfo",
    }
)
FORBIDDEN_CALLS = frozenset({"__import__", "compile", "eval", "exec", "open"})
CLOCK_METHODS = frozenset({"now", "today", "utcnow"})


def _allowed(module: str) -> bool:
    return any(module == ok or module.startswith(f"{ok}.") for ok in ALLOWED_MODULES)


def _import_from_violations(node: ast.ImportFrom, depth: int) -> list[str]:
    # A file `depth` packages below core/ may climb at most to core/ itself.
    if node.level > depth + 1:
        return [f"from {'.' * node.level}{node.module or ''} import"]
    if node.level == 0 and not _allowed(node.module or ""):
        return [f"from {node.module} import"]
    return []


def _call_violations(node: ast.Call) -> list[str]:
    func = node.func
    if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
        return [f"{func.id}()"]
    if isinstance(func, ast.Attribute) and func.attr in CLOCK_METHODS:
        return [f"{ast.unparse(func)}()"]
    return []


def purity_violations(source: str, depth: int = 0) -> list[str]:
    """Return every impurity in *source*, a module `depth` packages below core/."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [f"import {alias.name}" for alias in node.names if not _allowed(alias.name)]
        elif isinstance(node, ast.ImportFrom):
            found += _import_from_violations(node, depth)
        elif isinstance(node, ast.Call):
            found += _call_violations(node)
    return found


@pytest.mark.parametrize(
    ("source", "depth", "expected"),
    [
        # Pure: allowlisted modules, imports that stay inside core.
        ("from datetime import datetime, timedelta", 0, []),
        ("import itertools\nfrom collections.abc import Iterable", 0, []),
        ("from . import model\nfrom milchglas.core.model import Interval", 0, []),
        ("from .. import model", 1, []),
        # Impure imports.
        ("import sqlite3", 0, ["import sqlite3"]),
        ("from gzip import open as gz_open", 0, ["from gzip import"]),
        ("import os.path", 0, ["import os.path"]),
        ("import tarfile, zipfile", 0, ["import tarfile", "import zipfile"]),
        ("import builtins", 0, ["import builtins"]),
        ("x = __import__('os')", 0, ["__import__()"]),
        ("open('feed.ics')", 0, ["open()"]),
        # Relative imports climbing out of core.
        ("from .. import refresh", 0, ["from .. import"]),
        ("from ..sources import caldav", 0, ["from ..sources import"]),
        ("from ... import state", 1, ["from ... import"]),
        # Clock reads.
        ("stamp = datetime.now(tz=UTC)", 0, ["datetime.now()"]),
        ("day = date.today()", 0, ["date.today()"]),
        ("t = dt.datetime.utcnow()", 0, ["dt.datetime.utcnow()"]),
    ],
)
def test_purity_violations_discriminates(source: str, depth: int, expected: list[str]) -> None:
    assert purity_violations(source, depth) == expected


def test_core_is_a_package_so_the_scan_cannot_go_silently_empty() -> None:
    assert not CORE.with_suffix(".py").exists()


def test_core_modules_are_pure() -> None:
    violations = {
        str(path.relative_to(CORE)): found
        for path in sorted(CORE.rglob("*.py"))
        if (
            found := purity_violations(
                path.read_text(encoding="utf-8"), len(path.relative_to(CORE).parts) - 1
            )
        )
    }
    assert violations == {}
