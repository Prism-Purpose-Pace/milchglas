"""Reduce one parsed VEVENT to a busy block, or to the reason it yields none (FR-4).

Only the span and the tentative flag leave this module: a block has no field that could
carry a title, a description, a location or an attendee. Errors carry the property name
only, never a value, because the library quotes raw values in its messages.
"""

from datetime import UTC, date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from icalendar import Component

from milchglas.core.model import Block, DayBlock, TimedBlock


class Skip(Enum):
    """Why an event yields no block; carries no event content."""

    EMPTY = "empty"  # zero length, decided before rounding (CORE-ZERO-1, RFC 5545 §3.6.1)
    NEGATIVE = "negative"  # ends before it starts: dropped, the caller warns


class MalformedEventError(ValueError):
    """The event's times cannot be read; the refresh fails and keeps the last feed (Q-14)."""


def reduce_event(event: Component, *, tz: ZoneInfo) -> Block | Skip:
    """The busy block of `event`; floating times are read in `tz`."""
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
        stop = _after(start, duration)
    elif end is None and duration is None:
        stop = start
    else:
        msg = "DTEND or DURATION does not fit a date-time DTSTART"
        raise MalformedEventError(msg)
    if stop == start:
        return Skip.EMPTY
    if stop < start:
        return Skip.NEGATIVE
    return TimedBlock(start.astimezone(UTC), stop.astimezone(UTC))


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


def _after(start: datetime, duration: timedelta) -> datetime:
    """RFC 5545 §3.3.6: whole days are nominal (same wall time), the rest is exact.

    shortcut: timedelta stores PT24H as one day, so PT24H counts as nominal; it differs
    only for a zoned DTSTART across a DST change, the local-expansion path (CORE-DUR-4).
    """
    days = timedelta(days=duration.days)
    return (start + days).astimezone(UTC) + (duration - days)
