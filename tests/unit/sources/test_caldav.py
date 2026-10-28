"""Bindings of `tests/features/caldav/fetch.feature`, run against a loopback CalDAV stand-in.

The world is a real HTTP server on 127.0.0.1 that answers each request from a script, and
the real urllib opener behind a recorder: it notes the timeout `fetch` asks for and passes
a short one on, so a server that never answers costs a quarter second, not 10 s.

Two cases need no server. A refused connection is a loopback port nobody listens on, so
the kernel refuses it. A connection that times out cannot be made on loopback without
platform tricks, so the world raises `TimeoutError` where the operating system reports it,
in `socket.create_connection`, and urllib's own handling of it runs unchanged.
"""

import socket
import threading
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NoReturn, override

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from milchglas.sources.caldav import FetchError, fetch

SHORT_TIMEOUT = 0.25  # what reaches the socket; the recorder keeps what `fetch` asked for
HANG = None  # a script entry: read the request, never answer


@dataclass
class World:
    url: str = ""
    script: list[int | None] = field(default_factory=list)
    received: int = 0
    timeouts: list[float] = field(default_factory=list)
    waits: list[float] = field(default_factory=list)
    error: FetchError | None = None
    release: threading.Event = field(default_factory=threading.Event)


class _Server(ThreadingHTTPServer):
    def __init__(self, world: World) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.world = world


class _Handler(BaseHTTPRequestHandler):
    def do_REPORT(self) -> None:
        assert isinstance(self.server, _Server)
        world = self.server.world
        world.received += 1
        # A request the script did not plan for gets a 500, so a wrong retry shows in the count.
        answer = world.script.pop(0) if world.script else 500
        if answer is HANG:
            world.release.wait()
            return
        self.send_response(answer)
        self.send_header("Content-Length", "0")
        self.end_headers()

    @override
    def log_message(self, *args: object) -> None:
        """Keep the server out of the test output."""


class _RecordingOpener:
    def __init__(self, world: World) -> None:
        self.world = world
        self.inner = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> HTTPResponse:
        self.world.timeouts.append(timeout)
        response: HTTPResponse = self.inner.open(fullurl, timeout=SHORT_TIMEOUT)
        return response


@pytest.fixture
def world() -> Iterator[World]:
    world = World()
    server = _Server(world)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    world.url = f"http://127.0.0.1:{server.server_port}/calendars/demo/"
    yield world
    world.release.set()
    server.shutdown()
    server.server_close()


@scenario("caldav/fetch.feature", "A client error ends the fetch after one request")
def test_orch_fetch_2_client_error_ends_the_fetch() -> None:
    """A retried 401 or 429 would turn a wrong password into a lockout (Q-15)."""


@scenario("caldav/fetch.feature", "A server error is retried")
def test_orch_fetch_2_server_error_is_retried() -> None:
    """One 5xx followed by a good answer is a success."""


@scenario("caldav/fetch.feature", "A timeout is retried three times, then fails")
def test_orch_fetch_1_timeout_is_retried_then_fails() -> None:
    """Four attempts, 1, 2 and 4 s apart, each with the 10 s timeout of FR-1."""


@scenario("caldav/fetch.feature", "A refused connection ends the fetch after one attempt")
def test_orch_fetch_11_refused_connection_ends_the_fetch() -> None:
    """Only timeouts and 5xx are retried (FR-1, Q-15)."""


def _never_connects(*_args: object, **_kwargs: object) -> NoReturn:
    msg = "timed out"  # the text the socket module itself gives a timeout
    raise TimeoutError(msg)


@given(parsers.parse("the server answers {status:d}"))
def server_answers(world: World, status: int) -> None:
    world.script = [status]


@given(parsers.parse("the server answers {status:d} and then 207"))
def server_answers_then_207(world: World, status: int) -> None:
    world.script = [status, 207]


@given(parsers.parse("the server lets every {stage} time out"))
def server_lets_stage_time_out(world: World, stage: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if stage == "connection":
        monkeypatch.setattr(socket, "create_connection", _never_connects)
    else:
        world.script = [HANG, HANG, HANG, HANG]


@given("the server refuses every connection")
def server_refuses(world: World) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    world.url = f"http://127.0.0.1:{port}/calendars/demo/"


@when("the client fetches one calendar")
def client_fetches(world: World) -> None:
    try:
        fetch(world.url, opener=_RecordingOpener(world), sleep=world.waits.append)
    except FetchError as error:
        world.error = error


@then(parsers.parse("the fetch fails naming status {status:d}"))
def fails_naming_status(world: World, status: int) -> None:
    assert world.error is not None
    assert str(status) in str(world.error)


@then("the server received exactly 1 request")
def received_one(world: World) -> None:
    assert world.received == 1


@then("the fetch succeeds after 2 requests")
def succeeds_after_two(world: World) -> None:
    assert world.error is None
    assert world.received == 2


@then("the client waited 1 s")
def waited_once(world: World) -> None:
    assert world.waits == [1]


@then("the fetch fails as a timeout")
def fails_as_timeout(world: World) -> None:
    assert world.error is not None
    assert "timeout" in str(world.error)


@then("the client tried 4 times, each with a 10 s timeout")
def tried_four_times(world: World) -> None:
    assert world.timeouts == [10, 10, 10, 10]


@then("the fetch fails naming the refused connection")
def fails_naming_refusal(world: World) -> None:
    assert world.error is not None
    assert "refused" in str(world.error).lower()


@then("the client tried 1 time")
def tried_once(world: World) -> None:
    assert len(world.timeouts) == 1


@then("the client waited 1 s, 2 s and 4 s")
def waited_with_backoff(world: World) -> None:
    assert world.waits == [1, 2, 4]
