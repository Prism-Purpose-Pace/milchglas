"""The refresher as a long-running process: the loop, SIGTERM and configuration on every run.

FR-10, FR-12, AC-10, AC-22. The loop gets a fake clock and a stop event whose `wait`
advances that clock, so a day of runs takes no real time. One smoke test sends a real
SIGTERM to `python -m milchglas refresh --loop`.
"""

import json
import logging
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import final, override

import pytest

from milchglas.config import ConfigError
from milchglas.refresh import ConfigWatch, SignalStop, loop
from milchglas.state import read_state
from tests.unit.test_refresh import HREF, NOW, World, event, multistatus
from tests.unit.test_refresh import world as world  # noqa: PLC0414 - the shared fixture

INTERVAL = 900


@dataclass
class Clock:
    now: float = 1000.0
    waits: list[float] = field(default_factory=list)


@final
class FakeStop(threading.Event):
    """`wait` moves the fake clock instead of sleeping; `stop_after` waits end the loop."""

    def __init__(self, clock: Clock, stop_after: int) -> None:
        super().__init__()
        self.clock = clock
        self.stop_after = stop_after

    @override
    def wait(self, timeout: float | None = None) -> bool:
        assert timeout is not None
        self.clock.waits.append(timeout)
        self.clock.now += timeout
        if len(self.clock.waits) >= self.stop_after:
            self.set()
        return self.is_set()


def test_runs_on_the_interval_and_survives_a_failing_run_orch_loop_1() -> None:
    clock = Clock()
    started: list[float] = []

    def run_once() -> None:
        started.append(clock.now)
        clock.now += 30  # a run takes 30 s
        if len(started) == 2:
            msg = "tz: unknown time zone"
            raise ConfigError(msg)

    stop = FakeStop(clock, stop_after=4)
    assert loop(run_once, interval=INTERVAL, stop=stop, clock=lambda: clock.now) == 0

    assert started == [1000, 1900, 2800, 3700]
    assert clock.waits == [870, 870, 870, 870]


def test_an_overrunning_run_skips_to_the_next_slot_orch_loop_1() -> None:
    clock = Clock()
    started: list[float] = []

    def run_once() -> None:
        started.append(clock.now)
        clock.now += 1000 if len(started) == 1 else 10

    stop = FakeStop(clock, stop_after=2)
    loop(run_once, interval=INTERVAL, stop=stop, clock=lambda: clock.now)

    assert started == [1000, 2800]


def test_sigterm_during_a_run_finishes_it_then_exits_orch_loop_2() -> None:
    clock = Clock()
    stop = threading.Event()
    finished: list[bool] = []

    def run_once() -> None:
        stop.set()  # the SIGTERM handler's only action, mid-run
        finished.append(True)

    assert loop(run_once, interval=INTERVAL, stop=stop, clock=lambda: clock.now) == 0
    assert finished == [True]


def test_sigterm_while_sleeping_exits_at_once_orch_loop_2() -> None:
    stop = threading.Event()
    runs: list[float] = []
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()

    assert loop(lambda: runs.append(0), interval=INTERVAL, stop=stop) == 0

    assert runs == [0]
    assert time.monotonic() - started < 5


