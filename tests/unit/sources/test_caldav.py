"""Bindings of `tests/features/caldav/fetch.feature`, run against a loopback CalDAV stand-in.

The world is a real HTTP server on 127.0.0.1 that answers each request from a script and,
like Nextcloud, can challenge a request without the service user's credentials. It keeps
every request it receives. Its 207 to a check (PROPFIND) describes the calendar, by default
as a share the owner made read-only; its 207 to a query (REPORT) holds no events. The
client is the production opener behind a recorder: it notes the timeout `fetch` asks for
and passes a short one on, so a server that never answers costs a quarter second, not 10 s.

The answers to a check are synthetic, written after sabre's multistatus, until the contract
suite captures a real one from Baikal.

Two cases need no server. A refused connection is a loopback port nobody listens on, so
the kernel refuses it. A connection that times out cannot be made on loopback without
platform tricks, so the world raises `TimeoutError` where the operating system reports it,
in `socket.create_connection`, and urllib's own handling of it runs unchanged.
"""

import base64
import dataclasses
import http.client
import socket
import threading
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from email.message import Message
from http import HTTPStatus
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BufferedIOBase
from typing import NoReturn, override
from zoneinfo import ZoneInfo

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from milchglas.config import Calendar
from milchglas.core.model import Window, window
from milchglas.sources.caldav import Account, FetchError, build_opener, fetch

SHORT_TIMEOUT = 0.25  # what reaches the socket; the recorder keeps what `fetch` asked for
HANG = None  # a script entry: read the request, never answer
MIB = 2**20
CHUNK = b"x" * 2**16  # filler: the client must stop by size, before it parses anything
USER = "svc-milchglas"
SECRET = "synthetic-app-password"
CREDENTIALS = "Basic " + base64.b64encode(f"{USER}:{SECRET}".encode()).decode("ascii")
HOME = "/remote.php/dav/calendars/svc-milchglas/"
PRIVAT = Calendar(href=f"{HOME}privat_shared_by_owner/", name="Privat", enabled=True)
FAMILIE = Calendar(href=f"{HOME}familie_shared_by_owner/", name="Familie", enabled=False)
ARBEIT = Calendar(href=f"{HOME}arbeit_shared_by_owner/", name="Arbeit", enabled=True)
BERLIN = ZoneInfo("Europe/Berlin")
OWNER = "/remote.php/dav/principals/users/owner/"
SERVICE_USER = "/remote.php/dav/principals/users/svc-milchglas/"
PRINCIPALS = {"the owner": OWNER, "svc-milchglas": SERVICE_USER}
DAV = "{DAV:}"
CALDAV = "{urn:ietf:params:xml:ns:caldav}"


@dataclass(frozen=True)
class Received:
    method: str
    path: str
    headers: Message
    body: bytes


@dataclass(frozen=True)
class Description:
    """What the server says about an href in its answer to a check."""

    resource: str = "calendar"
    owner: str = OWNER
    privileges: tuple[str, ...] = ("read", "write-properties")


@dataclass
class World:
    account: Account = field(default_factory=lambda: Account("", USER, SECRET))
    calendars: tuple[Calendar, ...] = (PRIVAT,)
    window: Window = field(
        default_factory=lambda: window(datetime(2026, 10, 28, tzinfo=UTC), BERLIN, 33)
    )
    script: list[int | None] = field(default_factory=list)
    requests: list[Received] = field(default_factory=list)
    descriptions: dict[str, Description] = field(default_factory=dict)
    check_answer: bytes | None = None
    raw: bytes | None = None
    challenge: bool = False
    set_cookie: bool = False
    location: str | None = None
    body_size: int = 0
    sent_all: bool | None = None
    done: threading.Event = field(default_factory=threading.Event)
    body: bytes | None = field(default=None, repr=False)
    timeouts: list[float] = field(default_factory=list)
    waits: list[float] = field(default_factory=list)
    error: FetchError | None = None
    release: threading.Event = field(default_factory=threading.Event)


