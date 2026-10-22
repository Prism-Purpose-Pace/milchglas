"""The suite runs inside git hooks: no inherited GIT_* variable may steer a test (GATE-18).

`git push` hands its pre-push hook GIT_DIR, and pre-commit's pytest hook inherits it. In a
linked worktree that path is absolute, so a test that builds a throwaway repository and
runs a script in it acted on the real repository instead: 56 failures, and the main
checkout's hook shim rewritten. GIT_INDEX_FILE and GIT_WORK_TREE outrank `-C` the same way,
so the whole family is planted here, at a decoy, and the decoy must come out untouched.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Builds throwaway repositories and writes hook files: the case that hit the real checkout.
PROBE = "tests/scripts/test_install_push_guard.py"


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_planted_git_environment_reaches_no_test_gate_18(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy"
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "init", "-q", str(decoy)], check=True, env=clean)
    before = _tree(decoy / ".git")
    planted = {
        **clean,
        "GIT_DIR": str(decoy / ".git"),
        "GIT_WORK_TREE": str(decoy),
        "GIT_INDEX_FILE": str(decoy / ".git" / "index"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--no-cov", "-q", "-p", "no:cacheprovider", PROBE],
        cwd=REPO,
        env=planted,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    assert _tree(decoy / ".git") == before
