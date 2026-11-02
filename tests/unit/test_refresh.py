"""One refresh run end to end: fetch, parse, build, atomic write and state (FR-8, FR-11, AC-6, AC-7).

The world is the production `fetch` and `parse` behind a fake opener: every PROPFIND gets a
read-only share as Nextcloud describes one, every REPORT the multistatus answer scripted for
its calendar (synthetic, in the sabre/dav dialect of `tests/fixtures/MANIFEST.md`). Answers
are `Body` objects, which count how many of them are alive at once.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from http.client import HTTPResponse
from itertools import pairwise
from pathlib import Path
from types import TracebackType
from typing import Self, cast
from zoneinfo import ZoneInfo

import pytest

from milchglas import refresh as refresh_module
from milchglas.config import Config, parse
from milchglas.core.model import Block, DayBlock, TimedBlock, clip, merge, round_to_grid, window
from milchglas.refresh import build, refresh
from milchglas.sources.caldav import Account, FetchError
from milchglas.state import FEED, STATE, BusyError, State, read_state, run_lock
from tests.support.feed import assert_feed_invariants, parse_feed

BERLIN = ZoneInfo("Europe/Berlin")
SALT = "0123456789abcdef0123456789abcdef"
DIGEST = "ab" * 32
ACCOUNT = Account("https://cal.example.com", "svc-milchglas", "synthetic-app-password")
NOW = datetime(2026, 11, 2, 8, 5, tzinfo=UTC)  # 09:05 in Berlin
CHECK = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
 <d:response><d:href>/calendars/svc-milchglas/x/</d:href><d:propstat><d:prop>
  <d:resourcetype><d:collection/><cal:calendar/></d:resourcetype>
  <d:owner><d:href>/principals/users/owner/</d:href></d:owner>
  <d:current-user-principal><d:href>/principals/users/svc-milchglas/</d:href></d:current-user-principal>
  <d:current-user-privilege-set><d:privilege><d:read/></d:privilege>
   <d:privilege><d:write-properties/></d:privilege></d:current-user-privilege-set>
 </d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>
</d:multistatus>
"""


class Body(bytes):
    """A REPORT answer that counts the live ones and records the most ever alive at once."""

    alive = 0
    most = 0

    def __new__(cls, data: bytes) -> Self:
        Body.alive += 1
        Body.most = max(Body.most, Body.alive)
        return super().__new__(cls, data)

    def __del__(self) -> None:
        Body.alive -= 1


class Answer:
    """What the opener hands `fetch`: a context manager with `read`."""

    def __init__(self, data: bytes) -> None:
        self.data: bytes | None = data

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.data = None

    def read(self, _limit: int) -> bytes:
        data, self.data = self.data, None
        assert data is not None
        return data


def event(uid: str, start: str, end: str) -> str:
    """One expanded instance in UTC, its title a sentinel that must never reach the feed."""
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Sabre//Sabre VObject 4.5.6//EN\r\n"
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTAMP:20261001T000000Z\r\n"
        f"DTSTART:{start}\r\nDTEND:{end}\r\nSUMMARY:BBX-{uid}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def multistatus(*objects: str) -> bytes:
    responses = "".join(
        f"<d:response><d:href>/calendars/svc-milchglas/x/{index}.ics</d:href>"
        "<d:propstat><d:prop><cal:calendar-data>"
        + data.replace("\r", "&#13;")
        + "</cal:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>"
        "</d:response>"
        for index, data in enumerate(objects)
    )
    return (
        '<?xml version="1.0"?>\n<d:multistatus xmlns:d="DAV:"'
        f' xmlns:cal="urn:ietf:params:xml:ns:caldav">{responses}</d:multistatus>'
    ).encode()


