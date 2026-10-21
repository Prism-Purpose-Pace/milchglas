"""The grid and zone strategies must be able to draw every pair the zone check accepts.

Catalogue GATE-15.

A property over generated input holds by construction when the generator draws from a
hand-picked subset (grids 5, 15, 30 and 60 in Berlin only): the config space the check
accepts is wider than the space the property saw. This test enumerates the accepted
pairs on its own, over every zone of the tz database and every grid from 1 to 1440, and
compares them with the list the strategies draw from. A pair the check accepts and the
strategies cannot draw fails it, and so does a pair the strategies draw that the check
rejects. Known limit: the enumeration shares `grid_fits_zone` with the strategies, so a
wrong rule in the check is the unit tests' job, and the date is the strategies' own.
"""

import zoneinfo
from zoneinfo import ZoneInfo

import pytest

from milchglas.core.model import grid_fits_zone
from tests.support.strategies import GRID_ZONE_PAIRS, YEAR_START

type Pair = tuple[int, ZoneInfo]

BERLIN, KOLKATA, LORD_HOWE, CAIRO = (
    ZoneInfo(key)
    for key in ("Europe/Berlin", "Asia/Kolkata", "Australia/Lord_Howe", "Africa/Cairo")
)
# AC-22 passes these; a strategy that cannot draw one has lost a corner of the config space.
CORNERS: frozenset[Pair] = frozenset(
    {(15, BERLIN), (60, BERLIN), (45, KOLKATA), (120, KOLKATA), (30, LORD_HOWE), (60, CAIRO)}
)


def accepted_pairs() -> set[Pair]:
    zones = [ZoneInfo(key) for key in zoneinfo.available_timezones()]
    return {
        (grid, zone)
        for zone in zones
        for grid in range(1, 24 * 60 + 1)
        if grid_fits_zone(grid, zone, YEAR_START)
    }


def space_problems(drawable: set[Pair], accepted: set[Pair]) -> list[str]:
    """What keeps the strategies from covering exactly the accepted pairs."""
    problems = [
        f"accepted but not drawable: {pair}" for pair in sorted(accepted - drawable, key=str)
    ]
    problems += [f"drawable but rejected: {pair}" for pair in sorted(drawable - accepted, key=str)]
    return problems


def test_the_strategies_draw_exactly_the_pairs_the_zone_check_accepts() -> None:
    accepted = accepted_pairs()
    assert accepted >= CORNERS  # an empty or shrunken enumeration would pass the next line
    assert space_problems(set(GRID_ZONE_PAIRS), accepted) == []


@pytest.mark.parametrize(
    ("drawable", "expected"),
    [
        (set(CORNERS), 0),
        (set(CORNERS) - {(45, KOLKATA)}, 1),  # a corner the strategies lost
        (set(CORNERS) | {(45, BERLIN)}, 1),  # a pair the check rejects
        ({(grid, BERLIN) for grid in (15, 30)}, 6),  # a hand-picked space: 4 lost, 2 extra
    ],
    ids=["equal", "lost-corner", "extra-pair", "hand-picked"],
)
def test_the_space_check_fails_on_a_lost_or_an_extra_pair(
    drawable: set[Pair], expected: int
) -> None:
    assert len(space_problems(drawable, set(CORNERS))) == expected
