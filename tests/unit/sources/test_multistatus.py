"""Bindings of `tests/features/caldav/parse.feature`, run against the real parser.

The world is a multistatus answer as sabre/dav writes one (synthetic, see
`tests/fixtures/MANIFEST.md`): `calendar-data` as escaped XML text with CR written as
`&#13;`, built here byte for byte so a fold can split a UTF-8 character. A spy on the
hand-over to `reduce_event` records what each event looks like when it leaves the parser,
and an audit hook records every file the process opens while it reads an answer.
"""

import hashlib
import logging
import re
import signal
import sys
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from icalendar import Component
from icalendar.timezone import tzp
from pytest_bdd import given, parsers, scenario, then, when

from milchglas.core.model import Block, TimedBlock
from milchglas.core.reduce import MalformedEventError, Skip, reduce_event
from milchglas.sources import multistatus

HEAD = (
    b'<?xml version="1.0"?>\n'
    b'<d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns"'
    b' xmlns:cal="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/"'
    b' xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">\n'
)
HREF = "/calendars/svc/BBX-team/ev-1.ics"
NOT_FOUND = b"HTTP/1.1 404 Not Found"
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
    logged: list[str] = field(default_factory=list)
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


def propstat(prop: bytes, status: bytes = b"HTTP/1.1 200 OK") -> bytes:
    return (
        b"  <d:propstat>\n   <d:prop>\n    " + prop + b"\n   </d:prop>\n"
        b"   <d:status>" + status + b"</d:status>\n  </d:propstat>\n"
    )


