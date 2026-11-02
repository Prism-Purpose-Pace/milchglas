"""`python -m milchglas.web.liveness`: the container health check of `web` (WEB-17).

Liveness only: any HTTP answer from `/healthz`, 200 or 503, exits 0; only no answer at all
exits 1. A stale feed answers 503, and an unhealthy container could be taken out of the
proxy's routing, while the last good feed is exactly what a source outage must keep
serving (D-7d). Freshness is the external monitor's job (AC-19).
"""

import sys
import urllib.error
import urllib.request
from collections.abc import Sequence

URL = "http://127.0.0.1:8000/healthz"
TIMEOUT_SECONDS = 3.0


def main(argv: Sequence[str] = ()) -> int:
    url = argv[0] if argv else URL
    timeout = float(argv[1]) if len(argv) > 1 else TIMEOUT_SECONDS
    try:
        with urllib.request.urlopen(url, timeout=timeout):  # noqa: S310 - a fixed local URL
            pass
    except urllib.error.HTTPError:
        return 0  # an answer, whatever its status
    except (OSError, ValueError):
        return 1  # refused, timed out or hung: nothing answers
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
