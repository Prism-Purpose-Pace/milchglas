"""Golden cases for the interval algebra: window, clip, round, merge (spec FR-5, FR-6).

IDs refer to the test catalogue; the zone is Europe/Berlin and the grid 15 minutes unless
a case says otherwise. EU DST 2026: 03-29 (02:00 CET -> 03:00 CEST), 10-25 (03:00 CEST ->
02:00 CET).
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from milchglas.core.model import Block, DayBlock, TimedBlock, clip, merge, round_to_grid, window
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


def test_round_keeps_the_fold_of_the_second_pass() -> None:
    # 02:07 occurs twice on 2026-10-25; the second pass (fold=1, CET) is 01:07Z and must
    # floor to 01:00Z. Rebuilding the local time from its fields would lose the fold and
    # give 00:00Z, an hour early.
    start = datetime(2026, 10, 25, 2, 7, fold=1, tzinfo=BERLIN).astimezone(UTC)
    end = datetime(2026, 10, 25, 2, 20, fold=1, tzinfo=BERLIN).astimezone(UTC)
    assert round_to_grid([TimedBlock(start, end)], 15, BERLIN) == [
        timed("2026-10-25T01:00Z", "2026-10-25T01:30Z")
    ]


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


@pytest.mark.parametrize("grid", [0, -15, 7, 25])
def test_round_rejects_a_grid_that_does_not_divide_the_day(grid: int) -> None:
    with pytest.raises(ValueError, match="grid"):
        round_to_grid([], grid, BERLIN)


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