class _Server(ThreadingHTTPServer):
    def __init__(self, world: World) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.world = world


class _Handler(BaseHTTPRequestHandler):
    def do_PROPFIND(self) -> None:
        self._answer()

    def do_REPORT(self) -> None:
        self._answer()

    def do_GET(self) -> None:
        """What a client that follows a 301 or 302 sends instead."""
        self._answer()

    def _answer(self) -> None:
        assert isinstance(self.server, _Server)
        world = self.server.world
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        world.requests.append(Received(self.command, self.path, self.headers, body))
        if world.challenge and self.headers.get("Authorization") != CREDENTIALS:
            # Nextcloud's answer to a request without valid credentials.
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Nextcloud", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if world.raw is not None:
            self.wfile.write(world.raw)  # bytes no well-behaved server would send
            self.close_connection = True
            return
        # A request the script did not plan for gets a 207, as from a healthy server.
        answer = world.script.pop(0) if world.script else 207
        if answer is HANG:
            world.release.wait()
            return
        self.send_response(answer)
        if world.set_cookie:
            self.send_header("Set-Cookie", "nc_session_id=synthetic; Path=/; HttpOnly")
        if world.location:
            self.send_header("Location", world.location)
        if world.body_size and self.command == "REPORT":
            # No length: the body ends when the server closes the connection.
            self.end_headers()
            world.sent_all = _stream(self.wfile, world.body_size)
            world.done.set()
            return
        body = b""
        if answer == HTTPStatus.MULTI_STATUS and self.command == "PROPFIND":
            description = world.descriptions.get(self.path, Description())
            body = world.check_answer or _check_answer(self.path, description)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @override
    def log_message(self, *args: object) -> None:
        """Keep the server out of the test output."""


def _check_answer(href: str, description: Description) -> bytes:
    calendar = "<cal:calendar/>" if description.resource == "calendar" else ""
    privileges = "".join(
        f"<d:privilege><d:{name}/></d:privilege>" for name in description.privileges
    )
    return _multistatus(
        href,
        f"<d:resourcetype><d:collection/>{calendar}</d:resourcetype>"
        f"<d:owner><d:href>{description.owner}</d:href></d:owner>"
        f"<d:current-user-principal><d:href>{SERVICE_USER}</d:href></d:current-user-principal>"
        f"<d:current-user-privilege-set>{privileges}</d:current-user-privilege-set>",
    )


def _multistatus(href: str, found: str, missing: str = "", *, responses: int = 1) -> bytes:
    """The response for `href`: the found properties under 200, the missing ones under 404."""
    not_found = (
        f"<d:propstat><d:prop>{missing}</d:prop><d:status>HTTP/1.1 404 Not Found</d:status>"
        "</d:propstat>"
        if missing
        else ""
    )
    response = (
        f"<d:response><d:href>{href}</d:href>"
        f"<d:propstat><d:prop>{found}</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>"
        f"{not_found}</d:response>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">'
        f"{response * responses}</d:multistatus>"
    ).encode()


