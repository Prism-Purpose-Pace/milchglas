"""Entry point of options A and B: `gunicorn 'milchglas.web.wsgi:create()'` (D-13, D-16).

The CALDAV_* refusal lives here and not in FeedApp, so a Passenger entry point (option C)
can reuse the app unchanged.
"""

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from milchglas.config import config_path
from milchglas.web.app import FeedApp


class StartupError(RuntimeError):
    """`web` refuses to start; the message names a variable, never a value."""


def create(environ: Mapping[str, str] = os.environ) -> FeedApp:
    if leaked := sorted(name for name in environ if name.startswith("CALDAV_")):
        msg = f"{leaked[0]} is set: web serves files and never holds the CalDAV credential"
        raise StartupError(msg)
    var_dir = environ.get("MILCHGLAS_VAR_DIR")
    if not var_dir:
        msg = "MILCHGLAS_VAR_DIR is not set"
        raise StartupError(msg)
    logging.basicConfig(
        stream=sys.stdout,
        level=environ.get("MILCHGLAS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return FeedApp(var_dir=Path(var_dir), config=config_path(environ))
