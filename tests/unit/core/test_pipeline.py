"""The demo calendars through the whole pure pipeline, against the e2e oracle.

objects/demo2.ics and demo3.ics are the import fixtures of the live end-to-end suite;
expected_blocks.json is its oracle, so both suites share one source of truth (AC-1, AC-3,
AC-4, AC-5, AC-8). Recurring masters and their overrides are left out: expanding them is
the source layer's job (server-side `expand`, spec FR-2), not the core's.
"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from milchglas.core.emit import emit
from milchglas.core.model import Block, DayBlock, TimedBlock, clip, merge, round_to_grid, window
from milchglas.core.reduce import Skip, reduce_event
from tests.support.feed import assert_feed_invariants, parse_feed
from tests.support.ical import components

ORACLE: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "expected_blocks.json").read_text()
)
TZ = ZoneInfo(ORACLE["tz"])
GRID = 15
WINDOW_DAYS = 28


def _sentinel(uid: str) -> str:
    """`bbx-d2-17@…` -> `BBX-D2-17`, the id the oracle's `from` lists use."""
    return uid.split("@", 1)[0].upper()


def _pipeline() -> tuple[list[Block], set[str]]:
    events, recurring = [], set()
    for name in ORACLE["source_fixtures"]:
        for event in components(Path(name).name):
            if "RRULE" in event or "RECURRENCE-ID" in event:
                recurring.add(_sentinel(str(event["UID"])))
            else:
                events.append(event)
    win = window(datetime.fromisoformat(ORACLE["now"]), TZ, WINDOW_DAYS)
    reduced = [reduce_event(e, tz=TZ, owner_emails=ORACLE["owner_emails"]) for e in events]
    blocks = [r for r in reduced if not isinstance(r, Skip)]
    return merge(round_to_grid(clip(blocks, win), GRID, TZ)), recurring


def _stamp(text: str) -> datetime:
    return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _expected(recurring: set[str]) -> list[tuple[str, date, date]]:
    def keep(entry: dict[str, Any]) -> bool:
        return not recurring.intersection(entry["from"])

    days = [
        ("day", date.fromisoformat(e["start"]), date.fromisoformat(e["end"]))
        for e in ORACLE["allday_date"]
        if keep(e)
    ]
    timed = [
        ("timed", _stamp(e["start"]), _stamp(e["end"])) for e in ORACLE["timed_utc"] if keep(e)
    ]
    return [*days, *timed]


def _spans(blocks: list[Block]) -> list[tuple[str, date, date]]:
    return [("day" if isinstance(b, DayBlock) else "timed", b.start, b.end) for b in blocks]


def test_window_matches_the_oracle() -> None:
    win = window(datetime.fromisoformat(ORACLE["now"]), TZ, WINDOW_DAYS)
    assert (win.start, win.end) == (
        _stamp(ORACLE["window"]["start_utc"]),
        _stamp(ORACLE["window"]["end_utc"]),
    )


def test_demo_calendars_reduce_to_the_oracle_blocks() -> None:
    blocks, recurring = _pipeline()
    assert recurring == {"BBX-D2-17", "BBX-D3-14"}  # the filter removes exactly these
    assert _spans(blocks) == _expected(recurring)


def test_demo_blocks_carry_no_event_content() -> None:
    blocks, _ = _pipeline()
    assert all(isinstance(b, DayBlock | TimedBlock) for b in blocks)
    assert not any(s in repr(blocks) for s in ORACLE["forbidden_substrings"])


def test_demo_feed_holds_every_invariant_and_no_event_content() -> None:
    blocks, _ = _pipeline()
    feed = emit(
        blocks,
        summary="Blocker Privat",
        salt="demo-salt",
        ttl_seconds=900,
        version="0.1.2",
        now=datetime.fromisoformat(ORACLE["now"]),
        dtstamps={},
    )
    # AC-8: the grep for every fixture title runs inside the invariants.
    assert_feed_invariants(feed, forbidden=tuple(ORACLE["forbidden_substrings"]))
    assert parse_feed(feed) == [replace(b, tentative=False) for b in blocks]
