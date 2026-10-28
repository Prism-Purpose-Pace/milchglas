"""CalDAV requests with the request and retry rules of FR-1 and Q-15."""

import base64
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http import HTTPStatus
from http.client import HTTPResponse
from typing import Protocol

TIMEOUT_SECONDS = 10
BACKOFF_SECONDS = (1, 2, 4)  # Q-15: the waits before the three retries


class FetchError(Exception):
    """A fetch that failed; the message names the status or the timeout, never a URL."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class Opener(Protocol):
    """The part of `urllib.request.OpenerDirector` that `fetch` uses."""

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> HTTPResponse: ...


def build_opener() -> urllib.request.OpenerDirector:
    """The opener of every request: no cookie jar, and no proxy from the environment (NFR-S7)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


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
            return response.read()
    except urllib.error.HTTPError as error:
        error.close()  # the error holds the open response; the refresher must not leak it
        msg = f"HTTP {error.code}"
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
