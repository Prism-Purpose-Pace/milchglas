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
from typing import ClassVar, override
from xml.parsers import expat
from zoneinfo import ZoneInfo

from icalendar import Calendar, vText
from icalendar.prop.factory import TypesFactory

from milchglas.core.model import Block
from milchglas.core.reduce import Skip, reduce_event

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


def parse(body: bytes, *, tz: ZoneInfo, owner_emails: Collection[str]) -> list[Block]:
    """The busy blocks of every object in one calendar's multistatus `body`."""
    blocks: list[Block] = []
    for data in _calendar_data(body):
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


def _calendar_data(body: bytes) -> list[bytes]:
    """The bytes of every `calendar-data` element, as the server sent them."""
    parser = expat.ParserCreate(encoding="ISO-8859-1", namespace_separator=" ")
    found: list[bytes] = []
    chunks: list[str] | None = None

    def start(name: str, _attributes: dict[str, str]) -> None:
        nonlocal chunks
        if name == _DATA:
            chunks = []

    def text(data: str) -> None:
        if chunks is not None:
            chunks.append(data)

    def end(name: str) -> None:
        nonlocal chunks
        if name == _DATA and chunks is not None:
            found.append("".join(chunks).encode("latin-1"))
            chunks = None

    parser.StartElementHandler = start
    parser.CharacterDataHandler = text
    parser.EndElementHandler = end
    parser.ParseFile(BytesIO(body))
    return found
