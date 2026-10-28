"""CalDAV requests with the request and retry rules of FR-1 and Q-15."""

import base64
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC
from http import HTTPStatus
from http.client import HTTPResponse
from io import BytesIO
from typing import NoReturn, Protocol
from xml.parsers import expat

from milchglas.config import Calendar
from milchglas.core.model import Window

TIMEOUT_SECONDS = 10
BACKOFF_SECONDS = (1, 2, 4)  # Q-15: the waits before the three retries
MAX_BYTES = 16 * 2**20  # Q-15: the largest answer read
# A host name or IP address as `urlsplit` lower-cases it; anything else stays out of the error.
_HOST = re.compile(r"[a-z0-9.:-]{1,253}")
_PROPFIND = b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:resourcetype/>
    <D:owner/>
    <D:current-user-principal/>
    <D:current-user-privilege-set/>
  </D:prop>
</D:propfind>
"""
# The privileges that let the service user change a calendar or who may (RFC 3744 section 3).
# write-properties is not among them: Nextcloud grants it to every read-only share.
_WRITING = frozenset(
    f"{{DAV:}}{name}" for name in ("all", "write", "write-content", "bind", "unbind", "write-acl")
)


class FetchError(Exception):
    """A fetch that failed; the message names the status or the timeout, never a URL."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class Account:
    """The service user on the CalDAV server: `CALDAV_URL`, `CALDAV_USER`, `CALDAV_SECRET`.

    `origin` is the scheme, host and port of `CALDAV_URL`; every request goes there (NFR-S7).
    """

    origin: str
    user: str
    secret: str = field(repr=False)


class Opener(Protocol):
    """The part of `urllib.request.OpenerDirector` that `fetch` uses."""

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> HTTPResponse: ...


def build_opener() -> urllib.request.OpenerDirector:
    """The opener of every request: HTTP(S) only, and no redirect, cookie jar or proxy.

    Without a redirect handler a 3xx falls through to the default error handler, which
    raises it as an HTTPError (NFR-S7). urllib's own redirect handler would parse
    `Location` before it refuses a REPORT, and a malformed one escapes as a bare ValueError.
    """
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.UnknownHandler(),
        urllib.request.HTTPHandler(),
        urllib.request.HTTPSHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