@dataclass
class World:
    var_dir: Path
    config_file: Path
    answers: dict[str, bytes | Callable[[], bytes]] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)

    def configure(self, hrefs: list[str], **members: object) -> None:
        calendars = [
            {"href": href, "name": f"c{i}", "enabled": True} for i, href in enumerate(hrefs)
        ]
        self.config_file.write_text(
            json.dumps(
                {
                    "uid_salt": SALT,
                    "token_sha256": DIGEST,
                    "owner_emails": ["owner@example.org"],
                    "calendars": calendars,
                    **members,
                }
            )
        )

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> HTTPResponse:
        """The `Opener` seam of `fetch`; `Answer` has the part of HTTPResponse it reads."""
        assert timeout > 0
        path = fullurl.full_url.removeprefix(ACCOUNT.origin)
        self.requests.append(f"{fullurl.get_method()} {path}")
        if fullurl.get_method() == "PROPFIND":
            return cast("HTTPResponse", Answer(CHECK))
        answer = self.answers[path]
        return cast("HTTPResponse", Answer(Body(answer() if callable(answer) else answer)))

    def run(self, now: datetime = NOW, *, dry_run: bool = False) -> None:
        refresh(self.config_file, self.var_dir, ACCOUNT, now=now, opener=self, dry_run=dry_run)

    @property
    def feed(self) -> bytes:
        return (self.var_dir / FEED).read_bytes()

    @property
    def state(self) -> State:
        return read_state(self.var_dir)


