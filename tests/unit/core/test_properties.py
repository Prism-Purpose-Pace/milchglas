"""Properties of the interval algebra over generated blocks (catalogue PROP-1 to PROP-6)."""

from datetime import date, timedelta
from itertools import pairwise

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
from tests.support.blocks import BERLIN
from tests.support.strategies import GRIDS, instants, mixed_blocks, timed_blocks

KINDS: tuple[type[Block], ...] = (DayBlock, TimedBlock)


def _windows() -> st.SearchStrategy[Window]:
    return st.builds(window, instants(), st.just(BERLIN), st.integers(1, 60))


def _rounded(blocks: list[Block], grid: int) -> list[Block]:
    return round_to_grid(blocks, grid, BERLIN)


def _covers(blocks: list[Block], point: date) -> bool:
    return any(b.start <= point < b.end for b in blocks)


def _outside(block: Block, win: Window) -> bool:
    if isinstance(block, TimedBlock):
        return block.end <= win.start or block.start >= win.end
    return block.end <= win.first_day or block.start >= win.end_day


@given(mixed_blocks(), GRIDS)
def test_merge_output_is_sorted_and_never_touches_prop_1(blocks: list[Block], grid: int) -> None:
    merged = merge(_rounded(blocks, grid))
    for kind in KINDS:
        same = [b for b in merged if isinstance(b, kind)]
        assert all(a.end < b.start for a, b in pairwise(same))
    kinds = [isinstance(b, TimedBlock) for b in merged]
    assert kinds == sorted(kinds)  # day blocks first


@given(mixed_blocks(), GRIDS)
def test_merge_and_round_are_idempotent_prop_2(blocks: list[Block], grid: int) -> None:
    assert merge(merge(blocks)) == merge(blocks)
    assert _rounded(_rounded(blocks, grid), grid) == _rounded(blocks, grid)


@given(mixed_blocks(), GRIDS)
def test_merge_preserves_the_covered_set_prop_3(blocks: list[Block], grid: int) -> None:
    rounded = _rounded(blocks, grid)
    merged = merge(rounded)
    for kind in KINDS:
        before = [b for b in rounded if isinstance(b, kind)]
        after = [b for b in merged if isinstance(b, kind)]
        # Coverage of half-open blocks only changes at a boundary, so probing every
        # boundary of either side compares the two unions exactly.
        for point in {edge for b in before + after for edge in (b.start, b.end)}:
            assert _covers(after, point) == _covers(before, point)


@given(timed_blocks(), GRIDS)
def test_rounding_widens_onto_the_grid_by_less_than_one_step_prop_4(
    block: TimedBlock, grid: int
) -> None:
    [rounded] = _rounded([block], grid)
    step = timedelta(minutes=grid)
    assert isinstance(rounded, TimedBlock)
    assert block.start - step < rounded.start <= block.start
    assert block.end <= rounded.end < block.end + step
    # Berlin's offsets are whole hours, so its local grid is also the UTC epoch grid.
    for edge in (rounded.start, rounded.end):
        assert int(edge.timestamp()) % (grid * 60) == 0
    assert rounded.end - rounded.start >= step


@given(st.data(), mixed_blocks())
def test_merge_ignores_input_order_prop_5(data: st.DataObject, blocks: list[Block]) -> None:
    assert merge(data.draw(st.permutations(blocks))) == merge(blocks)


@given(mixed_blocks(), _windows())
def test_clip_stays_inside_the_window_prop_6(blocks: list[Block], win: Window) -> None:
    for block in clip(blocks, win):
        if isinstance(block, TimedBlock):
            assert win.start <= block.start < block.end <= win.end
        else:
            assert win.first_day <= block.start < block.end <= win.end_day
    assert clip([b for b in blocks if _outside(b, win)], win) == []


@given(mixed_blocks(), _windows(), GRIDS)
def test_clip_and_round_commute_on_a_midnight_window_prop_6(
    blocks: list[Block], win: Window, grid: int
) -> None:
    assert clip(_rounded(blocks, grid), win) == _rounded(clip(blocks, win), grid)
