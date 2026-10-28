"""Suite-wide setup: host zone, Hypothesis profiles and a git environment that belongs to no hook.

`dev` runs locally, `ci` on CI runners (GitHub sets CI): more examples, derandomized so a
failing example reproduces from the printed blob. HYPOTHESIS_PROFILE overrides either.
"""

import os
import re
import time

import pytest
from hypothesis import settings

# A catalogue ID such as AREA-3 or AREA-SUB-3: the shape of the ID column of the catalogue.
CATALOGUE_ID = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+")

# GATE-20: CI runners run in UTC, which hides a conversion to local time where UTC is
# meant. A zone with DST and a half-hour offset makes every such slip move a block.
os.environ["TZ"] = "America/St_Johns"
time.tzset()

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


def pytest_bdd_apply_tag(tag: str) -> bool | None:
    """Keep a scenario's catalogue ID out of the markers (GATE-22).

    The ID tag names the scenario's catalogue row, so `--strict-markers` must not refuse it.
    Any other tag stays a marker and has to be registered in `pyproject.toml`.
    """
    return True if CATALOGUE_ID.fullmatch(tag) else None
