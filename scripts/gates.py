# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Run the pre-commit gates with a cache directory this host can actually write.

    python3 scripts/gates.py                                  # commit stage, all files
    python3 scripts/gates.py run --hook-stage pre-push --all-files

Plain `python3`, never `uv run --script`: uv needs a writable cache before it runs
anything, which is the problem this script exists to solve. Stdlib only, for the same
reason.

uv's default cache (`~/.cache/uv`) is write-denied inside the Claude Code sandbox, and a
relative override does not help. A relative value is resolved by the process that READS
it, with that process's CWD — not against the repository root. pre-commit builds each
remote hook's environment by spawning `uv venv` from inside the hook repository, so
`.claude/.cache/uv` resolves below that repository and dies with "Operation not
permitted". Both variables therefore get an absolute path chosen here, at runtime, so the
repository needs no host configuration at all.

Candidate order, most persistent first: an absolute value already in the environment (so
a host-level cache keeps being shared across repositories), then `~/.cache/<name>`, then
the repo-local `.claude/.cache/<name>`, then the system temp directory. A relative value
in the environment is discarded, which is also the migration path off the old setting.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

DEFAULT_ARGS = ("run", "--all-files")
# (environment variable, directory name under the chosen cache root)
CACHES = (("UV_CACHE_DIR", "uv"), ("PRE_COMMIT_HOME", "pre-commit"))


def writable(path: Path) -> bool:
    """True when `path` exists or can be created, and accepts a write."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def candidates(current: str, name: str, home: Path, repo: Path, tmp: Path) -> list[Path]:
    """Cache locations to try for one variable, most persistent first.

    `current` is the value already in the environment; it only counts when absolute. The
    home cache comes before the repo-local one so an unsandboxed host shares one cache
    across repositories instead of duplicating it; `tmp` is the last resort and is lost
    on reboot.
    """
    found = [Path(current)] if current.strip() and Path(current.strip()).is_absolute() else []
    found.append(home / ".cache" / name)
    found.append(repo / ".claude" / ".cache" / name)
    found.append(tmp / name)
    return found


def pick(paths: Iterable[Path], is_writable: Callable[[Path], bool] = writable) -> Path:
    """First writable path. Raises when every candidate is refused."""
    for path in paths:
        if is_writable(path):
            return path
    message = "no writable cache directory: tried " + ", ".join(str(p) for p in paths)
    raise RuntimeError(message)


def gate_env(
    env: Mapping[str, str],
    home: Path,
    repo: Path,
    tmp: Path,
    is_writable: Callable[[Path], bool] = writable,
) -> dict[str, str]:
    """`env` with both cache variables pointed at absolute, writable directories."""
    chosen = {
        var: pick(candidates(env.get(var, ""), name, home, repo, tmp), is_writable)
        for var, name in CACHES
    }
    return {**env, **{var: str(path) for var, path in chosen.items()}}


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    exec_fn: Callable[[str, list[str], Mapping[str, str]], None] = os.execvpe,
) -> int:
    args = list(argv) if argv else list(DEFAULT_ARGS)
    new_env = gate_env(
        os.environ if env is None else env,
        Path.home(),
        Path(__file__).resolve().parent.parent,  # scripts/gates.py -> repository root
        Path(tempfile.gettempdir()),
    )
    for var, _ in CACHES:
        print(f"gates: {var}={new_env[var]}", file=sys.stderr)
    exec_fn("uv", ["uv", "run", "--frozen", "pre-commit", *args], new_env)
    return 0  # a real execvpe never returns; reached only with an injected exec_fn


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
