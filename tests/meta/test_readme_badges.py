"""README badges state what the repository enforces and link to files that exist.

The coverage badge is static, so nothing updates it when `fail_under` changes; the
document badges point at repository files, which a rename breaks silently.
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
README = (REPO / "README.md").read_text(encoding="utf-8")
BADGE = re.compile(r"\[!\[[^\]]*\]\((https://img\.shields\.io/[^)\s]+)\)\]\(([^)\s]+)\)")


def test_coverage_badge_matches_the_enforced_threshold() -> None:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    badge = re.search(r"img\.shields\.io/badge/coverage-%E2%89%A5(\d+)%25", README)
    assert badge is not None
    assert int(badge.group(1)) == pyproject["tool"]["coverage"]["report"]["fail_under"]


def test_threat_model_and_architecture_have_badges() -> None:
    targets = {target for _, target in BADGE.findall(README)}
    assert {"docs/threat-model.md", "docs/architecture.md"} <= targets


def test_local_badge_targets_exist() -> None:
    local = [t for _, t in BADGE.findall(README) if not t.startswith("https://")]
    assert local
    assert [t for t in local if not (REPO / t).is_file()] == []
