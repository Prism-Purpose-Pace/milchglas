"""Properties of the interval algebra over generated blocks (catalogue PROP-1 to PROP-6).

Rounding and clipping run over every (grid, zone) pair the zone check accepts (spec
AC-22), so each property holds for each valid configuration, not only for Berlin.
"""

from datetime import date, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from milchglas.core.model import (
    Block,
    DayBlock,
    TimedBlock,
    Window,
    clip,
    merge,
    round_to_grid,
    window,
)
from tests.support.strategies import GRID_ZONES, instants, mixed_blocks, timed_blocks

KINDS: tuple[type[Block], ...] = (DayBlock, TimedBlock)

type Pair = tuple[int, ZoneInfo]


@st.composite
def _pairs_with_windows(draw: st.DrawFn) -> tuple[Pair, Window]:
    """An accepted (grid, zone) and a window of 1 to 60 days laid in that zone."""
    pair = draw(GRID_ZONES)
    return pair, window(draw(instants()), pair[1], draw(st.integers(1, 60)))


def _rounded(blocks: list[Block], pair: Pair) -> list[Block]:
    grid, zone = pair
    return round_to_grid(blocks, grid, zone)


def _covers(blocks: list[Block], point: date) -> bool:
    return any(b.start <= point < b.end for b in blocks)


def _outside(block: Block, win: Window) -> bool:
    if isinstance(block, TimedBlock):
        return block.end <= win.start or block.start >= win.end
    return block.end <= win.first_day or block.start >= win.end_day


@given(mixed_blocks(), GRID_ZONES)
def test_merge_output_is_sorted_and_never_touches_prop_1(blocks: list[Block], pair: Pair) -> None:
    merged = merge(_rounded(blocks, pair))
    for kind in KINDS:
        same = [b for b in merged if isinstance(b, kind)]
        assert all(a.end < b.start for a, b in pairwise(same))
    kinds = [isinstance(b, TimedBlock) for b in merged]
    assert kinds == sorted(kinds)  # day blocks first


@given(mixed_blocks(), GRID_ZONES)
def test_merge_and_round_are_idempotent_prop_2(blocks: list[Block], pair: Pair) -> None:
    assert merge(merge(blocks)) == merge(blocks)
    assert _rounded(_rounded(blocks, pair), pair) == _rounded(blocks, pair)


@given(mixed_blocks(), GRID_ZONES)
def test_merge_preserves_the_covered_set_prop_3(blocks: list[Block], pair: Pair) -> None:
    rounded = _rounded(blocks, pair)
    merged = merge(rounded)
    for kind in KINDS:
        before = [b for b in rounded if isinstance(b, kind)]
        after = [b for b in merged if isinstance(b, kind)]
        # Coverage of half-open blocks only changes at a boundary, so probing every
        # boundary of either side compares the two unions exactly.
        for point in {edge for b in before + after for edge in (b.start, b.end)}:
            assert _covers(after, point) == _covers(before, point)


@given(timed_blocks(), GRID_ZONES)
def test_rounding_widens_onto_the_local_grid_by_less_than_one_step_prop_4(
    block: TimedBlock, pair: Pair
) -> None:
    grid, zone = pair
    [rounded] = _rounded([block], pair)
    step = timedelta(minutes=grid)
    assert isinstance(rounded, TimedBlock)
    assert block.start - step < rounded.start <= block.start
    assert block.end <= rounded.end < block.end + step
    # The grid lies on the zone's own wall clock, read here from the datetime fields.
    for edge in (rounded.start, rounded.end):
        local = edge.astimezone(zone)
        assert (local.hour * 60 + local.minute) % grid == 0
        assert local.second == local.microsecond == 0
    assert rounded.end - rounded.start >= step


@given(st.data(), mixed_blocks())
def test_merge_ignores_input_order_prop_5(data: st.DataObject, blocks: list[Block]) -> None:
    assert merge(data.draw(st.permutations(blocks))) == merge(blocks)


@given(mixed_blocks(), _pairs_with_windows())
def test_clip_stays_inside_the_window_prop_6(
    blocks: list[Block], pair_window: tuple[Pair, Window]
) -> None:
    _, win = pair_window
    for block in clip(blocks, win):
        if isinstance(block, TimedBlock):
            assert win.start <= block.start < block.end <= win.end
        else:
            assert win.first_day <= block.start < block.end <= win.end_day
    assert clip([b for b in blocks if _outside(b, win)], win) == []


@given(mixed_blocks(), _pairs_with_windows())
def test_clip_and_round_commute_on_a_midnight_window_prop_6(
    blocks: list[Block], pair_window: tuple[Pair, Window]
) -> None:
    pair, win = pair_window
    assert clip(_rounded(blocks, pair), win) == _rounded(clip(blocks, win), pair)
