"""Reduce one parsed VEVENT to a busy block, or to the reason it yields none (FR-4).

Only the span and the tentative flag leave this module: a block has no field that could
carry a title, a description, a location or an attendee. Errors carry the property name
only, never a value, because the library quotes raw values in its messages.
"""

import re
from collections.abc import Collection
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, tzinfo
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


# RFC 5545 §3.3.6 dur-value; weeks and days may precede a time part, as producers write them.
_DURATION = re.compile(
    r"(?P<sign>[+-])?P(?:(?P<w>[0-9]{1,9})W)?(?:(?P<d>[0-9]{1,9})D)?"
    r"(?:T(?=[0-9])(?:(?P<h>[0-9]{1,9})H)?(?:(?P<m>[0-9]{1,9})M)?(?:(?P<s>[0-9]{1,9})S)?)?"
)
type _Duration = tuple[int, timedelta]  # nominal days, exact time; both carry the sign


def reduce_event(
    event: Component,
    *,
    tz: ZoneInfo,
    owner_emails: Collection[str],
    duration: str | None,
) -> Block | Skip:
    """The busy block of `event`, or why it has none (FR-3, FR-4).

    `CLASS` is never read: redaction is Milchglas's job (D-3). The filters run before the
    times, so an event that cannot block anyway cannot fail a refresh either. Floating
    times are read in `tz`. OPEN Q-12 default: all-day events ignore TRANSP, because most
    clients write TRANSPARENT as their all-day default; only timed events are dropped.

    `duration` is the raw text of the DURATION property, `None` if the event has none.
    icalendar hands DURATION over as a timedelta, which loses what RFC 5545 §3.3.6
    distinguishes: PT24H and P1D are one day to it, and a minus sign is folded into the
    day count. So the source layer passes the text and `_parse_duration` reads it.
    """
    status = _text(event, "STATUS")
    replies = _owner_replies(event, {_address(email) for email in owner_emails})
    transparent = _text(event, "TRANSP") == "TRANSPARENT"
    skip = _excluded(event, status, replies)
    if skip is not None:
        return skip
    block = _span(event, tz, duration)
    if isinstance(block, Skip):
        return block
    if transparent and isinstance(block, TimedBlock):
        return Skip.TRANSPARENT
    # OPEN Q-11 default: the owner's own TENTATIVE reply counts like STATUS:TENTATIVE.
    tentative = status == "TENTATIVE" or "TENTATIVE" in replies
    return replace(block, tentative=True) if tentative else block


def _excluded(event: Component, status: str, replies: list[str]) -> Skip | None:
    if event.name != "VEVENT":
        return Skip.NOT_EVENT
    if status == "CANCELLED":
        return Skip.CANCELLED
    # Declined under one address but not under another still means attending.
    if replies and all(reply == "DECLINED" for reply in replies):
        return Skip.DECLINED
    return None


def _span(event: Component, tz: ZoneInfo, text: str | None) -> Block | Skip:
    if text is None and "DURATION" in event:
        # Treating it as absent would read the event as zero length: a false free slot.
        msg = "DURATION text was not handed over"
        raise MalformedEventError(msg)
    duration = None if text is None else _parse_duration(text)
    start = _read(event, "DTSTART")
    try:
        if isinstance(start, datetime):
            return _timed(event, _zoned(start, tz), tz, duration)
        if isinstance(start, date):
            return _allday(event, start, duration)
    except OverflowError:
        # Dates near year 1 or 9999, or a huge duration; the message would hold no content.
        msg = "a time is out of range"
        raise MalformedEventError(msg) from None
    msg = "DTSTART is missing or neither a date nor a date-time"
    raise MalformedEventError(msg)


def _timed(
    event: Component, start: datetime, tz: ZoneInfo, duration: _Duration | None
) -> TimedBlock | Skip:
    end = _read(event, "DTEND")
    ends: list[datetime] = []
    if isinstance(end, datetime):
        ends.append(_zoned(end, tz))
    elif end is not None:
        msg = "DTEND or DURATION does not fit a date-time DTSTART"
        raise MalformedEventError(msg)
    if duration is not None:
        # RFC 5545 §3.3.6: the days of a DURATION count in the zone the event was written
        # in. A UTC or floating start has none, so `tz` stands in for it (OPEN Q-20).
        own = start.tzinfo if "TZID" in event["DTSTART"].params else None
        ends.append(_after(start, duration, own or tz))
    # Instants, not wall times: two datetimes of one tzinfo compare by wall clock, which
    # ignores the gap and the fold of a DST change (RFC 5545 §3.3.5). DTEND and DURATION
    # together are invalid (§3.6.1); the later end errs towards busy, never free (G5).
    begin = start.astimezone(UTC)
    stop = max((moment.astimezone(UTC) for moment in ends), default=begin)
    if stop == begin:
        return Skip.EMPTY
    if stop < begin:
        return Skip.NEGATIVE
    return TimedBlock(begin, stop)


def _allday(event: Component, start: date, duration: _Duration | None) -> DayBlock | Skip:
    end = _read(event, "DTEND")
    ends: list[date] = []
    if isinstance(end, date) and not isinstance(end, datetime):
        ends.append(end)
    elif end is not None:
        msg = "DTEND or DURATION does not fit a date DTSTART"
        raise MalformedEventError(msg)
    if duration is not None:
        days, exact = duration
        if exact % timedelta(days=1):
            msg = "DTEND or DURATION does not fit a date DTSTART"
            raise MalformedEventError(msg)
        ends.append(start + timedelta(days=days) + exact)
    stop = max(ends, default=start + timedelta(days=1))
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
        value = prop.dt
    except (AttributeError, ValueError):
        # The library's message quotes the raw value, which may be private text.
        msg = f"{name} is unreadable"
        raise MalformedEventError(msg) from None
    if isinstance(value, datetime) and value.tzinfo is None and "TZID" in prop.params:
        # An unresolvable TZID comes back naive and without an error; reading it as
        # floating time in `tz` would shift the event by the zone difference, unannounced.
        msg = f"{name} has an unknown TZID"
        raise MalformedEventError(msg)
    return value


def _zoned(value: datetime, tz: ZoneInfo) -> datetime:
    return value.replace(tzinfo=tz) if value.tzinfo is None else value


def _parse_duration(text: str) -> _Duration:
    """RFC 5545 §3.3.6: weeks and days are nominal, hours to seconds are exact."""
    match = _DURATION.fullmatch(text.strip())
    if match is None or not any(match.group("w", "d", "h", "m", "s")):
        msg = "DURATION is unreadable"  # never the text: it may be private
        raise MalformedEventError(msg)
    weeks, days, hours, minutes, seconds = (
        int(g or 0) for g in match.group("w", "d", "h", "m", "s")
    )
    sign = -1 if match["sign"] == "-" else 1
    return sign * (7 * weeks + days), sign * timedelta(
        hours=hours, minutes=minutes, seconds=seconds
    )


def _after(start: datetime, duration: _Duration, zone: tzinfo) -> datetime:
    """OPEN Q-20 default: days and weeks are nominal in `zone`, the rest is exact.

    RFC 5545 §3.3.6 counts a day as the same wall time next day, in the zone of DTSTART.
    The server expands an instance to a UTC DTSTART and keeps DURATION, so for those the
    caller passes the configured zone, not UTC: P1D from 2026-10-24 07:00Z ends 08:00Z,
    25 real hours (CORE-DUR-6). PT24H has no day part and stays 24 real hours.
    """
    days, exact = duration
    return (start.astimezone(zone) + timedelta(days=days)).astimezone(UTC) + exact
