"""The feed and the health check, called as WSGI without a server (FR-9, FR-11, AC-9)."""

import ast
import base64
import builtins
import hashlib
import hmac
import io
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from milchglas.__main__ import main
from milchglas.config import ConfigError
from milchglas.state import FEED, State, write_state
from milchglas.web.app import FeedApp
from milchglas.web.wsgi import StartupError, create

# The shape `init` prints: 32 bytes, URL-safe base64 without padding.
TOKEN = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode()
WRONG = base64.urlsafe_b64encode(bytes(range(1, 33))).rstrip(b"=").decode()
DIGEST = hashlib.sha256(TOKEN.encode()).hexdigest()
BODY = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
NOW = datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
FEED_PATH = f"/f/{TOKEN}.ics"

type Response = tuple[str, list[tuple[str, str]], bytes]


@dataclass
class Clock:
    now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


@dataclass
class Site:
    var: Path
    config: Path
    clock: Clock = field(default_factory=Clock)

    def app(self) -> FeedApp:
        return FeedApp(var_dir=self.var, config=self.config, clock=self.clock)

    def write_config(self, raw: object) -> None:
        self.config.write_text(json.dumps(raw))


@pytest.fixture
def site(tmp_path: Path) -> Site:
    var, config = tmp_path / "var", tmp_path / "config.json"
    var.mkdir()
    (var / FEED).write_bytes(BODY)
    write_state(var, State(NOW - timedelta(minutes=5), None))
    built = Site(var, config)
    built.write_config({"token_sha256": DIGEST, "uid_salt": "salt"})
    return built


def call(
    app: FeedApp,
    method: str = "GET",
    path: str = "/",
    *,
    remote: str = "203.0.113.77",
    **headers: str,
) -> Response:
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "REMOTE_ADDR": remote,
        "HTTP_USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64)",
        **{f"HTTP_{name.upper()}": value for name, value in headers.items()},
    }
    seen: list[tuple[str, list[tuple[str, str]]]] = []

    def start_response(
        status: str, response_headers: list[tuple[str, str]], _exc_info: object = None
    ) -> Callable[[bytes], object]:
        seen.append((status, response_headers))
        return lambda _chunk: None

    body = b"".join(app(environ, start_response))
    status, response_headers = seen[-1]
    return status, list(response_headers), body


def header(response: Response, name: str) -> str | None:
    return dict(response[1]).get(name)


# --- the feed ----------------------------------------------------------------------------


def test_right_token_gets_the_feed_with_its_headers_web_1(site: Site) -> None:
    status, headers, body = call(site.app(), path=FEED_PATH)
    assert (status, body) == ("200 OK", BODY)
    assert dict(headers) == {
        "Content-Type": "text/calendar; charset=utf-8",
        "Content-Length": str(len(BODY)),
        "ETag": f'"{hashlib.sha256(BODY).hexdigest()}"',
        "X-Robots-Tag": "noindex",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=0",
    }


NOT_FOUND_PATHS = [
    pytest.param(f"/f/{WRONG}.ics", id="wrong-token"),
    pytest.param(f"/f/{TOKEN[:-1]}.ics", id="shorter-token"),
    pytest.param(f"/f/{TOKEN}x.ics", id="longer-token"),
    pytest.param("/f/.ics", id="empty-token"),
    pytest.param("/f/\xc3\xa4.ics", id="non-ascii-token"),
    pytest.param("/f/€.ics", id="beyond-latin-1"),
    pytest.param("/", id="root"),
    pytest.param("/f/", id="f"),
    pytest.param(f"{FEED_PATH}/x", id="below-feed"),
    pytest.param("/robots.txt", id="robots"),
    pytest.param("/f/../config.json", id="dot-config"),
    pytest.param("/f/../state", id="dot-state"),
    pytest.param("/f/../state.json", id="dot-state-json"),
    pytest.param("/f/%2e%2e%2fstate.json", id="encoded-dots"),
    pytest.param("/f/%252e%252e%252f.ics", id="double-encoded"),
    pytest.param("/f/\x00.ics", id="nul"),
    pytest.param(f"/{FEED_PATH}", id="double-slash"),
    pytest.param(f"/f/{TOKEN}.ICS", id="upper-suffix"),
    pytest.param(f"{FEED_PATH}/", id="trailing-slash"),
    pytest.param(f"{FEED_PATH};x=1", id="parameter"),
    pytest.param("/healthz/", id="healthz-slash"),
]
METHODS = ["GET", "HEAD", "OPTIONS", "POST"]
CONDITIONS: list[dict[str, str]] = [
    {},
    {"if_none_match": f'"{hashlib.sha256(BODY).hexdigest()}"'},
    {"range": "bytes=0-5"},
]


