"""Busy blocks and the interval algebra of the pipeline: window, clip, round, merge.

A block is all that survives an event (spec FR-4): its span and a tentative flag. Timed
blocks hold aware UTC instants, day blocks whole local dates; the two kinds never mix
(OPEN Q-9 default: a timed block inside an all-day block stays separate).
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from itertools import pairwise
from zoneinfo import ZoneInfo

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DAY_MINUTES = 24 * 60


@dataclass(frozen=True, order=True, slots=True)
class TimedBlock:
    """Busy from `start` up to, not including, `end`; both canonical UTC instants."""

    start: datetime
    end: datetime
    tentative: bool = False

    def __post_init__(self) -> None:
        # UTC only: UIDs hash the instants, and one instant must have one spelling (DET-7).
        if self.start.tzinfo is not UTC or self.end.tzinfo is not UTC:
            msg = "TimedBlock needs aware UTC instants"
            raise ValueError(msg)
        if not self.start < self.end:
            msg = "TimedBlock needs start < end"
            raise ValueError(msg)


@dataclass(frozen=True, order=True, slots=True)
class DayBlock:
    """Busy on the whole dates from `start` up to, not including, `end` (RFC 5545 DTEND)."""

    start: date
    end: date
    tentative: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.start, datetime) or isinstance(self.end, datetime):
            msg = "DayBlock needs dates, not datetimes"
            raise TypeError(msg)
        if not self.start < self.end:
            msg = "DayBlock needs start < end"
            raise ValueError(msg)


type Block = TimedBlock | DayBlock


@dataclass(frozen=True, slots=True)
class Window:
    """The published span: local dates `first_day` to `end_day` (exclusive) as instants."""

    first_day: date
    end_day: date
    start: datetime
    end: datetime


def window(now: datetime, tz: ZoneInfo, days: int) -> Window:
    """Today 00:00 local up to `days` local midnights later (FR-5).

    Every refresh on the same local day gets the same window (CORE-CLIP-6).
    """
    if now.utcoffset() is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)
    if days < 1:
        msg = "window days must be positive"
        raise ValueError(msg)
    first_day = now.astimezone(tz).date()
    end_day = first_day + timedelta(days=days)
    return Window(first_day, end_day, _midnight(first_day, tz), _midnight(end_day, tz))


def clip(blocks: Iterable[Block], win: Window) -> list[Block]:
    """Cut every block to the window; drop blocks that do not intersect it."""
    clipped: list[Block] = []
    for block in blocks:
        if isinstance(block, TimedBlock):
            start, end = max(block.start, win.start), min(block.end, win.end)
            if start < end:
                clipped.append(TimedBlock(start, end, block.tentative))
        else:
            first, last = max(block.start, win.first_day), min(block.end, win.end_day)
            if first < last:
                clipped.append(DayBlock(first, last, block.tentative))
    return clipped


def round_to_grid(blocks: Iterable[Block], grid_minutes: int, tz: ZoneInfo) -> list[Block]:
    """Floor starts and ceil ends of timed blocks to the local grid of `tz` (FR-6).

    The grid is laid on local wall time with the UTC offset in force at each instant, so
    the fold and the gap of a DST change are read correctly. For any grid that divides
    the day: a start only moves earlier and an end only later, each by less than one step,
    and day blocks pass through. Every edge lands on the local grid, and a second rounding
    changes nothing, only where `grid_fits_zone` is true; otherwise an edge on the far side
    of a UTC-offset change that the grid does not divide can sit off the grid.
    """
    if grid_minutes < 1 or _DAY_MINUTES % grid_minutes:
        msg = "grid_minutes must be a positive divisor of 1440"
        raise ValueError(msg)
    step = timedelta(minutes=grid_minutes)
    return [
        TimedBlock(
            block.start - _wall(block.start, tz) % step,
            block.end + (-_wall(block.end, tz)) % step,
            block.tentative,
        )
        if isinstance(block, TimedBlock)
        else block
        for block in blocks
    ]


def grid_fits_zone(grid_minutes: int, tz: ZoneInfo, start: datetime) -> bool:
    """Whether rounding to `grid_minutes` lands every edge on the local grid of `tz` (FR-6).

    True when the grid divides the day and every UTC-offset change of `tz` in the 366 days
    after `start`, measured in minutes (AC-22). Only then are the edges of `round_to_grid`
    on the grid and the rounding idempotent. `round_to_grid` itself needs only the day
    rule, so a caller that takes the grid from configuration calls this one first.
    """
    if start.utcoffset() is None:
        msg = "start must be timezone-aware"
        raise ValueError(msg)
    if grid_minutes < 1 or _DAY_MINUTES % grid_minutes:
        return False
    step = timedelta(minutes=grid_minutes)
    return all(shift % step == timedelta(0) for shift in _offset_shifts(tz, start))


def merge(blocks: Iterable[Block]) -> list[Block]:
    """Set union per kind: overlapping and touching blocks become one (D-7b).

    Output is canonical: day blocks first, then timed blocks, each sorted, and no two
    blocks of a kind overlap or touch. A merged block is tentative only if every block in
    it was (OPEN Q-10 default).
    """
    pending = list(blocks)
    days = _union(sorted(b for b in pending if isinstance(b, DayBlock)))
    timed = _union(sorted(b for b in pending if isinstance(b, TimedBlock)))
    return [*days, *timed]


def _union[B: (TimedBlock, DayBlock)](ordered: list[B]) -> list[B]:
    united: list[B] = []
    for block in ordered:
        if united and block.start <= united[-1].end:
            last = united[-1]
            united[-1] = replace(
                last, end=max(last.end, block.end), tentative=last.tentative and block.tentative
            )
        else:
            united.append(block)
    return united


def _midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tz).astimezone(UTC)


def _wall(instant: datetime, tz: ZoneInfo) -> timedelta:
    """Local wall-clock time of `instant` in `tz`, as a duration since the epoch."""
    offset = instant.astimezone(tz).utcoffset() or timedelta(0)
    return instant - _EPOCH + offset


@lru_cache(maxsize=1024)
def _offset_shifts(tz: ZoneInfo, start: datetime) -> frozenset[timedelta]:
    """The sizes of the UTC-offset changes of `tz` in the 366 days after `start`.

    zoneinfo has no public transition list, so the offset is read once an hour. Shortcut:
    two changes inside one hour would cancel, and tzdata has none. The cache keeps a scan
    of all zones fast in tests; a refresher passes a new `start` every run, so it is bounded.
    """
    offsets = [
        (start + timedelta(hours=hour)).astimezone(tz).utcoffset() or timedelta(0)
        for hour in range(366 * 24 + 1)
    ]
    return frozenset(abs(after - before) for before, after in pairwise(offsets) if before != after)
