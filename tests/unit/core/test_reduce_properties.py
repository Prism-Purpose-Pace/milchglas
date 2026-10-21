"""The error contract of `reduce_event` over generated events (Q-14).

A caller handles an event it cannot read by catching `MalformedEventError` and keeping the
last feed. Any other exception from `reduce_event` would end the refresh loop instead, so
the only outcomes allowed are a block, a skip reason, or that one error.

The second property (PROP-14) holds the end of a DURATION event to an RFC 5545 reading
written out again in the test, over the 2026 offset changes of every zone the tz database
has.
"""

import zoneinfo
from bisect import bisect_left
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from functools import cache, partial
from zoneinfo import ZoneInfo

import pytest
from hypothesis import assume, example, find, given, settings
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


# --- the end of a DURATION event beside an offset change (PROP-14) -------------------------

_YEAR = datetime(2026, 1, 1, tzinfo=UTC)
type _Case = tuple[str, datetime, int, int, int, str]  # zone, start, weeks, days, minutes, text


@cache
def _changes_2026(zone: str) -> tuple[datetime, ...]:
    """The UTC instants, to the minute, at which `zone` takes a new offset in 2026.

    A daily scan, then bisection on the minute; shortcut: two changes inside one day would
    go unseen, and the tz database has none in 2026.
    """
    info = ZoneInfo(zone)
    found: list[datetime] = []
    before = _YEAR.astimezone(info).utcoffset()
    for day in range(1, 366):
        high = _YEAR + timedelta(days=day)
        if high.astimezone(info).utcoffset() == before:
            continue
        low = high - timedelta(days=1)
        minute = bisect_left(
            range(24 * 60 + 1),
            x=True,
            key=lambda m: (low + timedelta(minutes=m)).astimezone(info).utcoffset() != before,
        )
        found.append(low + timedelta(minutes=minute))
        before = high.astimezone(info).utcoffset()
    return tuple(found)


@st.composite
def _cases(draw: st.DrawFn) -> _Case:
    """A zone, a UTC start, and a DURATION; a start or a day-part end lies near a 2026 change.

    The start lies within three hours of one of the zone's changes. For half of the cases
    with a day part the nominal end does instead, which is the only way it reaches a gap or
    a fold: the zone's 2026 changes are at least 35 days apart and a day part is at most
    nine days.
    """
    zone = draw(st.sampled_from(ZONES))
    changes = _changes_2026(zone)
    # A zone without a change in 2026 still gets a start: the plain path must stay right.
    anchor = (
        draw(st.sampled_from(changes))
        if changes
        else _YEAR + timedelta(minutes=draw(st.integers(0, 365 * 24 * 60)))
    )
    # Half the cases have no day or week part: that is the path the fold broke.
    weeks, days = draw(st.just((0, 0)) | st.tuples(st.integers(0, 1), st.integers(0, 2)))
    nominal = timedelta(days=7 * weeks + days)
    if nominal and draw(st.booleans()):
        anchor -= nominal  # the start is as many days before the change as the part counts
    start = anchor + timedelta(minutes=draw(st.integers(-180, 180)))
    minutes = draw(st.integers(0, 240))
    zero_days = draw(st.booleans())  # `P0DT30M` as well as `PT30M`
    date_part = (f"{weeks}W" if weeks else "") + (
        f"{days}D" if days or (zero_days and not weeks) else ""
    )
    time_part = ""
    if minutes or not date_part:
        time_part = draw(st.sampled_from([f"T{minutes}M", f"T{minutes // 60}H{minutes % 60}M"]))
    return zone, start, weeks, days, minutes, f"P{date_part}{time_part}"


def _wall_end(case: _Case) -> datetime | None:
    """The local wall time after the day and week parts, or None without them (§3.3.6)."""
    zone, start, weeks, days, _, _ = case
    if weeks == 0 and days == 0:
        return None
    return start.astimezone(ZoneInfo(zone)).replace(tzinfo=None) + timedelta(days=7 * weeks + days)


