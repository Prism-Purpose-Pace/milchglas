"""Suite-wide setup: Hypothesis profiles and a git environment that belongs to no hook.

`dev` runs locally, `ci` on CI runners (GitHub sets CI): more examples, derandomized so a
failing example reproduces from the printed blob. HYPOTHESIS_PROFILE overrides either.
"""

import os

import pytest
from hypothesis import settings

settings.register_profile("dev", max_examples=100, deadline=None)
settings.register_profile("ci", max_examples=500, deadline=None, derandomize=True, print_blob=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci" if os.environ.get("CI") else "dev"))


@pytest.fixture(autouse=True)
def _no_inherited_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every GIT_* variable a git hook hands the suite (GATE-18).

    The whole family, not GIT_DIR alone: GIT_INDEX_FILE and GIT_WORK_TREE outrank `-C` too.
    os.environ itself, not `env=` per call, because the scripts under test spawn git again.
    """
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
