"""The feed and the health check as one WSGI callable (FR-9, FR-11, NFR-S1, AC-9).

The token is the feed's only credential (a capability URL), so the surface must not tell a
wrong token from an unknown path. Every request that does not get the feed gets one
identical 404, and every request outside `/healthz` passes through exactly one digest
comparison before anything else differs. The token is only hashed, never joined into a
path. The digest is re-read on a timer, never per request, so no 404 path opens a file.
"""

import hashlib
import hmac
import ipaddress
import logging
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from wsgiref.types import StartResponse, WSGIEnvironment

from milchglas.config import ConfigError, read_digest
from milchglas.state import FEED, read_state

_LOG = logging.getLogger(__name__)
_FEED_PATH = re.compile(r"/f/([^/]*)\.ics")
_STALE = timedelta(minutes=60)  # FR-11
# Well inside one refresh interval, so a rotation needs no restart (AC-20).
_REREAD = timedelta(seconds=60)
# Q-17 default: cheap hardening on every response.
_COMMON = [("X-Content-Type-Options", "nosniff"), ("Cache-Control", "private, max-age=0")]
_NOT_FOUND = b"Not Found\n"
_AGENT = re.compile(r"[A-Za-z][A-Za-z0-9.-]{0,31}")


def _now() -> datetime:
    return datetime.now(UTC)


class FeedApp:
    def __init__(
        self, *, var_dir: Path, config: Path, clock: Callable[[], datetime] = _now
    ) -> None:
        """Refuses to start (ConfigError) while `token_sha256` is malformed (WEB-13)."""
        self._var_dir = var_dir
        self._config = config
        self._clock = clock
        self._digest = read_digest(config)
        self._digest_ok = True
        self._next_read = clock() + _REREAD

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> Iterable[bytes]:
        now = self._clock()
        if now >= self._next_read:
            self._reread(now)
        method, path = environ.get("REQUEST_METHOD", ""), environ.get("PATH_INFO", "")
        readable, head = method in {"GET", "HEAD"}, method == "HEAD"
        if readable and path == "/healthz":
            return self._health(now, start_response)
        match = _FEED_PATH.fullmatch(path)
        # PEP 3333 hands the path over as latin-1, so this recovers the raw UTF-8 bytes.
        presented = (match.group(1) if match else path).encode("latin-1", "replace")
        if (
            hmac.compare_digest(hashlib.sha256(presented).digest(), self._digest)
            and match
            and readable
        ):
            return self._feed(environ, start_response, head=head)
        return _miss(start_response, head=head)

    def _reread(self, now: datetime) -> None:
        """Q-23 default (a): a failed re-read keeps the last valid digest and turns health 503."""
        self._next_read = now + _REREAD
        try:
            self._digest = read_digest(self._config)
        except ConfigError:
            self._digest_ok = False
            _LOG.warning("config.json: token_sha256 unreadable; keeping the last valid digest")
        else:
            self._digest_ok = True

    def _feed(
        self, environ: WSGIEnvironment, start_response: StartResponse, *, head: bool
    ) -> Iterable[bytes]:
        try:
            body = (self._var_dir / FEED).read_bytes()
        except FileNotFoundError:  # never refreshed yet (WEB-6)
            return _miss(start_response, head=head)
        except OSError as error:
            # An escaping exception puts the request path, token included, into the WSGI
            # server's error log (NFR-S5): answer the identical 404 instead (WEB-18).
            _LOG.warning("feed.ics unreadable (%s); answering 404", type(error).__name__)
            return _miss(start_response, head=head)
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        headers = [
            ("ETag", etag),
            ("X-Robots-Tag", "noindex"),
            ("Referrer-Policy", "no-referrer"),
            *_COMMON,
        ]
        tags = {
            tag.strip().removeprefix("W/")
            for tag in environ.get("HTTP_IF_NONE_MATCH", "").split(",")
        }
        if etag in tags or "*" in tags:
            start_response("304 Not Modified", headers)
            return [b""]
        _LOG.info(
            "feed served to %s (%s)",
            _network(environ.get("REMOTE_ADDR", "")),
            _agent(environ.get("HTTP_USER_AGENT", "")),
        )
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/calendar; charset=utf-8"),
                ("Content-Length", str(len(body))),
                *headers,
            ],
        )
        return [b"" if head else body]

    def _health(self, now: datetime, start_response: StartResponse) -> Iterable[bytes]:
        """200 or 503 with one identical empty body: no timestamps, no counts (FR-11)."""
        success = read_state(self._var_dir).last_success
        # A success dated in the future (a skewed clock) proves no live refresher.
        healthy = self._digest_ok and success is not None and timedelta(0) <= now - success < _STALE
        start_response(
            "200 OK" if healthy else "503 Service Unavailable",
            [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", "0"), *_COMMON],
        )
        return [b""]


def _miss(start_response: StartResponse, *, head: bool) -> Iterable[bytes]:
    start_response(
        "404 Not Found",
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(_NOT_FOUND))),
            *_COMMON,
        ],
    )
    return [b"" if head else _NOT_FOUND]


def _network(address: str) -> str:
    """The client's /24 (IPv4) or /48 (IPv6), never the address itself (NFR-S5)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "unknown"
    # A dual-stack bind hands IPv4 clients over as ::ffff:a.b.c.d, which /48 would erase.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    prefix = 24 if isinstance(ip, ipaddress.IPv4Address) else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def _agent(header: str) -> str:
    """The product name of the user agent, lower case: a class, not the full header."""
    match = _AGENT.match(header)
    return match.group().lower() if match else "other"
