"""gunicorn's own error log never quotes the feed token (WEB-21, NFR-S5).

gunicorn logs a malformed request line, and the URI of a request whose handler raised,
before the WSGI app can see either. Both can carry the token, so the filter installed by
`milchglas.web.gunicorn_conf` replaces those messages with constant text.
"""

import json
import logging
import os
import re
import selectors
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from milchglas.web.gunicorn_conf import RequestRedaction, on_starting

# A synthetic value shaped like a feed token (43 URL-safe characters), never a real one.
TOKEN = "SYNTHETICfeedTOKEN0123456789abcdefghijklmno"  # noqa: S105


def _record(msg: str, *args: object, exc: BaseException | None = None) -> logging.LogRecord:
    info = (type(exc), exc, exc.__traceback__) if exc else None
    return logging.LogRecord("gunicorn.error", logging.WARNING, __file__, 1, msg, args, info)


def _rendered(record: logging.LogRecord) -> str:
    assert RequestRedaction().filter(record)
    return logging.Formatter("%(message)s").format(record)


def test_web_21_malformed_request_line_is_withheld() -> None:
    record = _record(
        f"Invalid request from ip=192.0.2.7: Invalid HTTP request line: 'GET /f/{TOKEN}.ics'"
    )
    assert _rendered(record) == "Invalid request; the request line is withheld"


def test_web_21_failing_request_keeps_its_traceback_without_the_uri() -> None:
    def lookup() -> None:
        msg = f"lookup failed for /f/{TOKEN}.ics"
        raise OSError(msg)

    with pytest.raises(OSError, match="lookup failed") as raised:
        lookup()
    record = _record("Error handling request %s %s", "GET", f"/f/{TOKEN}.ics", exc=raised.value)
    text = _rendered(record)
    assert text.startswith("Error handling request; the URI is withheld\nTraceback")
    assert "OSError: lookup failed for /f/[withheld]" in text
    assert TOKEN not in text


@pytest.mark.parametrize(
    "message",
    [
        f"Error parsing headers: 'Referer: https://example.org/f/{TOKEN}.ics'",
        f"Request Line is too large: GET /f/{TOKEN}",
        f"something about \"/f/{TOKEN}.ics\" and '/f/{TOKEN}'",
    ],
    ids=["WEB-21-header", "WEB-21-truncated", "WEB-21-quoted"],
)
def test_web_21_any_feed_path_is_withheld(message: str) -> None:
    text = _rendered(_record("%s", message))
    assert TOKEN not in text
    assert "/f/[withheld]" in text


def test_web_21_other_messages_pass_unchanged() -> None:
    assert _rendered(_record("Booting worker with pid: %s", 7)) == "Booting worker with pid: 7"


def test_web_21_on_starting_installs_the_filter_on_both_gunicorn_loggers() -> None:
    loggers = [logging.getLogger(name) for name in ("gunicorn.error", "gunicorn.access")]
    before = [list(logger.filters) for logger in loggers]
    try:
        on_starting(object())
        on_starting(object())  # a second call adds nothing
        for logger, old in zip(loggers, before, strict=True):
            added = [f for f in logger.filters if f not in old]
            assert len(added) == 1
            assert isinstance(added[0], RequestRedaction)
    finally:
        for logger, old in zip(loggers, before, strict=True):
            logger.filters[:] = old


# --- the real gunicorn, as the image runs it -------------------------------------------


def _read_until(stream: int, pattern: re.Pattern[str], deadline: float) -> str:
    seen = ""
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        while not pattern.search(seen) and (left := deadline - time.monotonic()) > 0:
            if not selector.select(left) or not (chunk := os.read(stream, 4096)):
                break
            seen += chunk.decode("utf-8", "replace")
    return seen


@pytest.fixture
def gunicorn(tmp_path: Path) -> Iterator[tuple[subprocess.Popen[bytes], int]]:
    config = tmp_path / "config.json"
    # Any valid digest: the requests below must miss.
    config.write_text(json.dumps({"token_sha256": "0" * 64}), encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "MILCHGLAS_VAR_DIR": str(tmp_path),
        "MILCHGLAS_CONFIG": str(config),
        "MILCHGLAS_LOG_LEVEL": "DEBUG",
    }
    process = subprocess.Popen(  # noqa: S603  (fixed argv, no shell)
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--config",
            "python:milchglas.web.gunicorn_conf",
            "--bind",
            "127.0.0.1:0",
            "--workers",
            "1",
            "--log-level",
            "debug",
            "--no-control-socket",
            "--worker-tmp-dir",
            str(tmp_path),
            "milchglas.web.wsgi:create()",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        assert process.stdout is not None
        seen = _read_until(
            process.stdout.fileno(), re.compile(r"Booting worker"), time.monotonic() + 15
        )
        port = re.search(r"Listening at: http://127\.0\.0\.1:(\d+)", seen)
        assert port, seen
        yield process, int(port.group(1))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.mark.parametrize(
    "request_bytes",
    [
        f"GET /f/{TOKEN}.ics\r\n\r\n".encode(),  # no HTTP version
        f"GET /f/{TOKEN}.ics HTTP/1.1 extra\r\nHost: x\r\n\r\n".encode(),
        f"GET\t/f/{TOKEN}.ics HTTP/1.1\r\nHost: x\r\n\r\n".encode(),
        f"GET /f/{TOKEN}.ics HTTP/9.9\r\nHost: x\r\n\r\n".encode(),
    ],
    ids=["WEB-21-no-version", "WEB-21-extra-field", "WEB-21-tab", "WEB-21-bad-version"],
)
def test_web_21_gunicorn_logs_no_token_for_a_malformed_request(
    gunicorn: tuple[subprocess.Popen[bytes], int], request_bytes: bytes
) -> None:
    process, port = gunicorn
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.sendall(request_bytes)
        answer = client.recv(1024)
    assert answer.startswith(b"HTTP/1.1 400"), answer
    process.terminate()
    output, _ = process.communicate(timeout=10)
    text = output.decode("utf-8", "replace")
    assert "Invalid request; the request line is withheld" in text, text
    assert TOKEN not in text