@pytest.mark.parametrize("path", NOT_FOUND_PATHS)
@pytest.mark.parametrize("method", METHODS)
def test_every_miss_is_the_identical_404_web_2_web_9(site: Site, method: str, path: str) -> None:
    app = site.app()
    baseline = call(app, method, "/no/such/path")
    assert baseline[0] == "404 Not Found"
    assert header(baseline, "X-Content-Type-Options") == "nosniff"
    assert header(baseline, "Cache-Control") == "private, max-age=0"
    assert header(baseline, "Server") is None
    for condition in CONDITIONS:
        assert call(app, method, path, **condition) == baseline


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
def test_other_methods_on_the_feed_get_the_identical_404_web_4(site: Site, method: str) -> None:
    app = site.app()
    assert call(app, method, FEED_PATH) == call(app, method, "/no/such/path")
    assert call(app, method, "/healthz") == call(app, method, "/no/such/path")


def test_head_gets_the_headers_without_the_body_web_4(site: Site) -> None:
    app = site.app()
    get, head = call(app, "GET", FEED_PATH), call(app, "HEAD", FEED_PATH)
    assert head == (get[0], get[1], b"")
    assert call(app, "HEAD", "/x") == ("404 Not Found", call(app, "GET", "/x")[1], b"")


def test_etag_answers_a_conditional_request_web_3(site: Site) -> None:
    app = site.app()
    etag = header(call(app, path=FEED_PATH), "ETag")
    assert etag is not None
    for match in (etag, f"W/{etag}", f'"other", {etag}', "*"):
        status, headers, body = call(app, path=FEED_PATH, if_none_match=match)
        assert (status, body) == ("304 Not Modified", b"")
        assert dict(headers)["ETag"] == etag
    assert call(app, path=FEED_PATH, if_none_match='"other"')[0] == "200 OK"
    (site.var / FEED).write_bytes(BODY)  # a refresh of an unchanged source
    assert header(call(app, path=FEED_PATH), "ETag") == etag


def test_missing_feed_is_the_identical_404_web_6(site: Site) -> None:
    (site.var / FEED).unlink()
    app = site.app()
    for method in ("GET", "HEAD"):
        assert call(app, method, FEED_PATH) == call(app, method, "/no/such/path")


@pytest.mark.parametrize(
    "error",
    [PermissionError(13, "denied"), IsADirectoryError(21, "directory"), OSError(5, "I/O")],
    ids=["permission", "directory", "eio"],
)
def test_unreadable_feed_is_the_identical_404_web_18(
    site: Site, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, error: OSError
) -> None:
    # An exception leaving the app would put the request path, token included, into the
    # WSGI server's error log; the app answers the identical 404 and logs a constant line.
    app = site.app()
    baseline = {method: call(app, method, "/no/such/path") for method in ("GET", "HEAD")}

    def unreadable(_self: Path) -> bytes:
        raise error

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    caplog.set_level(logging.DEBUG)
    for method in ("GET", "HEAD"):
        assert call(app, method, FEED_PATH) == baseline[method]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == [f"feed.ics unreadable ({type(error).__name__}); answering 404"] * 2
    assert not any(TOKEN[i : i + 8] in caplog.text for i in range(len(TOKEN) - 7))


