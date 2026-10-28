"""Bindings of `tests/features/caldav/parse.feature`, run against the real parser.

The world is a multistatus answer as sabre/dav writes one (synthetic, see
`tests/fixtures/MANIFEST.md`): `calendar-data` as escaped XML text with CR written as
`&#13;`, built here byte for byte so a fold can split a UTF-8 character. A spy on the
hand-over to `reduce_event` records what each event looks like when it leaves the parser,
and an audit hook records every file the process opens while it reads an answer.
"""

import sys
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from icalendar import Component
from pytest_bdd import given, parsers, scenario, then, when

from milchglas.core.model import Block, TimedBlock
from milchglas.core.reduce import Skip, reduce_event
from milchglas.sources import multistatus

HEAD = (
    b'<?xml version="1.0"?>\n'
    b'<d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns"'
    b' xmlns:cal="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/"'
    b' xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">\n'
)
HREF = "/calendars/svc/BBX-team/ev-1.ics"
# What an entity in a DOCTYPE can do: expand a thousandfold, or name a local file.
DECLARATIONS = {
    "a bare DOCTYPE": "<!DOCTYPE d:multistatus>",
    "an entity bomb": (
        '<!DOCTYPE d:multistatus [<!ENTITY a "BBX-boom">'
        ' <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"> <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">'
        ' <!ENTITY bomb "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">]>'
    ),
    "an external entity naming a local file": '<!DOCTYPE d:multistatus [<!ENTITY bomb SYSTEM "{file}">]>',
}
_LISTENERS: list[list[str]] = []


def _record_opens(event: str, args: tuple[object, ...]) -> None:
    if event == "open":
        for opened in _LISTENERS:
            opened.append(str(args[0]))


sys.addaudithook(_record_opens)


@dataclass
class World:
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    status: int = 207
    body: bytes = b""
    blocks: list[Block] | None = None
    error: Exception | None = None
    opened: list[str] = field(default_factory=list)
    secret: Path | None = None  # a local file an entity names
    handed: list[tuple[Component, str | None]] = field(default_factory=list)
    duration: str | None = None  # the DURATION text the answer carries
    description: str | None = None  # the text the answer's DESCRIPTION must read as


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    world = World()

    def spy(
        event: Component, *, tz: ZoneInfo, owner_emails: Collection[str], duration: str | None
    ) -> Block | Skip:
        world.handed.append((event, duration))
        return reduce_event(event, tz=tz, owner_emails=owner_emails, duration=duration)

    monkeypatch.setattr("milchglas.sources.multistatus.reduce_event", spy)
    return world


def vcalendar(*props: bytes, newline: bytes = b"\r\n") -> bytes:
    """One calendar object holding one VEVENT with `props`, in sabre's order."""
    lines = [
        b"BEGIN:VCALENDAR",
        b"VERSION:2.0",
        b"PRODID:-//Sabre//Sabre VObject 4.5.6//EN",
        b"CALSCALE:GREGORIAN",
        b"BEGIN:VEVENT",
        b"UID:ev-1@example.org",
        b"DTSTAMP:20261001T000000Z",
        *props,
        b"END:VEVENT",
        b"END:VCALENDAR",
    ]
    return newline.join(lines) + newline


def response(href: str, data: bytes) -> bytes:
    """One object of the answer; sabre escapes the iCalendar text and writes CR as `&#13;`."""
    text = data.replace(b"&", b"&amp;").replace(b"<", b"&lt;").replace(b">", b"&gt;")
    return (
        b" <d:response>\n  <d:href>" + href.encode() + b"</d:href>\n"
        b"  <d:propstat>\n   <d:prop>\n    <cal:calendar-data>"
        + text.replace(b"\r", b"&#13;")
        + b"</cal:calendar-data>\n   </d:prop>\n"
        b"   <d:status>HTTP/1.1 200 OK</d:status>\n  </d:propstat>\n </d:response>\n"
    )


def answer(*responses: bytes) -> bytes:
    return HEAD + b"".join(responses) + b"</d:multistatus>\n"


def utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


@scenario("caldav/parse.feature", "A repeated event lasts as long as written")
def test_parse_5_repeated_event_lasts_as_written() -> None:
    """P1D is a nominal day across the 2026-10-25 change, PT24H is 24 hours (Q-20)."""


@scenario("caldav/parse.feature", "A line folded inside a character still reads")
def test_parse_13_fold_inside_a_character() -> None:
    """The fold is removed from the bytes before they are decoded as UTF-8."""


@scenario("caldav/parse.feature", "A line longer than 75 octets still reads")
def test_parse_13_line_longer_than_75_octets() -> None:
    """RFC 5545 section 3.1 says SHOULD NOT, so the parser accepts it."""


@scenario("caldav/parse.feature", "A calendar without events in the window")
def test_parse_7_calendar_without_events() -> None:
    """An empty calendar is a valid answer (Q-16); the type guard before it is #77's."""


@scenario("caldav/parse.feature", "An answer that is not a multistatus fails without quoting it")
def test_parse_8_not_a_multistatus() -> None:
    """The error names status and size, never a byte of the body (NFR-P4)."""


@scenario("caldav/parse.feature", "An answer that declares markup is refused unread")
def test_parse_10_declaration_refused() -> None:
    """A DOCTYPE is refused before any entity in it expands (Q-14, NFR-O3)."""


