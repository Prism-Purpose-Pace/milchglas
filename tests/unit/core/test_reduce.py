"""Golden cases for reducing one VEVENT to a busy block (spec FR-3, FR-4).

Fixtures: tests/fixtures/objects/*.ics, one VEVENT per catalogue case, looked up by UID.
"""

from collections.abc import Collection
from dataclasses import fields

import pytest
from icalendar import Component

from milchglas.core.model import Block, DayBlock, TimedBlock
from milchglas.core.reduce import MalformedEventError, Skip, reduce_event
from tests.support.blocks import BERLIN, day, timed
from tests.support.ical import OBJECTS, component, components, duration_text

TIMES = "core-times.ics"
FILTER = "core-filter.ics"
# Configured spelling differs in case from the fixtures on purpose.
OWNERS = ("OWNER@example.org", "owner.private@example.org")


def _reduce(name: str, uid: str) -> Block | Skip:
    return _reduce_event(name, component(name, uid))


def _reduce_event(
    name: str,
    event: Component,
    owner_emails: Collection[str] = OWNERS,
    *,
    keep_transparent_allday: bool = True,
) -> Block | Skip:
    return reduce_event(
        event,
        tz=BERLIN,
        owner_emails=owner_emails,
        duration=duration_text(name, event),
        keep_transparent_allday=keep_transparent_allday,
    )


# --- filter (CORE-FIL, FR-3, D-3) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("uid", "expected"),
    [
        ("CORE-FIL-1", Skip.CANCELLED),
        ("CORE-FIL-2", Skip.CANCELLED),
        ("CORE-FIL-3-transparent", Skip.TRANSPARENT),
        ("CORE-FIL-4-upper", Skip.DECLINED),
        ("CORE-FIL-4-lower", Skip.DECLINED),
        ("CORE-FIL-4-second-address", Skip.DECLINED),
        ("CORE-FIL-11-todo", Skip.NOT_EVENT),
        ("CORE-FIL-11-journal", Skip.NOT_EVENT),
        ("CORE-FIL-11-freebusy", Skip.NOT_EVENT),
        # Filters run before the times are read: a cancelled event cannot fail a refresh.
        ("cancelled-with-broken-start", Skip.CANCELLED),
    ],
)
def test_excluded_events_yield_their_skip_reason(uid: str, expected: Skip) -> None:
    assert _reduce(FILTER, uid) is expected


@pytest.mark.parametrize(
    ("uid", "expected"),
    [
        ("CORE-FIL-3-absent", timed("2026-10-02T08:00Z", "2026-10-02T09:00Z")),
        ("CORE-FIL-3-opaque", timed("2026-10-02T08:00Z", "2026-10-02T09:00Z")),
        ("CORE-FIL-5", timed("2026-10-05T08:00Z", "2026-10-05T09:00Z")),
        ("CORE-FIL-6", timed("2026-10-05T08:00Z", "2026-10-05T09:00Z")),
        ("CORE-FIL-7", timed("2026-10-05T08:00Z", "2026-10-05T09:00Z")),
        # OPEN Q-19 default: an unanswered invitation blocks; a block too many costs
        # a slot, a block too few a double booking.
        ("CORE-FIL-7-needs-action", timed("2026-10-05T08:00Z", "2026-10-05T09:00Z")),
        # Declined under one address, accepted under the other: still attending.
        ("owner-twice-one-accepted", timed("2026-10-05T08:00Z", "2026-10-05T09:00Z")),
        # D-3: redaction is Milchglas's job, so CLASS never hides a block.
        ("CORE-FIL-8-private", timed("2026-10-06T06:00Z", "2026-10-06T07:00Z")),
        ("CORE-FIL-8-confidential", timed("2026-10-06T06:00Z", "2026-10-06T07:00Z")),
        # D-3: what a read-only sharee receives of a CONFIDENTIAL event (SUMMARY rewritten,
        # no STATUS, TRANSP or ATTENDEE) still blocks; it can never be excluded.
        ("confidential-as-sharee", timed("2026-10-06T10:00Z", "2026-10-06T10:30Z")),
        ("CORE-FIL-9", timed("2026-10-02T13:00Z", "2026-10-02T14:00Z", tentative=True)),
        # OPEN Q-11 default: the owner's own TENTATIVE reply marks the block tentative.
        ("CORE-FIL-10", timed("2026-10-02T13:00Z", "2026-10-02T14:00Z", tentative=True)),
        # OPEN Q-12 default: all-day events ignore TRANSP, so a Thunderbird all-day
        # event, written TRANSPARENT by default, still blocks (allday_mode busy).
        ("CORE-FIL-12", day("2026-10-13", "2026-10-14")),
    ],
)
def test_busy_events_yield_a_block(uid: str, expected: Block) -> None:
    assert _reduce(FILTER, uid) == expected


