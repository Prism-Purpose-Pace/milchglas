"""Hypothesis strategies for busy blocks in 2026, a year holding the DST days of most zones.

Timed blocks have second resolution so rounding has work to do; durations run up to
72 hours so blocks cross midnight and the DST transitions.
"""

import zoneinfo
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import strategies as st

from milchglas.core.model import Block, DayBlock, TimedBlock, grid_fits_zone

YEAR_START = datetime(2026, 1, 1, tzinfo=UTC)
YEAR_SECONDS = 365 * 86400
# Every (grid, zone) the zone check accepts at YEAR_START, over all zones of the tz database
# and every divisor of the day: a property over these pairs holds for each valid config, and
# no hand-picked list narrows it. The meta test compares this list with an enumeration of
# its own. Building it reads each zone's offsets for a year, about 6 s for 600 zones.
GRID_ZONE_PAIRS: list[tuple[int, ZoneInfo]] = [
    (grid, zone)
    for zone in map(ZoneInfo, sorted(zoneinfo.available_timezones()))
    for grid in range(1, 24 * 60 + 1)
    if 24 * 60 % grid == 0 and grid_fits_zone(grid, zone, YEAR_START)
]
GRID_ZONES = st.sampled_from(GRID_ZONE_PAIRS)


@st.composite
def timed_blocks(draw: st.DrawFn) -> TimedBlock:
    start = YEAR_START + timedelta(seconds=draw(st.integers(0, YEAR_SECONDS)))
    length = timedelta(seconds=draw(st.integers(1, 72 * 3600)))
    return TimedBlock(start, start + length, draw(st.booleans()))


@st.composite
def day_blocks(draw: st.DrawFn) -> DayBlock:
    start = date(2026, 1, 1) + timedelta(days=draw(st.integers(0, 364)))
    return DayBlock(start, start + timedelta(days=draw(st.integers(1, 10))), draw(st.booleans()))


def mixed_blocks(max_size: int = 30) -> st.SearchStrategy[list[Block]]:
    block: st.SearchStrategy[Block] = st.one_of(timed_blocks(), day_blocks())
    return st.lists(block, max_size=max_size)


def instants() -> st.SearchStrategy[datetime]:
    return st.integers(0, YEAR_SECONDS).map(lambda s: YEAR_START + timedelta(seconds=s))