@given("the owner's time zone is Europe/Berlin")
def owner_zone(world: World) -> None:
    world.tz = ZoneInfo("Europe/Berlin")


@given(
    parsers.parse(
        'calendar 1 answers with one instance from 2026-10-24 07:00 UTC lasting "{duration}"'
    )
)
def answers_instance_with_duration(world: World, duration: str) -> None:
    world.duration = duration
    world.body = answer(
        response(
            HREF,
            vcalendar(
                b"DTSTART:20261024T070000Z",
                b"DURATION:" + duration.encode(),
                b"RECURRENCE-ID:20261024T070000Z",
                b"SUMMARY:BBX-standup",
            ),
        )
    )


@given(
    parsers.parse(
        "calendar 1 answers with an event from 2026-11-02 08:00 UTC to 09:00 UTC whose "
        'description "BBX-Kälte" is folded inside the "ä" with {line_end}'
    )
)
def answers_fold_inside_character(world: World, line_end: str) -> None:
    newline = {"CRLF": b"\r\n", "LF": b"\n"}[line_end]
    world.description = "BBX-Kälte"
    before, after = "BBX-Kälte".encode().split(b"\xa4")  # the second byte of "ä"
    world.body = answer(
        response(
            HREF,
            vcalendar(
                b"DTSTART:20261102T080000Z",
                b"DTEND:20261102T090000Z",
                b"DESCRIPTION:" + before + newline + b" \xa4" + after,
                newline=newline,
            ),
        )
    )


@given(
    "calendar 1 answers with an event from 2026-11-02 08:00 UTC to 09:00 UTC whose "
    "description line is 200 octets long"
)
def answers_long_line(world: World) -> None:
    line = b"DESCRIPTION:BBX-" + b"x" * 184
    assert len(line) == 200
    world.description = line.removeprefix(b"DESCRIPTION:").decode()
    world.body = answer(
        response(HREF, vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z", line))
    )


@given("calendar 1 answers with a multistatus that holds no response")
def answers_no_response(world: World) -> None:
    world.body = answer()


@given(parsers.parse('calendar 1 answers with status {status:d} and the body "{body}"'))
def answers_body(world: World, status: int, body: str) -> None:
    world.status, world.body = status, body.encode()


@given(parsers.parse("calendar 1 answers with a multistatus that starts with {declaration}"))
def answers_declaration(world: World, declaration: str, tmp_path: Path) -> None:
    world.secret = tmp_path / "secret.txt"
    world.secret.write_text("BBX-local-secret")
    doctype = DECLARATIONS[declaration].format(file=world.secret.as_uri())
    event = vcalendar(
        b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z", b"DESCRIPTION:BBX-ref"
    )
    body = answer(response(HREF, event)).replace(
        b"BBX-ref", b"&bomb;" if "ENTITY" in doctype else b""
    )
    world.body = body.replace(b"?>\n", b"?>\n" + doctype.encode() + b"\n", 1)


@when("Milchglas reads the answer")
def reads_the_answer(world: World) -> None:
    _LISTENERS.append(world.opened)
    try:
        world.blocks = multistatus.parse(
            world.body, status=world.status, tz=world.tz, owner_emails=()
        )
    except multistatus.ParseError as error:
        world.error = error
    finally:
        _LISTENERS.remove(world.opened)


@then(parsers.parse("the owner is busy from 2026-10-24 07:00 UTC to 2026-10-25 {end} UTC"))
def busy_across_the_change(world: World, end: str) -> None:
    assert world.blocks == [TimedBlock(utc("2026-10-24 07:00"), utc(f"2026-10-25 {end}"))]
    # The hand-over carries the text, and the event holds no timedelta for it (Q-20).
    [(event, duration)] = world.handed
    assert duration == world.duration
    assert isinstance(event["DURATION"], str)


@then("the owner is busy from 2026-11-02 08:00 UTC to 2026-11-02 09:00 UTC")
def busy_on_monday_morning(world: World) -> None:
    assert world.blocks == [TimedBlock(utc("2026-11-02 08:00"), utc("2026-11-02 09:00"))]
    [(event, _)] = world.handed
    assert world.description is None or event["DESCRIPTION"] == world.description


@then("the owner is busy at no time from calendar 1")
def busy_at_no_time(world: World) -> None:
    assert world.blocks == []


@then("reading reports no error")
def no_error(world: World) -> None:
    assert world.error is None


@then(parsers.parse("reading fails naming status {status:d} and {size:d} bytes"))
def fails_naming_status_and_size(world: World, status: int, size: int) -> None:
    assert len(world.body) == size
    assert isinstance(world.error, multistatus.ParseError)
    assert f"HTTP {status}, {size} bytes" in str(world.error)


@then("the error holds nothing of the body")
def error_holds_nothing(world: World) -> None:
    assert world.error is not None
    assert "BBX" not in str(world.error)
    # The library's message is gone, not only hidden behind ours.
    assert world.error.__cause__ is None
    assert world.error.__context__ is None or world.error.__suppress_context__


@then("reading fails as a refused declaration")
def fails_as_refused_declaration(world: World) -> None:
    assert isinstance(world.error, multistatus.ParseError)
    assert "declaration" in str(world.error)
    assert "BBX" not in str(world.error)


@then("no local file was read")
def no_file_read(world: World) -> None:
    assert world.secret is not None
    assert str(world.secret) not in world.opened