def test_feed_fetch_logs_network_and_agent_class_only_web_7(
    site: Site, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    app = site.app()
    call(app, path=FEED_PATH)
    call(app, path=FEED_PATH, remote="2001:db8:1234:5678::1")
    # A dual-stack bind ([::]) hands IPv4 clients over as IPv4-mapped IPv6.
    call(app, path=FEED_PATH, remote="::ffff:198.51.100.9")
    call(app, path=FEED_PATH, remote="")
    for path in ("/no/such/path", f"/f/{WRONG}.ics", f"{FEED_PATH}/x"):
        call(app, path=path)
    served = [r.getMessage() for r in caplog.records if r.name == "milchglas.web.app"]
    assert served == [
        "feed served to 203.0.113.0/24 (mozilla)",
        "feed served to 2001:db8:1234::/48 (mozilla)",
        "feed served to 198.51.100.0/24 (mozilla)",
        "feed served to unknown (mozilla)",
    ]
    text = caplog.text
    for secret in (TOKEN, DIGEST):
        assert not any(secret[i : i + 8] in text for i in range(len(secret) - 7))


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    counts = {"compare": 0, "open": 0}
    real_compare = hmac.compare_digest

    def compare(a: bytes, b: bytes) -> bool:
        counts["compare"] += 1
        return real_compare(a, b)

    monkeypatch.setattr(hmac, "compare_digest", compare)
    return counts


@pytest.mark.parametrize("path", NOT_FOUND_PATHS)
@pytest.mark.parametrize("method", [*METHODS, "PUT"])
def test_one_comparison_and_no_file_open_before_a_404_web_8(
    site: Site, monkeypatch: pytest.MonkeyPatch, spies: dict[str, int], method: str, path: str
) -> None:
    app = site.app()
    monkeypatch.setattr(io, "open", _counting(spies, io.open))
    monkeypatch.setattr(builtins, "open", _counting(spies, builtins.open))
    for target in (path, "/no/such/path"):
        spies.update(compare=0, open=0)
        assert call(app, method, target)[0] == "404 Not Found"
        assert spies == {"compare": 1, "open": 0}
    # The timed re-read opens config.json once per tick, whatever the request presents.
    site.clock.now = NOW + timedelta(seconds=61)
    for opens in (1, 0):
        spies.update(compare=0, open=0)
        assert call(app, method, path)[0] == "404 Not Found"
        assert spies == {"compare": 1, "open": opens}


def _counting(spies: dict[str, int], real: Callable[..., object]) -> Callable[..., object]:
    def opened(*args: object, **kwargs: object) -> object:
        spies["open"] += 1
        return real(*args, **kwargs)

    return opened


def test_only_the_feed_path_serves_the_feed(site: Site) -> None:
    # A digest whose preimage is a whole path: the path shape still decides, not the hash.
    site.write_config({"token_sha256": hashlib.sha256(b"/robots.txt").hexdigest()})
    app = site.app()
    assert call(app, path="/robots.txt") == call(app, path="/no/such/path")


def test_token_never_reaches_a_path(site: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    app = site.app()
    opened: list[str] = []
    real_open = io.open

    def spy(file: object, *args: object, **kwargs: object) -> object:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(io, "open", spy)
    assert call(app, path=FEED_PATH)[0] == "200 OK"
    assert opened == [str(site.var / FEED)]


# --- health ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("recorded", "status"),
    [
        (State(NOW - timedelta(minutes=59), None), "200 OK"),
        (State(NOW - timedelta(minutes=59), "TimeoutError calendar=0"), "200 OK"),
        (State(NOW - timedelta(minutes=60), None), "503 Service Unavailable"),
        (State(None, "TimeoutError calendar=0"), "503 Service Unavailable"),
        (State(NOW, None), "200 OK"),
        # A success dated ahead of web's clock is no evidence of a live refresher.
        (State(NOW + timedelta(seconds=1), None), "503 Service Unavailable"),
        (State(NOW + timedelta(hours=5), None), "503 Service Unavailable"),
    ],
)
def test_health_follows_the_last_success_web_5(site: Site, recorded: State, status: str) -> None:
    write_state(site.var, recorded)
    response = call(site.app(), "GET", "/healthz")
    assert response[0] == status
    assert response[2] == b""
    assert header(response, "Content-Length") == "0"


@pytest.mark.parametrize("content", [None, b"", b"{", b"[]"])
def test_missing_or_corrupt_state_is_unhealthy_web_5(site: Site, content: bytes | None) -> None:
    state = site.var / "state.json"
    if content is None:
        state.unlink()
    else:
        state.write_bytes(content)
    assert call(site.app(), "GET", "/healthz")[0] == "503 Service Unavailable"


def test_health_body_and_headers_do_not_change_with_the_state_web_5(site: Site) -> None:
    app = site.app()
    healthy = call(app, "GET", "/healthz")
    site.clock.now = NOW + timedelta(hours=2)
    site.write_config({"token_sha256": DIGEST})
    unhealthy = call(app, "GET", "/healthz")
    assert (healthy[1], healthy[2]) == (unhealthy[1], unhealthy[2])
    assert healthy[0] != unhealthy[0]
    assert call(app, "HEAD", "/healthz") == unhealthy


# --- the digest: start, re-read, rotation ------------------------------------------------


def test_rotation_needs_no_restart_web_12(
    site: Site, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    app = site.app()
    main(["rotate-token"])
    lines = capsys.readouterr().out.splitlines()
    new_token = lines[1]
    pasted = json.loads("{" + lines[-1] + "}")
    site.write_config({"token_sha256": pasted["token_sha256"], "uid_salt": "salt"})
    site.clock.now = NOW + timedelta(seconds=59)
    assert call(app, path=FEED_PATH)[0] == "200 OK"
    site.clock.now = NOW + timedelta(minutes=15)
    assert call(app, path=FEED_PATH) == call(app, path="/no/such/path")
    assert call(app, path=f"/f/{new_token}.ics")[0] == "200 OK"
    names = [path.name for path in tmp_path.rglob("*")]
    assert not any(token in name for token in (TOKEN, new_token) for name in names)


@pytest.mark.parametrize(
    "raw",
    [
        {"token_sha256": "ab" * 31},
        {"token_sha256": "zz" * 32},
        {"token_sha256": None},
        {"uid_salt": "salt"},
        [],
    ],
)
def test_malformed_digest_stops_the_start_web_13(site: Site, raw: object) -> None:
    site.write_config(raw)
    with pytest.raises(ConfigError, match="token_sha256"):
        site.app()


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"token_sha256": "ab" * 31}).encode(),
        json.dumps({"token_sha256": DIGEST})[:30].encode(),
        b"\xff\xfe not json",
    ],
    ids=["malformed-digest", "truncated", "unparsable"],
)
def test_failed_reread_keeps_the_last_digest_and_turns_health_503_web_14(
    site: Site, caplog: pytest.LogCaptureFixture, content: bytes
) -> None:
    app = site.app()
    site.config.write_bytes(content)
    for minute in (1, 2):
        site.clock.now = NOW + timedelta(minutes=minute)
        assert call(app, path=FEED_PATH)[0] == "200 OK"
        assert call(app, path=f"/f/{WRONG}.ics") == call(app, path="/no/such/path")
        assert call(app, "GET", "/healthz")[0] == "503 Service Unavailable"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert all("token_sha256" in message for message in warnings)
    text = "\n".join(warnings)
    for value in (DIGEST, "ab" * 31, "not json"):
        assert not any(value[i : i + 8] in text for i in range(len(value) - 7))
    site.write_config({"token_sha256": hashlib.sha256(WRONG.encode()).hexdigest()})
    site.clock.now = NOW + timedelta(minutes=3)
    assert call(app, "GET", "/healthz")[0] == "200 OK"
    assert call(app, path=f"/f/{WRONG}.ics")[0] == "200 OK"
    assert call(app, path=FEED_PATH) == call(app, path="/no/such/path")


