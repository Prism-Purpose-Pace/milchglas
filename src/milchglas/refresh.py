"""One refresh run, `python -m milchglas refresh` (NFR-O1, FR-8, FR-11).

fetch, parse and reduce one calendar at a time, then clip, round, merge and emit as one
pure `build`, the atomic feed write and the state that `/healthz` reads. A failure of any
step keeps the last good feed byte for byte and records the error by class, calendar index
and HTTP status only (G5, D-7d, NFR-P4).
"""

import contextlib
import dataclasses
import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from milchglas import __version__
from milchglas.config import Calendar, Config, ConfigError, load
from milchglas.core.emit import emit, stamps
from milchglas.core.model import Block, Window, clip, merge, round_to_grid, window
from milchglas.core.reduce import MalformedEventError
from milchglas.sources.caldav import Account, FetchError, Opener, fetch
from milchglas.sources.multistatus import ParseError, parse_counted
from milchglas.state import FEED, BusyError, State, read_state, run_lock, write_atomic, write_state

_LOG = logging.getLogger(__name__)
_MULTI_STATUS = 207  # what `fetch` returned the body for; anything else raised already
# Errors whose messages this package writes without content, href or host (NFR-P4).
_OWN_MESSAGES = (ConfigError, FetchError, ParseError, MalformedEventError)


@dataclass(slots=True)
class ConfigWatch:
    """The configuration of the last run, so the next one can log what changed (AC-22)."""

    last: Config | None = field(default=None)

    def seen(self, config: Config) -> None:
        if self.last is not None and (changed := _changed_keys(self.last, config)):
            # Key names only: a value may be a pasted secret or name a calendar (NFR-P4).
            _LOG.info("config changed: %s", ", ".join(changed))
        self.last = config


@dataclass(frozen=True, slots=True)
class _Run:
    config_file: Path
    var_dir: Path
    account: Account
    now: datetime
    opener: Opener | None
    watch: ConfigWatch | None


@dataclass(slots=True)
class Report:
    """The counts of one run, the only thing logged or printed about it (NFR-P4)."""

    calendars: int = 0
    objects: int = 0
    blocks: int = 0
    first_day: date | None = None
    end_day: date | None = None  # exclusive


def refresh(  # noqa: PLR0913 - everything after `now` is a keyword-only switch
    config_file: Path,
    var_dir: Path,
    account: Account,
    *,
    now: datetime,
    opener: Opener | None = None,
    dry_run: bool = False,
    watch: ConfigWatch | None = None,
) -> Report:
    """Publish the feed for `now`, or raise and keep the last good one.

    A dry run takes no lock and writes neither feed nor state, so it works while the
    refresher runs. A run that finds the lock held raises BusyError and touches nothing.
    """
    started, outcome, report = time.monotonic(), "failed", Report()
    run = _Run(config_file, var_dir, account, now, opener, watch)
    try:
        if dry_run:
            _produce(run, report)
            outcome = "dry run"
        else:
            with run_lock(var_dir):
                _publish(run, report)
            outcome = "ok"
    except BusyError:
        outcome = "skipped, another run holds the lock"
        raise
    except Exception as error:
        outcome = f"failed ({_describe(error)})"
        raise
    finally:
        _LOG.info(
            "refresh %s: %d calendars, %d objects, %d blocks, %.2f s",
            outcome,
            report.calendars,
            report.objects,
            report.blocks,
            time.monotonic() - started,
        )
    return report


def loop(
    run_once: Callable[[], object],
    *,
    interval: float,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Run at t0, t0 + interval, ... until `stop` is set; return the exit code 0 (FR-10).

    A failed run does not end the loop: its summary line and the state already name it,
    and the last good feed stays. A run that overruns skips the slots it missed. `stop` is
    set by SIGTERM: during a run the run finishes its write first, during a wait the loop
    ends at once.
    """
    start, slot = clock(), 0
    while not stop.is_set():
        # A failure is logged and recorded by `refresh` itself; the loop goes on.
        with contextlib.suppress(Exception):
            run_once()
        slot += 1
        now = clock()
        slot = max(slot, int((now - start) // interval) + 1)
        if stop.wait(start + slot * interval - now):
            break
    return 0


def build(
    blocks: Iterable[Block], config: Config, span: Window, now: datetime, previous: bytes | None
) -> bytes:
    """The feed bytes: pure, so equal input gives equal bytes (AC-6, D-7c).

    A block that was in `previous` keeps its DTSTAMP; a new one gets `now`.
    """
    merged = merge(round_to_grid(clip(blocks, span), config.grid_minutes, config.tz))
    dtstamps = {}
    if previous is not None:
        try:
            dtstamps = stamps(previous)
        except ValueError:
            _LOG.warning(
                "previous feed unreadable; %d blocks stamped with the current time", len(merged)
            )
    return emit(
        merged,
        summary=config.summary,
        salt=config.uid_salt,
        ttl_seconds=config.ttl_seconds,
        version=__version__,
        now=now,
        dtstamps=dtstamps,
    )


def _publish(run: _Run, report: Report) -> None:
    last_success = read_state(run.var_dir).last_success
    try:
        feed = _produce(run, report)
        write_atomic(run.var_dir / FEED, feed)
    except Exception as error:
        write_state(run.var_dir, State(last_success, _describe(error)))
        raise
    # A crash before this line leaves the new feed and the old state; the next run writes
    # the same feed again and repairs the state (ORCH-WRITE-3).
    write_state(run.var_dir, State(run.now, None))


def _produce(run: _Run, report: Report) -> bytes:
    # Read on every run, so an edit applies without a restart (FR-12).
    config = load(run.config_file, run.now)
    if run.watch is not None:
        run.watch.seen(config)
    span = window(run.now, config.tz, config.window_days)
    report.first_day, report.end_day = span.first_day, span.end_day
    blocks: list[Block] = []
    for index, body in fetch(run.account, config.calendars, span, opener=run.opener):
        objects, found = parse_counted(
            body,
            calendar=index,
            status=_MULTI_STATUS,
            tz=config.tz,
            owner_emails=config.owner_emails,
        )
        # Dropped before the next request: one answer alive at a time (Q-15).
        del body
        report.calendars += 1
        report.objects += objects
        blocks += found
    feed = build(blocks, config, span, run.now, _previous(run.var_dir / FEED))
    report.blocks = feed.count(b"\r\nBEGIN:VEVENT\r\n")
    return feed


def _previous(path: Path) -> bytes | None:
    """The last published feed, or None if there is none to read."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return b""  # unreadable: `build` stamps every block now and warns


def _describe(error: Exception) -> str:
    """The state's error text: this package's own message, else the class name only."""
    if isinstance(error, _OWN_MESSAGES):
        return f"{type(error).__name__}: {error}"
    return type(error).__name__


def _changed_keys(old: Config, new: Config) -> list[str]:
    """The names of the keys whose values differ, calendars by index and member."""
    changed = [
        item.name
        for item in dataclasses.fields(Config)
        if item.name != "calendars" and getattr(old, item.name) != getattr(new, item.name)
    ]
    if len(old.calendars) != len(new.calendars):
        changed.append("calendars")
    else:
        changed += [
            f"calendars[{index}].{member.name}"
            for index, (before, after) in enumerate(zip(old.calendars, new.calendars, strict=True))
            for member in dataclasses.fields(Calendar)
            if getattr(before, member.name) != getattr(after, member.name)
        ]
    return sorted(changed)
