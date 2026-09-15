# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Refuse to push history that does not descend from the public root commit.

The public history starts from a fresh root; older, private history can still exist as
local branches in a maintainer's clone. Pushing such a branch (or --all / --mirror)
would publish it for good, so the pre-push stage checks every pushed ref: it must
contain PUBLIC_ROOT. pre-commit exports the pushed commit as PRE_COMMIT_TO_REF. A
missing root object (shallow clone) makes git answer "not an ancestor", so the check
fails closed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

PUBLIC_ROOT = "7cb315336bec341c61dfd6ec70099bc988400db1"
NULL_SHA = "0" * 40


def refusal(to_ref: str | None, is_ancestor: Callable[[str, str], bool]) -> str | None:
    """Return why `to_ref` must not be pushed, or None when it may."""
    if not to_ref or to_ref == NULL_SHA:
        return None  # nothing pushed (ref deletion)
    if is_ancestor(PUBLIC_ROOT, to_ref):
        return None
    return (
        f"refusing to push {to_ref[:12]}: it does not descend from the public root "
        f"{PUBLIC_ROOT[:12]} (private or pre-release history)"
    )


def git_is_ancestor(root: str, ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", root, ref], capture_output=True, check=False
    )
    return result.returncode == 0


def main(is_ancestor: Callable[[str, str], bool] = git_is_ancestor) -> int:
    message = refusal(os.environ.get("PRE_COMMIT_TO_REF"), is_ancestor)
    if message is None:
        return 0
    print(f"check-push-ancestry: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