def _start_loop(tmp_path: Path) -> subprocess.Popen[str]:
    """The refresher as the image runs it; every run fails at once on a refused port."""
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
    environment = {
        **os.environ,
        "CALDAV_URL": "https://127.0.0.1:1/",  # refused: every run fails without network
        "CALDAV_USER": "svc-milchglas",
        "CALDAV_SECRET": "BBX-synthetic",
        "MILCHGLAS_CONFIG": str(config),
        "MILCHGLAS_VAR_DIR": str(tmp_path / "var"),
        "MILCHGLAS_LOG_LEVEL": "INFO",  # the summary line this test waits for is INFO
    }
    return subprocess.Popen(
        [sys.executable, "-m", "milchglas", "refresh", "--loop", "--interval", "900"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _first_line(process: subprocess.Popen[str], deadline: float = 10) -> str:
    """The first stdout line, or a failure after `deadline` seconds instead of a hang."""
    assert process.stdout is not None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=deadline), "no summary line within the deadline"
    return str(process.stdout.readline())


@pytest.mark.parametrize("signals", [1, 3], ids=["ORCH-LOOP-2-once", "ORCH-LOOP-2-repeated"])
def test_a_real_sigterm_while_waiting_ends_the_loop_with_exit_0(
    tmp_path: Path, signals: int
) -> None:
    process = _start_loop(tmp_path)
    try:
        line = _first_line(process)  # the first run's summary: the loop is now waiting
        for _ in range(signals):
            process.send_signal(signal.SIGTERM)
        out, err = process.communicate(timeout=10)
    finally:
        process.kill()
        process.communicate()

    assert "refresh failed (FetchError" in line
    assert process.returncode == 0
    assert "BBX-" not in line + out + err


def test_a_signal_stop_wakes_a_wait_without_a_lock_orch_loop_2() -> None:
    stop = SignalStop()
    try:
        threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
        started = time.monotonic()

        assert stop.wait(30) is True
        assert time.monotonic() - started < 5
        assert stop.is_set()
    finally:
        stop.close()
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


def test_a_signal_before_the_wait_ends_it_at_once_orch_loop_2() -> None:
    stop = SignalStop()
    try:
        os.kill(os.getpid(), signal.SIGTERM)
        started = time.monotonic()

        assert stop.wait(30) is True
        assert time.monotonic() - started < 1
    finally:
        stop.close()


def test_a_signal_stop_without_a_signal_waits_out_the_timeout() -> None:
    stop = SignalStop()
    try:
        assert stop.wait(0.05) is False
        assert stop.wait(-1) is False
    finally:
        stop.close()


def test_disabling_a_calendar_removes_its_blocks_on_the_next_run_orch_cfg_1(
    world: World,
) -> None:
    other = "/calendars/svc-milchglas/familie/"
    world.answers[other] = multistatus(event("f", "20261105T090000Z", "20261105T100000Z"))
    world.configure([HREF, other])
    world.run()
    assert world.feed.count(b"BEGIN:VEVENT") == 3

    # Replaced by write and rename, as an editor or a platform mount does.
    replacement = world.config_file.with_suffix(".new")
    config = json.loads(world.config_file.read_text())
    config["calendars"][1]["enabled"] = False
    replacement.write_text(json.dumps(config))
    replacement.replace(world.config_file)
    world.run(NOW + timedelta(minutes=15))

    assert world.feed.count(b"BEGIN:VEVENT") == 2
    assert f"REPORT {other}" not in world.requests[-2:]


@pytest.mark.parametrize(
    ("members", "field"),
    [
        ({"tz": "Mars/Olympus"}, "tz"),
        ({"grid_minutes": 7}, "grid_minutes"),
        ({"calendars": []}, "calendars"),
        ({"owner_emails": "owner@example.org"}, "owner_emails"),
        ({"token": "BBX-plaintext"}, "token"),
        ({"token_sha256": "BBX-not-hex"}, "token_sha256"),
        ({"summary": "Blocker\nBBX-two lines"}, "summary"),
        ({"uid_salt": None}, "uid_salt"),
    ],
    ids=[
        "ORCH-CFG-2-tz",
        "ORCH-CFG-2-grid",
        "ORCH-CFG-2-empty",
        "ORCH-CFG-2-owners",
        "ORCH-CFG-7-plaintext",
        "ORCH-CFG-7-digest",
        "ORCH-CFG-8",
        "ORCH-CFG-6",
    ],
)
def test_invalid_configuration_fails_before_any_request_and_keeps_the_feed(
    world: World, members: dict[str, object], field: str
) -> None:
    world.run()
    feed = world.feed
    world.requests.clear()
    config = json.loads(world.config_file.read_text())
    config.update(members)
    config = {k: v for k, v in config.items() if v is not None}
    world.config_file.write_text(json.dumps(config))

    with pytest.raises(ConfigError) as raised:
        world.run(NOW + timedelta(minutes=15))

    assert world.requests == []
    assert world.feed == feed
    error = read_state(world.var_dir).last_error
    assert error is not None
    assert field in error
    assert "BBX-" not in error + str(raised.value)


def test_a_changed_configuration_logs_the_key_names_only_orch_cfg_11(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    other = "/calendars/svc-milchglas/familie/"
    world.answers[other] = multistatus()
    world.configure([HREF, other], summary="BBX-Old")
    watch = ConfigWatch()
    world.run(watch=watch)
    config = json.loads(world.config_file.read_text())
    config["calendars"][1]["enabled"] = False
    config["summary"] = "BBX-New"

    with caplog.at_level(logging.INFO, logger="milchglas.refresh"):
        world.config_file.write_text(json.dumps(config))
        world.run(NOW + timedelta(minutes=15), watch=watch)
        world.run(NOW + timedelta(minutes=30), watch=watch)

    changes = [r.getMessage() for r in caplog.records if "config" in r.getMessage()]
    assert changes == ["config changed: calendars[1].enabled, summary"]
    assert "BBX-" not in caplog.text


def test_the_first_run_logs_no_change_orch_cfg_11(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="milchglas.refresh"):
        world.run(watch=ConfigWatch())

    assert not [r for r in caplog.records if "config changed" in r.getMessage()]
