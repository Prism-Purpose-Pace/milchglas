"""`init` and `rotate-token` print a token once and write no file (D-14, NFR-O1, Q-13)."""

import base64
import hashlib
import json
import logging
import os
import runpy
import subprocess
import sys
import zoneinfo
from collections.abc import Iterator
from pathlib import Path

import pytest

from milchglas.__main__ import main, run

type Snapshot = dict[str, tuple[bytes, int, int]]


def _snapshot(root: Path) -> Snapshot:
    return {
        str(path.relative_to(root)): (
            path.read_bytes() if path.is_file() else b"",
            path.stat().st_mtime_ns,
            path.stat().st_mode,
        )
        for path in sorted(root.rglob("*"))
    }


def _printed(text: str) -> tuple[str, dict[str, str]]:
    """The token and the JSON members of one command's output."""
    lines = text.splitlines()
    token = lines[lines.index("Feed token, shown once:") + 1]
    start = lines.index("Paste into config.json:") + 1
    members: dict[str, str] = json.loads("{" + "\n".join(lines[start:]) + "}")
    return token, members


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A working directory with a read-only config directory and a filled var directory."""
    config_dir, var_dir = tmp_path / "config", tmp_path / "var"
    config_dir.mkdir()
    var_dir.mkdir()
    (config_dir / "config.json").write_text('{"uid_salt": "kept"}')
    (var_dir / "feed.ics").write_bytes(b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    (var_dir / "state.json").write_text('{"last_error": null, "last_success": null}')
    config_dir.chmod(0o555)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MILCHGLAS_CONFIG", str(config_dir / "config.json"))
    monkeypatch.setenv("MILCHGLAS_VAR_DIR", str(var_dir))
    yield tmp_path
    config_dir.chmod(0o755)


def test_init_prints_token_salt_and_digest_and_writes_nothing_orch_cli_3(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _snapshot(workspace)
    assert main(["init"]) == 0
    assert _snapshot(workspace) == before
    token, members = _printed(capsys.readouterr().out)
    assert list(members) == ["uid_salt", "token_sha256"]
    assert members["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert len(members["uid_salt"]) == 32


def test_rotate_token_prints_a_256_bit_token_and_writes_nothing_orch_cli_4(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _snapshot(workspace)
    assert main(["rotate-token"]) == 0
    first, members = _printed(capsys.readouterr().out)
    assert main(["rotate-token"]) == 0
    second, _ = _printed(capsys.readouterr().out)
    assert _snapshot(workspace) == before
    assert list(members) == ["token_sha256"]
    assert members["token_sha256"] == hashlib.sha256(first.encode()).hexdigest()
    assert len(base64.urlsafe_b64decode(first + "=" * (-len(first) % 4))) == 32
    assert first != second


def test_token_appears_only_in_the_command_output_orch_cli_5(
    workspace: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    outputs = []
    for command in ("init", "rotate-token"):
        main([command])
        outputs.append(capsys.readouterr())
    tokens = [_printed(output.out)[0] for output in outputs]
    files = b"".join(path.read_bytes() for path in workspace.rglob("*") if path.is_file())
    for token in tokens:
        assert [output.out.count(token) for output in outputs].count(1) == 1
        assert sum(output.out.count(token) for output in outputs) == 1
        assert not any(token in output.err for output in outputs)
        assert token not in caplog.text
        assert token.encode() not in files


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2
    assert "init" in capsys.readouterr().err


def test_entry_point_pins_the_tzdata_package_det_9(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(zoneinfo, "reset_tzpath", lambda to=None: calls.append(to))
    assert main(["rotate-token"]) == 0
    assert calls == []
    assert run(["rotate-token"]) == 0
    assert calls == [()]


def test_dash_m_guard_goes_through_run_det_9(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(zoneinfo, "reset_tzpath", lambda to=None: calls.append(to))
    monkeypatch.setattr(sys, "argv", ["milchglas", "rotate-token"])
    # runpy warns when the module it executes is already imported.
    monkeypatch.delitem(sys.modules, "milchglas.__main__", raising=False)
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("milchglas", run_name="__main__")
    assert caught.value.code == 0
    assert calls == [()]
    assert "Feed token, shown once:" in capsys.readouterr().out


def test_only_the_entry_point_touches_the_tz_path_det_9() -> None:
    src = Path(__file__).resolve().parents[2] / "src" / "milchglas"
    touching = [p.relative_to(src) for p in src.rglob("*.py") if "reset_tzpath" in p.read_text()]
    assert touching == [Path("__main__.py")]


# PYTHONOPTIMIZE=2 (-OO) strips docstrings, as some slim images set it.
@pytest.mark.parametrize("optimize", ["", "2"], ids=["plain", "optimized"])
def test_python_dash_m_milchglas_runs(tmp_path: Path, optimize: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "milchglas", "rotate-token"],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONOPTIMIZE": optimize},
    )
    token, members = _printed(result.stdout)
    assert members["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert list(tmp_path.iterdir()) == []
