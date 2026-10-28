"""CalDAV requests with the retry rules of FR-1 and Q-15."""

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


def fetch(
    url: str, *, opener: Opener | None = None, sleep: Callable[[float], None] = time.sleep
) -> bytes:
    """One calendar's answer; timeouts and 5xx are retried, anything else fails at once."""
    opener = opener or urllib.request.build_opener()
    for wait in BACKOFF_SECONDS:
        try:
            return _request(opener, url)
        except FetchError as error:
            if not error.retryable:
                raise
        sleep(wait)
    return _request(opener, url)


def _request(opener: Opener, url: str) -> bytes:
    request = urllib.request.Request(url, method="REPORT")
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        error.close()  # the error holds the open response; the refresher must not leak it
        msg = f"HTTP {error.code}"
        # Only 5xx: a retried 401 or 429 turns a wrong password into a lockout (Q-15).
        raise FetchError(msg, retryable=error.code >= HTTPStatus.INTERNAL_SERVER_ERROR) from None
    except TimeoutError:
        msg = "timeout"
        raise FetchError(msg, retryable=True) from None
