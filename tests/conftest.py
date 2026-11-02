"""Suite-wide setup: host zone, Hypothesis profiles and a git environment that belongs to no hook.

`dev` runs locally, `ci` on CI runners (GitHub sets CI): more examples, derandomized so a
failing example reproduces from the printed blob. HYPOTHESIS_PROFILE overrides either.
"""

import os
import re
import time
from collections.abc import Callable

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


def pytest_bdd_apply_tag(tag: str, function: Callable[..., object]) -> bool | None:
    """Give the feature-file tags that are no markers their meaning (GATE-22).

    A catalogue ID names the scenario's row and `@id:<ticket>` the feature's ticket, so
    `--strict-markers` must not refuse them. `@backlog` marks a scenario as specified but not
    built yet: it is expected to fail, strictly, so a scenario built without removing the
    tag fails the run (D-18). Any other tag stays a marker and has to be registered in
    `pyproject.toml`.
    """
    if tag == "backlog":
        pytest.mark.xfail(strict=True, reason="@backlog: specified, not built yet")(function)
        return True
    return True if CATALOGUE_ID.fullmatch(tag) or tag.startswith("id:") else None
