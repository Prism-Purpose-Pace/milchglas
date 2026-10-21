"""The error contract of `reduce_event` over generated events (Q-14).

A caller handles an event it cannot read by catching `MalformedEventError` and keeping the
last feed. Any other exception from `reduce_event` would end the refresh loop instead, so
the only outcomes allowed are a block, a skip reason, or that one error.
"""

import zoneinfo
from datetime import date, time
from functools import partial
from zoneinfo import ZoneInfo

from hypothesis import assume, find, given
from hypothesis import strategies as st
from icalendar import Calendar

from milchglas.core.model import DayBlock, TimedBlock
from milchglas.core.reduce import MalformedEventError, Skip, reduce_event

ZONES = sorted(zoneinfo.available_timezones())
# Every zone the tz database has, and one that icalendar cannot resolve.
TZIDS = st.sampled_from([*ZONES, "Mars/Olympus"])

_STAMPS = st.one_of(
    # Anywhere in the range datetime supports, so the arithmetic can run off either end.
    st.tuples(st.dates(), st.times()),
    # Around both Berlin DST changes of 2026: the gap and the fold.
    st.tuples(st.sampled_from([date(2026, 3, 29), date(2026, 10, 25)]), st.times(time(1), time(4))),
)


def _stamp(day: date, clock: time) -> str:
    return f"{day.year:04d}{day:%m%d}T{clock:%H%M%S}"


@st.composite
def _values(draw: st.DrawFn) -> str:
    """What follows the property name of a DTSTART or DTEND line."""
    moment = _stamp(*draw(_STAMPS))
    kind = draw(st.sampled_from(["floating", "utc", "zoned", "date", "garbage"]))
    return {
        "floating": f":{moment}",
        "utc": f":{moment}Z",
        "zoned": f";TZID={draw(TZIDS)}:{moment}",
        "date": f";VALUE=DATE:{moment[:8]}",
        "garbage": ":BBY-garbage",
    }[kind]


_COUNT = st.one_of(st.integers(0, 3), st.integers(0, 10**9 - 1), st.just(999999))


@st.composite
def _durations(draw: st.DrawFn) -> str:
    """A DURATION text: mostly well-formed, sometimes close to the grammar, sometimes not."""
    if draw(st.integers(0, 5)) == 0:
        return draw(st.text("PTWDHMS+-.0123456789", max_size=12))
    parts = [draw(st.none() | _COUNT) for _ in range(5)]
    sign = draw(st.sampled_from(["", "+", "-"]))
    weeks, days, hours, minutes, seconds = parts
    date_part = (f"{weeks}W" if weeks is not None else "") + (
        f"{days}D" if days is not None else ""
    )
    time_part = "".join(
        f"{n}{unit}" for n, unit in ((hours, "H"), (minutes, "M"), (seconds, "S")) if n is not None
    )
    return f"{sign}P{date_part}" + (f"T{time_part}" if time_part else "")


@st.composite
def events(draw: st.DrawFn) -> tuple[str, str | None]:
    """An iCalendar object with one VEVENT, and the raw text of its DURATION."""
    duration = draw(st.none() | _durations())
    lines = ["BEGIN:VCALENDAR", "BEGIN:VEVENT", "UID:generated"]
    if draw(st.integers(0, 9)):  # one in ten has no DTSTART
        lines.append("DTSTART" + draw(_values()))
    if draw(st.booleans()):
        lines.append("DTEND" + draw(_values()))
    if duration is not None:
        lines.append(f"DURATION:{duration}")
    lines += ["END:VEVENT", "END:VCALENDAR", ""]
    return "\r\n".join(lines), duration


def _reduce(drawn: tuple[str, str | None], zone: str) -> object:
    ics, duration = drawn
    try:
        [event] = Calendar.from_ical(ics).subcomponents
    except (ValueError, OverflowError):
        # icalendar refuses the object before core sees it (a DURATION beyond timedelta).
        assume(condition=False)
    try:
        return reduce_event(event, tz=ZoneInfo(zone), owner_emails=(), duration=duration)
    except MalformedEventError as error:
        return error


@given(events(), st.sampled_from(ZONES))
def test_reduce_returns_a_block_or_a_skip_or_raises_malformed_prop_13(
    drawn: tuple[str, str | None], zone: str
) -> None:
    # Any other exception propagates out of `_reduce` and fails the test.
    assert isinstance(_reduce(drawn, zone), TimedBlock | DayBlock | Skip | MalformedEventError)


def _is(kind: type, drawn: tuple[tuple[str, str | None], str]) -> bool:
    return isinstance(_reduce(*drawn), kind)


def test_generated_events_reach_every_kind_of_outcome_prop_13() -> None:
    # Without this the property above could hold only because nothing ever succeeds.
    for kind in (TimedBlock, DayBlock, Skip, MalformedEventError):
        find(st.tuples(events(), st.sampled_from(ZONES)), partial(_is, kind))
