"""Block constructors for readable golden cases: times are ISO strings with their offset."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from milchglas.core.model import DayBlock, TimedBlock

BERLIN = ZoneInfo("Europe/Berlin")


def at(text: str) -> datetime:
    """`2026-10-01T10:07+02:00` or `2026-10-25T01:40Z` as an aware UTC instant."""
    return datetime.fromisoformat(text).astimezone(UTC)


def timed(start: str, end: str, *, tentative: bool = False) -> TimedBlock:
    return TimedBlock(at(start), at(end), tentative)


def day(start: str, end: str, *, tentative: bool = False) -> DayBlock:
    return DayBlock(date.fromisoformat(start), date.fromisoformat(end), tentative)
