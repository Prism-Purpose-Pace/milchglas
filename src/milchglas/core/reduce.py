"""Reduce one parsed VEVENT to a busy block, or to the reason it yields none (FR-4).

Only the span and the tentative flag leave this module: a block has no field that could
carry a title, a description, a location or an attendee. Errors carry the property name
only, never a value, because the library quotes raw values in its messages.
"""

from collections.abc import Collection
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from icalendar import Component

from milchglas.core.model import Block, DayBlock, TimedBlock


class Skip(Enum):
    """Why an event yields no block; carries no event content."""

    NOT_EVENT = "not-event"  # VTODO, VJOURNAL, VFREEBUSY (CORE-FIL-11)
    CANCELLED = "cancelled"  # STATUS:CANCELLED, any case (FR-3)
    TRANSPARENT = "transparent"  # TRANSP:TRANSPARENT (FR-3)
    DECLINED = "declined"  # every owner ATTENDEE entry has PARTSTAT=DECLINED (FR-3)
    EMPTY = "empty"  # zero length, decided before rounding (CORE-ZERO-1, RFC 5545 §3.6.1)
    NEGATIVE = "negative"  # ends before it starts: dropped, the caller warns


class MalformedEventError(ValueError):
    """The event's times cannot be read; the refresh fails and keeps the last feed (Q-14)."""


def reduce_event(
    event: Component,
    *,
    tz: ZoneInfo,
    owner_emails: Collection[str],
    keep_transparent_allday: bool = True,
) -> Block | Skip:
    """The busy block of `event`, or why it has none (FR-3, FR-4).

    `CLASS` is never read: redaction is Milchglas's job (D-3). The filters run before the
    times, so an event that cannot block anyway cannot fail a refresh either. Floating
    times are read in `tz`. OPEN Q-12 default: all-day events ignore TRANSP, because most
    clients write TRANSPARENT as their all-day default; `keep_transparent_allday=False`
    drops them like timed transparent events.
    """
    status = _text(event, "STATUS")
    replies = _owner_replies(event, {_address(email) for email in owner_emails})
    transparent = _text(event, "TRANSP") == "TRANSPARENT"
    skip = _excluded(
        event, status, replies, transparent=transparent and not keep_transparent_allday
    )
    if skip is not None:
        return skip
    block = _span(event, tz)
    if isinstance(block, Skip):
        return block
    if transparent and isinstance(block, TimedBlock):
        return Skip.TRANSPARENT
    # OPEN Q-11 default: the owner's own TENTATIVE reply counts like STATUS:TENTATIVE.
    tentative = status == "TENTATIVE" or "TENTATIVE" in replies
    return replace(block, tentative=True) if tentative else block


def _excluded(
    event: Component, status: str, replies: list[str], *, transparent: bool
) -> Skip | None:
    if event.name != "VEVENT":
        return Skip.NOT_EVENT
    if status == "CANCELLED":
        return Skip.CANCELLED
    # Declined under one address but not under another still means attending.
    if replies and all(reply == "DECLINED" for reply in replies):
        return Skip.DECLINED
    if transparent:
        return Skip.TRANSPARENT
    return None


def _span(event: Component, tz: ZoneInfo) -> Block | Skip:
    start = _read(event, "DTSTART")
    if isinstance(start, datetime):
        return _timed(event, _zoned(start, tz), tz)
    if isinstance(start, date):
        return _allday(event, start)
    msg = "DTSTART is missing or neither a date nor a date-time"
    raise MalformedEventError(msg)


def _timed(event: Component, start: datetime, tz: ZoneInfo) -> TimedBlock | Skip:
    end, duration = _read(event, "DTEND"), _read(event, "DURATION")
    if isinstance(end, datetime):
        stop = _zoned(end, tz)
    elif end is None and isinstance(duration, timedelta):
        stop = _after(start, duration, tz)
    elif end is None and duration is None:
        stop = start
    else:
        msg = "DTEND or DURATION does not fit a date-time DTSTART"
        raise MalformedEventError(msg)
    # Instants, not wall times: two datetimes of one tzinfo compare by wall clock, which
    # ignores the gap and the fold of a DST change (RFC 5545 §3.3.5).
    start, stop = start.astimezone(UTC), stop.astimezone(UTC)
    if stop == start:
        return Skip.EMPTY
    if stop < start:
        return Skip.NEGATIVE
    return TimedBlock(start, stop)


def _allday(event: Component, start: date) -> DayBlock | Skip:
    end, duration = _read(event, "DTEND"), _read(event, "DURATION")
    if isinstance(end, date) and not isinstance(end, datetime):
        stop = end
    elif end is None and isinstance(duration, timedelta) and not duration % timedelta(days=1):
        stop = start + duration
    elif end is None and duration is None:
        stop = start + timedelta(days=1)
    else:
        msg = "DTEND or DURATION does not fit a date DTSTART"
        raise MalformedEventError(msg)
    if stop == start:
        return Skip.EMPTY
    if stop < start:
        return Skip.NEGATIVE
    return DayBlock(start, stop)


def _text(event: Component, name: str) -> str:
    return str(event.get(name, "")).strip().upper()


def _owner_replies(event: Component, owners: set[str]) -> list[str]:
    """PARTSTAT of every ATTENDEE entry that is one of `owners` (NEEDS-ACTION if unset)."""
    attendees = event.get("ATTENDEE", [])
    if not isinstance(attendees, list):
        attendees = [attendees]
    return [
        str(attendee.params.get("PARTSTAT", "NEEDS-ACTION")).upper()
        for attendee in attendees
        if _address(str(attendee)) in owners
    ]


def _address(value: str) -> str:
    """`MAILTO:Owner@Example.ORG` and `owner@example.org` compare equal.

    Folding the whole address is pragmatic: RFC 5321 local parts are case-sensitive,
    but no mail provider in use treats them so.
    """
    value = value.strip()
    if value[:7].lower() == "mailto:":
        value = value[7:]
    return value.casefold()


def _read(event: Component, name: str) -> object:
    prop = event.get(name)
    if prop is None:
        return None
    try:
        return prop.dt
    except (AttributeError, ValueError):
        # The library's message quotes the raw value, which may be private text.
        msg = f"{name} is unreadable"
        raise MalformedEventError(msg) from None


def _zoned(value: datetime, tz: ZoneInfo) -> datetime:
    return value.replace(tzinfo=tz) if value.tzinfo is None else value


def _after(start: datetime, duration: timedelta, tz: ZoneInfo) -> datetime:
    """OPEN Q-20 default: days and weeks are nominal in `tz`, the rest is exact.

    RFC 5545 §3.3.6 counts a day as the same wall time next day. The server expands an
    instance to a UTC DTSTART and keeps DURATION, so the day is counted in the configured
    zone, not in UTC: P1D from 2026-10-24 07:00Z ends 08:00Z, 25 real hours (CORE-DUR-6).

    shortcut: timedelta stores PT24H as one day, so a PT24H instance also counts as
    nominal and over-blocks by one hour on a DST change day; reading the raw DURATION
    text in the source layer would tell the two apart.
    """
    days = timedelta(days=duration.days)
    return (start.astimezone(tz) + days).astimezone(UTC) + (duration - days)
