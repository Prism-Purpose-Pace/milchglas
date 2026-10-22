"""Golden cases for the emitted feed (spec FR-7, D-8, NFR-P3; catalogue EMIT-*, DET-5, DET-7)."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime

import pytest

from milchglas.core.emit import emit, stamps, uid
from milchglas.core.model import Block, TimedBlock, merge
from milchglas.core.reduce import reduce_event
from tests.support.blocks import BERLIN, at, day, timed
from tests.support.feed import assert_feed_invariants, logical_lines, parse_feed, summaries
from tests.support.ical import component, duration_text

SALT = "test-salt"
NOW = at("2026-09-14T12:00Z")
TIMED = timed("2026-09-15T07:00Z", "2026-09-15T09:30Z")
DAY = day("2026-10-03", "2026-10-05")


def _emit(
    blocks: list[Block],
    *,
    summary: str = "Blocker Privat",
    ttl_seconds: int = 900,
    now: datetime = NOW,
    dtstamps: Mapping[str, datetime] | None = None,
) -> bytes:
    return emit(
        blocks,
        summary=summary,
        salt=SALT,
        ttl_seconds=ttl_seconds,
        version="0.1.2",
        now=now,
        dtstamps=dtstamps or {},
    )


def _crlf(*lines: str) -> bytes:
    return "".join(f"{line}\r\n" for line in lines).encode()


GOLDEN = _crlf(
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Milchglas//0.1.2//DE",
    "X-WR-CALNAME:Privat (busy)",
    "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
    "X-PUBLISHED-TTL:PT15M",
    "BEGIN:VEVENT",
    "UID:423e2fa40b2c97ac5c8cb78d0975ccd5@milchglas",
    "DTSTAMP:20260914T120000Z",
    "DTSTART;VALUE=DATE:20261003",
    "DTEND;VALUE=DATE:20261005",
    "SUMMARY:Blocker Privat",
    "TRANSP:OPAQUE",
    "STATUS:CONFIRMED",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:cea67c423baa7951ebe3acd2482abc59@milchglas",
    "DTSTAMP:20260914T120000Z",
    "DTSTART:20260915T070000Z",
    "DTEND:20260915T093000Z",
    "SUMMARY:Blocker Privat",
    "TRANSP:OPAQUE",
    "STATUS:CONFIRMED",
    "END:VEVENT",
    "END:VCALENDAR",
)


# --- the feed as a whole ------------------------------------------------------------------


def test_feed_matches_the_golden_bytes() -> None:
    # EMIT-2..5 and EMIT-8 in one; emit writes the blocks in the order merge gives them.
    feed = _emit([DAY, TIMED])
    assert feed == GOLDEN
    assert_feed_invariants(feed)


def test_feed_has_no_method_emit_2() -> None:
    # Without METHOD, RFC 5545 §3.8.7.2 reads DTSTAMP as the component's last revision,
    # which is what the feed carries; with METHOD it would mean the creation of this copy.
    assert not [line for line in logical_lines(GOLDEN) if line.startswith("METHOD")]


def test_unchanged_input_gives_byte_identical_feeds() -> None:
    orders: list[list[Block]] = [[TIMED, DAY], [DAY, TIMED], [TIMED, DAY]]
    assert {_emit(merge(blocks)) for blocks in orders} == {GOLDEN}


def test_feed_reparses_to_the_same_blocks_emit_10() -> None:
    blocks: list[Block] = [DAY, timed("2026-09-15T07:00Z", "2026-09-15T09:30Z", tentative=True)]
    assert parse_feed(_emit(blocks)) == [DAY, TIMED]  # tentative is emitted as busy (FR-14)


def test_empty_feed_is_valid() -> None:
    feed = _emit([])
    assert logical_lines(feed)[-1] == "END:VCALENDAR"
    assert parse_feed(feed) == []
    assert_feed_invariants(feed)


def test_feed_orders_day_blocks_first_then_by_start_emit_9() -> None:
    blocks: list[Block] = [
        timed("2026-10-02T08:00Z", "2026-10-02T09:00Z"),
        day("2026-10-20", "2026-10-21"),
        timed("2026-10-01T08:00Z", "2026-10-01T09:00Z"),
        day("2026-10-03", "2026-10-04"),
    ]
    assert parse_feed(_emit(merge(blocks))) == [blocks[3], blocks[1], blocks[2], blocks[0]]


# --- header (EMIT-2) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ttl_seconds", "duration"),
    [
        (900, "PT15M"),
        (3600, "PT1H"),
        (5400, "PT1H30M"),
        (3605, "PT1H0M5S"),
        (86461, "PT24H1M1S"),
    ],
)
def test_ttl_sets_both_refresh_hints_emit_2(ttl_seconds: int, duration: str) -> None:
    lines = logical_lines(_emit([], ttl_seconds=ttl_seconds))
    hints = [line for line in lines if line.startswith(("REFRESH-INTERVAL", "X-PUBLISHED-TTL"))]
    assert hints == [
        f"REFRESH-INTERVAL;VALUE=DURATION:{duration}",
        f"X-PUBLISHED-TTL:{duration}",
    ]


@pytest.mark.parametrize("ttl_seconds", [0, -900])
def test_ttl_must_be_positive(ttl_seconds: int) -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        _emit([], ttl_seconds=ttl_seconds)


# --- summary: escaping, injection, folding (EMIT-6, EMIT-7) -------------------------------


# RFC 5545 §3.3.11: TEXT escapes backslash, semicolon and comma; \n and \N in the escaped
# form mean a line break, so a literal backslash before n or N must be escaped too. A
# fixed table (FR-7), not icalendar's vText, which reads a literal \N as a newline.
ESCAPES = [
    ("Blocker Privat", "Blocker Privat"),
    ("A\\B", "A\\\\B"),
    ("Blocker; Privat", "Blocker\\; Privat"),
    ("Blocker, Privat", "Blocker\\, Privat"),
    ("C:\\New", "C:\\\\New"),
    ("a\\nb", "a\\\\nb"),
    ('Termin: "privat"', 'Termin: "privat"'),
    ("Blocker\tPrivat", "Blocker\tPrivat"),
    ("Größe €", "Größe €"),
]


@pytest.mark.parametrize(("summary", "escaped"), ESCAPES)
def test_summary_is_escaped_as_rfc_5545_text_emit_6(summary: str, escaped: str) -> None:
    feed = _emit([TIMED], summary=summary)
    assert f"SUMMARY:{escaped}" in logical_lines(feed)
    assert summaries(feed) == [summary]  # a real reader gets the configured text back


@pytest.mark.parametrize(
    "summary",
    [
        "Blocker\nPrivat",
        "Blocker\rPrivat",
        "Blocker\r\nATTENDEE:mailto:someone@example.org",
        "Blocker\x00",
        "Blocker\x0bPrivat",
        "Blocker\x85Privat",
        "Blocker\u2028Privat",
        "Blocker\u2029Privat",
        "Blocker\ud800Privat",
    ],
    ids=[
        "LF",
        "CR",
        "CRLF-injection",
        "NUL",
        "VT",
        "NEL",
        "LINE-SEPARATOR",
        "PARAGRAPH-SEPARATOR",
        "LONE-SURROGATE",
    ],
)
def test_summary_with_a_line_break_or_control_character_is_rejected_emit_6(summary: str) -> None:
    # The only free text in the feed: a raw line break would start a new property.
    with pytest.raises(ValueError, match="summary") as caught:
        _emit([TIMED], summary=summary)
    assert summary not in str(caught.value)


def test_long_summary_folds_at_75_octets_without_splitting_characters_emit_7() -> None:
    # Two- and three-octet characters (ä, €) so a fold can land inside a sequence.
    summary = ("Blocker Privat € Übergröße äöü ß " * 4)[:120]
    feed = _emit([TIMED], summary=summary)
    physical = feed.split(b"\r\n")
    assert len([line for line in physical if line.startswith(b" ")]) >= 2  # it did fold
    for line in physical:
        assert len(line) <= 75
        line.decode("utf-8")  # no UTF-8 sequence split across lines
    assert summaries(feed) == [summary]
    assert_feed_invariants(feed)


@pytest.mark.parametrize(("length", "physical_lines"), [(67, 1), (68, 2)])
def test_a_75_octet_line_stays_and_76_folds(length: int, physical_lines: int) -> None:
    # "SUMMARY:" is 8 octets, so 67 characters make a 75-octet line; only SUMMARY folds.
    feed = _emit([TIMED], summary="x" * length)
    assert feed.count(b"\r\n ") == physical_lines - 1


def test_folding_never_splits_a_text_escape() -> None:
    # 8 + 66 octets, then "\," would straddle the 75-octet limit: it moves as a whole.
    feed = _emit([TIMED], summary="x" * 66 + ",")
    assert b"x" * 66 + b"\r\n \\," in feed
    assert summaries(feed) == ["x" * 66 + ","]


# --- identity: UID and DTSTAMP (DET-5, DET-7, D-7c) ---------------------------------------


def test_uid_is_the_salted_hash_of_the_span() -> None:
    assert uid(SALT, DAY) == "423e2fa40b2c97ac5c8cb78d0975ccd5@milchglas"
    assert uid(SALT, TIMED) == "cea67c423baa7951ebe3acd2482abc59@milchglas"
    assert uid(SALT, replace(TIMED, tentative=True)) == uid(SALT, TIMED)


def test_uid_changes_with_the_salt_det_5() -> None:
    blocks: list[Block] = [TIMED, DAY]
    assert {uid("other", b) for b in blocks}.isdisjoint({uid(SALT, b) for b in blocks})
    assert [uid(SALT, b) for b in blocks] == [uid(SALT, b) for b in blocks]


def test_dtstamp_is_kept_for_known_blocks_and_now_for_new_ones() -> None:
    earlier = at("2026-09-01T06:00Z")
    feed = _emit([DAY, TIMED], dtstamps={uid(SALT, TIMED): earlier})
    lines = logical_lines(feed)
    stamps = [line for line in lines if line.startswith("DTSTAMP:")]
    assert stamps == ["DTSTAMP:20260914T120000Z", "DTSTAMP:20260901T060000Z"]  # day, timed


def test_dtstamp_drops_fractional_seconds() -> None:
    feed = _emit([TIMED], now=at("2026-09-14T12:00:00.999+02:00"))
    assert "DTSTAMP:20260914T100000Z" in logical_lines(feed)


def test_stamps_reads_the_golden_feed() -> None:
    assert stamps(GOLDEN) == {uid(SALT, DAY): NOW, uid(SALT, TIMED): NOW}


@pytest.mark.parametrize(
    "feed",
    [
        pytest.param(GOLDEN[:-30], id="truncated"),
        pytest.param(GOLDEN.replace(b"Privat", b"Priv\xe4t"), id="not-utf-8"),
        pytest.param(b"<html>404</html>\r\n", id="not-a-calendar"),
        pytest.param(b"", id="empty"),
        pytest.param(GOLDEN.replace(b"DTSTAMP:20260914T120000Z", b"DTSTAMP:soon"), id="bad-stamp"),
    ],
)
def test_stamps_refuses_a_feed_emit_cannot_have_written(feed: bytes) -> None:
    with pytest.raises(ValueError, match="previous feed"):
        stamps(feed)


def test_naive_instants_are_rejected() -> None:
    naive = datetime(2026, 9, 14, 12)
    with pytest.raises(ValueError, match="aware"):
        _emit([TIMED], now=naive)
    with pytest.raises(ValueError, match="aware"):
        _emit([TIMED], dtstamps={uid(SALT, TIMED): naive})


def test_one_instant_in_three_spellings_gives_one_feed_det_7() -> None:
    events = [
        component("core-identity.ics", n) for n in ("DET-7-utc", "DET-7-berlin", "DET-7-new-york")
    ]
    blocks = [
        reduce_event(e, tz=BERLIN, owner_emails=(), duration=duration_text("core-identity.ics", e))
        for e in events
    ]
    assert blocks == [timed("2026-10-01T07:30Z", "2026-10-01T09:00Z")] * 3
    feeds = {_emit([b]) for b in blocks if isinstance(b, TimedBlock)}
    assert len(feeds) == 1


# --- the invariant check itself can fail ---------------------------------------------------


def _mutate(old: str, new: str) -> bytes:
    assert old.encode() in GOLDEN
    return GOLDEN.replace(old.encode(), new.encode(), 1)


@pytest.mark.parametrize(
    "feed",
    [
        _mutate("SUMMARY:Blocker Privat\r\n", "SUMMARY:Blocker Privat\r\nLOCATION:Praxis\r\n"),
        _mutate("TRANSP:OPAQUE\r\n", "TRANSP:OPAQUE\r\nX-MICROSOFT-CDO-BUSYSTATUS:BUSY\r\n"),
        _mutate("SUMMARY:Blocker Privat", "SUMMARY:BBX-D2-01 Nachtdienst"),
        _mutate("DTSTART:20260915T070000Z", "DTSTART;TZID=Europe/Berlin:20260915T090000"),
        _mutate("BEGIN:VEVENT", "BEGIN:VTIMEZONE\r\nTZID:UTC\r\nEND:VTIMEZONE\r\nBEGIN:VEVENT"),
        _mutate("TRANSP:OPAQUE", "TRANSP:TRANSPARENT"),
        _mutate("SUMMARY:Blocker Privat", "SUMMARY:" + "x" * 68),
        _mutate("X-PUBLISHED-TTL:PT15M", "X-PUBLISHED-TTL:PT1H"),
        _mutate("X-WR-CALNAME:", "METHOD:PUBLISH\r\nX-WR-CALNAME:"),
        GOLDEN.replace(b"\r\n", b"\n"),
        _emit([TIMED, TIMED]),
        _emit(
            [
                timed("2026-10-01T09:00Z", "2026-10-01T10:00Z"),
                timed("2026-10-01T10:00Z", "2026-10-01T11:00Z"),
            ]
        ),
    ],
    ids=[
        "extra-property",
        "busystatus-not-configured",
        "fixture-title",
        "tzid",
        "vtimezone",
        "transparent",
        "76-octets",
        "ttl-mismatch",
        "method",
        "bare-lf",
        "duplicate-uid",
        "touching-blocks",
    ],
)
def test_feed_invariants_catch_each_defect(feed: bytes) -> None:
    with pytest.raises(AssertionError):
        assert_feed_invariants(feed)
