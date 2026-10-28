"""Read a CalDAV multistatus answer into busy blocks (FR-2, FR-4).

Each event is reduced at once; nothing here keeps event text. The answer is read byte
for byte: a content line folded at 75 octets can split a UTF-8 character, which leaves
the XML itself invalid UTF-8. So expat decodes it as Latin-1, which maps every byte to
one character, and each object is unfolded on its bytes before icalendar decodes it
(RFC 5545 section 3.1, NFR-C1).
"""

import hashlib
import logging
import re
import warnings
from collections.abc import Collection
from datetime import datetime
from io import BytesIO
from typing import ClassVar, NoReturn, override
from xml.parsers import expat
from zoneinfo import ZoneInfo

from icalendar import Calendar, Component, vText
from icalendar.prop.factory import TypesFactory
from icalendar.timezone import tzp

from milchglas.core.model import Block
from milchglas.core.reduce import MalformedEventError, Skip, reduce_event

_LOG = logging.getLogger(__name__)

_MULTISTATUS = "DAV: multistatus"
_RESPONSE = "DAV: response"
_HREF = "DAV: href"
_PROPSTAT = "DAV: propstat"
_STATUS = "DAV: status"
_DATA = "urn:ietf:params:xml:ns:caldav calendar-data"
# A line break followed by one space or tab continues the line (RFC 5545 section 3.1);
# sabre writes CRLF in expanded answers and LF in unexpanded ones (NFR-C1).
_FOLD = re.compile(rb"\r?\n[ \t]")
_OK = re.compile(rb"\s*HTTP/\d\.\d 200\b")
# Left in an instance, these mean the server did not expand it; while local expansion
# is off, every later instance would be a free slot (FR-2, Q-14).
_UNEXPANDED = ("RRULE", "RDATE")
_TIMES = ("DTSTART", "DTEND")  # the times reduce_event reads
# RFC 5545 section 3.1: a component name is an iana-token or x-name.
_NAME = re.compile(r"[A-Za-z0-9-]+")
# One object per response: a second calendar-data would replace the first unseen.
_TWICE = "more than one calendar-data in a response"


class _TextDuration(TypesFactory):
    """Keeps DURATION as the text the server sent, for `reduce_event` to read (Q-20).

    icalendar would make it a timedelta, in which PT24H and P1D are the same day.
    """

    @override
    def for_property(self, name: str, value_param: str | None = None) -> type:
        if name.upper() == "DURATION":
            return vText
        return super().for_property(name, value_param)


class _Calendar(Calendar):
    types_factory: ClassVar[TypesFactory] = _TextDuration()


class ParseError(Exception):
    """An answer that is no readable multistatus; the message names its status and size only."""

    def __init__(self, reason: str, *, status: int, size: int) -> None:
        # Never a byte of the body (NFR-P4); expat's own reasons are fixed texts.
        super().__init__(f"HTTP {status}, {size} bytes: {reason}")


def parse(
    body: bytes, *, calendar: int, status: int, tz: ZoneInfo, owner_emails: Collection[str]
) -> list[Block]:
    """The busy blocks of every object in one calendar's multistatus `body`.

    Q-14 is decided here, before `reduce_event` sees an event: an object the parser reports
    any error for fails the read, even a cancelled one whose times reduce never reads.
    """
    blocks: list[Block] = []
    for href, data in _Answer(body, status).read():
        # An href names the calendar and the event file, so only its hash is shown (NFR-P4).
        where = f"calendar {calendar}, object {hashlib.sha256(href).hexdigest()[:16]}"
        failure = None
        try:
            for event in _events(data):
                duration = event.get("DURATION")
                block = reduce_event(
                    event,
                    tz=tz,
                    owner_emails=owner_emails,
                    duration=None if duration is None else str(duration),
                )
                if block is Skip.NEGATIVE:
                    _LOG.warning("%s: ends before it starts, dropped", where)
                elif not isinstance(block, Skip):
                    blocks.append(block)
        except MalformedEventError as error:
            failure = str(error)  # this package's own texts, which quote no value
        if failure is not None:
            # Raised outside the except block, so no library exception stays attached.
            msg = f"{where}: {failure}"
            raise MalformedEventError(msg)
    return blocks


def _events(data: bytes | None) -> list[Component]:
    """The VEVENTs of one object, or MalformedEventError if any of them cannot be trusted."""
    if data is None:
        msg = "no calendar-data with status 200"
        raise MalformedEventError(msg)
    events = [component for component in _components(data) if component.name == "VEVENT"]
    if any(name in event for event in events for name in _UNEXPANDED):
        msg = "an instance is not expanded"
        raise MalformedEventError(msg)
    for event in events:
        for name in _TIMES:
            value = getattr(event.get(name), "dt", None)
            # Any IANA, Windows or vendor TZID resolves to zoneinfo. Only a zone the object
            # defines itself runs through dateutil, whose rules a hostile VTIMEZONE can make
            # spin for hours; it fails before reduce_event asks it for an offset.
            if isinstance(value, datetime) and not isinstance(value.tzinfo, ZoneInfo | None):
                msg = f"{name} has a TZID outside the IANA database"
                raise MalformedEventError(msg)
    return events


