# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Apply the GitHub repository settings that files in .github/ cannot express.

Security features, workflow-token permissions, the default-branch ruleset, labels
and the Projects v2 board with its Priority field - idempotent, so re-running converges instead of
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
# Check names of jobs in .github/workflows/ci.yml (a reusable workflow reports as
# "<caller> / <called job>"); a test keeps both in sync, otherwise the ruleset would
# wait forever for a check that never reports. CodeQL is gated by the code_scanning rule.
REQUIRED_CHECKS = (
    "lint",
    "typecheck",
    "test",
    "public-guard",
    "secret-scan",
    "osv-scan / osv-scan",
    "dependency-review",
    "zizmor",
)
GITHUB_ACTIONS_APP_ID = 15368  # pins required checks to Actions, not to any status poster
RULESET_NAME = "main"
REVIEW_RULESET_NAME = "review"
TAG_RULESET_NAME = "tags"
PROJECT_TITLE = "Milchglas"
# Issue priority is this single-select project field; there are no priority labels.
PRIORITIES = ("High", "Medium", "Low")
# GitHub's default labels (bug, enhancement, documentation, good first issue, ...) stay.
LABELS = (
    ("needs-triage", "fbca04", "New issue, not yet assessed"),
    ("blocked", "b60205", "Waiting on something outside this issue"),
    ("security", "d93f0b", "Hardening; report vulnerabilities privately (SECURITY.md)"),
    ("dependencies", "0366d6", "Dependency updates"),
    ("ci", "5319e7", "Workflows, gates and tooling"),
    ("documentation", "0075ca", "Docs, README and contributor guides"),
    ("area: caldav", "c5def5", "Fetching and parsing source calendars"),
    ("area: core", "c5def5", "Pure pipeline: filter, reduce, round, merge"),
    ("area: feed", "c5def5", "ICS emission and determinism"),
    ("area: web", "c5def5", "Feed endpoint, tokens, health check"),
    ("area: deploy", "c5def5", "Deployment options and runbook"),
)
MANUAL_FOLLOW_UP = """\
Done. Manual follow-up (no API for these):
- Project board: enable the 'Auto-add to project' workflow for this repository.
- Secret PUBLIC_DENYLIST (newline-separated private regexes for the term guard), as
  Actions secret AND as Dependabot secret (`gh secret set ... --app dependabot`).
- Release PRs are opened by GITHUB_TOKEN and trigger no CI: close and reopen one to run
  the required checks, then approve and merge it. Own PRs merge through the admin bypass
  of the review ruleset, which skips only the approval.
- Tags are frozen by the tags ruleset (no move, no delete, no bypass); to repair a wrong
  tag, disable that ruleset, fix the tag, enable it again.
- If you added the admin:org scope for this run, drop it again:
  `gh auth refresh -h github.com -r admin:org`."""
ORG_POLICY_OFF = """\
Organization {owner} does not allow GitHub Actions to create and approve pull requests.
The repository setting cannot override it, so release-please cannot open release PRs.
An organization owner enables it under Settings > Actions > General > Workflow
permissions, or runs (scope admin:org):
  gh api -X PUT orgs/{owner}/actions/permissions/workflow \
-F can_approve_pull_request_reviews=true
Nothing was changed."""


class GhError(RuntimeError):
    """A gh invocation failed."""


@dataclass(frozen=True)
class Step:
    argv: list[str]
    body: dict[str, Any] | None = None
    kind: str = "plain"  # "org-policy", "ruleset" and "project" read before they act


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
            {
                "type": "code_scanning",
                "parameters": {
                    "code_scanning_tools": [
                        {
                            "tool": "CodeQL",
                            "alerts_threshold": "errors",
                            "security_alerts_threshold": "high_or_higher",
                        }
                    ]
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
        # A published tag never moves or disappears. Creation stays open to writers:
        # release-please tags with GITHUB_TOKEN, and GitHub rejects GitHub Actions as a
        # bypass actor even in this organization (HTTP 422, "must be part of the ruleset
        # source or owner organization"). No bypass: admins disable the ruleset instead.
        "bypass_actors": [],
        "rules": [{"type": "update"}, {"type": "deletion"}],
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
    actions = {"enabled": True, "allowed_actions": "all", "sha_pinning_required": True}
    # Approval for first-time contributors only is defeated by one merged typo fix.
    forks = {"approval_policy": "all_external_contributors"}
    return [
        # First, so a blocked organization stops the run before anything is written.
        Step(["gh", "api", f"orgs/{owner}/actions/permissions/workflow"], kind="org-policy"),
        Step(edit),
        Step([*put, f"{api}/vulnerability-alerts"]),
        Step([*put, f"{api}/automated-security-fixes"]),
        Step([*put, f"{api}/private-vulnerability-reporting"]),
        Step(["gh", "api", "-X", "PATCH", api, "--input", "-"], security),
        Step([*put, f"{api}/actions/permissions", "--input", "-"], actions),
        Step(
            [*put, f"{api}/actions/permissions/fork-pr-contributor-approval", "--input", "-"], forks
        ),
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


def _check_org_policy(step: Step, owner: str, full: str, runner: Runner) -> None:
    # An organization's Actions policy caps the repository setting the workflow step sets.
    owner_type = runner(["gh", "api", f"repos/{full}", "--jq", ".owner.type"], None).strip()
    if owner_type != "Organization":
        return
    try:
        policy: dict[str, Any] = json.loads(runner(step.argv, None) or "{}")
    except GhError as exc:  # reading it needs admin:org
        print(f"warning: organization Actions policy not checked: {exc}", file=sys.stderr)
        return
    if not policy.get("can_approve_pull_request_reviews"):
        raise GhError(ORG_POLICY_OFF.format(owner=owner))


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
    listing = runner(
        ["gh", "project", "field-list", str(number), "--owner", owner, "--format", "json"], None
    )
    fields: list[dict[str, Any]] = json.loads(listing or "{}").get("fields", [])
    if not any(f.get("name") == "Priority" for f in fields):
        runner(
            [
                "gh", "project", "field-create", str(number), "--owner", owner,
                "--name", "Priority", "--data-type", "SINGLE_SELECT",
                "--single-select-options", ",".join(PRIORITIES),
            ],
            None,
        )  # fmt: skip


def apply(steps: Sequence[Step], owner: str, repo: str, runner: Runner) -> None:
    full = f"{owner}/{repo}"
    for step in steps:
        if step.kind == "org-policy":
            _check_org_policy(step, owner, full, runner)
        elif step.kind == "ruleset":
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
