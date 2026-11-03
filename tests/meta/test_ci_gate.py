"""CI runs lint, the strict type check and the tests with the branch-coverage floor.

Catalogue GATE-1.

The gate itself is CI: a red job blocks the merge. What can drift unseen is the wiring, a
step dropped from the workflow or a weaker setting in `pyproject.toml`, after which CI stays
green while checking less. These tests fail on that drift.
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
RUN = re.compile(r"^\s*- run: (.+?)\s*$", re.MULTILINE)


def test_ci_runs_lint_types_and_tests_gate_1() -> None:
    runs = set(RUN.findall(WORKFLOW))
    required = {
        "uv run --frozen ruff check --output-format=github",
        "uv run --frozen ruff format --check",
        "uv run --frozen mypy",
        "uv run --frozen pytest",
    }
    assert required - runs == set()


def test_type_check_is_strict_gate_1() -> None:
    assert PYPROJECT["tool"]["mypy"]["strict"] is True


def test_tests_measure_branch_coverage_with_a_floor_of_90_gate_1() -> None:
    assert "--cov-branch" in PYPROJECT["tool"]["pytest"]["addopts"]
    assert PYPROJECT["tool"]["coverage"]["run"]["branch"] is True
    assert PYPROJECT["tool"]["coverage"]["report"]["fail_under"] >= 90
