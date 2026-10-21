"""Golden cases for reducing one VEVENT to a busy block (spec FR-3, FR-4).

Fixtures: tests/fixtures/objects/*.ics, one VEVENT per catalogue case, looked up by UID.
"""

from dataclasses import fields

import pytest
from icalendar import Component

from milchglas.core.model import Block, DayBlock, TimedBlock
from milchglas.core.reduce import MalformedEventError, Skip, reduce_event
from tests.support.blocks import BERLIN, day, timed
from tests.support.ical import OBJECTS, component, components

TIMES = "core-times.ics"
FILTER = "core-filter.ics"
# Configured spelling differs in case from the fixtures on purpose.
OWNERS = ("OWNER@example.org", "owner.private@example.org")


def _reduce(name: str, uid: str) -> Block | Skip:
    return reduce_event(component(name, uid), tz=BERLIN, owner_emails=OWNERS)


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
        # Declined under one address, accepted under the other: still attending.
        ("owner-twice-one-accepted", timed("2026-10-05T08:00Z", "2026-10-05T09:00Z")),
        # D-3: redaction is Milchglas's job, so CLASS never hides a block.
        ("CORE-FIL-8-private", timed("2026-10-06T06:00Z", "2026-10-06T07:00Z")),
        ("CORE-FIL-8-confidential", timed("2026-10-06T06:00Z", "2026-10-06T07:00Z")),
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
        assert reduce_event(
            event, tz=BERLIN, owner_emails=OWNERS, keep_transparent_allday=False
        ) is (Skip.TRANSPARENT)


def test_declines_count_only_for_configured_owners() -> None:
    event = component(FILTER, "CORE-FIL-4-upper")
    assert reduce_event(event, tz=BERLIN, owner_emails=()) == timed(
        "2026-10-05T08:00Z", "2026-10-05T09:00Z"
    )


def _outcome(event: Component) -> Block | Skip | MalformedEventError:
    try:
        return reduce_event(event, tz=BERLIN, owner_emails=OWNERS)
    except MalformedEventError as error:
        return error


def test_no_event_content_survives_reduction_core_fil_14() -> None:
    outcomes = [
        _outcome(c) for path in sorted(OBJECTS.glob("*.ics")) for c in components(path.name)
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
        # The documented weakness: an event made in a zone with other DST dates counts its
        # days in the configured zone (New York changes on 11-01, Berlin on 10-25).
        ("CORE-DUR-6-other-zone", timed("2026-10-24T07:00Z", "2026-10-25T08:00Z")),
        # The time part is exact: 01:30 CEST + PT2H = 02:30 CET, not 03:30 CET.
        ("dur-exact-across-fold", timed("2026-10-25T01:30+02:00", "2026-10-25T02:30+01:00")),
        ("dtend-wins-over-duration", timed("2026-10-01T16:00Z", "2026-10-01T16:30Z")),
        ("utc", timed("2026-10-07T16:00Z", "2026-10-07T17:00Z")),
        # Floating time is read in the configured zone.
        ("floating", timed("2026-10-01T09:00+02:00", "2026-10-01T10:00+02:00")),
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
