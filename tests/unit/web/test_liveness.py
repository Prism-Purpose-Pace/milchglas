"""The container health check: liveness only (WEB-17, FR-11, D-7d).

A stale feed answers 503 on `/healthz`, and that must not mark `web` unhealthy: the
platform's proxy could then stop routing it, and the last good feed is what a source
outage keeps serving. So any HTTP answer passes and only silence fails.
"""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import override

import pytest

from milchglas.web import liveness
from milchglas.web.liveness import main


def _server(status: int) -> ThreadingHTTPServer:
    class Answer(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        @override
        def log_message(self, format: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Answer)


@pytest.fixture(params=[200, 503, 404])
def answering(request: pytest.FixtureRequest) -> Iterator[str]:
    server = _server(request.param)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/healthz"
    server.shutdown()
    server.server_close()


def test_any_http_answer_passes_web_17(answering: str) -> None:
    assert main([answering]) == 0


def test_nothing_answering_fails_web_17() -> None:
    server = _server(200)
    url = f"http://127.0.0.1:{server.server_port}/healthz"
    server.server_close()  # the port is now free: the connection is refused

    assert main([url]) == 1


def test_a_hung_server_fails_after_the_timeout_web_17() -> None:
    server = _server(200)  # bound and listening, never accepted: the request hangs
    try:
        assert main([f"http://127.0.0.1:{server.server_port}/healthz", "0.2"]) == 1
    finally:
        server.server_close()


def test_the_default_target_is_the_local_web_port() -> None:
    assert liveness.URL == "http://127.0.0.1:8000/healthz"