def _components(data: bytes) -> list[Component]:
    """Every component of one object, or MalformedEventError if icalendar reports any error."""
    components: list[Component] = []
    try:
        # Its warnings quote raw values, such as a TZID it had to guess.
        with warnings.catch_warnings(action="ignore"):
            # Bytes, never str: icalendar reads a str without a line break as a file path.
            components = _Calendar.from_ical(_FOLD.sub(b"", data)).walk()
    except Exception as error:
        # Untrusted input: icalendar fails with ValueError, TypeError, AttributeError,
        # AssertionError, OverflowError and OSError among others, and its messages quote
        # the value. Whatever the class, the object is unparsable (Q-14, PARSE-9).
        failure = f"unparsable ({type(error).__name__})"
    else:
        failure = ""
    finally:
        # icalendar keeps every zone an object defines in one cache for the whole process,
        # where the first definition of a TZID wins for every later object and run.
        tzp.use_zoneinfo()
    if failure:
        # Raised outside the except block, so the library's exception does not stay attached.
        raise MalformedEventError(failure)
    # In lenient mode icalendar keeps a broken value and only lists the error (Q-14).
    if any(component.errors for component in components):
        failure = "the parser reported an error"
    # "BEGIN:VEVENT " becomes a component named "VEVENT ", with no error listed.
    elif not all(_NAME.fullmatch(component.name or "") for component in components):
        failure = "a component name outside RFC 5545"
    if failure:
        raise MalformedEventError(failure)
    return components


class _Answer:
    """The expat handlers that collect each response's href and `calendar-data` as bytes.

    A response whose `calendar-data` is missing or comes with any status but 200 keeps
    `None` for it: such an object is not skipped but fails the read (PARSE-2).
    """

    def __init__(self, body: bytes, status: int) -> None:
        self.body = body
        self.status = status
        self.found: list[tuple[bytes, bytes | None]] = []
        self.path: list[str] = []
        self.chunks: list[str] | None = None
        self.href = b""
        self.data: bytes | None = None  # of the propstat being read
        self.state = b""  # the status line of the propstat being read
        self.kept: bytes | None = None  # the response's calendar-data from a 200 propstat

    def read(self) -> list[tuple[bytes, bytes | None]]:
        parser = expat.ParserCreate(encoding="ISO-8859-1", namespace_separator=" ")
        parser.StartDoctypeDeclHandler = self.declaration
        parser.EntityDeclHandler = self.declaration
        parser.StartElementHandler = self.start
        parser.CharacterDataHandler = self.text
        parser.EndElementHandler = self.end
        try:
            parser.ParseFile(BytesIO(self.body))
        except expat.ExpatError as error:
            reason = f"not well-formed XML ({expat.ErrorString(error.code)})"
        else:
            return self.found
        raise self.refused(reason)

    def refused(self, reason: str) -> ParseError:
        return ParseError(reason, status=self.status, size=len(self.body))

    def declaration(self, *_args: object) -> NoReturn:
        # Refused before any entity expands: a bomb, or one naming a local file (Q-14).
        msg = "a document type or entity declaration"
        raise self.refused(msg)

    def start(self, name: str, _attributes: dict[str, str]) -> None:
        if not self.path and name != _MULTISTATUS:
            # Any other XML holds no calendar-data and would read as an empty calendar.
            msg = "not a multistatus"
            raise self.refused(msg)
        self.path.append(name)
        if name == _DATA or self.path[-2:] in ([_RESPONSE, _HREF], [_PROPSTAT, _STATUS]):
            self.chunks = []

    def text(self, data: str) -> None:
        if self.chunks is not None:
            self.chunks.append(data)

    def end(self, name: str) -> None:
        self.path.pop()
        if name == _DATA:
            if self.data is not None:
                raise self.refused(_TWICE)
            self.data = self.captured()
        elif name == _HREF and self.path[-1:] == [_RESPONSE]:
            self.href = self.captured()
        elif name == _STATUS and self.path[-1:] == [_PROPSTAT]:
            self.state = self.captured()
        elif name == _PROPSTAT:
            if self.data is not None and _OK.match(self.state):
                if self.kept is not None:
                    raise self.refused(_TWICE)
                self.kept = self.data
            self.data, self.state = None, b""
        elif name == _RESPONSE:
            self.found.append((self.href, self.kept))
            self.href, self.kept = b"", None

    def captured(self) -> bytes:
        """The bytes of the element that just closed, as the server sent them."""
        text = "".join(self.chunks or ())
        self.chunks = None
        if max(text, default="") > "\xff":
            # A character reference such as &#8364; stands for no byte the server sent.
            msg = "a character reference beyond Latin-1"
            raise self.refused(msg)
        return text.encode("latin-1")
