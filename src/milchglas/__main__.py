"""`python -m milchglas init | rotate-token | refresh [--dry-run | --loop]` (NFR-O1, D-14, Q-13).

`init` and `rotate-token` print and write no file: the operator pastes the printed members
into `config.json`, which Option B mounts read-only, and copies the token straight into the
consumer dialogs. Run them on the operator's own machine, never in a platform web terminal.

`refresh` is one idempotent run: exit 0 on success, 1 when the run failed and the last good
feed was kept, 2 when the environment is incomplete and nothing was requested.
`refresh --loop --interval 900` is the refresher: it runs until SIGTERM and exits 0.
"""

import argparse
import hashlib
import json
import logging
import os
import secrets
import signal
import sys
import threading
import urllib.parse
import zoneinfo
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from milchglas.config import config_path
from milchglas.refresh import ConfigWatch, loop, refresh
from milchglas.sources.caldav import Account

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class UsageError(ValueError):
    """The environment cannot start a run; the message names a variable, never a value."""


def main(argv: Sequence[str] | None = None) -> int:
    # A literal: -OO strips __doc__ (PYTHONOPTIMIZE=2 images).
    parser = argparse.ArgumentParser(
        prog="milchglas", description="python -m milchglas init | rotate-token"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="print a feed token, its token_sha256 and a new uid_salt")
    commands.add_parser("rotate-token", help="print a new feed token and its token_sha256")
    once = commands.add_parser("refresh", help="fetch the calendars and publish the feed once")
    once.add_argument(
        "--dry-run", action="store_true", help="print counts only; write nothing, take no lock"
    )
    once.add_argument("--loop", action="store_true", help="keep running until SIGTERM")
    once.add_argument(
        "--interval", type=int, default=900, help="seconds between runs of --loop (default 900)"
    )
    args = parser.parse_args(argv)
    if args.command == "refresh":
        if args.loop and (args.dry_run or args.interval < 1):
            parser.error("--loop needs a positive --interval and no --dry-run")
        return _refresh(
            os.environ, dry_run=args.dry_run, interval=args.interval if args.loop else None
        )
    # 256 bits from a CSPRNG (NFR-S1); only the digest goes into config.json (D-14).
    token = secrets.token_urlsafe(32)
    members = {"token_sha256": hashlib.sha256(token.encode()).hexdigest()}
    if args.command == "init":
        # A second init's salt would change every UID (Q-13): run init once, then rotate-token.
        members = {"uid_salt": secrets.token_hex(16), **members}
    pasted = ",\n".join(f"{json.dumps(key)}: {json.dumps(value)}" for key, value in members.items())
    sys.stdout.write(f"Feed token, shown once:\n{token}\n\nPaste into config.json:\n{pasted}\n")
    return 0


def _refresh(environ: Mapping[str, str], *, dry_run: bool, interval: int | None = None) -> int:
    try:
        _logging(environ)
        account = _account(environ)
        var_dir = Path(_required(environ, "MILCHGLAS_VAR_DIR"))
    except UsageError as error:
        sys.stderr.write(f"milchglas: {error}\n")
        return 2
    if interval is not None:
        stop, watch = threading.Event(), ConfigWatch()
        # SIGTERM only sets the event: a run in progress finishes its write first.
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
        return loop(
            lambda: refresh(
                config_path(environ), var_dir, account, now=datetime.now(UTC), watch=watch
            ),
            interval=interval,
            stop=stop,
        )
    try:
        report = refresh(
            config_path(environ), var_dir, account, now=datetime.now(UTC), dry_run=dry_run
        )
    except Exception:  # noqa: BLE001 - the summary line and the state already name it
        return 1
    if dry_run:
        sys.stdout.write(
            f"dry run: {report.calendars} calendars, {report.objects} objects, "
            f"{report.blocks} blocks, window {report.first_day} to {report.end_day}\n"
        )
    return 0


def _logging(environ: Mapping[str, str]) -> None:
    # Platform forms often save a set-but-empty variable; logging accepts upper case only.
    level = environ.get("MILCHGLAS_LOG_LEVEL", "").upper() or "INFO"
    if level not in logging.getLevelNamesMapping():
        msg = "MILCHGLAS_LOG_LEVEL is not a logging level name"
        raise UsageError(msg)
    logging.basicConfig(stream=sys.stdout, level=level, format=_LOG_FORMAT)


def _account(environ: Mapping[str, str]) -> Account:
    """The service user; every request goes to the origin of `CALDAV_URL` (NFR-S7)."""
    raw = _required(environ, "CALDAV_URL")
    try:
        url = urllib.parse.urlsplit(raw)
        valid = url.scheme == "https" and bool(url.hostname) and url.username is None
        origin = f"https://{url.netloc}" if valid and url.port != 0 else ""
    except ValueError:  # a port that is no number, or a malformed IPv6 literal
        origin = ""
    if not origin:
        msg = "CALDAV_URL: must be an https URL without user information"
        raise UsageError(msg)
    try:
        return Account(
            origin,
            _required(environ, "CALDAV_USER"),
            _required(environ, "CALDAV_SECRET"),
        )
    except ValueError as error:  # Account's own message names the key only
        raise UsageError(str(error)) from None


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if not value:
        msg = f"{name} is not set"
        raise UsageError(msg)
    return value


def run(argv: Sequence[str] | None = None) -> int:
    """The `python -m` entry: the pinned tzdata package decides every DST rule (DET-9)."""
    zoneinfo.reset_tzpath(to=())
    return main(argv)


if __name__ == "__main__":
    sys.exit(run())