def fetch(
    account: Account,
    calendars: Sequence[Calendar],
    window: Window,
    *,
    opener: Opener | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[tuple[int, bytes]]:
    """Each enabled calendar's answer with its index, one at a time, in configuration order.

    One REPORT per calendar (FR-1); timeouts and 5xx are retried, anything else fails at once.
    Every href is an absolute path on the account's origin.
    """
    opener = opener or build_opener()
    query = _calendar_query(window)
    for index, calendar in enumerate(calendars):
        if not calendar.enabled:
            continue
        try:
            _check(opener, _dav_request(account, calendar.href, "PROPFIND", "0", _PROPFIND), sleep)
            answer = _send(
                opener, _dav_request(account, calendar.href, "REPORT", "1", query), sleep
            )
        except FetchError as error:
            # Named by index: a calendar's href and name stay out of every message (NFR-P4).
            msg = f"calendars[{index}]: {error}"
            raise FetchError(msg, retryable=False) from None
        yield index, answer


def _check(opener: Opener, request: urllib.request.Request, sleep: Callable[[float], None]) -> None:
    """Fail unless the href is a calendar that someone else shares read-only (FR-1, NFR-S3)."""
    if refusal := _refusal(_found(_send(opener, request, sleep))):
        raise FetchError(refusal, retryable=False)


def _found(answer: bytes) -> dict[str, ET.Element]:
    """The properties the server found for the one resource it answered for, else none."""
    responses = _tree(answer).findall("{DAV:}response")
    if len(responses) != 1:
        return {}
    return {
        prop.tag: prop
        for propstat in responses[0].iterfind("{DAV:}propstat")
        if (propstat.findtext("{DAV:}status") or "").split()[1:2] == ["200"]
        for prop in propstat.iterfind("{DAV:}prop/*")
    }


def _refusal(found: dict[str, ET.Element]) -> str | None:
    """Why the properties found show no read-only share; fails closed on a missing one."""
    resource = found.get("{DAV:}resourcetype")
    if resource is None or resource.find("{urn:ietf:params:xml:ns:caldav}calendar") is None:
        return "not a calendar"
    owner = _href(found.get("{DAV:}owner"))
    principal = _href(found.get("{DAV:}current-user-principal"))
    if owner is None or principal is None:
        return "owner unknown"
    if owner == principal:
        return "owned by the service user"
    privileges = found.get("{DAV:}current-user-privilege-set")
    if privileges is None:
        return "privileges unknown"
    if any(privilege.tag in _WRITING for privilege in privileges.iterfind("{DAV:}privilege/*")):
        return "writable by the service user"
    return None


def _href(prop: ET.Element | None) -> str | None:
    return None if prop is None else prop.findtext("{DAV:}href")


def _tree(answer: bytes) -> ET.Element:
    """The answer as elements named `{namespace}name`; a DOCTYPE is refused (Q-14).

    Without a DOCTYPE no entity can be declared, so none can expand.
    """
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(namespace_separator=" ")
    parser.StartDoctypeDeclHandler = _declaration
    parser.EntityDeclHandler = _declaration
    parser.StartElementHandler = lambda name, attributes: builder.start(_tag(name), attributes)
    parser.EndElementHandler = lambda name: builder.end(_tag(name))
    parser.CharacterDataHandler = builder.data
    try:
        parser.ParseFile(BytesIO(answer))
    except expat.ExpatError:
        msg = "check answer is not well-formed XML"
        raise FetchError(msg, retryable=False) from None
    return builder.close()


def _tag(name: str) -> str:
    namespace, _, local = name.rpartition(" ")
    return f"{{{namespace}}}{local}" if namespace else local


def _declaration(*_args: object) -> NoReturn:
    msg = "check answer declares a DOCTYPE"
    raise FetchError(msg, retryable=False)


def _calendar_query(window: Window) -> bytes:
    """Every VEVENT in the window, recurrences expanded by the server over the same range."""
    start, end = (t.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ") for t in (window.start, window.end))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <C:calendar-data><C:expand start="{start}" end="{end}"/></C:calendar-data>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT"><C:time-range start="{start}" end="{end}"/></C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>
""".encode()


def _dav_request(
    account: Account, href: str, method: str, depth: str, body: bytes
) -> urllib.request.Request:
    request = urllib.request.Request(
        account.origin + href,
        data=body,
        method=method,
        headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
    )
    # Basic auth with the first request: urllib's auth handlers wait for a 401 first (FR-1).
    # Unredirected, so no redirect could ever carry it on.
    credentials = base64.b64encode(f"{account.user}:{account.secret}".encode()).decode("ascii")
    request.add_unredirected_header("Authorization", f"Basic {credentials}")
    return request


def _send(opener: Opener, request: urllib.request.Request, sleep: Callable[[float], None]) -> bytes:
    for wait in BACKOFF_SECONDS:
        try:
            return _request(opener, request)
        except FetchError as error:
            if not error.retryable:
                raise
        sleep(wait)
    return _request(opener, request)


def _request(opener: Opener, request: urllib.request.Request) -> bytes:
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            # One byte past the limit tells an oversized answer apart; the rest is never read.
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        error.close()  # the error holds the open response; the refresher must not leak it
        msg = f"HTTP {error.code}"
        # A 3xx names where it pointed (NFR-S7).
        if HTTPStatus.MULTIPLE_CHOICES <= error.code < HTTPStatus.BAD_REQUEST:
            msg += _redirect_target(error.headers.get("Location"))
        # Only 5xx: a retried 401 or 429 turns a wrong password into a lockout (Q-15).
        raise FetchError(msg, retryable=error.code >= HTTPStatus.INTERNAL_SERVER_ERROR) from None
    except urllib.error.URLError as error:
        # urllib wraps what fails before an answer, a connect timeout included. Only the
        # timeout is retried; the reason's class names the rest, never a host (NFR-P4).
        if isinstance(error.reason, TimeoutError):
            msg = "timeout"
            raise FetchError(msg, retryable=True) from None
        msg = f"connection failed: {type(error.reason).__name__}"
        raise FetchError(msg, retryable=False) from None
    except TimeoutError:
        msg = "timeout"
        raise FetchError(msg, retryable=True) from None
    if len(body) > MAX_BYTES:
        msg = "answer over 16 MiB"  # not retried: the next try reads the same answer (Q-15)
        raise FetchError(msg, retryable=False)
    return body


def _redirect_target(location: str | None) -> str:
    """` redirect to <host>`, or ` redirect` for a relative or unreadable `Location`."""
    try:
        host = urllib.parse.urlsplit(location or "").hostname
    except ValueError:  # a malformed IPv6 literal
        host = None
    return f" redirect to {host}" if host and _HOST.fullmatch(host) else " redirect"