def _rfc_interval(case: _Case) -> tuple[datetime, datetime] | None:
    """RFC 5545 §3.3.6 and §3.3.5, from the case alone: no milchglas name is used."""
    zone, start, _, _, minutes, _ = case
    exact = timedelta(minutes=minutes)
    wall = _wall_end(case)
    if wall is None:
        end = start + exact  # no nominal part: the UTC instant plus real time
    else:
        # An ambiguous or missing wall time reads as the first pass, the offset before a gap.
        end = wall.replace(tzinfo=ZoneInfo(zone), fold=0).astimezone(UTC) + exact
    return None if end == start else (start, end)


@given(_cases())
@example(("Europe/Berlin", datetime(2026, 10, 25, 1, 10, tzinfo=UTC), 0, 0, 30, "PT30M"))
@example(("Europe/Berlin", datetime(2026, 10, 25, 1, 30, tzinfo=UTC), 0, 0, 60, "PT1H"))
@example(("Australia/Lord_Howe", datetime(2026, 4, 4, 15, 10, tzinfo=UTC), 0, 0, 10, "PT10M"))
@example(("Europe/Berlin", datetime(2026, 10, 25, 1, 10, tzinfo=UTC), 0, 1, 30, "P1DT30M"))
# The day-part end in the spring gap (01:30Z is 02:30 CET, the next 02:30 does not exist), the
# exact part across the change after a day part, and a gap that opens at midnight.
@example(("Europe/Berlin", datetime(2026, 3, 28, 1, 30, tzinfo=UTC), 0, 1, 0, "P1D"))
@example(("Europe/Berlin", datetime(2026, 3, 28, 0, 30, tzinfo=UTC), 0, 1, 120, "P1DT2H"))
@example(("Africa/Cairo", datetime(2026, 4, 22, 22, 0, tzinfo=UTC), 0, 1, 0, "P1D"))
def test_reduce_end_follows_rfc_beside_an_offset_change_prop_14(case: _Case) -> None:
    zone, start, _, _, _, text = case
    ics = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "BEGIN:VEVENT",
            "UID:generated",
            f"DTSTART:{start:%Y%m%dT%H%M%SZ}",
            f"DURATION:{text}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    got = _reduce((ics, text), zone)
    want = _rfc_interval(case)
    if want is None:
        assert got is Skip.EMPTY
    else:
        assert isinstance(got, TimedBlock)
        assert (got.start, got.end) == want


def _starts_in_a_fold_second_pass_with_exact_time_only(case: _Case) -> bool:
    zone, start, weeks, days, minutes, _ = case
    return start.astimezone(ZoneInfo(zone)).fold == 1 and weeks == days == 0 and minutes > 0


def _readings(case: _Case) -> tuple[datetime, datetime] | None:
    """The day-part end read as `fold=0` and as `fold=1`: they differ in a gap or a fold."""
    wall = _wall_end(case)
    if wall is None:
        return None
    info = ZoneInfo(case[0])
    first, second = (wall.replace(tzinfo=info, fold=fold).astimezone(UTC) for fold in (0, 1))
    return first, second


def _day_part_end_in_a_fold(case: _Case) -> bool:
    readings = _readings(case)
    return readings is not None and readings[0] < readings[1]


def _day_part_end_in_a_gap(case: _Case) -> bool:
    readings = _readings(case)
    return readings is not None and readings[0] > readings[1]


def _exact_part_crosses_a_change_after_a_day_part(case: _Case) -> bool:
    readings = _readings(case)
    if readings is None:
        return False
    info = ZoneInfo(case[0])
    nominal = readings[0]
    after = nominal + timedelta(minutes=case[4])
    return nominal.astimezone(info).utcoffset() != after.astimezone(info).utcoffset()


@pytest.mark.parametrize(
    "reached",
    [
        _starts_in_a_fold_second_pass_with_exact_time_only,
        _day_part_end_in_a_fold,
        _day_part_end_in_a_gap,
        _exact_part_crosses_a_change_after_a_day_part,
    ],
)
def test_generated_cases_reach_the_edges_of_an_offset_change_prop_14(
    reached: Callable[[_Case], bool],
) -> None:
    # Without this the property above could hold only because the search never gets there.
    # A day-part end in a fold is 3 draws in 1000: 20000 draws leave a miss at e**-60.
    find(_cases(), reached, settings=settings(max_examples=20000))
