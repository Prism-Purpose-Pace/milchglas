"""GATE-6: the smoke run against a seeded Baikal is wired into CI and checks what the row names.

The run itself needs Docker and pulls images, so it is the CI job `smoke`
(`bash scripts/smoke_baikal.sh`); this static check keeps that job, the production Compose
file under test and the script's assertions from drifting apart.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "smoke_baikal.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def smoke_job() -> dict[str, Any]:
    jobs: dict[str, Any] = yaml.safe_load(CI.read_text())["jobs"]
    job: dict[str, Any] = jobs["smoke"]
    return job


def test_ci_runs_the_smoke_script_read_only_gate_6() -> None:
    job = smoke_job()

    assert job["permissions"] == {"contents": "read"}
    assert {"run": "bash scripts/smoke_baikal.sh"} in job["steps"]
    checkout = next(step for step in job["steps"] if "uses" in step)
    assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", checkout["uses"])
    assert checkout["with"] == {"persist-credentials": False}


def test_the_smoke_run_uses_the_production_compose_file_gate_6() -> None:
    text = SCRIPT.read_text()

    assert '-f "$root/deploy/option-b/compose.yaml"' in text
    assert "compose up -d web refresher" in text


def test_every_image_the_smoke_run_pulls_is_pinned_by_digest_gate_6() -> None:
    images = re.findall(r"^\w+=(docker\.io/\S+)$", SCRIPT.read_text(), flags=re.MULTILINE)

    assert len(images) == 2
    for image in images:
        assert re.fullmatch(r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}", image), image


def test_the_smoke_run_asserts_each_behaviour_of_the_row_gate_6() -> None:
    text = SCRIPT.read_text()

    for check in (
        '[ "$health" = "200" ]',  # /healthz 200 after the first refresh
        "grep -q '^HTTP/1.1 200'",  # the right token gets the feed
        '[ "$events" = "5" ]',  # the blocks the seeded events must give
        '[ "$wrong" != "$unknown" ]',  # a wrong token: the identical 404
        '[ "$code" != "0" ] || [ "$elapsed" -ge 10 ]',  # docker stop: exit 0 within 10 s
    ):
        assert check in text, check


def test_the_smoke_run_holds_no_credential_literal_gate_6() -> None:
    text = SCRIPT.read_text()

    assert re.search(r"^svc_pass=\$\(openssl rand ", text, flags=re.MULTILINE)
    assert re.search(r"^owner_pass=\$\(openssl rand ", text, flags=re.MULTILINE)
    assert re.search(r"^token=\$\(openssl rand ", text, flags=re.MULTILINE)
    assert not re.search(r"https?://[^/\s]+:[^@/\s]+@", text)