def _stream(wfile: BufferedIOBase, size: int) -> bool:
    """Write `size` bytes of filler; False when the client hung up first."""
    try:
        wfile.writelines(CHUNK for _ in range(size // len(CHUNK)))
    except OSError:
        return False
    return True


class _RecordingOpener:
    def __init__(self, world: World) -> None:
        self.world = world
        self.inner = build_opener()

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> HTTPResponse:
        self.world.timeouts.append(timeout)
        response: HTTPResponse = self.inner.open(fullurl, timeout=SHORT_TIMEOUT)
        return response


def _serve(world: World) -> Iterator[World]:
    server = _Server(world)
    threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True).start()
    world.account = dataclasses.replace(
        world.account, origin=f"http://127.0.0.1:{server.server_port}"
    )
    yield world
    world.release.set()
    server.shutdown()
    server.server_close()


@pytest.fixture
def world() -> Iterator[World]:
    yield from _serve(World())


@pytest.fixture
def second() -> Iterator[World]:
    """A second server, the target of a redirect; it would answer 207."""
    yield from _serve(World(script=[207]))


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


@scenario("caldav/fetch.feature", "The first request already carries the credentials")
def test_orch_fetch_9_first_request_carries_the_credentials() -> None:
    """A client that waits for the 401 challenge sends every request twice (FR-1)."""


@scenario("caldav/fetch.feature", "A cookie the server sets is not sent back")
def test_orch_fetch_9_cookie_is_not_sent_back() -> None:
    """The HTTP client keeps no cookies (FR-1): the same opener serves the whole run."""


@scenario("caldav/fetch.feature", "An answer over 16 MiB is cut off mid-stream")
def test_orch_fetch_4_answer_over_16_mib_is_cut_off() -> None:
    """An endless body must neither exhaust memory nor hold the run (Q-15, T-04)."""


@scenario("caldav/fetch.feature", "An answer of exactly 16 MiB is read whole")
def test_orch_fetch_4_answer_of_16_mib_is_read_whole() -> None:
    """The limit is 16 MiB, not less (Q-15)."""


@scenario("caldav/fetch.feature", "A redirect ends the fetch without following it")
def test_orch_fetch_5_redirect_is_not_followed() -> None:
    """A followed redirect resends the credentials wherever the server points (T-03)."""


@scenario("caldav/fetch.feature", "The query covers the window in UTC")
def test_orch_fetch_7_query_covers_the_window_in_utc() -> None:
    """sabre runs a calendar-query only at Depth 1 (FR-1)."""


@scenario("caldav/fetch.feature", "Only enabled calendars are asked, in configuration order")
def test_orch_fetch_7_only_enabled_calendars_in_order() -> None:
    """A disabled calendar is neither asked nor counted (FR-1)."""


@scenario("caldav/fetch.feature", "A calendar the service user must not read from ends the fetch")
def test_orch_fetch_8_refused_calendar_ends_the_fetch() -> None:
    """The check before each query keeps an href that is no read-only share out (NFR-S3)."""


@scenario("caldav/fetch.feature", "A calendar the owner shares read-only is fetched")
def test_orch_fetch_8_read_only_share_is_fetched() -> None:
    """Nextcloud's read-only share holds write-properties and passes (FR-1)."""


@pytest.mark.parametrize(
    "location",
    [None, "/calendars/other/", "http://[::1/", "http://ev\x1bil.example/"],
    ids=["none", "relative", "malformed-ipv6", "control-character"],
)
def test_orch_fetch_5_redirect_error_names_no_unreadable_host(
    world: World, location: str | None
) -> None:
    """Only a readable host from the untrusted `Location` reaches the error (NFR-P4)."""
    world.script = [307]
    world.location = location
    with pytest.raises(FetchError) as caught:
        list(fetch(world.account, world.calendars, world.window, opener=_RecordingOpener(world)))
    assert str(caught.value) == "calendars[0]: HTTP 307 redirect"


FOUND = (
    "<d:resourcetype><d:collection/><cal:calendar/></d:resourcetype>"
    f"<d:owner><d:href>{OWNER}</d:href></d:owner>"
    f"<d:current-user-principal><d:href>{SERVICE_USER}</d:href></d:current-user-principal>"
)
READ_ONLY = "<d:current-user-privilege-set><d:privilege><d:read/></d:privilege></d:current-user-privilege-set>"


@pytest.mark.parametrize(
    ("answer", "refusal"),
    [
        (b'<d:multistatus xmlns:d="DAV:"/>', "not a calendar"),
        (_multistatus(PRIVAT.href, FOUND + READ_ONLY, responses=2), "not a calendar"),
        (_multistatus(PRIVAT.href, FOUND, "<d:current-user-privilege-set/>"), "privileges unknown"),
        (
            _multistatus(
                PRIVAT.href, FOUND.split("<d:owner>", maxsplit=1)[0] + READ_ONLY, "<d:owner/>"
            ),
            "owner unknown",
        ),
        (
            _multistatus(
                PRIVAT.href,
                FOUND.split("<d:current-user-principal>", maxsplit=1)[0] + READ_ONLY,
                "<d:current-user-principal/>",
            ),
            "owner unknown",
        ),
        (
            _check_answer(PRIVAT.href, Description(privileges=("read", "all"))),
            "writable by the service user",
        ),
        (
            _check_answer(PRIVAT.href, Description(privileges=("read", "bind"))),
            "writable by the service user",
        ),
        (
            b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY e "x">]><d:multistatus xmlns:d="DAV:"/>',
            "check answer declares a DOCTYPE",
        ),
        (b'<d:multistatus xmlns:d="DAV:">', "check answer is not well-formed XML"),
    ],
    ids=[
        "no-response",
        "two-responses",
        "privileges-not-found",
        "owner-not-found",
        "principal-not-found",
        "all",
        "bind",
        "doctype",
        "not-xml",
    ],
)
def test_orch_fetch_8_check_fails_closed(world: World, answer: bytes, refusal: str) -> None:
    """A check answer that does not prove a read-only share refuses the calendar (FR-1)."""
    world.check_answer = answer
    with pytest.raises(FetchError) as caught:
        list(fetch(world.account, world.calendars, world.window, opener=_RecordingOpener(world)))
    assert str(caught.value) == f"calendars[0]: {refusal}"
    assert [r.method for r in world.requests] == ["PROPFIND"]


