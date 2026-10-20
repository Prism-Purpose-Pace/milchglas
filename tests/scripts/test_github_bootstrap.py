"""github_bootstrap.py: the repo settings plan and its idempotent apply loop."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

import github_bootstrap as gb

REPO = Path(__file__).resolve().parents[2]
PLAN = gb.plan("octo", "milchglas")


def _step(endpoint: str) -> gb.Step:
    matches = [s for s in PLAN if endpoint in s.argv]
    assert len(matches) == 1, endpoint
    return matches[0]


def _body(endpoint: str) -> dict[str, Any]:
    body = _step(endpoint).body
    assert body is not None
    return body


@pytest.mark.parametrize(
    "endpoint",
    [
        "repos/octo/milchglas/vulnerability-alerts",
        "repos/octo/milchglas/automated-security-fixes",
        "repos/octo/milchglas/private-vulnerability-reporting",
    ],
)
def test_security_feature_is_enabled_with_put(endpoint: str) -> None:
    assert _step(endpoint).argv[:4] == ["gh", "api", "-X", "PUT"]


def test_push_protection_is_the_only_security_setting_patched() -> None:
    # Secret scanning is always on for public repositories; patching it can fail.
    assert _body("repos/octo/milchglas")["security_and_analysis"] == {
        "secret_scanning_push_protection": {"status": "enabled"}
    }


def test_workflow_token_is_read_only_but_may_open_release_prs() -> None:
    assert _body("repos/octo/milchglas/actions/permissions/workflow") == {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": True,
    }


def _ruleset(name: str) -> dict[str, Any]:
    bodies = [s.body for s in PLAN if s.kind == "ruleset" and s.body and s.body["name"] == name]
    assert len(bodies) == 1, name
    body = bodies[0]
    assert body is not None
    return body


def test_no_ruleset_asks_for_an_integration_bypass() -> None:
    # GitHub accepts a bypass actor of type Integration only for an organization-owned
    # ruleset: "Actor GitHub Actions integration must be part of the ruleset source or
    # owner organization" (HTTP 422). This repository belongs to a user account, and the
    # run aborts on that error, so every later step (labels, project) is lost with it.
    actor_types = {
        actor.get("actor_type")
        for step in PLAN
        if step.kind == "ruleset" and step.body
        for actor in step.body.get("bypass_actors", [])
    }
    assert "Integration" not in actor_types


def test_main_ruleset_protects_the_default_branch() -> None:
    ruleset = _ruleset("main")
    rule_types = {rule["type"] for rule in ruleset["rules"]}
    assert {
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "pull_request",
        "required_status_checks",
    } <= rule_types
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]


def test_required_checks_exist_as_ci_jobs() -> None:
    ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = set(re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", ci, re.MULTILINE))
    assert gb.REQUIRED_CHECKS
    assert set(gb.REQUIRED_CHECKS) <= jobs


def test_labels_are_upserted_with_force() -> None:
    labels = [s for s in PLAN if s.argv[:3] == ["gh", "label", "create"]]
    names = {s.argv[3] for s in labels}
    assert {"needs-triage", "security", "dependencies", "area: caldav"} <= names
    assert all("--force" in s.argv for s in labels)


def test_repo_edit_disables_wiki_and_merge_commits() -> None:
    edit = next(s for s in PLAN if s.argv[:3] == ["gh", "repo", "edit"])
    assert "--enable-wiki=false" in edit.argv
    assert "--enable-merge-commit=false" in edit.argv
    assert "--delete-branch-on-merge" in edit.argv


def test_rebase_is_the_only_merge_method() -> None:
    # A squash commit is created by GitHub and takes the account's display name as its
    # author instead of the identity the branch commits carry; one such commit (a995e8f)
    # tripped the public-tree guard. A rebase merge keeps every commit's author.
    edit = next(s for s in PLAN if s.argv[:3] == ["gh", "repo", "edit"])
    assert "--enable-squash-merge=false" in edit.argv
    assert "--enable-rebase-merge" in edit.argv
    assert "--enable-squash-merge" not in edit.argv


def test_dry_run_prints_plan_without_calling_gh(capsys: pytest.CaptureFixture[str]) -> None:
    def refuse(argv: list[str], stdin: str | None) -> str:
        raise AssertionError(argv, stdin)

    assert gb.main(["--owner", "octo", "--repo", "milchglas", "--dry-run"], runner=refuse) == 0
    out = capsys.readouterr().out
    assert "private-vulnerability-reporting" in out
    assert "gh project create" in out


class FakeGh:
    def __init__(self, existing_rulesets: str = "[]", existing_projects: str = "[]") -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self.rulesets = existing_rulesets
        self.projects = existing_projects

    def __call__(self, argv: list[str], stdin: str | None) -> str:
        self.calls.append(argv)
        self.stdins.append(stdin)
        if argv[:3] == ["gh", "project", "list"]:
            return '{"projects": ' + self.projects + "}"
        if argv[:3] == ["gh", "project", "create"]:
            return '{"number": 7}'
        if argv == ["gh", "api", "repos/octo/milchglas/rulesets"]:
            return self.rulesets
        return ""


def test_apply_creates_ruleset_and_links_new_project() -> None:
    gh = FakeGh()
    assert gb.main(["--owner", "octo", "--repo", "milchglas"], runner=gh) == 0
    post = ["gh", "api", "-X", "POST", "repos/octo/milchglas/rulesets", "--input", "-"]
    assert post in gh.calls
    sent = gh.stdins[gh.calls.index(post)]
    assert sent is not None
    assert json.loads(sent)["name"] == "main"
    assert ["gh", "project", "link", "7", "--owner", "octo", "--repo", "milchglas"] in gh.calls


def test_apply_updates_existing_ruleset_and_reuses_project() -> None:
    gh = FakeGh(
        existing_rulesets='[{"id": 42, "name": "main"}]',
        existing_projects='[{"number": 3, "title": "Milchglas"}]',
    )
    assert gb.main(["--owner", "octo", "--repo", "milchglas"], runner=gh) == 0
    assert [
        "gh",
        "api",
        "-X",
        "PUT",
        "repos/octo/milchglas/rulesets/42",
        "--input",
        "-",
    ] in gh.calls
    assert not any(call[:3] == ["gh", "project", "create"] for call in gh.calls)
    assert ["gh", "project", "link", "3", "--owner", "octo", "--repo", "milchglas"] in gh.calls