def test_transparent_all_day_events_can_be_dropped_open_q_12() -> None:
    # The switch restores the RFC-literal reading for all-day events; timed transparent
    # events are dropped either way (FR-3).
    for uid in ("CORE-FIL-12", "CORE-FIL-3-transparent"):
        event = component(FILTER, uid)
        assert _reduce_event(FILTER, event, keep_transparent_allday=False) is Skip.TRANSPARENT


def test_declines_count_only_for_configured_owners() -> None:
    event = component(FILTER, "CORE-FIL-4-upper")
    assert _reduce_event(FILTER, event, owner_emails=()) == timed(
        "2026-10-05T08:00Z", "2026-10-05T09:00Z"
    )


def _outcome(name: str, event: Component) -> Block | Skip | MalformedEventError:
    try:
        return _reduce_event(name, event)
    except MalformedEventError as error:
        return error


def test_no_event_content_survives_reduction_core_fil_14() -> None:
    outcomes = [
        _outcome(path.name, c)
        for path in sorted(OBJECTS.glob("*.ics"))
        for c in components(path.name)
    ]
    blocks = [o for o in outcomes if isinstance(o, DayBlock | TimedBlock)]
    # The scan saw every kind of outcome, so the checks below are not vacuous.
    assert blocks
    assert any(isinstance(o, Skip) for o in outcomes)
    assert any(isinstance(o, MalformedEventError) for o in outcomes)
    # FR-4: structurally, a block has a span and a flag and nothing else.
    assert {tuple(f.name for f in fields(type(b))) for b in blocks} == {
        ("start", "end", "tentative")
    }
    rendered = repr(outcomes) + " ".join(str(o) for o in outcomes)
    assert "BBX-" not in rendered
    assert "BBY-" not in rendered


# --- zero length and duration (CORE-ZERO, CORE-DUR) ---------------------------------------


@pytest.mark.parametrize(
    ("uid", "expected"),
    [
        # ZERO-1: decided before rounding, so off-grid and on-grid behave the same.
        ("CORE-ZERO-1-off-grid", Skip.EMPTY),
        ("CORE-ZERO-1-on-grid", Skip.EMPTY),
        # ZERO-2: the caller warns on NEGATIVE with the object-href hash.
        ("CORE-ZERO-2", Skip.NEGATIVE),
        # ZERO-3: RFC 5545 §3.6.1, a timed DTSTART alone has zero length.
        ("CORE-ZERO-3", Skip.EMPTY),
        ("dur-negative", Skip.NEGATIVE),
        ("allday-zero", Skip.EMPTY),
        ("allday-negative", Skip.NEGATIVE),
        # RFC 5545 §3.3.5: a local time in the spring gap takes the offset before the gap,
        # so 02:30 and 03:30 are the same instant and the event has no length.
        ("floating-gap-empty", Skip.EMPTY),
        # Both times are 03:xx CEST by wall clock but 01:30Z and 01:10Z as instants.
        ("zoned-gap-instants-reversed", Skip.NEGATIVE),
        # RFC 5545 §3.3.6: the sign belongs to the whole duration. -PT30M on a 23-hour
        # local day is still half an hour backwards, never a +30 minute block.
        ("dur-negative-half-hour-on-spring-day", Skip.NEGATIVE),
        ("dur-negative-hour-on-spring-day", Skip.NEGATIVE),
    ],
)
def test_events_without_positive_length_yield_no_block(uid: str, expected: Skip) -> None:
    assert _reduce(TIMES, uid) is expected


