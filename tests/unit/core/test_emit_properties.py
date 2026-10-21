"""Properties of the emitted feed over generated blocks (catalogue PROP-7 to PROP-10)."""

import re
import unicodedata
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from milchglas.core.emit import emit, uid
from milchglas.core.model import Block, TimedBlock, Window, clip, merge, round_to_grid, window
from tests.support.blocks import BERLIN
from tests.support.feed import assert_feed_invariants, logical_lines, parse_feed, summaries
from tests.support.strategies import GRIDS, YEAR_START, mixed_blocks

WINDOW = window(YEAR_START, BERLIN, 365)
# What emit must refuse in a summary, decided from the Unicode database and not from the
# emitter's own pattern: controls (C0, DEL, C1) except TAB, the line and paragraph
# separators, and lone surrogates, which cannot be written as UTF-8.
UNSAFE_CATEGORIES = frozenset({"Cc", "Zl", "Zp", "Cs"})


def _unsafe(text: str) -> bool:
    return any(c != "\t" and unicodedata.category(c) in UNSAFE_CATEGORIES for c in text)


# Plain text rarely draws the refused set, and `st.text` drops surrogates: the ends of
# both surrogate ranges are named, and the characters are joined by hand.
SUMMARIES = st.lists(
    st.characters()
    | st.characters(categories=["Cc", "Zl", "Zp"])
    | st.sampled_from(["\ud800", "\udbff", "\udc00", "\udfff"]),
    max_size=200,
).map("".join)


def _feed(blocks: list[Block], summary: str = "Blocker Privat", ttl_seconds: int = 900) -> bytes:
    return emit(
        blocks,
        summary=summary,
        salt="prop-salt",
        ttl_seconds=ttl_seconds,
        version="0.1.2",
        now=YEAR_START,
        dtstamps={},
    )


def _pipeline(blocks: list[Block], win: Window, grid: int) -> bytes:
    return _feed(merge(round_to_grid(clip(blocks, win), grid, BERLIN)))


@given(st.data(), mixed_blocks(), GRIDS)
def test_the_pure_pipeline_is_deterministic_prop_7(
    data: st.DataObject, blocks: list[Block], grid: int
) -> None:
    feed = _pipeline(blocks, WINDOW, grid)
    assert _pipeline(blocks, WINDOW, grid) == feed
    assert _pipeline(data.draw(st.permutations(blocks)), WINDOW, grid) == feed


@given(mixed_blocks())
def test_the_feed_reparses_to_the_merged_blocks_prop_8(blocks: list[Block]) -> None:
    merged = merge(blocks)
    # The MVP emits tentative blocks as plain busy (FR-14), so the flag does not survive.
    assert parse_feed(_feed(merged)) == [replace(b, tentative=False) for b in merged]


@given(mixed_blocks(max_size=2))
def test_uid_identifies_kind_and_span_prop_9(pair: list[Block]) -> None:
    for block in pair:
        assert re.fullmatch(r"[0-9a-f]{32}@milchglas", uid("s", block))
    if len(pair) == 2:
        a, b = pair
        same = (type(a), a.start, a.end) == (type(b), b.start, b.end)
        assert (uid("s", a) == uid("s", b)) is same


@given(mixed_blocks(), GRIDS)
def test_every_generated_feed_holds_the_invariants_prop_10(blocks: list[Block], grid: int) -> None:
    assert_feed_invariants(_pipeline(blocks, WINDOW, grid))


@given(SUMMARIES)
def test_any_summary_is_either_refused_or_survives_a_reparse(summary: str) -> None:
    if _unsafe(summary):
        with pytest.raises(ValueError, match="summary"):
            _feed([], summary)
        return
    feed = _feed([TimedBlock(WINDOW.start, WINDOW.end)], summary)
    assert summaries(feed) == [summary]
    assert_feed_invariants(feed, forbidden=())


# RFC 5545 §3.3.6 dur-value, written out from the ABNF.
_TIME_PART = r"T(?:\d+H(?:\d+M(?:\d+S)?)?|\d+M(?:\d+S)?|\d+S)"
DUR_VALUE = re.compile(rf"[+-]?P(?:\d+W|\d+D(?:{_TIME_PART})?|{_TIME_PART})")
_SECONDS = {"H": 3600, "M": 60, "S": 1}


@given(st.integers(min_value=1, max_value=10**7))
def test_every_emitted_ttl_is_a_dur_value_of_the_configured_seconds(ttl_seconds: int) -> None:
    hints = [
        line.partition(":")[2]
        for line in logical_lines(_feed([], ttl_seconds=ttl_seconds))
        if line.startswith(("REFRESH-INTERVAL", "X-PUBLISHED-TTL"))
    ]
    assert len(hints) == 2  # the two refresh hints of FR-7
    for hint in hints:
        assert DUR_VALUE.fullmatch(hint), hint
        said = sum(int(n) * _SECONDS[unit] for n, unit in re.findall(r"(\d+)([HMS])", hint))
        assert said == ttl_seconds
