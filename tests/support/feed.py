"""Read an emitted feed back and check every invariant it must hold (spec FR-7, NFR-P3).

icalendar is the independent reader here: the emitter is hand-rolled, so a feed only
counts as valid when a real parser agrees with it.
"""

import re
from datetime import UTC, date, datetime
from itertools import pairwise

from icalendar import Calendar

from milchglas.core.model import Block, DayBlock, TimedBlock

FORBIDDEN = ("BBX-", "BBY-")
EVENT_PROPERTIES = {"UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "TRANSP", "STATUS"}
_HEADER = [
    r"BEGIN:VCALENDAR",
    r"VERSION:2\.0",
    r"PRODID:-//Milchglas//[0-9A-Za-z.+-]+//DE",
    r"X-WR-CALNAME:Privat \(busy\)",
    r"REFRESH-INTERVAL;VALUE=DURATION:(?P<ttl>PT\w+)",
    r"X-PUBLISHED-TTL:(?P=ttl)",
]
_TIME = re.compile(r"DT(START|END)(:\d{8}T\d{6}Z|;VALUE=DATE:\d{8})")
_STAMP = re.compile(r"DTSTAMP:\d{8}T\d{6}Z")
_UID = re.compile(r"UID:[0-9a-f]{32}@milchglas")


def logical_lines(feed: bytes) -> list[str]:
    """The feed's content lines, unfolded (RFC 5545 §3.1)."""
    return feed.decode("utf-8").replace("\r\n ", "").split("\r\n")[:-1]


def parse_feed(feed: bytes) -> list[Block]:
    """The blocks a consumer reads from `feed`, in file order."""
    blocks: list[Block] = []
    for event in _calendar(feed).events:
        start, end = event.start, event.end
        if isinstance(start, datetime) and isinstance(end, datetime):
            blocks.append(TimedBlock(start.astimezone(UTC), end.astimezone(UTC)))
        else:
            blocks.append(DayBlock(start, end))
    return blocks


def summaries(feed: bytes) -> list[str]:
    return [str(event["SUMMARY"]) for event in _calendar(feed).events]


def _calendar(feed: bytes) -> Calendar:
    calendar = Calendar.from_ical(feed)
    assert isinstance(calendar, Calendar)
    return calendar


def assert_feed_invariants(feed: bytes, forbidden: tuple[str, ...] = FORBIDDEN) -> None:
    text = feed.decode("utf-8")
    # EMIT-8: CRLF after every line, no bare CR or LF anywhere.
    assert text.endswith("\r\n")
    assert "\r" not in text.replace("\r\n", "")
    assert "\n" not in text.replace("\r\n", "")
    # EMIT-7: at most 75 octets per physical line.
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    lines = logical_lines(feed)
    header = re.compile("\n".join(_HEADER))
    assert header.fullmatch("\n".join(lines[: len(_HEADER)])), lines[: len(_HEADER)]
    assert lines[-1] == "END:VCALENDAR"
    # EMIT-3: UTC only, so no zone data at all.
    assert "VTIMEZONE" not in text
    assert "TZID" not in text
    events = _events(lines[len(_HEADER) : -1])
    for event in events:
        # EMIT-1 / NFR-P3: exactly the whitelisted properties, once each.
        names = [line.split(":", 1)[0].split(";", 1)[0] for line in event]
        assert sorted(names) == sorted(EVENT_PROPERTIES)
        assert all(_TIME.fullmatch(line) for line in event if line.startswith(("DTSTART", "DTEND")))
        assert any(_STAMP.fullmatch(line) for line in event)
        assert "TRANSP:OPAQUE" in event
        assert "STATUS:CONFIRMED" in event
        assert any(_UID.fullmatch(line) for line in event)
    uids = [line for event in events for line in event if line.startswith("UID:")]
    assert len(set(uids)) == len(uids)
    _assert_canonical(parse_feed(feed))
    assert not [s for s in forbidden if s in text]


def _events(body: list[str]) -> list[list[str]]:
    events: list[list[str]] = []
    for line in body:
        if line == "BEGIN:VEVENT":
            events.append([])
        elif line != "END:VEVENT":
            events[-1].append(line)
    assert body.count("BEGIN:VEVENT") == body.count("END:VEVENT") == len(events)
    return events


def _assert_canonical(blocks: list[Block]) -> None:
    """EMIT-9 and AC-1: day blocks first, each kind sorted, no two blocks overlap or touch."""
    kinds = [isinstance(b, TimedBlock) for b in blocks]
    assert kinds == sorted(kinds)
    days: list[date] = [d for b in blocks if isinstance(b, DayBlock) for d in (b.start, b.end)]
    instants: list[date] = [
        t for b in blocks if isinstance(b, TimedBlock) for t in (b.start, b.end)
    ]
    for edges in (days, instants):
        assert all(a < b for a, b in pairwise(edges))