@pytest.mark.parametrize(
    ("uid", "expected"),
    [
        ("CORE-DUR-1", timed("2026-10-01T14:00+02:00", "2026-10-01T16:00+02:00")),
        ("CORE-DUR-2", day("2026-10-03", "2026-10-05")),
        ("CORE-DUR-3", day("2026-10-07", "2026-10-08")),
        ("allday-dtend", day("2026-10-12", "2026-10-13")),
        # OPEN Q-20 default: days and weeks are nominal in the configured zone,
        # the time part is exact (RFC 5545 §3.3.6). DUR-4: 09:00 CET + P1D = 09:00 CEST.
        ("CORE-DUR-4", timed("2026-03-28T09:00+01:00", "2026-03-29T09:00+02:00")),
        ("CORE-DUR-6-zoned-autumn", timed("2026-10-24T07:00Z", "2026-10-25T08:00Z")),
        # As the server expands it: UTC DTSTART, DURATION kept. Read in UTC, the autumn
        # instance would end at 07:00Z, a false-free hour; the spring one an hour late.
        ("CORE-DUR-6-expanded-autumn", timed("2026-10-24T07:00Z", "2026-10-25T08:00Z")),
        ("CORE-DUR-6-expanded-spring", timed("2026-03-28T08:00Z", "2026-03-29T07:00Z")),
        ("CORE-DUR-6-week-and-time", timed("2026-10-20T07:00Z", "2026-10-27T09:00Z")),
        # RFC 5545 §3.3.6 counts the day in the event's own zone: New York changes on 11-01,
        # so 09:00 EDT + P1D is 09:00 EST, 25 real hours (Berlin changed a week earlier).
        ("CORE-DUR-6-other-zone", timed("2026-10-31T13:00Z", "2026-11-01T14:00Z")),
        # The time part is exact: 01:30 CEST + PT2H = 02:30 CET, not 03:30 CET.
        ("dur-exact-across-fold", timed("2026-10-25T01:30+02:00", "2026-10-25T02:30+01:00")),
        # Hours are exact time even when they add up to a day: PT24H is 24 real hours,
        # not "one day", so on the spring day it ends at 08:00Z, not 07:00Z.
        ("dur-24-hours-across-spring", timed("2026-03-28T08:00Z", "2026-03-29T08:00Z")),
        ("dur-36-hours-across-spring", timed("2026-03-28T08:00Z", "2026-03-29T20:00Z")),
        # RFC 5545 §3.6.1 forbids both; the later end errs towards busy (G5), never free.
        ("dtend-shorter-than-duration", timed("2026-10-01T16:00Z", "2026-10-01T18:00Z")),
        ("dtend-later-than-duration", timed("2026-10-01T16:00Z", "2026-10-01T18:00Z")),
        ("allday-dtend-and-duration", day("2026-10-12", "2026-10-15")),
        ("utc", timed("2026-10-07T16:00Z", "2026-10-07T17:00Z")),
        # Floating time is read in the configured zone.
        ("floating", timed("2026-10-01T09:00+02:00", "2026-10-01T10:00+02:00")),
        # NFR-C1: 02:30 does not exist on 2026-03-29 and reads as 01:30Z.
        ("floating-gap-start", timed("2026-03-29T01:30Z", "2026-03-29T02:00Z")),
        # 02:30 happens twice on 2026-10-25; the first pass (CEST) is the one that counts.
        ("floating-fold-first-pass", timed("2026-10-25T00:30Z", "2026-10-25T02:00Z")),
        # Wall clock says 03:10 -> 02:50 is backwards; as instants it is 40 real minutes.
        ("zoned-gap-wall-reversed", timed("2026-03-29T01:10Z", "2026-03-29T01:50Z")),
    ],
)
def test_event_times_reduce_to_one_block(uid: str, expected: Block) -> None:
    assert _reduce(TIMES, uid) == expected


