"""The var directory (`MILCHGLAS_VAR_DIR`): feed, state and run lock (FR-8, FR-11, D-16).

Both files are replaced atomically or not at all, so a failed run leaves the last good
feed byte-identical (D-7d), and `web` never reads a half-written file.
"""

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

FEED = "feed.ics"
STATE = "state.json"
LOCK = "run.lock"


class BusyError(RuntimeError):
    """Another run holds the lock."""


@dataclass(frozen=True, slots=True)
class State:
    """What `/healthz` reads: the last success and the last error (exception class, index)."""

    last_success: datetime | None = None
    last_error: str | None = None


@contextmanager
def run_lock(var_dir: Path) -> Iterator[None]:
    """Hold the exclusive run lock, creating the var directory `0700` if it is missing.

    The lock file is never removed: deleting it would let a second run lock a new inode.
    """
    var_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (var_dir / LOCK).open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            msg = "another run holds the lock"
            raise BusyError(msg) from None
        yield


def write_atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Replace `path` with `data`, or leave it as it was (FR-8).

    The temporary file sits beside the target, never in a tmpfs `/tmp`: a rename across
    filesystems fails with EXDEV.
    """
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        temp.replace(path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_state(var_dir: Path) -> State:
    """The recorded state; a missing or corrupt file counts as absent."""
    try:
        raw = json.loads((var_dir / STATE).read_bytes())
        success, error = raw["last_success"], raw["last_error"]
        moment = None if success is None else datetime.fromisoformat(success)
    except (OSError, ValueError, KeyError, TypeError):
        return State()
    if (moment is not None and moment.utcoffset() is None) or not isinstance(error, str | None):
        return State()
    return State(moment, error)


def write_state(var_dir: Path, recorded: State) -> None:
    success = recorded.last_success
    payload = {
        "last_error": recorded.last_error,
        "last_success": None if success is None else success.isoformat(),
    }
    write_atomic(var_dir / STATE, json.dumps(payload, sort_keys=True).encode() + b"\n")
