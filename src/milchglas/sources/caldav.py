"""CalDAV requests with the request and retry rules of FR-1 and Q-15."""

import base64
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from http import HTTPStatus
from http.client import HTTPResponse
from typing import Protocol

TIMEOUT_SECONDS = 10
BACKOFF_SECONDS = (1, 2, 4)  # Q-15: the waits before the three retries
MAX_BYTES = 16 * 2**20  # Q-15: the largest answer read
# A host name or IP address as `urlsplit` lower-cases it; anything else stays out of the error.
_HOST = re.compile(r"[a-z0-9.:-]{1,253}")


class FetchError(Exception):
    """A fetch that failed; the message names the status or the timeout, never a URL."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


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
    url: str,
    *,
    user: str,
    secret: str,
    opener: Opener | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """One calendar's answer; timeouts and 5xx are retried, anything else fails at once."""
    opener = opener or build_opener()
    # Basic auth with the first request: urllib's auth handlers wait for a 401 first (FR-1).
    authorization = "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode("ascii")
    for wait in BACKOFF_SECONDS:
        try:
            return _request(opener, url, authorization)
        except FetchError as error:
            if not error.retryable:
                raise
        sleep(wait)
    return _request(opener, url, authorization)


def _request(opener: Opener, url: str, authorization: str) -> bytes:
    request = urllib.request.Request(url, method="REPORT")
    request.add_unredirected_header("Authorization", authorization)
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
