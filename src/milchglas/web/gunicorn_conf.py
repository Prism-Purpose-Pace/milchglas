"""gunicorn settings, read with `--config python:milchglas.web.gunicorn_conf` (NFR-S5, WEB-21).

The access log is off, but gunicorn's error log still quotes a malformed request line
and the URI of a request whose handler raised, before the WSGI app sees either; both can
carry the feed token. `on_starting` installs a filter on gunicorn's loggers in the
master, before any worker forks, so every worker inherits it. The other settings stay as
flags on the image's command line.
"""

import logging
import re
from typing import override

_FEED = re.compile(r"/f/[^\s'\"]*")
_WITHHELD = "/f/[withheld]"
# gunicorn 26 (workers/base.py, handle_error): the first quotes the parser exception,
# which holds the raw request line; the second is logged with the method and the URI.
_CONSTANT = (
    ("Invalid request from ip=", "Invalid request; the request line is withheld"),
    ("Error handling request", "Error handling request; the URI is withheld"),
)


class RequestRedaction(logging.Filter):
    """Rewrites a record in place; it never drops one."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for prefix, constant in _CONSTANT:
            if message.startswith(prefix):
                message = constant
                break
        else:
            message = _FEED.sub(_WITHHELD, message)
        record.msg, record.args = message, ()
        if record.exc_info:
            # The traceback stays, as text with any feed path withheld.
            text = logging.Formatter().formatException(record.exc_info)
            record.exc_text, record.exc_info = _FEED.sub(_WITHHELD, text), None
        return True


def on_starting(server: object) -> None:  # noqa: ARG001  (gunicorn's hook signature)
    """The gunicorn hook: install the filter once on its error and access loggers."""
    for name in ("gunicorn.error", "gunicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RequestRedaction) for f in logger.filters):
            logger.addFilter(RequestRedaction())