@pytest.mark.parametrize(
    ("raw", "broken"),
    [
        (b"HTTP/1.1 OOPS \x1b[31mSynthetic title\r\n\r\n", "BadStatusLine"),
        (
            (
                b"HTTP/1.1 207 Multi-Status\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"40\r\nBEGIN:VEVENT\r\nSUMMARY:Synthetic title\r\n"
            ),
            "IncompleteRead",
        ),
        (b"HTTP/1.1 207 Multi-Status\r\n" + b"X-Filler: 1\r\n" * 101 + b"\r\n", "HTTPException"),
        (b"", "RemoteDisconnected"),
    ],
    ids=["bad-status-line", "cut-chunked-body", "too-many-headers", "no-answer"],
)
def test_orch_fetch_12_broken_answer_names_only_its_class(
    world: World, raw: bytes, broken: str
) -> None:
    """http.client keeps the server's bytes in its errors; none of them leaves (NFR-P4)."""
    world.raw = raw
    with pytest.raises(FetchError) as caught:
        list(fetch(world.account, world.calendars, world.window, opener=_RecordingOpener(world)))
    assert str(caught.value) == f"calendars[0]: connection failed: {broken}"
    chain: BaseException | None = caught.value
    while chain is not None:
        assert "Synthetic title" not in repr(chain.args)
        chain = chain.__cause__ or chain.__context__
    assert len(world.requests) == 1


@pytest.mark.parametrize("key", ["CALDAV_USER", "CALDAV_SECRET"])
def test_orch_fetch_12_credential_utf8_cannot_encode_is_refused(key: str) -> None:
    """A secret read with surrogateescape would sit whole in a UnicodeEncodeError (NFR-S2)."""
    unencodable = "p\udcfcss-synthetic"
    user, secret = (unencodable, SECRET) if key == "CALDAV_USER" else (USER, unencodable)
    with pytest.raises(ValueError, match=f"^{key}: ") as caught:
        Account("http://127.0.0.1:1", user, secret)
    assert unencodable not in repr(caught.value)
    assert caught.value.__context__ is None