def test_unrelated_invalid_key_does_not_touch_the_feed_web_15(site: Site) -> None:
    site.write_config({"token_sha256": DIGEST, "grid_minutes": 7, "colour": "red"})
    app = site.app()
    site.clock.now = NOW + timedelta(minutes=2)
    assert call(app, path=FEED_PATH)[0] == "200 OK"
    assert call(app, "GET", "/healthz")[0] == "200 OK"


# --- the entry point ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["CALDAV_SECRET", "CALDAV_URL", "CALDAV_USER", "CALDAV_X"])
def test_web_refuses_to_start_with_a_caldav_variable_web_10(site: Site, name: str) -> None:
    environ = {
        "MILCHGLAS_VAR_DIR": str(site.var),
        "MILCHGLAS_CONFIG": str(site.config),
        name: "BBX-SECRET",
    }
    with pytest.raises(StartupError) as caught:
        create(environ)
    assert name in str(caught.value)
    assert "BBX-SECRET" not in str(caught.value)


def test_create_reads_paths_from_the_environment(
    site: Site, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create({"MILCHGLAS_VAR_DIR": str(site.var), "MILCHGLAS_CONFIG": str(site.config)})
    assert call(app, path=FEED_PATH)[0] == "200 OK"
    monkeypatch.chdir(site.config.parent)
    assert call(create({"MILCHGLAS_VAR_DIR": str(site.var)}), path=FEED_PATH)[0] == "200 OK"
    with pytest.raises(StartupError, match="MILCHGLAS_VAR_DIR"):
        create({})


@pytest.mark.parametrize(
    ("value", "level"),
    [("debug", "DEBUG"), ("Warning", "WARNING"), ("ERROR", "ERROR"), ("", "INFO"), (None, "INFO")],
)
def test_log_level_is_read_in_any_letter_case_web_19(
    site: Site, monkeypatch: pytest.MonkeyPatch, value: str | None, level: str
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: seen.update(kwargs))
    environ = {"MILCHGLAS_VAR_DIR": str(site.var), "MILCHGLAS_CONFIG": str(site.config)}
    if value is not None:
        environ["MILCHGLAS_LOG_LEVEL"] = value
    create(environ)
    assert seen["level"] == level


@pytest.mark.parametrize("value", ["verbose", "5", "BBX-LEVEL"])
def test_unknown_log_level_refuses_the_start_web_19(site: Site, value: str) -> None:
    environ = {
        "MILCHGLAS_VAR_DIR": str(site.var),
        "MILCHGLAS_CONFIG": str(site.config),
        "MILCHGLAS_LOG_LEVEL": value,
    }
    with pytest.raises(StartupError) as caught:
        create(environ)
    assert "MILCHGLAS_LOG_LEVEL" in str(caught.value)
    assert value not in str(caught.value)


def _imports(module: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(module.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_import_scan_sees_a_module_imported_from_its_package(tmp_path: Path) -> None:
    module = tmp_path / "probe.py"
    module.write_text("from milchglas import refresh\nimport milchglas.sources.caldav\n")
    assert {"milchglas.refresh", "milchglas.sources.caldav"} <= _imports(module)


def test_web_never_reaches_the_source_side_web_11() -> None:
    src = Path(__file__).resolve().parents[3] / "src"
    pending = [f"milchglas.web.{path.stem}" for path in (src / "milchglas" / "web").glob("*.py")]
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        base = src / Path(*name.split("."))
        module = base / "__init__.py" if base.is_dir() else base.with_suffix(".py")
        if module.exists():
            pending += [n for n in _imports(module) if n.startswith("milchglas")]
    assert "milchglas.web.app" in seen
    assert "milchglas.state" in seen
    assert not [n for n in seen if n.startswith(("milchglas.sources", "milchglas.refresh"))]
