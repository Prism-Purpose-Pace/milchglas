"""Read and validate `config.json` (spec section 8, AC-22, D-14, D-16).

Every error names the key and never its value: the file is meant to be shareable, but a
value pasted into the wrong place (a token, a password) must not reach a log line.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeGuard
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from milchglas.core.emit import valid_text
from milchglas.core.model import grid_fits_zone

_DIGEST = re.compile(r"[0-9a-fA-F]{64}")
# The shape `init` prints, so a placeholder or hand-typed word cannot become the salt.
_SALT = re.compile(r"[0-9a-f]{32}")
_KEYS = frozenset(
    {
        "tz",
        "window_days",
        "grid_minutes",
        "summary",
        "ttl_seconds",
        "allday_mode",
        "tentative_mode",
        "owner_emails",
        "calendars",
        "token_sha256",
        "uid_salt",
    }
)
_CALENDAR_KEYS = frozenset({"href", "name", "enabled"})
_MAX_WINDOW_DAYS = 90


class ConfigError(ValueError):
    """Invalid configuration; the message names the key, never its value."""


@dataclass(frozen=True, slots=True)
class Calendar:
    href: str
    name: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class Config:
    tz: ZoneInfo
    window_days: int
    grid_minutes: int
    summary: str
    ttl_seconds: int
    allday_mode: str
    tentative_mode: str
    owner_emails: tuple[str, ...]
    calendars: tuple[Calendar, ...]
    token_sha256: str
    uid_salt: str


def config_path(environ: Mapping[str, str]) -> Path:
    """`MILCHGLAS_CONFIG`, or `config.json` in the working directory (D-16); empty means unset."""
    return Path(environ.get("MILCHGLAS_CONFIG") or "config.json")


def load(path: Path, now: datetime) -> Config:
    """The validated configuration; `now` dates the grid check of AC-22."""
    return parse(_read(path), now)


def read_digest(path: Path) -> bytes:
    """Only `token_sha256`, as 32 bytes: `web` must not fail on an unrelated key (Q-23)."""
    try:
        raw = _read(path)
    except ConfigError:
        msg = "token_sha256: config.json is missing or not valid JSON"
        raise ConfigError(msg) from None
    if not _is_object(raw):
        msg = "token_sha256: config.json is not a JSON object"
        raise ConfigError(msg)
    return bytes.fromhex(_digest(raw.get("token_sha256")))


def parse(raw: object, now: datetime) -> Config:
    if not _is_object(raw):
        msg = "config: must be a JSON object"
        raise ConfigError(msg)
    if unknown := sorted(set(raw) - _KEYS):
        msg = f"config: unknown key {unknown[0]!r}"
        raise ConfigError(msg)
    tz = _zone(_get(raw, "tz", str, "Europe/Berlin"))
    window_days = _get(raw, "window_days", int, 33)
    if not 1 <= window_days <= _MAX_WINDOW_DAYS:
        msg = f"window_days: must be between 1 and {_MAX_WINDOW_DAYS}"
        raise ConfigError(msg)
    grid_minutes = _get(raw, "grid_minutes", int, 15)
    if not grid_fits_zone(grid_minutes, tz, now):
        msg = "grid_minutes: must divide 1440 and every UTC-offset change of tz within 366 days"
        raise ConfigError(msg)
    summary = _get(raw, "summary", str, "Blocker Privat")
    if not valid_text(summary):
        msg = "summary: line breaks and control characters are not allowed"
        raise ConfigError(msg)
    ttl_seconds = _get(raw, "ttl_seconds", int, 900)
    if ttl_seconds < 1:
        msg = "ttl_seconds: must be positive"
        raise ConfigError(msg)
    uid_salt = _get(raw, "uid_salt", str)
    if not _SALT.fullmatch(uid_salt):
        msg = "uid_salt: must be the 32 hex characters `python -m milchglas init` prints"
        raise ConfigError(msg)
    return Config(
        tz=tz,
        window_days=window_days,
        grid_minutes=grid_minutes,
        summary=summary,
        ttl_seconds=ttl_seconds,
        # FR-13, FR-14: the MVP builds the busy mode only.
        allday_mode=_busy_only(raw, "allday_mode"),
        tentative_mode=_busy_only(raw, "tentative_mode"),
        owner_emails=_owners(_get(raw, "owner_emails", list)),
        calendars=_calendars(_get(raw, "calendars", list)),
        token_sha256=_digest(raw.get("token_sha256")),
        uid_salt=uid_salt,
    )


def _read(path: Path) -> object:
    try:
        raw: object = json.loads(path.read_bytes())
    except (OSError, ValueError):
        # No chained cause: a decode error carries the bytes it choked on.
        msg = "config: config.json is missing or not valid JSON"
        raise ConfigError(msg) from None
    return raw


def _is_object(raw: object) -> TypeGuard[dict[str, object]]:
    """A JSON object as `json.loads` returns it; its values are still unchecked."""
    return isinstance(raw, dict) and all(isinstance(key, str) for key in raw)


def _get[T](
    raw: dict[str, object], key: str, kind: type[T], default: T | None = None, *, where: str = ""
) -> T:
    value = raw.get(key, default)
    if value is None:
        msg = f"{where}{key}: missing key"
        raise ConfigError(msg)
    # bool is an int to Python, never to the configuration.
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        msg = f"{where}{key}: must be of type {kind.__name__}"
        raise ConfigError(msg)
    return value


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        msg = "tz: unknown time zone"
        raise ConfigError(msg) from None


def _busy_only(raw: dict[str, object], key: str) -> str:
    if _get(raw, key, str, "busy") != "busy":
        msg = f"{key}: only 'busy' is supported"
        raise ConfigError(msg)
    return "busy"


def _owners(values: list[object]) -> tuple[str, ...]:
    if not all(isinstance(value, str) for value in values):
        msg = "owner_emails: must be a list of strings"
        raise ConfigError(msg)
    return tuple(str(value) for value in values)


def _calendars(entries: list[object]) -> tuple[Calendar, ...]:
    calendars: list[Calendar] = []
    for index, entry in enumerate(entries):
        key = f"calendars[{index}]"
        if not _is_object(entry) or set(entry) != _CALENDAR_KEYS:
            msg = f"{key}: must be an object with exactly href, name and enabled"
            raise ConfigError(msg)
        calendar = Calendar(
            href=_get(entry, "href", str, where=f"{key}."),
            name=_get(entry, "name", str, where=f"{key}."),
            enabled=_get(entry, "enabled", bool, where=f"{key}."),
        )
        if calendar.href in {known.href for known in calendars}:
            # Named by index: a calendar's href and name stay out of every message (NFR-P4).
            msg = f"{key}.href: duplicate"
            raise ConfigError(msg)
        calendars.append(calendar)
    if not any(calendar.enabled for calendar in calendars):
        msg = "calendars: at least one calendar must be enabled"
        raise ConfigError(msg)
    return tuple(calendars)


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        msg = "token_sha256: must be 64 hex characters; run `python -m milchglas rotate-token`"
        raise ConfigError(msg)
    return value.lower()