HREF = "/calendars/svc-milchglas/privat/"
TWO_EVENTS = multistatus(
    event("a", "20261103T090000Z", "20261103T100000Z"),
    event("b", "20261104T130000Z", "20261104T143000Z"),
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    world = World(var_dir=tmp_path / "var", config_file=tmp_path / "config.json")
    world.configure([HREF])
    world.answers[HREF] = TWO_EVENTS
    Body.alive = Body.most = 0
    return world


def _stamps(feed: bytes) -> dict[str, str]:
    lines = feed.decode().split("\r\n")
    return {
        uid.removeprefix("UID:"): stamp.removeprefix("DTSTAMP:")
        for uid, stamp in pairwise(lines)
        if uid.startswith("UID:")
    }


def test_a_refresh_publishes_the_blocks_and_records_the_success(world: World) -> None:
    world.run()

    assert_feed_invariants(world.feed)
    assert parse_feed(world.feed) == [
        TimedBlock(datetime(2026, 11, 3, 9, tzinfo=UTC), datetime(2026, 11, 3, 10, tzinfo=UTC)),
        TimedBlock(
            datetime(2026, 11, 4, 13, tzinfo=UTC), datetime(2026, 11, 4, 14, 30, tzinfo=UTC)
        ),
    ]
    assert world.state == State(NOW, None)
    assert world.requests == [f"PROPFIND {HREF}", f"REPORT {HREF}"]


def test_two_runs_a_quarter_hour_apart_write_identical_bytes_det_1(world: World) -> None:
    world.run(NOW)
    first = world.feed
    world.run(NOW + timedelta(minutes=15))

    assert world.feed == first


def test_no_previous_feed_stamps_every_block_now_det_4(world: World) -> None:
    world.run()

    assert set(_stamps(world.feed).values()) == {"20261102T080500Z"}


def test_an_unchanged_block_keeps_its_stamp_det_2(world: World) -> None:
    world.run()
    world.run(NOW + timedelta(hours=3))

    assert set(_stamps(world.feed).values()) == {"20261102T080500Z"}


def test_a_moved_event_swaps_exactly_one_uid_det_3(world: World) -> None:
    world.run()
    before = _stamps(world.feed)
    world.answers[HREF] = multistatus(
        event("a", "20261103T090000Z", "20261103T100000Z"),
        event("b", "20261104T150000Z", "20261104T163000Z"),
    )
    later = NOW + timedelta(hours=1)
    world.run(later)
    after = _stamps(world.feed)

    assert len(before.keys() - after.keys()) == 1
    (new,) = after.keys() - before.keys()
    assert after[new] == "20261102T090500Z"
    assert {uid: after[uid] for uid in before.keys() & after.keys()} == {
        uid: before[uid] for uid in before.keys() & after.keys()
    }


@pytest.mark.parametrize(
    "previous",
    [
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nUID:x",
        b"\xff\xfe not utf-8",
        b"<html>not a calendar</html>",
        b"BEGIN:VCALENDAR\r\nUID:x@milchglas\r\nDTSTAMP:garbage\r\nEND:VCALENDAR\r\n",
    ],
    ids=["DET-8-truncated", "DET-8-not-utf-8", "DET-8-not-a-calendar", "DET-8-bad-stamp"],
)
def test_an_unreadable_previous_feed_restamps_and_warns_once(
    world: World, previous: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    world.var_dir.mkdir(mode=0o700)
    (world.var_dir / FEED).write_bytes(previous)

    with caplog.at_level(logging.WARNING, logger="milchglas.refresh"):
        world.run()

    assert set(_stamps(world.feed).values()) == {"20261102T080500Z"}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["previous feed unreadable; 2 blocks stamped with the current time"]


def _snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _fails_closed(world: World, error: type[Exception]) -> None:
    """A run that fails keeps the feed byte for byte and its mtime, and records the error."""
    feed = _snapshot(world.var_dir / FEED)
    later = NOW + timedelta(minutes=15)

    with pytest.raises(error):
        world.run(later)

    assert _snapshot(world.var_dir / FEED) == feed
    assert world.state.last_success == NOW
    assert world.state.last_error is not None
    assert "BBX-" not in world.state.last_error


def test_a_fetch_failure_keeps_the_feed_and_records_the_error_orch_fetch_3(world: World) -> None:
    def refused() -> bytes:
        raise urllib.error.HTTPError(ACCOUNT.origin, 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

    world.run()
    world.answers[HREF] = refused

    _fails_closed(world, FetchError)
    assert world.state.last_error == "FetchError: calendars[0]: HTTP 401"


def test_a_parse_failure_keeps_the_feed_and_records_the_error_orch_fetch_3(world: World) -> None:
    world.run()
    world.answers[HREF] = multistatus(event("c", "BBY-garbage", "20261104T100000Z"))

    _fails_closed(world, ValueError)
    assert world.state.last_error is not None
    assert world.state.last_error.startswith("MalformedEventError: calendar 0, object ")


def test_a_crash_before_the_state_write_is_repaired_by_the_next_run_orch_write_3(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def crash(_var_dir: Path, _state: State) -> None:
        raise OSError

    world.run()
    first = world.feed
    with monkeypatch.context() as patch:
        patch.setattr(refresh_module, "write_state", crash)
        with pytest.raises(OSError):  # noqa: PT011
            world.run(NOW + timedelta(minutes=15))
    later = NOW + timedelta(minutes=30)
    world.run(later)

    assert world.feed == first
    assert world.state == State(later, None)


@pytest.mark.parametrize("content", [None, b"{not json", b'{"last_success": 3}'])
def test_a_missing_or_corrupt_state_does_not_stop_a_refresh_orch_write_4(
    world: World, content: bytes | None
) -> None:
    world.var_dir.mkdir(mode=0o700)
    if content is not None:
        (world.var_dir / STATE).write_bytes(content)

    world.run()

    assert world.state == State(NOW, None)


def test_a_second_run_while_one_holds_the_lock_touches_nothing_orch_lock_1(world: World) -> None:
    world.run()
    feed, state = _snapshot(world.var_dir / FEED), _snapshot(world.var_dir / STATE)
    world.requests.clear()

    with run_lock(world.var_dir), pytest.raises(BusyError):
        world.run(NOW + timedelta(minutes=15))

    assert _snapshot(world.var_dir / FEED) == feed
    assert _snapshot(world.var_dir / STATE) == state
    assert world.requests == []


def test_one_answer_is_alive_at_a_time_orch_fetch_10(world: World) -> None:
    hrefs = [f"/calendars/svc-milchglas/c{i}/" for i in range(10)]
    world.configure(hrefs)
    for i, href in enumerate(hrefs):
        world.answers[href] = multistatus(
            event(f"e{i}", f"202611{10 + i:02d}T090000Z", f"202611{10 + i:02d}T100000Z")
        )

    world.run()

    assert len(parse_feed(world.feed)) == 10
    assert Body.most == 1


def test_zero_events_publish_an_empty_feed_and_a_success_orch_empty_1(world: World) -> None:
    world.answers[HREF] = multistatus()

    world.run()

    assert_feed_invariants(world.feed)
    assert parse_feed(world.feed) == []
    assert world.state == State(NOW, None)


def test_one_summary_line_with_counts_only_orch_log_4(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="milchglas.refresh"):
        world.run()

    (line,) = [r.getMessage() for r in caplog.records if r.name == "milchglas.refresh"]
    assert line.startswith("refresh ok: 1 calendars, 2 objects, 2 blocks, ")
    assert line.endswith(" s")
    assert "BBX-" not in caplog.text


def test_a_failed_run_logs_one_summary_line_too_orch_log_4(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    world.answers[HREF] = multistatus(event("c", "BBY-garbage", "20261104T100000Z"))

    with caplog.at_level(logging.INFO, logger="milchglas.refresh"), pytest.raises(ValueError):  # noqa: PT011
        world.run()

    (line,) = [r.getMessage() for r in caplog.records if r.name == "milchglas.refresh"]
    assert line.startswith("refresh failed (MalformedEventError: calendar 0, object ")
    assert ": 0 calendars, 0 objects, 0 blocks, " in line
    assert "BBY-" not in caplog.text


def test_a_dry_run_writes_nothing_and_takes_no_lock_orch_cli_2(world: World) -> None:
    world.run()
    before = {path.name: _snapshot(path) for path in world.var_dir.iterdir()}

    with run_lock(world.var_dir):
        report = refresh(
            world.config_file,
            world.var_dir,
            ACCOUNT,
            now=NOW + timedelta(hours=1),
            opener=world,
            dry_run=True,
        )

    assert (report.calendars, report.objects, report.blocks) == (1, 2, 2)
    assert {path.name: _snapshot(path) for path in world.var_dir.iterdir()} == before


def _config(**members: object) -> Config:
    return parse(
        {
            "uid_salt": SALT,
            "token_sha256": DIGEST,
            "owner_emails": [],
            "calendars": [{"href": HREF, "name": "c", "enabled": True}],
            **members,
        },
        NOW,
    )


def test_a_year_of_daily_builds_keeps_every_invariant_and_stamp_det_6() -> None:
    config = _config()
    blocks: list[Block] = []
    day = date(2026, 1, 1)
    while day < date(2027, 3, 1):
        # A timed block each third day, one across each DST change, and an all-day pair.
        start = datetime(day.year, day.month, day.day, 6, 7, tzinfo=UTC)
        blocks.append(TimedBlock(start, start + timedelta(hours=2, minutes=50)))
        blocks.append(DayBlock(day + timedelta(days=1), day + timedelta(days=3)))
        day += timedelta(days=9)
    blocks += [
        TimedBlock(
            datetime(2026, 3, 29, 0, 30, tzinfo=UTC), datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
        ),
        TimedBlock(
            datetime(2026, 10, 25, 0, 30, tzinfo=UTC), datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
        ),
    ]
    previous: bytes | None = None
    published: list[Block] = []
    clock = datetime(2026, 1, 1, 5, tzinfo=UTC)
    started = time.monotonic()
    for _ in range(365):
        span = window(clock, BERLIN, config.window_days)
        feed = build(blocks, config, span, clock, previous)
        assert_feed_invariants(feed)
        shown = merge(round_to_grid(clip(blocks, span), config.grid_minutes, BERLIN))
        if previous is not None:
            before, after = _stamps(previous), _stamps(feed)
            assert all(after[uid] == before[uid] for uid in before.keys() & after.keys())
            # The bytes change only on a day the window boundary crosses a block.
            assert (feed != previous) == (shown != published)
        previous, published = feed, shown
        clock += timedelta(days=1)
    # About 1 s plain and 2.5 s under coverage tracing; the bound catches a blow-up, not jitter.
    assert time.monotonic() - started < 10
    assert os.environ["TZ"] == "America/St_Johns"  # the suite's host zone stays out of it


def test_a_feed_that_cannot_be_read_counts_as_unreadable_det_8(tmp_path: Path) -> None:
    previous = refresh_module._previous  # noqa: SLF001 - a read error a fixture cannot make as root
    assert previous(tmp_path) == b""  # a directory: IsADirectoryError
    assert previous(tmp_path / "missing") is None