@pytest.mark.parametrize(
    "uid",
    [
        "CORE-DUR-5",  # timed DTSTART with a DATE DTEND
        "date-start-timed-end",
        "date-start-time-duration",
        "no-start",
        "broken-start",
        "broken-duration",
        # icalendar returns a naive time for a TZID it cannot resolve and reports no error.
        "unknown-tzid-start",
        "unknown-tzid-end",
        # The arithmetic runs past year 9999 (OverflowError in the standard library).
        "dur-weeks-beyond-year-9999",
        "allday-beyond-year-9999",
    ],
)
def test_malformed_times_raise_without_quoting_the_event(uid: str) -> None:
    with pytest.raises(MalformedEventError) as caught:
        _reduce(TIMES, uid)
    # The library's own message quotes the raw value; none of it may survive (AC-8).
    rendered = f"{caught.value!s} {caught.value!r}"
    assert "BBX-" not in rendered
    assert "BBY-" not in rendered
    # No chained library exception either: a logged traceback would print its message.
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None or caught.value.__suppress_context__


# --- the DURATION text (RFC 5545 §3.3.6) --------------------------------------------------

# A two-hour event at 14:00 Berlin time; only the DURATION text changes below.
DURATION_BASE = "CORE-DUR-1"
START = "2026-10-01T12:00Z"


def _with_duration(text: str | None) -> Block | Skip:
    event = component(TIMES, DURATION_BASE)
    return reduce_event(event, tz=BERLIN, owner_emails=OWNERS, duration=text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PT90M", timed(START, "2026-10-01T13:30Z")),
        ("PT1H30M", timed(START, "2026-10-01T13:30Z")),
        ("+PT1H", timed(START, "2026-10-01T13:00Z")),
        ("PT30S", timed(START, "2026-10-01T12:00:30Z")),
        ("P1DT1H", timed(START, "2026-10-02T13:00Z")),
        ("P1W", timed(START, "2026-10-08T12:00Z")),
        ("  PT1H\r", timed(START, "2026-10-01T13:00Z")),
        ("PT0S", Skip.EMPTY),
        ("P0D", Skip.EMPTY),
        # A zero has no sign to speak of: it is empty, not backwards.
        ("-PT0S", Skip.EMPTY),
        ("-P1D", Skip.NEGATIVE),
        ("-P1DT2H", Skip.NEGATIVE),
        ("-PT1M", Skip.NEGATIVE),
    ],
)
def test_duration_text_sets_the_end(text: str, expected: Block | Skip) -> None:
    assert _with_duration(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "P",
        "PT",
        "P1H",  # hours need the T
        "1D",
        "PT1.5H",
        "P1D2H",
        "PT1S1M",  # parts keep their order
        "P\u0661D",  # Arabic-Indic digit one: int() would take it, the grammar does not
        "P9999999999D",  # more digits than any real duration
        "BBY-garbage",
    ],
)
def test_unreadable_duration_text_raises_without_quoting_it(text: str) -> None:
    with pytest.raises(MalformedEventError) as caught:
        _with_duration(text)
    assert str(caught.value) == "DURATION is unreadable"  # the text may be private
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None or caught.value.__suppress_context__


def test_an_event_with_a_duration_property_needs_its_text() -> None:
    # Reading it as "no duration" would make the event zero length: a false free slot.
    with pytest.raises(MalformedEventError):
        _with_duration(None)
