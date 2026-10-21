"""Every wheel in the runtime closure is pure Python (spec NFR-O3, AC-12; catalogue GATE-2).

Options A to C share one codebase only while no runtime dependency ships native code.
The closure is walked from `importlib.metadata.requires("milchglas")`: a requirement
whose marker is false here (an extra, another platform, another Python) is skipped, so
dev tools such as mypy, which ship native wheels, never enter. Each distribution's WHEEL
file must say `Root-Is-Purelib: true`, and every `Tag:` must match `py*-none-any`.

`milchglas` itself is the project under test and not a dependency: it is the root of the
walk and its own WHEEL is never read, so an editable install without one cannot fail the
test. A dependency without a WHEEL file does fail it, because its purity cannot be shown.
Known limit: the check reads the installed environment, which `uv sync --locked` builds
from `uv.lock`; it does not read the lock file itself.
"""

from collections.abc import Callable
from email.parser import Parser
from fnmatch import fnmatchcase
from importlib import metadata

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

type Requires = Callable[[str], list[str] | None]

PURE = "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
NATIVE = "Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-cp312-linux_x86_64\n"


def runtime_closure(root: str, requires: Requires = metadata.requires) -> set[str]:
    """Names of every distribution `root` needs at run time, `root` excluded."""
    seen: set[str] = set()
    pending = [canonicalize_name(root)]
    while pending:
        for text in requires(pending.pop()) or []:
            requirement = Requirement(text)
            name = canonicalize_name(requirement.name)
            if name in seen or name == canonicalize_name(root):
                continue
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                seen.add(name)
                pending.append(name)
    return seen


def wheel_problems(wheel: str) -> list[str]:
    """Why the text of a WHEEL file does not show a pure-Python wheel."""
    message = Parser().parsestr(wheel)
    problems = []
    if (message.get("Root-Is-Purelib") or "").strip().lower() != "true":
        problems.append(f"Root-Is-Purelib is {message.get('Root-Is-Purelib')!r}, not 'true'")
    tags = message.get_all("Tag") or []
    if not tags:
        problems.append("no Tag line")
    problems += [f"Tag {tag!r} is not py*-none-any" for tag in tags if not _pure_tag(tag)]
    return problems


def _pure_tag(tag: str) -> bool:
    return fnmatchcase(tag.strip(), "py*-none-any")


def test_every_runtime_wheel_is_pure_python() -> None:
    closure = runtime_closure("milchglas")
    assert closure  # an empty walk would pass the loop below
    problems = {}
    for name in sorted(closure):
        wheel = metadata.distribution(name).read_text("WHEEL")
        found = ["no WHEEL file"] if wheel is None else wheel_problems(wheel)
        if found:
            problems[name] = found
    assert problems == {}


def test_the_closure_holds_the_declared_dependencies_and_what_they_pull_in() -> None:
    declared = {
        canonicalize_name(Requirement(r).name) for r in metadata.requires("milchglas") or []
    }
    closure = runtime_closure("milchglas")
    assert declared <= closure
    # python-dateutil comes in through icalendar, not from our own list.
    assert "python-dateutil" in closure - declared


def test_the_walk_follows_runtime_requirements_only() -> None:
    graph = {
        "root": ["a>=1", "Dev-Tool; extra == 'dev'", "win-only; sys_platform == 'win32'"],
        "a": ["b", "root", "A_Dep; python_version >= '3.0'"],
        "b": ["a"],  # a cycle must end
        "a-dep": [],
        "dev-tool": ["native-thing"],
    }
    assert runtime_closure("root", graph.get) == {"a", "b", "a-dep"}


@pytest.mark.parametrize(
    ("wheel", "expected"),
    [
        (PURE, 0),
        ("Root-Is-Purelib: true\nTag: py2-none-any\nTag: py3-none-any\n", 0),
        (NATIVE, 2),  # not purelib, and a cp312-cp312-linux_x86_64 tag
        ("Root-Is-Purelib: true\nTag: cp312-cp312-linux_x86_64\n", 1),
        ("Root-Is-Purelib: false\nTag: py3-none-any\n", 1),
        ("Root-Is-Purelib: true\nTag: py3-none-any\nTag: cp312-cp312-macosx_11_0_arm64\n", 1),
        ("Root-Is-Purelib: true\nTag: cp312-none-any\n", 1),  # NFR-O3 names py*-none-any
        ("Root-Is-Purelib: true\n", 1),  # no tag says nothing about the platform
        ("Tag: py3-none-any\n", 1),  # no purelib line
    ],
    ids=[
        "pure",
        "pure-two-tags",
        "native",
        "native-tag",
        "not-purelib",
        "one-native-tag-of-two",
        "non-py-python-tag",
        "no-tag",
        "no-purelib-line",
    ],
)
def test_the_wheel_check_fails_on_anything_that_is_not_pure(wheel: str, expected: int) -> None:
    assert len(wheel_problems(wheel)) == expected
