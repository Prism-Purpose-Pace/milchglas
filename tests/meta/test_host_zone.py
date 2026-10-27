"""The suite runs in a host zone that is not UTC (GATE-20).

CI runners run in UTC, where a conversion to local time changes nothing, so code that loses
an `astimezone(UTC)` would still pass every test. `tests/conftest.py` pins a zone with DST
and a half-hour offset; this test fails when that pin is lost.
"""

from datetime import UTC, datetime, timedelta


def test_suite_runs_in_a_zone_with_dst_and_a_half_hour_offset_gate_20() -> None:
    winter = datetime(2026, 1, 15, 12, tzinfo=UTC).astimezone().utcoffset()
    summer = datetime(2026, 7, 15, 12, tzinfo=UTC).astimezone().utcoffset()
    assert winter == -timedelta(hours=3, minutes=30)
    assert summer == -timedelta(hours=2, minutes=30)
