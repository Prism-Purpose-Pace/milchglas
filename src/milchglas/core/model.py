"""Busy blocks and the interval algebra of the pipeline: window, clip, round, merge.

A block is all that survives an event (spec FR-4): its span and a tentative flag. Timed
blocks hold aware UTC instants, day blocks whole local dates; the two kinds never mix
(OPEN Q-9 default: a timed block inside an all-day block stays separate).
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
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
    the fold and the gap of a DST change round correctly in any zone. A grid that divides
    the day keeps local midnight, and with it every window boundary, on the grid.
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
