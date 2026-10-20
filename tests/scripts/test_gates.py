"""gates.py: the runtime cache probe that lets the gates run on a sandboxed host."""

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

import gates


def _only(*allowed: Path) -> Callable[[Path], bool]:
    allowed_set = {str(path) for path in allowed}
    return lambda path: str(path) in allowed_set


def test_first_writable_candidate_wins(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    assert gates.pick([first, second], _only(first, second)) == first


def test_unwritable_candidate_is_skipped(tmp_path: Path) -> None:
    denied, usable = tmp_path / "denied", tmp_path / "usable"
    assert gates.pick([denied, usable], _only(usable)) == usable


def test_no_writable_candidate_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no writable cache directory"):
        gates.pick([tmp_path / "x"], lambda _: False)


def test_absolute_value_from_the_environment_is_preferred(tmp_path: Path) -> None:
    shared = tmp_path / "host-cache"
    found = gates.candidates(str(shared), "uv", tmp_path / "home", tmp_path / "r", tmp_path / "t")
    assert found[0] == shared


def test_relative_value_from_the_environment_is_discarded(tmp_path: Path) -> None:
    # The measured defect: `.claude/.cache/uv` is resolved by whichever process reads it,
    # with that process's CWD, so pre-commit's `uv venv` child wrote outside the allowlist
    # and failed with "Operation not permitted". A relative value must never be honoured.
    found = gates.candidates(
        ".claude/.cache/uv", "uv", tmp_path / "home", tmp_path / "r", tmp_path / "t"
    )
    assert all(path.is_absolute() for path in found)
    assert Path(".claude/.cache/uv") not in found


def test_blank_environment_value_falls_through(tmp_path: Path) -> None:
    home, repo, tmp = tmp_path / "home", tmp_path / "repo", tmp_path / "tmp"
    assert gates.candidates("   ", "uv", home, repo, tmp) == [
        home / ".cache" / "uv",
        repo / ".claude" / ".cache" / "uv",
        tmp / "uv",
    ]


def test_both_cache_variables_get_absolute_paths(tmp_path: Path) -> None:
    env = gates.gate_env(
        {"UV_CACHE_DIR": ".claude/.cache/uv", "PATH": "/usr/bin"},
        tmp_path / "home",
        tmp_path / "repo",
        tmp_path / "tmp",
        lambda path: "home" in str(path),
    )
    assert Path(env["UV_CACHE_DIR"]).is_absolute()
    assert Path(env["PRE_COMMIT_HOME"]).is_absolute()
    assert env["PATH"] == "/usr/bin"  # the rest of the environment survives


def test_home_cache_is_preferred_over_the_repo_and_tmp(tmp_path: Path) -> None:
    home, repo, tmp = tmp_path / "home", tmp_path / "repo", tmp_path / "tmp"
    env = gates.gate_env({}, home, repo, tmp, lambda _: True)
    assert env["UV_CACHE_DIR"] == str(home / ".cache" / "uv")
    assert env["PRE_COMMIT_HOME"] == str(home / ".cache" / "pre-commit")


def test_repo_cache_is_used_when_the_home_cache_is_refused(tmp_path: Path) -> None:
    # The sandboxed host: ~/.cache is write-denied, so the gates keep a persistent cache
    # inside the repository instead of rebuilding under $TMPDIR after every reboot.
    home, repo, tmp = tmp_path / "home", tmp_path / "repo", tmp_path / "tmp"
    env = gates.gate_env({}, home, repo, tmp, lambda path: not str(path).startswith(str(home)))
    assert env["UV_CACHE_DIR"] == str(repo / ".claude" / ".cache" / "uv")


def test_tmp_is_the_last_resort(tmp_path: Path) -> None:
    home, repo, tmp = tmp_path / "home", tmp_path / "repo", tmp_path / "tmp"
    env = gates.gate_env({}, home, repo, tmp, lambda path: str(path).startswith(str(tmp)))
    assert env["UV_CACHE_DIR"] == str(tmp / "uv")


def test_writable_reports_false_on_a_refused_mkdir(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    assert gates.writable(blocker / "below") is False


def test_writable_creates_a_missing_directory(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "cache"
    assert gates.writable(target) is True
    assert target.is_dir()


class FakeExec:
    def __init__(self) -> None:
        self.argv: list[str] = []
        self.env: dict[str, str] = {}

    def __call__(self, file: str, argv: list[str], env: Mapping[str, str]) -> None:
        self.file = file
        self.argv = argv
        self.env = dict(env)


def test_default_runs_every_hook_through_the_lock() -> None:
    fake = FakeExec()
    assert gates.main([], {}, fake) == 0
    assert fake.file == "uv"
    assert fake.argv == ["uv", "run", "--frozen", "pre-commit", "run", "--all-files"]


def test_arguments_pass_through_to_pre_commit() -> None:
    fake = FakeExec()
    gates.main(["run", "--hook-stage", "pre-push", "--all-files"], {}, fake)
    assert fake.argv[4:] == ["run", "--hook-stage", "pre-push", "--all-files"]


def test_the_exec_environment_carries_absolute_caches() -> None:
    fake = FakeExec()
    gates.main([], {"UV_CACHE_DIR": "relative/path"}, fake)
    assert Path(fake.env["UV_CACHE_DIR"]).is_absolute()
    assert Path(fake.env["PRE_COMMIT_HOME"]).is_absolute()
