"""The var directory: atomic feed and state writes, one run at a time (FR-8, FR-11).

The catalogue rows for a crash between two writes, a corrupt state and a second concurrent
run describe whole refresh runs and close with the refresh tests; the primitives they rest
on are pinned here.
"""

import errno
import os
import stat
import tempfile
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from milchglas.state import (
    FEED,
    STATE,
    BusyError,
    State,
    read_state,
    run_lock,
    write_atomic,
    write_state,
)

OLD = b"BEGIN:VCALENDAR\r\nold\r\nEND:VCALENDAR\r\n"
NEW = b"BEGIN:VCALENDAR\r\nnew\r\nEND:VCALENDAR\r\n"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name.endswith(".tmp"))


def test_success_writes_beside_the_target_and_syncs_orch_write_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    var = tmp_path / "var"
    synced: list[str] = []
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        synced.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        real_fsync(fd)

    created: list[Path] = []
    real_mkstemp = tempfile.mkstemp

    def mkstemp(**kwargs: str | Path) -> tuple[int, str]:
        fd, name = real_mkstemp(**kwargs)  # type: ignore[call-overload]
        created.append(Path(name))
        return fd, name

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    with run_lock(var):
        write_atomic(var / FEED, NEW)
    assert (var / FEED).read_bytes() == NEW
    assert [p.parent for p in created] == [var]
    assert synced == ["file", "dir"]
    assert _leftovers(var) == []
    assert _mode(var / FEED) == 0o644
    assert _mode(var) == 0o700


def test_failure_before_the_replace_keeps_the_old_file_orch_write_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = tmp_path / FEED
    feed.write_bytes(OLD)

    def replace(_self: Path, _target: Path) -> Path:
        raise OSError(errno.EIO, "injected")

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OSError, match="injected"):
        write_atomic(feed, NEW)
    assert feed.read_bytes() == OLD
    assert _leftovers(tmp_path) == []


def test_full_disk_keeps_the_old_file_orch_write_5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = tmp_path / FEED
    feed.write_bytes(OLD)
    mtime = feed.stat().st_mtime_ns

    def fsync(_fd: int) -> None:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(OSError, match="No space"):
        write_atomic(feed, NEW)
    assert feed.read_bytes() == OLD
    assert feed.stat().st_mtime_ns == mtime
    assert _leftovers(tmp_path) == []


def test_state_round_trips(tmp_path: Path) -> None:
    recorded = State(datetime(2026, 10, 22, 7, 0, tzinfo=UTC), "TimeoutError calendar=1")
    write_state(tmp_path, recorded)
    assert read_state(tmp_path) == recorded
    assert _mode(tmp_path / STATE) == 0o644


def test_state_keeps_the_offset_as_an_instant(tmp_path: Path) -> None:
    moment = datetime(2026, 10, 22, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    write_state(tmp_path, State(moment, None))
    assert read_state(tmp_path).last_success == moment


def test_missing_state_counts_as_absent(tmp_path: Path) -> None:
    assert read_state(tmp_path) == State()


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"\xff",
        b"[]",
        b"{}",
        b'{"last_success": 5, "last_error": null}',
        b'{"last_success": "yesterday", "last_error": null}',
        b'{"last_success": "2026-10-22T07:00:00", "last_error": null}',
        b'{"last_success": null, "last_error": 3}',
    ],
)
def test_corrupt_state_counts_as_absent(tmp_path: Path, content: bytes) -> None:
    (tmp_path / STATE).write_bytes(content)
    assert read_state(tmp_path) == State()


def test_second_run_is_refused_while_the_lock_is_held(tmp_path: Path) -> None:
    with run_lock(tmp_path), pytest.raises(BusyError), run_lock(tmp_path):
        pytest.fail("a second run got the lock")
    with run_lock(tmp_path):
        pass


def test_lock_leaves_an_existing_var_dir_mode_alone(tmp_path: Path) -> None:
    tmp_path.chmod(0o750)
    with run_lock(tmp_path):
        pass
    assert _mode(tmp_path) == 0o750
