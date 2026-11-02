"""`python -m milchglas refresh`: exit codes and what the environment must hold (NFR-O1, NFR-S7).

No test here reaches the network: a missing variable stops the run before any request, and
a failing run goes to a loopback port nobody listens on, which the kernel refuses.
"""

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from milchglas import __main__ as cli
from milchglas.__main__ import main
from milchglas.refresh import Report
from milchglas.state import FEED, STATE, read_state

SECRET = "BBX-synthetic-app-password"  # noqa: S105 - a sentinel, no credential
ENVIRONMENT = {
    "CALDAV_URL": "https://127.0.0.1:1/remote.php/dav/",
    "CALDAV_USER": "svc-milchglas",
    "CALDAV_SECRET": SECRET,
}


@pytest.fixture
def var_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "uid_salt": "0123456789abcdef0123456789abcdef",
                "token_sha256": "ab" * 32,
                "owner_emails": [],
                "calendars": [{"href": "/cal/privat/", "name": "Privat", "enabled": True}],
            }
        )
    )
    monkeypatch.setenv("MILCHGLAS_CONFIG", str(config))
    monkeypatch.setenv("MILCHGLAS_VAR_DIR", str(tmp_path / "var"))
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    return tmp_path / "var"


@pytest.mark.parametrize(
    "name", ["CALDAV_SECRET", "CALDAV_USER", "CALDAV_URL", "MILCHGLAS_VAR_DIR"]
)
def test_a_missing_variable_exits_2_and_names_only_the_variable_orch_cfg_3(
    var_dir: Path, name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(name, "")

    assert main(["refresh"]) == 2

    out, err = capsys.readouterr()
    assert err == f"milchglas: {name} is not set\n"
    assert SECRET not in out + err
    assert not var_dir.exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://cal.example.com/",
        "https://svc:BBX-pw@cal.example.com/",
        "https://cal.example.com:port/",
        "https://[::1/",
        "https:///path-only",
        "cal.example.com",
    ],
)
def test_caldav_url_must_be_https_without_user_information_orch_cfg_9(
    var_dir: Path, url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CALDAV_URL", url)

    assert main(["refresh"]) == 2

    out, err = capsys.readouterr()
    assert err == "milchglas: CALDAV_URL: must be an https URL without user information\n"
    assert "BBX-" not in out + err
    assert not var_dir.exists()


def test_a_failed_one_shot_run_exits_1_and_keeps_the_feed_orch_fetch_3(
    var_dir: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    var_dir.mkdir(mode=0o700)
    (var_dir / FEED).write_bytes(b"the last good feed")

    with caplog.at_level(logging.INFO, logger="milchglas.refresh"):
        assert main(["refresh"]) == 1

    assert (var_dir / FEED).read_bytes() == b"the last good feed"
    assert read_state(var_dir).last_error == (
        "FetchError: calendars[0]: connection failed: ConnectionRefusedError"
    )
    out, err = capsys.readouterr()
    assert "refresh failed (FetchError: calendars[0]: connection failed" in caplog.text
    assert SECRET not in out + err + caplog.text


def test_a_failed_dry_run_exits_1_and_writes_nothing_orch_cli_2(
    var_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["refresh", "--dry-run"]) == 1

    assert not (var_dir / FEED).exists()
    assert not (var_dir / STATE).exists()
    assert "dry run:" not in capsys.readouterr().out


@pytest.mark.usefixtures("var_dir")
def test_an_unknown_log_level_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MILCHGLAS_LOG_LEVEL", "chatty")

    assert main(["refresh"]) == 2

    assert capsys.readouterr().err == "milchglas: MILCHGLAS_LOG_LEVEL is not a logging level name\n"


@pytest.mark.usefixtures("var_dir")
def test_a_dry_run_prints_counts_and_the_window_only_orch_cli_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def counted(*_args: object, dry_run: bool, **_kwargs: object) -> Report:
        seen["dry_run"] = dry_run
        return Report(1, 4, 3, date(2026, 11, 2), date(2026, 12, 5))

    monkeypatch.setattr(cli, "refresh", counted)

    assert main(["refresh", "--dry-run"]) == 0

    assert seen == {"dry_run": True}
    assert capsys.readouterr().out == (
        "dry run: 1 calendars, 4 objects, 3 blocks, window 2026-11-02 to 2026-12-05\n"
    )
