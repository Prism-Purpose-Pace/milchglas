"""Golden cases for the interval algebra: window, clip, round, merge (spec FR-5, FR-6).

IDs refer to the test catalogue; the zone is Europe/Berlin and the grid 15 minutes unless
a case says otherwise. EU DST 2026: 03-29 (02:00 CET -> 03:00 CEST), 10-25 (03:00 CEST ->
02:00 CET).
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from milchglas.core.model import (
    Block,
    DayBlock,
    TimedBlock,
    clip,
    grid_fits_zone,
    merge,
    round_to_grid,
    window,
)
from tests.support.blocks import BERLIN, at, day, timed

# Monday 2026-09-28, the window the e2e oracle pins: 28 days, ending in CET.
WINDOW = window(at("2026-09-28T00:00+02:00"), BERLIN, 28)


# --- model invariants -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 10, 1, 8), datetime(2026, 10, 1, 9)),
        (
            datetime(2026, 10, 1, 8, tzinfo=BERLIN),
            datetime(2026, 10, 1, 9, tzinfo=BERLIN),
        ),  # aware, but not canonical UTC (DET-7 hashes UTC only)
        (at("2026-10-01T09:00Z"), at("2026-10-01T09:00Z")),  # zero length
        (at("2026-10-01T09:00Z"), at("2026-10-01T08:00Z")),  # negative
    ],
    ids=["naive", "zoned", "zero", "negative"],
)
def test_timed_block_rejects_non_utc_or_empty_spans(start: datetime, end: datetime) -> None:
    with pytest.raises(ValueError, match="TimedBlock"):
        TimedBlock(start, end)


def test_timed_block_accepts_a_positive_utc_span() -> None:
    block = TimedBlock(at("2026-10-01T08:00Z"), at("2026-10-01T09:00Z"))
    assert (block.start, block.end, block.tentative) == (
        datetime(2026, 10, 1, 8, tzinfo=UTC),
        datetime(2026, 10, 1, 9, tzinfo=UTC),
        False,
    )


def test_day_block_rejects_datetimes() -> None:
    with pytest.raises(TypeError, match="DayBlock"):
        DayBlock(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC))


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 10, 2), date(2026, 10, 2)), (date(2026, 10, 2), date(2026, 10, 1))],
    ids=["zero", "negative"],
)
def test_day_block_rejects_empty_spans(start: date, end: date) -> None:
    with pytest.raises(ValueError, match="DayBlock"):
        DayBlock(start, end)


# --- window (FR-5) ------------------------------------------------------------------------


def test_window_spans_whole_local_days_across_the_dst_change() -> None:
    assert (WINDOW.first_day, WINDOW.end_day) == (date(2026, 9, 28), date(2026, 10, 26))
    assert (WINDOW.start, WINDOW.end) == (at("2026-09-27T22:00Z"), at("2026-10-25T23:00Z"))


def test_window_starts_on_the_local_date_not_the_utc_date() -> None:
    # 23:30Z on 09-27 is already 01:30 on 09-28 in Berlin.
    assert window(at("2026-09-27T23:30Z"), BERLIN, 28) == WINDOW


def test_window_is_stable_within_a_day_core_clip_6() -> None:
    assert window(at("2026-09-28T09:05+02:00"), BERLIN, 28) == window(
        at("2026-09-28T09:20+02:00"), BERLIN, 28
    )


@pytest.mark.parametrize("days", [0, -1])
def test_window_rejects_a_non_positive_length(days: int) -> None:
    with pytest.raises(ValueError, match="days"):
        window(at("2026-09-28T09:00Z"), BERLIN, days)


def test_window_rejects_a_naive_now() -> None:
    with pytest.raises(ValueError, match="aware"):
        window(datetime(2026, 9, 28, 9), BERLIN, 28)


# --- clip (FR-5) --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        # CLIP-1: Sunday 23:50 -> Monday 00:10 local, window from Monday 00:00.
        (
            timed("2026-09-27T23:50+02:00", "2026-09-28T00:10+02:00"),
            [timed("2026-09-28T00:00+02:00", "2026-09-28T00:10+02:00")],
        ),
        # CLIP-2: ends exactly at the window start.
        (timed("2026-09-27T21:00+02:00", "2026-09-28T00:00+02:00"), []),
        # CLIP-3: starts exactly at the window end.
        (timed("2026-10-26T00:00+01:00", "2026-10-26T01:00+01:00"), []),
        # CLIP-4: straddles the window end.
        (
            timed("2026-10-25T22:00+01:00", "2026-10-26T01:00+01:00"),
            [timed("2026-10-25T22:00+01:00", "2026-10-26T00:00+01:00")],
        ),
        # Inside: unchanged, tentative flag kept.
        (
            timed("2026-10-01T10:00+02:00", "2026-10-01T11:00+02:00", tentative=True),
            [timed("2026-10-01T10:00+02:00", "2026-10-01T11:00+02:00", tentative=True)],
        ),
        # CLIP-5: day block straddling the window start starts on the first day.
        (day("2026-09-26", "2026-09-29"), [day("2026-09-28", "2026-09-29")]),
        # Day block ending exactly at the first day, starting exactly at the end day.
        (day("2026-09-27", "2026-09-28"), []),
        (day("2026-10-26", "2026-10-27"), []),
        # Day block straddling the window end.
        (day("2026-10-24", "2026-10-28"), [day("2026-10-24", "2026-10-26")]),
    ],
    ids=[
        "CORE-CLIP-1",
        "CORE-CLIP-2",
        "CORE-CLIP-3",
        "CORE-CLIP-4",
        "inside",
        "CORE-CLIP-5",
        "day-ends-at-start",
        "day-starts-at-end",
        "day-straddles-end",
    ],
)
def test_clip_cuts_blocks_to_the_window(block: Block, expected: list[Block]) -> None:
    assert clip([block], WINDOW) == expected


# --- round (FR-6) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("block", "grid", "expected"),
    [
        (
            timed("2026-10-01T10:07+02:00", "2026-10-01T10:52+02:00"),
            15,
            timed("2026-10-01T10:00+02:00", "2026-10-01T11:00+02:00"),
        ),
        (
            timed("2026-10-01T10:00+02:00", "2026-10-01T10:15+02:00"),
            15,
            timed("2026-10-01T10:00+02:00", "2026-10-01T10:15+02:00"),
        ),
        (
            timed("2026-10-01T10:00+02:00", "2026-10-01T10:16+02:00"),
            15,
            timed("2026-10-01T10:00+02:00", "2026-10-01T10:30+02:00"),
        ),
        (
            timed("2026-10-01T10:07+02:00", "2026-10-01T10:52+02:00"),
            30,
            timed("2026-10-01T10:00+02:00", "2026-10-01T11:00+02:00"),
        ),
        (
            timed("2026-10-01T10:07+02:00", "2026-10-01T10:52+02:00"),
            5,
            timed("2026-10-01T10:05+02:00", "2026-10-01T10:55+02:00"),
        ),
        # Seconds count: 10:00:01 ceils to the next slot.
        (
            timed("2026-10-01T09:00:30+02:00", "2026-10-01T10:00:01+02:00"),
            15,
            timed("2026-10-01T09:00+02:00", "2026-10-01T10:15+02:00"),
        ),
        # RND-5: 02:40-02:50 CET, the second pass through the fold.
        (
            timed("2026-10-25T01:40Z", "2026-10-25T01:50Z"),
            15,
            timed("2026-10-25T01:30Z", "2026-10-25T02:00Z"),
        ),
        # RND-6: 02:40-02:50 CEST, the first pass.
        (
            timed("2026-10-25T00:40Z", "2026-10-25T00:50Z"),
            15,
            timed("2026-10-25T00:30Z", "2026-10-25T01:00Z"),
        ),
        # RND-7: 01:40 CET before the spring gap; 03:05 CEST after it.
        (
            timed("2026-03-29T00:40Z", "2026-03-29T00:50Z"),
            15,
            timed("2026-03-29T00:30Z", "2026-03-29T01:00Z"),
        ),
        (
            timed("2026-03-29T01:05Z", "2026-03-29T01:10Z"),
            15,
            timed("2026-03-29T01:00Z", "2026-03-29T01:15Z"),
        ),
        (
            timed("2026-03-29T01:05Z", "2026-03-29T01:10Z"),
            60,
            timed("2026-03-29T01:00Z", "2026-03-29T02:00Z"),
        ),
    ],
    ids=[
        "CORE-RND-1",
        "CORE-RND-2",
        "CORE-RND-3",
        "CORE-RND-4-grid-30",
        "CORE-RND-4-grid-5",
        "seconds",
        "CORE-RND-5",
        "CORE-RND-6",
        "CORE-RND-7-before-gap",
        "CORE-RND-7-after-gap",
        "CORE-RND-7-grid-60",
    ],
)
def test_round_floors_start_and_ceils_end_on_the_local_grid(
    block: TimedBlock, grid: int, expected: TimedBlock
) -> None:
    assert round_to_grid([block], grid, BERLIN) == [expected]


@pytest.mark.parametrize(
    ("grid", "expected"),
    [
        (15, timed("2026-10-25T01:00Z", "2026-10-25T01:30Z")),
        # The zone check rejects 45, 90 and 120 for Berlin, but round_to_grid still reads the
        # offset in force at each instant, so direction and bound hold. At these grids the
        # one-hour offset error of a wall clock that loses the fold changes the result; at
        # 15 it cancels, because 60 is a multiple of 15.
        (45, timed("2026-10-25T00:30Z", "2026-10-25T02:00Z")),
        (90, timed("2026-10-25T00:30Z", "2026-10-25T02:00Z")),
        (120, timed("2026-10-25T01:00Z", "2026-10-25T03:00Z")),
    ],
)
def test_round_keeps_the_fold_of_the_second_pass(grid: int, expected: TimedBlock) -> None:
    # 02:07 occurs twice on 2026-10-25; the second pass (fold=1, CET) is 01:07Z. Rebuilding
    # the local time from its fields would lose the fold and read it an hour early.
    start = datetime(2026, 10, 25, 2, 7, fold=1, tzinfo=BERLIN).astimezone(UTC)
    end = datetime(2026, 10, 25, 2, 20, fold=1, tzinfo=BERLIN).astimezone(UTC)
    assert round_to_grid([TimedBlock(start, end)], grid, BERLIN) == [expected]


def test_round_uses_the_local_grid_of_a_half_hour_zone() -> None:
    # Replaces catalogue CORE-RND-8 (reject grid 60 for +05:30): rounding reads the zone's
    # offset, so 10:07-10:52 IST rounds to whole local hours. UTC-epoch rounding would
    # give 09:30-11:30 IST here.
    kolkata = ZoneInfo("Asia/Kolkata")
    block = timed("2026-10-01T10:07+05:30", "2026-10-01T10:52+05:30")
    assert round_to_grid([block], 60, kolkata) == [
        timed("2026-10-01T10:00+05:30", "2026-10-01T11:00+05:30")
    ]


def test_round_keeps_the_tentative_flag_and_day_blocks() -> None:
    blocks: list[Block] = [
        timed("2026-10-01T10:07+02:00", "2026-10-01T10:52+02:00", tentative=True),
        day("2026-10-03", "2026-10-05"),
    ]
    assert round_to_grid(blocks, 15, BERLIN) == [
        timed("2026-10-01T10:00+02:00", "2026-10-01T11:00+02:00", tentative=True),
        day("2026-10-03", "2026-10-05"),
    ]


@pytest.mark.parametrize("grid", [0, -15, 7, 25, 50, 1441])
def test_round_rejects_a_grid_that_does_not_divide_the_day(grid: int) -> None:
    with pytest.raises(ValueError, match="grid"):
        round_to_grid([], grid, BERLIN)


@pytest.mark.parametrize("grid", [1, 45, 90, 120, 1440])
def test_round_accepts_every_divisor_of_the_day(grid: int) -> None:
    assert round_to_grid([], grid, BERLIN) == []


# --- grid and zone (FR-6, AC-22) -----------------------------------------------------------

KOLKATA = ZoneInfo("Asia/Kolkata")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")
CAIRO = ZoneInfo("Africa/Cairo")
UTC_ZONE = ZoneInfo("UTC")
JAN_2026 = at("2026-01-01T00:00Z")
# Pyongyang moved from +08:30 to +09:00 here, a 30-minute change and the only one near it.
PYONGYANG = ZoneInfo("Asia/Pyongyang")
PYONGYANG_CHANGE = at("2018-05-04T15:00Z")


@pytest.mark.parametrize("zone", [BERLIN, KOLKATA, LORD_HOWE, UTC_ZONE], ids=lambda z: z.key)
@pytest.mark.parametrize("grid", [0, -15, 7, 25, 50, 1441])
def test_grid_fits_no_zone_when_it_does_not_divide_the_day(grid: int, zone: ZoneInfo) -> None:
    assert not grid_fits_zone(grid, zone, JAN_2026)


@pytest.mark.parametrize(
    ("zone", "grid", "fits"),
    [
        # AC-22: 15, 30 and 60 pass for Berlin, where 45, 90 and 120 are rejected.
        *((BERLIN, grid, True) for grid in (15, 30, 60)),
        *((BERLIN, grid, False) for grid in (45, 90, 120, 1440)),
        # No DST in Kolkata, so every divisor of the day fits, 45, 90 and 120 included.
        *((KOLKATA, grid, True) for grid in (15, 45, 60, 90, 120, 1440)),
        *((UTC_ZONE, grid, True) for grid in (45, 1440)),
        # AC-22: Lord Howe shifts by 30 minutes, so 60 is rejected and 30 passes.
        (LORD_HOWE, 60, False),
        (LORD_HOWE, 30, True),
        (LORD_HOWE, 15, True),
        # Cairo changes at midnight; a 60-minute shift fits 60 and not 120.
        (CAIRO, 60, True),
        (CAIRO, 120, False),
    ],
    ids=lambda v: v.key if isinstance(v, ZoneInfo) else str(v),
)
def test_grid_fits_the_zone_by_the_offset_changes_it_has(
    zone: ZoneInfo, grid: int, *, fits: bool
) -> None:
    assert grid_fits_zone(grid, zone, JAN_2026) is fits


@pytest.mark.parametrize(
    ("start", "fits"),
    [
        (PYONGYANG_CHANGE - timedelta(days=367), True),  # the change is beyond 366 days
        (PYONGYANG_CHANGE - timedelta(days=365), False),
        (PYONGYANG_CHANGE - timedelta(hours=1), False),
        (PYONGYANG_CHANGE + timedelta(days=1), True),  # the change is in the past
    ],
    ids=["beyond-366-days", "inside-365-days", "an-hour-before", "past"],
)
def test_grid_fits_counts_only_the_changes_in_the_366_days_after_start(
    start: datetime, *, fits: bool
) -> None:
    # 45 does not divide the 30-minute change; 30 always does.
    assert grid_fits_zone(45, PYONGYANG, start) is fits
    assert grid_fits_zone(30, PYONGYANG, start)


def test_grid_fits_needs_an_aware_start() -> None:
    with pytest.raises(ValueError, match="aware"):
        grid_fits_zone(15, BERLIN, datetime(2026, 1, 1))


# --- merge (FR-6, D-7b) -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("blocks", "expected"),
    [
        # MRG-1: overlap chain.
        (
            [
                timed("2026-10-01T09:00Z", "2026-10-01T12:00Z"),
                timed("2026-10-01T10:00Z", "2026-10-01T11:00Z"),
                timed("2026-10-01T11:30Z", "2026-10-01T12:30Z"),
            ],
            [timed("2026-10-01T09:00Z", "2026-10-01T12:30Z")],
        ),
        # MRG-2: touching blocks become one.
        (
            [
                timed("2026-10-01T10:00Z", "2026-10-01T11:00Z"),
                timed("2026-10-01T09:00Z", "2026-10-01T10:00Z"),
            ],
            [timed("2026-10-01T09:00Z", "2026-10-01T11:00Z")],
        ),
        # MRG-3: a gap keeps two blocks.
        (
            [
                timed("2026-10-01T09:00Z", "2026-10-01T10:00Z"),
                timed("2026-10-01T10:15Z", "2026-10-01T11:00Z"),
            ],
            [
                timed("2026-10-01T09:00Z", "2026-10-01T10:00Z"),
                timed("2026-10-01T10:15Z", "2026-10-01T11:00Z"),
            ],
        ),
        # MRG-4: tentative only if every contributor is tentative (OPEN Q-10 default).
        (
            [
                timed("2026-10-01T09:00Z", "2026-10-01T10:00Z", tentative=True),
                timed("2026-10-01T09:30Z", "2026-10-01T11:00Z"),
            ],
            [timed("2026-10-01T09:00Z", "2026-10-01T11:00Z")],
        ),
        (
            [
                timed("2026-10-01T09:00Z", "2026-10-01T10:00Z", tentative=True),
                timed("2026-10-01T09:30Z", "2026-10-01T11:00Z", tentative=True),
            ],
            [timed("2026-10-01T09:00Z", "2026-10-01T11:00Z", tentative=True)],
        ),
        # MRG-5: touching day blocks merge.
        (
            [day("2026-10-19", "2026-10-20"), day("2026-10-17", "2026-10-19")],
            [day("2026-10-17", "2026-10-20")],
        ),
        # MRG-5 / OPEN Q-9 default: a timed block inside an all-day block stays separate;
        # day blocks come first.
        (
            [timed("2026-10-12T08:00Z", "2026-10-12T09:00Z"), day("2026-10-12", "2026-10-13")],
            [day("2026-10-12", "2026-10-13"), timed("2026-10-12T08:00Z", "2026-10-12T09:00Z")],
        ),
        ([], []),
    ],
    ids=[
        "CORE-MRG-1",
        "CORE-MRG-2",
        "CORE-MRG-3",
        "CORE-MRG-4-mixed",
        "CORE-MRG-4-all-tentative",
        "CORE-MRG-5-days",
        "CORE-MRG-5-kinds-apart",
        "empty",
    ],
)
def test_merge_unites_overlapping_and_touching_blocks_per_kind(
    blocks: list[Block], expected: list[Block]
) -> None:
    assert merge(blocks) == expected
