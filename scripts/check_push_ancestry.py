# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Refuse to push history that does not descend from the public root commit.

The public history starts from a fresh root. A pushed ref must contain PUBLIC_ROOT.
pre-commit exports the pushed commit as PRE_COMMIT_TO_REF, but not when the pushed
history is entirely new to the remote (a new branch or tag); then the local ref in
PRE_COMMIT_LOCAL_BRANCH is resolved instead. During a push without any usable ref the
hook fails closed; outside a push (a manual gate run) it passes.

Limit: pre-commit runs pre-push hooks for the FIRST ref of a multi-ref push only, so
`git push --all` / `--mirror` / `--tags` are not fully covered here. The real protection
is that a maintainer clone holds no pre-public history at all (maintainer runbook) and
that the repository's tag ruleset lets only the release workflow create tags.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

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


def pushed_commit(env: Mapping[str, str], resolve: Callable[[str], str | None]) -> str | None:
    if to_ref := env.get("PRE_COMMIT_TO_REF"):
        return to_ref
    if local_ref := env.get("PRE_COMMIT_LOCAL_BRANCH"):
        return resolve(local_ref)
    return None


def git_is_ancestor(root: str, ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", root, ref], capture_output=True, check=False
    )
    return result.returncode == 0


def git_resolve(ref: str) -> str | None:
    """Commit a local branch or (annotated) tag points to, or None."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def main(
    is_ancestor: Callable[[str, str], bool] = git_is_ancestor,
    resolve: Callable[[str], str | None] = git_resolve,
) -> int:
    env = os.environ
    pushing = "PRE_COMMIT_REMOTE_NAME" in env or "PRE_COMMIT_TO_REF" in env
    commit = pushed_commit(env, resolve)
    if commit is None:
        if not pushing:
            return 0  # manual `pre-commit run --hook-stage pre-push`
        print("check-push-ancestry: cannot determine the pushed ref, refusing", file=sys.stderr)
        return 1
    message = refusal(commit, is_ancestor)
    if message is None:
        return 0
    print(f"check-push-ancestry: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
