"""Read a CalDAV multistatus answer into busy blocks (FR-2, FR-4).

Each event is reduced at once; nothing here keeps event text. The answer is read byte
for byte: a content line folded at 75 octets can split a UTF-8 character, which leaves
the XML itself invalid UTF-8. So expat decodes it as Latin-1, which maps every byte to
one character, and each object is unfolded on its bytes before icalendar decodes it
(RFC 5545 section 3.1, NFR-C1).
"""

import re
from collections.abc import Collection
from io import BytesIO
from typing import ClassVar, NoReturn, override
from xml.parsers import expat
from zoneinfo import ZoneInfo

from icalendar import Calendar, vText
from icalendar.prop.factory import TypesFactory

from milchglas.core.model import Block
from milchglas.core.reduce import Skip, reduce_event

_MULTISTATUS = "DAV: multistatus"
_DATA = "urn:ietf:params:xml:ns:caldav calendar-data"
# A line break followed by one space or tab continues the line (RFC 5545 section 3.1);
# sabre writes CRLF in expanded answers and LF in unexpanded ones (NFR-C1).
_FOLD = re.compile(rb"\r?\n[ \t]")


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


def parse(body: bytes, *, status: int, tz: ZoneInfo, owner_emails: Collection[str]) -> list[Block]:
    """The busy blocks of every object in one calendar's multistatus `body`."""
    blocks: list[Block] = []
    for data in _Answer(body, status).read():
        # Bytes, never str: icalendar reads a str without a line break as a file path.
        for event in _Calendar.from_ical(_FOLD.sub(b"", data)).walk("VEVENT"):
            duration = event.get("DURATION")
            block = reduce_event(
                event,
                tz=tz,
                owner_emails=owner_emails,
                duration=None if duration is None else str(duration),
            )
            if not isinstance(block, Skip):
                blocks.append(block)
    return blocks


class _Answer:
    """The expat handlers that collect every `calendar-data` of a multistatus as bytes."""

    def __init__(self, body: bytes, status: int) -> None:
        self.body = body
        self.status = status
        self.found: list[bytes] = []
        self.chunks: list[str] | None = None
        self.rooted = False

    def read(self) -> list[bytes]:
        parser = expat.ParserCreate(encoding="ISO-8859-1", namespace_separator=" ")
        parser.StartDoctypeDeclHandler = self.declaration
        parser.EntityDeclHandler = self.declaration
        parser.StartElementHandler = self.start
        parser.CharacterDataHandler = self.text
        parser.EndElementHandler = self.end
        try:
            parser.ParseFile(BytesIO(self.body))
        except expat.ExpatError as error:
            msg = f"not well-formed XML ({expat.ErrorString(error.code)})"
            raise self.refused(msg) from None
        return self.found

    def refused(self, reason: str) -> ParseError:
        return ParseError(reason, status=self.status, size=len(self.body))

    def declaration(self, *_args: object) -> NoReturn:
        # Refused before any entity expands: a bomb, or one naming a local file (Q-14).
        msg = "a document type or entity declaration"
        raise self.refused(msg)

    def start(self, name: str, _attributes: dict[str, str]) -> None:
        if not self.rooted and name != _MULTISTATUS:
            # Any other XML holds no calendar-data and would read as an empty calendar.
            msg = "not a multistatus"
            raise self.refused(msg)
        self.rooted = True
        if name == _DATA:
            self.chunks = []

    def text(self, data: str) -> None:
        if self.chunks is not None:
            self.chunks.append(data)

    def end(self, name: str) -> None:
        if name == _DATA and self.chunks is not None:
            self.found.append("".join(self.chunks).encode("latin-1"))
            self.chunks = None