def response(href: str, data: bytes | None, *more: bytes) -> bytes:
    """One object of the answer; sabre escapes the iCalendar text and writes CR as `&#13;`.

    `data` None leaves out the propstat that carries `calendar-data`; `more` adds others.
    """
    found = b""
    if data is not None:
        text = data.replace(b"&", b"&amp;").replace(b"<", b"&lt;").replace(b">", b"&gt;")
        found = propstat(
            b"<cal:calendar-data>" + text.replace(b"\r", b"&#13;") + b"</cal:calendar-data>"
        )
    return (
        b" <d:response>\n  <d:href>"
        + href.encode()
        + b"</d:href>\n"
        + found
        + b"".join(more)
        + b" </d:response>\n"
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


@scenario("caldav/parse.feature", "A garbage start among valid events fails the read")
def test_parse_11_garbage_start_among_valid_events() -> None:
    """One unreadable object fails the read instead of becoming a free slot (Q-14)."""


@scenario("caldav/parse.feature", "A cancelled event with a garbage start still fails the read")
def test_parse_11_cancelled_event_with_garbage_start() -> None:
    """reduce would skip it unread; the source layer decides Q-14 first."""


@scenario("caldav/parse.feature", "A duration beyond any date fails the read")
def test_parse_14_duration_beyond_any_date() -> None:
    """DURATION reaches reduce as text; the alarm's TRIGGER overflows inside icalendar."""


@scenario("caldav/parse.feature", "Calendar data the server could not find fails the read")
def test_parse_2_calendar_data_not_found() -> None:
    """An object without its data would read as a free slot (Q-14)."""


@scenario("caldav/parse.feature", "A missing entity tag does not stop the read")
def test_parse_2_missing_entity_tag() -> None:
    """A 404 for any other requested property is ignored (NFR-C1)."""


@scenario("caldav/parse.feature", "An instance the server left unexpanded fails the read")
def test_parse_12_unexpanded_instance() -> None:
    """Only the first instance would block; every later one would be a free slot (FR-2)."""


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


@given(parsers.parse('calendar 1 answers with 3 events, the second at "{href}" starting "{value}"'))
def answers_garbage_among_valid(world: World, href: str, value: str) -> None:
    world.body = answer(
        response(HREF, vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z")),
        response(href, vcalendar(b"DTSTART:" + value.encode(), b"DTEND:20261102T110000Z")),
        response(
            "/calendars/svc/BBX-team/ev-3.ics",
            vcalendar(b"DTSTART:20261102T120000Z", b"DTEND:20261102T130000Z"),
        ),
    )


@given(parsers.parse('calendar 1 answers with a cancelled event at "{href}" starting "{value}"'))
def answers_cancelled_garbage(world: World, href: str, value: str) -> None:
    world.body = answer(
        response(href, vcalendar(b"STATUS:CANCELLED", b"DTSTART:" + value.encode()))
    )


@given(parsers.parse('calendar 1 answers with an event at "{href}" whose {name} is "{value}"'))
def answers_out_of_range(world: World, href: str, name: str, value: str) -> None:
    props = {
        "DURATION": [b"DURATION:" + value.encode()],
        "alarm TRIGGER": [
            b"DTEND:20261102T090000Z",
            b"BEGIN:VALARM",
            b"ACTION:DISPLAY",
            b"TRIGGER:" + value.encode(),
            b"END:VALARM",
        ],
    }[name]
    world.body = answer(response(href, vcalendar(b"DTSTART:20261102T080000Z", *props)))


@given(parsers.parse('calendar 1 answers for "{href}" that {what} was not found'))
def answers_not_found(world: World, href: str, what: str) -> None:
    # sabre's shape for a missing property, and a status for the whole response.
    missing = {
        "its calendar data": propstat(b"<cal:calendar-data/>", NOT_FOUND),
        "the whole object": b"  <d:status>" + NOT_FOUND + b"</d:status>\n",
    }[what]
    world.body = answer(response(href, None, missing))


@given(
    "calendar 1 answers with an event from 2026-11-02 08:00 UTC to 09:00 UTC and says its "
    "entity tag was not found"
)
def answers_etag_not_found(world: World) -> None:
    event = vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z")
    world.body = answer(response(HREF, event, propstat(b"<d:getetag/>", NOT_FOUND)))


@given(
    parsers.parse('calendar 1 answers with a weekly event at "{href}" that still holds its {rule}')
)
def answers_unexpanded(world: World, href: str, rule: str) -> None:
    line = {"RRULE": b"RRULE:FREQ=WEEKLY;COUNT=4", "RDATE": b"RDATE:20261109T080000Z"}[rule]
    event = vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z", line)
    world.body = answer(response(href, event))


@when("Milchglas reads the answer")
def reads_the_answer(world: World, caplog: pytest.LogCaptureFixture) -> None:
    _LISTENERS.append(world.opened)
    caplog.set_level(logging.DEBUG)  # every logger, the libraries' included
    try:
        world.blocks = multistatus.parse(
            world.body, calendar=1, status=world.status, tz=world.tz, owner_emails=()
        )
    except (multistatus.ParseError, MalformedEventError) as error:
        world.error = error
    finally:
        _LISTENERS.remove(world.opened)
    world.logged = [record.getMessage() for record in caplog.records]


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
    assert world.error.__context__ is None


@then("reading fails as a refused declaration")
def fails_as_refused_declaration(world: World) -> None:
    assert isinstance(world.error, multistatus.ParseError)
    assert "declaration" in str(world.error)
    assert "BBX" not in str(world.error)


@then("no local file was read")
def no_file_read(world: World) -> None:
    assert world.secret is not None
    assert str(world.secret) not in world.opened


@then(
    parsers.parse('reading fails as a malformed event naming calendar 1 and the hash of "{href}"')
)
def fails_as_malformed_event(world: World, href: str) -> None:
    assert isinstance(world.error, MalformedEventError)
    assert not isinstance(world.error, multistatus.ParseError)
    message = str(world.error)
    assert message.startswith("calendar 1, object ")
    assert hashlib.sha256(href.encode()).hexdigest()[:16] in message


@then(parsers.re(r"no error or log line holds (?P<values>.+)"))
def nothing_holds(world: World, values: str) -> None:
    assert world.error is not None
    assert world.error.__cause__ is None
    assert world.error.__context__ is None
    for value in re.findall(r'"([^"]+)"', values):
        assert value not in str(world.error)
        assert not any(value in line for line in world.logged)


def test_parse_2_reads_calendar_data_only_from_a_200_propstat() -> None:
    """Data under any other status is no object the server vouches for, however whole."""
    event = vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z")
    data = b"<cal:calendar-data>" + event.replace(b"\r", b"&#13;") + b"</cal:calendar-data>"
    body = answer(response(HREF, None, propstat(data, NOT_FOUND)))
    with pytest.raises(MalformedEventError, match="no calendar-data with status 200"):
        multistatus.parse(body, calendar=1, status=207, tz=ZoneInfo("UTC"), owner_emails=())


# --- Security regressions (review of 2026-10-28); plain tests, no scenario of their own ---


def parse_one(data: bytes, href: str = HREF) -> list[Block]:
    return multistatus.parse(
        answer(response(href, data)),
        calendar=1,
        status=207,
        tz=ZoneInfo("Europe/Berlin"),
        owner_emails=(),
    )


def zoned(zone: bytes, *rules: bytes) -> bytes:
    """An object whose event lives in a zone that the object defines itself."""
    return (
        b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VTIMEZONE\r\nTZID:BBX-zone\r\n"
        + zone
        + b"END:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:ev-1@example.org\r\n"
        b"DTSTART;TZID=BBX-zone:20261102T080000\r\nDTEND;TZID=BBX-zone:20261102T090000\r\n"
        + b"".join(rules)
        + b"END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def standard(offset: bytes, rule: bytes = b"") -> bytes:
    return (
        b"BEGIN:STANDARD\r\nDTSTART:19700101T000000\r\n"
        + rule
        + b"TZOFFSETFROM:"
        + offset
        + b"\r\nTZOFFSETTO:"
        + offset
        + b"\r\nEND:STANDARD\r\n"
    )


@contextmanager
def deadline(seconds: int) -> Iterator[None]:
    def expire(*_args: object) -> None:
        msg = f"still running after {seconds} s"
        raise TimeoutError(msg)

    previous = signal.signal(signal.SIGALRM, expire)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@pytest.mark.parametrize(
    "body",
    [
        HEAD + b"<d:response><d:href>BBX-&#8364;</d:href></d:response></d:multistatus>",
        answer(response(HREF, None, propstat(b"<d:getetag/>", b"BBX-&#8364;"))),
        answer(response(HREF, vcalendar(b"SUMMARY:BBX-&#8364;"))).replace(
            b"&amp;#8364;", b"&#8364;"
        ),
    ],
    ids=["href", "status", "calendar-data"],
)
def test_parse_8_character_beyond_latin_1_fails_without_quoting_it(body: bytes) -> None:
    """A reference such as &#8364; has no byte to stand for; the read fails, quoting nothing."""
    with pytest.raises(multistatus.ParseError) as caught:
        multistatus.parse(body, calendar=1, status=207, tz=ZoneInfo("UTC"), owner_emails=())
    assert "BBX" not in str(caught.value)
    assert "\u20ac" not in str(caught.value)
    assert caught.value.__context__ is None


def test_parse_11_zone_defined_in_the_object_fails_at_once() -> None:
    """A VTIMEZONE of its own runs through dateutil, whose rules can spin for hours.

    Every IANA, Windows and vendor TZID resolves to zoneinfo; only a zone the object
    defines does not. That zone fails the read before any of its rules is evaluated.
    """
    dense = standard(b"+0100", b"RRULE:FREQ=SECONDLY\r\n")
    with deadline(5), pytest.raises(MalformedEventError, match="outside the IANA"):
        parse_one(zoned(dense))


def test_parse_11_zone_of_one_object_never_reads_another() -> None:
    """icalendar caches a zone process-wide by TZID: the first definition would win."""
    with pytest.raises(MalformedEventError):
        parse_one(zoned(standard(b"+0100")))
    assert tzp.timezone("BBX-zone") is None  # the answer left no zone behind
    later = vcalendar(
        b"DTSTART;TZID=BBX-zone:20261102T080000", b"DTEND;TZID=BBX-zone:20261102T090000"
    )
    with pytest.raises(MalformedEventError, match="unknown TZID"):
        parse_one(later)


def test_parse_11_vendor_tzid_reads_without_a_warning(capsys: pytest.CaptureFixture[str]) -> None:
    """icalendar warns about a guessed vendor TZID and quotes it; the guess itself is right."""
    tzid = b"/BBX-vendor.example/20050126_1/Europe/Berlin"
    event = vcalendar(
        b"DTSTART;TZID=" + tzid + b":20261102T090000", b"DTEND;TZID=" + tzid + b":20261102T100000"
    )
    assert parse_one(event) == [TimedBlock(utc("2026-11-02 08:00"), utc("2026-11-02 09:00"))]
    assert "BBX" not in capsys.readouterr().err


def test_parse_11_vevent_with_a_trailing_blank_fails_the_read() -> None:
    """icalendar names the component "VEVENT " and records no error; the event would vanish."""
    data = vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T090000Z")
    with pytest.raises(MalformedEventError, match="component name"):
        parse_one(data.replace(b"BEGIN:VEVENT\r\n", b"BEGIN:VEVENT \r\n"))


@pytest.mark.parametrize("shape", ["one propstat", "two propstats"])
def test_parse_2_second_calendar_data_in_a_response_fails_the_read(shape: str) -> None:
    """Only one object per response; the second would replace the first unseen."""
    first, second = (
        b"<cal:calendar-data>"
        + vcalendar(
            b"DTSTART:202611" + day + b"T080000Z", b"DTEND:202611" + day + b"T090000Z"
        ).replace(b"\r", b"&#13;")
        + b"</cal:calendar-data>"
        for day in (b"02", b"03")
    )
    props = (
        [propstat(first + second)]
        if shape == "one propstat"
        else [propstat(first), propstat(second)]
    )
    body = answer(response(HREF, None, *props))
    with pytest.raises(multistatus.ParseError, match="more than one calendar-data"):
        multistatus.parse(body, calendar=1, status=207, tz=ZoneInfo("UTC"), owner_emails=())


def test_parse_16_event_ending_before_it_starts_is_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """reduce drops it and leaves the warning to its caller; the warning names no value."""
    data = vcalendar(b"DTSTART:20261102T080000Z", b"DTEND:20261102T070000Z", b"SUMMARY:BBX-x")
    with caplog.at_level(logging.WARNING, logger="milchglas.sources.multistatus"):
        assert parse_one(data) == []
    [record] = caplog.records
    digest = hashlib.sha256(HREF.encode()).hexdigest()[:16]
    assert record.getMessage() == f"calendar 1, object {digest}: ends before it starts, dropped"
