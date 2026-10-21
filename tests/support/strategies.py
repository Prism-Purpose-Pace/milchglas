"""Hypothesis strategies for busy blocks in 2026, a year holding both Berlin DST days.

Timed blocks have second resolution so rounding has work to do; durations run up to
72 hours so blocks cross midnight and the DST transitions.
"""

from datetime import UTC, date, datetime, timedelta

from hypothesis import strategies as st

from milchglas.core.model import Block, DayBlock, TimedBlock

YEAR_START = datetime(2026, 1, 1, tzinfo=UTC)
YEAR_SECONDS = 365 * 86400
GRIDS = st.sampled_from([5, 15, 30, 60])


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
