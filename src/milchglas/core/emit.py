"""Serialise merged busy blocks into the published RFC 5545 feed (FR-7, D-8, NFR-P3).

Hand-rolled on purpose: the property whitelist holds by construction, and byte identity
must not hinge on a library's serialisation order or version (icalendar is the oracle in
the tests, never the emitter). The configured summary is the only free text that reaches
the feed, so it is escaped as TEXT and refused if it holds a line break.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime

from milchglas.core.model import Block, DayBlock

CALNAME = "Privat (busy)"
_LIMIT = 75  # octets per line, CRLF excluded (RFC 5545 §3.1)
# RFC 5545 §3.3.11 TEXT allows no control character but TAB; U+2028/U+2029 are refused
# too, because some readers (Python's str.splitlines among them) break lines there. A
# lone surrogate has no UTF-8 form: refused here, not as an encoding error later.
_UNSAFE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029\ud800-\udfff]")
# A TEXT escape (backslash + character) is never split across a fold.
_UNIT = re.compile(r"\\.|.", re.DOTALL)


def uid(salt: str, block: Block) -> str:
    """`sha256(salt|start|end)[:32]@milchglas`: stable while the span is (V-7)."""
    digest = hashlib.sha256(f"{salt}|{_value(block.start)}|{_value(block.end)}".encode())
    return f"{digest.hexdigest()[:32]}@milchglas"


def emit(
    blocks: Iterable[Block],
    *,
    summary: str,
    salt: str,
    ttl_seconds: int,
    version: str,
    now: datetime,
    dtstamps: Mapping[str, datetime],
) -> bytes:
    """The feed for `blocks`, canonical bytes for canonical input.

    `blocks` come from `merge`, which owns the order (day blocks first, then timed, each
    by start); they are written as given.

    `dtstamps` maps UIDs of the previous feed to their DTSTAMP: a block that is still
    there keeps it, a new block gets `now`, so DTSTAMP is the last content change (D-7c).
    """
    if _UNSAFE.search(summary):
        msg = "summary must not contain line breaks or control characters"
        raise ValueError(msg)
    ttl = _duration(ttl_seconds)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Milchglas//{version}//DE",
        # No METHOD (D-8): without it RFC 5545 §3.8.7.2 reads DTSTAMP as the last
        # revision of the component, which is what D-7c keeps.
        f"X-WR-CALNAME:{CALNAME}",
        f"REFRESH-INTERVAL;VALUE=DURATION:{ttl}",
        f"X-PUBLISHED-TTL:{ttl}",
    ]
    text = _escape(summary)
    for block in blocks:
        key = uid(salt, block)
        kind = ";VALUE=DATE" if isinstance(block, DayBlock) else ""
        lines += [
            "BEGIN:VEVENT",
            f"UID:{key}",
            f"DTSTAMP:{_value(dtstamps.get(key, now))}",
            f"DTSTART{kind}:{_value(block.start)}",
            f"DTEND{kind}:{_value(block.end)}",
            f"SUMMARY:{text}",
            "TRANSP:OPAQUE",
            # FR-14 MVP: tentative blocks are plain busy.
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(f"{_fold(line)}\r\n" for line in lines).encode()


def _value(moment: date) -> str:
    """DATE as `20261003`, DATE-TIME as UTC `20261003T070000Z` (seconds truncated)."""
    if not isinstance(moment, datetime):
        return moment.strftime("%Y%m%d")
    if moment.utcoffset() is None:
        msg = "instants must be timezone-aware"
        raise ValueError(msg)
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _duration(seconds: int) -> str:
    if seconds < 1:
        msg = "ttl_seconds must be positive"
        raise ValueError(msg)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    # RFC 5545 §3.3.6: seconds follow hours only through a minutes part (`PT1H0M5S`).
    return "PT" + "".join(
        [
            f"{hours}H" if hours else "",
            f"{minutes}M" if minutes or (hours and secs) else "",
            f"{secs}S" if secs else "",
        ]
    )


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def _fold(line: str) -> str:
    """Fold at 75 octets; continuation lines start with one space (RFC 5545 §3.1)."""
    parts, current, size = [], "", 0
    for unit in _UNIT.findall(line):
        width = len(unit.encode())
        if size + width > _LIMIT:
            parts.append(current)
            current, size = " ", 1
        current += unit
        size += width
    parts.append(current)
    return "\r\n".join(parts)
