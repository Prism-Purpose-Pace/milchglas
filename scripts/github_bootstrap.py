# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Apply the GitHub repository settings that files in .github/ cannot express.

Security features, workflow-token permissions, the default-branch ruleset, labels
and the Projects v2 board - idempotent, so re-running converges instead of
duplicating. Needs `gh auth login` with the `repo` and `project` scopes
(`gh auth refresh -s project`). Preview with --dry-run.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    Runner = Callable[[list[str], str | None], str]

DESCRIPTION = "Busy-only ICS feed from private CalDAV calendars: presence visible, content opaque"
TOPICS = ("caldav", "icalendar", "ics", "free-busy", "nextcloud", "privacy", "calendar", "python")
# Job ids in .github/workflows/ci.yml; a test keeps both lists in sync, otherwise the
# ruleset would wait forever for a check that never reports.
REQUIRED_CHECKS = ("lint", "typecheck", "test", "public-guard", "secret-scan")
GITHUB_ACTIONS_APP_ID = 15368  # pins required checks to Actions, not to any status poster
RULESET_NAME = "main"
REVIEW_RULESET_NAME = "review"
TAG_RULESET_NAME = "tags"
PROJECT_TITLE = "Milchglas"
# GitHub's default labels (bug, enhancement, documentation, good first issue, ...) stay.
LABELS = (
    ("needs-triage", "fbca04", "New issue, not yet assessed"),
    ("blocked", "b60205", "Waiting on something outside this issue"),
    ("security", "d93f0b", "Hardening; report vulnerabilities privately (SECURITY.md)"),
    ("dependencies", "0366d6", "Dependency updates"),
    ("ci", "5319e7", "Workflows, gates and tooling"),
    ("area: caldav", "c5def5", "Fetching and parsing source calendars"),
    ("area: core", "c5def5", "Pure pipeline: filter, reduce, round, merge"),
    ("area: feed", "c5def5", "ICS emission and determinism"),
    ("area: web", "c5def5", "Feed endpoint, tokens, health check"),
    ("area: deploy", "c5def5", "Deployment options and runbook"),
    ("priority: high", "b60205", "Next up"),
    ("priority: low", "e4e669", "Nice to have"),
)
MANUAL_FOLLOW_UP = """\
Done. Manual follow-up (no API for these):
- Project board: enable the 'Auto-add to project' workflow for this repository.
- Secret PUBLIC_DENYLIST (newline-separated private regexes for the term guard), as
  Actions secret AND as Dependabot secret (`gh secret set ... --app dependabot`).
- Release PRs are opened by GITHUB_TOKEN and trigger no CI: close and reopen one to run
  the required checks, then approve and merge it. Own PRs merge through the admin bypass
  of the review ruleset, which skips only the approval. Only GitHub Actions may tag: a
  release-please run under any other token is blocked by the tags ruleset."""


class GhError(RuntimeError):
    """A gh invocation failed."""


@dataclass(frozen=True)
class Step:
    argv: list[str]
    body: dict[str, Any] | None = None
    kind: str = "plain"  # "ruleset" and "project" need a lookup before they write


def _ruleset() -> dict[str, Any]:
    checks = [{"context": c, "integration_id": GITHUB_ACTIONS_APP_ID} for c in REQUIRED_CHECKS]
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        # No bypass: a bypass skips every unmet rule of its ruleset, so required checks
        # would turn optional for the maintainer. The review ruleset holds the bypass.
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": checks,
                },
            },
        ],
    }


def _review_ruleset() -> dict[str, Any]:
    return {
        "name": REVIEW_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        # Solo maintainer: nobody else can approve their own PRs, so admins may merge
        # without the review; bot PRs (Dependabot, release-please) get a real approval.
        # Organization owners hold admin access implicitly and are a separate actor type
        # (its actor_id is ignored); GitHub rejects that type for user-owned repositories.
        "bypass_actors": [
            {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"},
            {"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "pull_request"},
        ],
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": True,
                    "required_review_thread_resolution": False,
                },
            },
        ],
    }


def _tag_ruleset() -> dict[str, Any]:
    return {
        "name": TAG_RULESET_NAME,
        "target": "tag",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~ALL"], "exclude": []}},
        # Only the release workflow (GitHub Actions) creates, moves or deletes tags, so
        # no tag can be pushed onto history outside the public branch. An Integration
        # bypass is valid for organization-owned rulesets only (HTTP 422 on a user account).
        "bypass_actors": [
            {
                "actor_id": GITHUB_ACTIONS_APP_ID,
                "actor_type": "Integration",
                "bypass_mode": "always",
            }
        ],
        "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}],
    }


