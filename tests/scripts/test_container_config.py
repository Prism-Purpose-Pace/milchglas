"""GATE-3: the Option B Dockerfile and Compose file keep their hardening (AC-13, D-13).

A static check that needs no Docker: it reads the files as text and YAML. The built image
and the running containers are checked once they are built.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "deploy" / "option-b" / "compose.yaml"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
HARDENING = ("read_only", "cap_drop", "security_opt", "tmpfs", "ulimits", "pids_limit", "mem_limit")
_CALDAV = re.compile(r"CALDAV_(URL|USER|SECRET)")


def compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text())
    return loaded


def hardening_gaps(service: dict[str, Any]) -> list[str]:
    """The hardening keys a service lacks or weakens."""
    gaps = [key for key in HARDENING if key not in service]
    if service.get("read_only") is not True:
        gaps.append("read_only: true")
    if service.get("cap_drop") != ["ALL"]:
        gaps.append("cap_drop: [ALL]")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        gaps.append("no-new-privileges")
    if "/tmp" not in service.get("tmpfs", []):  # noqa: S108 - the mount point checked
        gaps.append("tmpfs /tmp")
    if service.get("ulimits", {}).get("core") != 0:
        gaps.append("ulimits core 0")
    return gaps


def test_every_from_is_pinned_by_tag_and_digest_gate_3() -> None:
    images = re.findall(r"^FROM\s+(\S+)", DOCKERFILE.read_text(), flags=re.MULTILINE)

    assert len(images) == 3
    for image in images:
        assert re.fullmatch(r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}", image), image
    assert sum(image.startswith("docker.io/library/python:3.12-slim@") for image in images) == 2


def test_the_image_installs_with_uv_only_and_runs_as_non_root_gate_3() -> None:
    text = DOCKERFILE.read_text()

    assert "pip install" not in text
    assert "uv sync --frozen --no-dev" in text
    assert re.search(r"^USER 10001:10001$", text, flags=re.MULTILINE)
    assert re.search(r"PYTHONTZPATH= ", text)
    assert not _CALDAV.search(text)


def test_web_starts_gunicorn_with_the_log_redaction_web_21() -> None:
    command = re.search(r"^CMD (\[.*?\])$", DOCKERFILE.read_text(), flags=re.MULTILINE | re.DOTALL)

    assert command
    argv = [part.strip(' "\\\n') for part in command.group(1).strip("[]").split(",")]
    assert argv[0] == "gunicorn"
    assert argv[argv.index("--config") + 1] == "python:milchglas.web.gunicorn_conf"


def test_both_services_carry_every_hardening_key_gate_3() -> None:
    services = compose()["services"]

    assert set(services) == {"web", "refresher"}
    assert {name: hardening_gaps(service) for name, service in services.items()} == {
        "web": [],
        "refresher": [],
    }


def test_a_service_without_cap_drop_fails_the_check_gate_3() -> None:
    service = dict(compose()["services"]["web"])
    del service["cap_drop"]

    assert "cap_drop" in hardening_gaps(service)


def test_only_web_exposes_a_port_and_the_refresher_loops_every_900_s_gate_3() -> None:
    services = compose()["services"]

    assert services["web"]["expose"] == ["8000"]
    assert not {"ports", "expose"} & set(services["refresher"])
    assert not {"ports"} & set(services["web"])
    assert services["refresher"]["command"] == [
        "python",
        "-m",
        "milchglas",
        "refresh",
        "--loop",
        "--interval",
        "900",
    ]


def test_state_is_shared_and_read_only_in_web_config_read_only_in_both_gate_3() -> None:
    services = compose()["services"]

    assert "state:/var/lib/milchglas:ro" in services["web"]["volumes"]
    assert "state:/var/lib/milchglas" in services["refresher"]["volumes"]
    for service in services.values():
        assert "./config:/etc/milchglas:ro" in service["volumes"]


@pytest.mark.parametrize("name", ["CALDAV_URL", "CALDAV_USER", "CALDAV_SECRET"])
def test_only_the_refresher_names_caldav_and_holds_no_value_gate_3(name: str) -> None:
    services = compose()["services"]

    assert name not in services["web"].get("environment", {})
    assert services["refresher"]["environment"][name] == f"${{{name}}}"


def test_dependabot_watches_the_image_and_holds_the_python_minor_gate_3() -> None:
    updates = yaml.safe_load(DEPENDABOT.read_text())["updates"]
    (docker,) = [entry for entry in updates if entry["package-ecosystem"] == "docker"]

    assert docker["directory"] == "/"
    held = {kind for rule in docker["ignore"] for kind in rule["update-types"]}
    assert "version-update:semver-minor" in held
