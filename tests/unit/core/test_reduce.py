"""Golden cases for reducing one VEVENT to a busy block (spec FR-3, FR-4).

Fixtures: tests/fixtures/objects/*.ics, one VEVENT per catalogue case, looked up by UID.
"""

import pytest

from milchglas.core.model import Block
from milchglas.core.reduce import MalformedEventError, Skip, reduce_event
from tests.support.blocks import BERLIN, day, timed
from tests.support.ical import component

TIMES = "core-times.ics"


def _reduce(name: str, uid: str) -> Block | Skip:
    return reduce_event(component(name, uid), tz=BERLIN)


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
        # DUR-4: RFC 5545 §3.3.6, a day is nominal: 09:00 CET + P1D = 09:00 CEST (23 h).
        ("CORE-DUR-4", timed("2026-03-28T09:00+01:00", "2026-03-29T09:00+02:00")),
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