def _label(full: str, name: str, color: str, text: str) -> Step:
    argv = ["gh", "label", "create", name, "--repo", full, "--color", color]
    return Step([*argv, "--description", text, "--force"])


def plan(owner: str, repo: str) -> list[Step]:
    full = f"{owner}/{repo}"
    api = f"repos/{full}"
    put = ["gh", "api", "-X", "PUT"]
    edit = [
        "gh", "repo", "edit", full,
        "--description", DESCRIPTION,
        "--add-topic", ",".join(TOPICS),
        "--enable-issues",
        "--enable-projects",
        "--enable-wiki=false",
        "--enable-discussions=false",
        "--enable-merge-commit=false",
        "--enable-squash-merge=false",  # squash commits take the account name as author
        "--enable-rebase-merge",
        "--delete-branch-on-merge",
        "--allow-update-branch",
    ]  # fmt: skip
    # Secret scanning itself is always on for public repositories; only push
    # protection is a setting (sending both risks a 422 that aborts the run).
    security = {"security_and_analysis": {"secret_scanning_push_protection": {"status": "enabled"}}}
    workflow = {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": True}
    return [
        Step(edit),
        Step([*put, f"{api}/vulnerability-alerts"]),
        Step([*put, f"{api}/automated-security-fixes"]),
        Step([*put, f"{api}/private-vulnerability-reporting"]),
        Step(["gh", "api", "-X", "PATCH", api, "--input", "-"], security),
        Step([*put, f"{api}/actions/permissions/workflow", "--input", "-"], workflow),
        *(
            Step(["gh", "api", "-X", "POST", f"{api}/rulesets", "--input", "-"], body, "ruleset")
            for body in (_ruleset(), _review_ruleset(), _tag_ruleset())
        ),
        *(_label(full, name, color, text) for name, color, text in LABELS),
        Step(
            [
                "gh",
                "project",
                "create",
                "--owner",
                owner,
                "--title",
                PROJECT_TITLE,
                "--format",
                "json",
            ],
            kind="project",
        ),
    ]


def _stdin(step: Step) -> str | None:
    return None if step.body is None else json.dumps(step.body)


def _upsert_ruleset(step: Step, full: str, runner: Runner) -> None:
    endpoint = f"repos/{full}/rulesets"
    existing: list[dict[str, Any]] = json.loads(runner(["gh", "api", endpoint], None) or "[]")
    name = (step.body or {}).get("name")
    match = next((r for r in existing if r.get("name") == name), None)
    argv = step.argv
    if match is not None:
        argv = ["gh", "api", "-X", "PUT", f"{endpoint}/{match['id']}", "--input", "-"]
    runner(argv, _stdin(step))


def _ensure_project(step: Step, owner: str, repo: str, runner: Runner) -> None:
    listing = runner(["gh", "project", "list", "--owner", owner, "--format", "json"], None)
    projects: list[dict[str, Any]] = json.loads(listing or "{}").get("projects", [])
    number = next((p["number"] for p in projects if p.get("title") == PROJECT_TITLE), None)
    if number is None:
        number = json.loads(runner(step.argv, None))["number"]
    # `gh project link --repo` takes the bare repository name; the owner comes from --owner.
    runner(["gh", "project", "link", str(number), "--owner", owner, "--repo", repo], None)


def apply(steps: Sequence[Step], owner: str, repo: str, runner: Runner) -> None:
    full = f"{owner}/{repo}"
    for step in steps:
        if step.kind == "ruleset":
            _upsert_ruleset(step, full, runner)
        elif step.kind == "project":
            _ensure_project(step, owner, repo, runner)
        else:
            runner(step.argv, _stdin(step))


def gh(argv: list[str], stdin: str | None) -> str:
    result = subprocess.run(argv, input=stdin, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        # `gh api` prints GitHub's error body (a 422's `errors` list) on stdout.
        detail = "\n".join(s for s in (result.stderr.strip(), result.stdout.strip()) if s)
        msg = f"{shlex.join(argv[:5])} failed: {detail}"
        raise GhError(msg)
    return result.stdout


def main(argv: Sequence[str] | None = None, runner: Runner = gh) -> int:
    parser = argparse.ArgumentParser(description="Apply GitHub repository settings via gh.")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    args = parser.parse_args(argv)
    steps = plan(args.owner, args.repo)
    if args.dry_run:
        for step in steps:
            print(shlex.join(step.argv))
            if step.body is not None:
                print(json.dumps(step.body, indent=2))
        return 0
    try:
        apply(steps, args.owner, args.repo, runner)
    except GhError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(MANUAL_FOLLOW_UP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