def test_orch_fetch_12_debug_level_never_reaches_the_wire_log(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A process-wide http.client debug level would print the Basic credential (T-10)."""
    monkeypatch.setattr(http.client.HTTPConnection, "debuglevel", 1)
    list(fetch(world.account, world.calendars, world.window, opener=_RecordingOpener(world)))
    out = capsys.readouterr().out
    assert "Authorization" not in out
    assert CREDENTIALS.split()[1] not in out


def test_orch_fetch_4_check_answer_over_64_kib_is_refused_before_parsing(world: World) -> None:
    """A Depth 0 answer is under 2 KiB; 16 MiB of elements would take some 600 MiB to parse."""
    world.check_answer = (
        b'<d:multistatus xmlns:d="DAV:">' + b'<a b=""/>' * 8000 + b"</d:multistatus>"
    )
    with pytest.raises(FetchError) as caught:
        list(fetch(world.account, world.calendars, world.window, opener=_RecordingOpener(world)))
    assert str(caught.value) == "calendars[0]: check answer over 64 KiB"


def _never_connects(*_args: object, **_kwargs: object) -> NoReturn:
    msg = "timed out"  # the text the socket module itself gives a timeout
    raise TimeoutError(msg)


@given(parsers.parse("the server answers {status:d}"))
def server_answers(world: World, status: int) -> None:
    world.script = [status]


@given(parsers.parse("the server answers {status:d} and then 207"))
def server_answers_then_207(world: World, status: int) -> None:
    world.script = [status]


@given(parsers.parse("the server lets every {stage} time out"))
def server_lets_stage_time_out(world: World, stage: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if stage == "connection":
        monkeypatch.setattr(socket, "create_connection", _never_connects)
    else:
        world.script = [HANG, HANG, HANG, HANG]


@given("the server challenges every request without the service user's credentials")
def server_challenges(world: World) -> None:
    world.challenge = True


@given("the server answers 503 with a session cookie and then 207")
def server_sets_cookie_then_207(world: World) -> None:
    world.set_cookie = True
    world.script = [503]


@given(parsers.parse("the server answers {status:d} pointing to a second server"))
def server_redirects(world: World, second: World, status: int) -> None:
    world.script = [status]
    # Another name for the loopback host, so the error can only name it from the Location.
    world.location = second.account.origin.replace("127.0.0.1", "localhost") + PRIVAT.href


@given("the server answers 207 with 64 MiB of calendar data and no length")
def server_streams_64_mib(world: World) -> None:
    world.body_size = 64 * MIB


@given("the server answers 207 with 16 MiB of calendar data and no length")
def server_streams_16_mib(world: World) -> None:
    world.body_size = 16 * MIB


@given("the server refuses every connection")
def server_refuses(world: World) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    world.account = dataclasses.replace(world.account, origin=f"http://127.0.0.1:{port}")


@given("the window runs from 2026-10-20 to 2026-11-22 in Europe/Berlin")
def window_across_summer_time_end(world: World) -> None:
    world.window = window(datetime(2026, 10, 20, 9, tzinfo=UTC), BERLIN, 33)
    assert (world.window.first_day, world.window.end_day) == (
        date(2026, 10, 20),
        date(2026, 11, 22),
    )


@given("the configuration lists Privat enabled, Familie disabled and Arbeit enabled")
def three_calendars(world: World) -> None:
    world.calendars = (PRIVAT, FAMILIE, ARBEIT)


@given(
    parsers.parse("the server describes {name} as a {resource} owned by {owner} with {privileges}")
)
def server_describes(world: World, name: str, resource: str, owner: str, privileges: str) -> None:
    href = {"Privat": PRIVAT.href, "Arbeit": ARBEIT.href}[name]
    world.descriptions[href] = Description(
        resource, PRINCIPALS[owner], tuple(privileges.split(", "))
    )


@when("the client fetches one calendar")
@when("the client fetches the calendars")
def client_fetches(world: World) -> None:
    try:
        for _index, body in fetch(
            world.account,
            world.calendars,
            world.window,
            opener=_RecordingOpener(world),
            sleep=world.waits.append,
        ):
            world.body = body
    except FetchError as error:
        world.error = error


@then(parsers.parse("the fetch fails naming status {status:d}"))
def fails_naming_status(world: World, status: int) -> None:
    assert world.error is not None
    assert str(status) in str(world.error)


@then(parsers.parse("the fetch fails naming status {status:d} and the second server's host"))
def fails_naming_status_and_host(world: World, status: int) -> None:
    assert world.error is not None
    assert str(status) in str(world.error)
    assert "localhost" in str(world.error)


@then("the second server received no request")
def second_received_none(second: World) -> None:
    assert second.requests == []


@then("the fetch fails naming the 16 MiB limit")
def fails_naming_limit(world: World) -> None:
    assert world.error is not None
    assert "16 MiB" in str(world.error)


@then("the fetch succeeds with all 16 MiB")
def succeeds_with_16_mib(world: World) -> None:
    assert world.error is None
    assert world.body is not None
    assert len(world.body) == 16 * MIB


@then("the server could not send the whole answer")
def server_cut_off(world: World) -> None:
    assert world.done.wait(5)
    assert world.sent_all is False


@then("the server received exactly 1 request")
def received_one(world: World) -> None:
    assert len(world.requests) == 1


@then("the server received exactly 1 query")
def received_one_query(world: World) -> None:
    assert [r.method for r in world.requests].count("REPORT") == 1


@then("the fetch succeeds after one retry")
def succeeds_after_one_retry(world: World) -> None:
    assert world.error is None
    assert [r.method for r in world.requests] == ["PROPFIND", "PROPFIND", "REPORT"]


@then("the fetch succeeds after one check and one query")
def succeeds_after_check_and_query(world: World) -> None:
    assert world.error is None
    assert [(r.method, r.headers.get("Depth")) for r in world.requests] == [
        ("PROPFIND", "0"),
        ("REPORT", "1"),
    ]


@then("no request reached the server without the credentials")
def no_request_without_credentials(world: World) -> None:
    assert [r.headers.get("Authorization") for r in world.requests] == [CREDENTIALS] * 2


@then("no request reached the server with a cookie")
def no_request_with_cookie(world: World) -> None:
    assert [r.headers.get("Cookie") for r in world.requests] == [None] * 3


@then(parsers.parse("the fetch fails naming calendars[2] as {refusal}"))
def fails_naming_calendar_2(world: World, refusal: str) -> None:
    assert world.error is not None
    assert str(world.error) == f"calendars[2]: {refusal}"


@then("the server received no query for Arbeit")
def no_query_for_arbeit(world: World) -> None:
    assert ("REPORT", ARBEIT.href) not in [(r.method, r.path) for r in world.requests]
    assert ("PROPFIND", ARBEIT.href) in [(r.method, r.path) for r in world.requests]


@then("the server received a calendar query at depth 1")
def received_calendar_query(world: World) -> None:
    assert world.error is None
    [query] = [r for r in world.requests if r.method == "REPORT"]
    assert (query.method, query.path, query.headers.get("Depth")) == ("REPORT", PRIVAT.href, "1")
    assert ET.fromstring(query.body).tag == f"{CALDAV}calendar-query"


@then(
    "it asked for the events from 20261019T220000Z to 20261121T230000Z, "
    "expanded over the same range"
)
def asked_for_the_window(world: World) -> None:
    [report] = [r for r in world.requests if r.method == "REPORT"]
    query = ET.fromstring(report.body)
    comp = query.find(f"{CALDAV}filter/{CALDAV}comp-filter[@name='VCALENDAR']")
    assert comp is not None
    time_range = comp.find(f"{CALDAV}comp-filter[@name='VEVENT']/{CALDAV}time-range")
    expand = query.find(f"{DAV}prop/{CALDAV}calendar-data/{CALDAV}expand")
    window_in_utc = {"start": "20261019T220000Z", "end": "20261121T230000Z"}
    assert time_range is not None
    assert time_range.attrib == window_in_utc
    assert expand is not None
    assert expand.attrib == window_in_utc


@then("the server received queries for Privat and then Arbeit")
def asked_privat_then_arbeit(world: World) -> None:
    assert world.error is None
    assert [(r.method, r.path) for r in world.requests if r.method == "REPORT"] == [
        ("REPORT", PRIVAT.href),
        ("REPORT", ARBEIT.href),
    ]


@then("the server received no request for Familie")
def nothing_for_familie(world: World) -> None:
    assert FAMILIE.href not in [r.path for r in world.requests]


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
