"""`python -m milchglas init | rotate-token` (NFR-O1, D-14, Q-13).

Both commands print and write no file: the operator pastes the printed members into
`config.json`, which Option B mounts read-only, and copies the token straight into the
consumer dialogs. Run them on the operator's own machine, never in a platform web terminal.
"""

import argparse
import hashlib
import json
import secrets
import sys
import zoneinfo
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="milchglas", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="print a feed token, its token_sha256 and a new uid_salt")
    commands.add_parser("rotate-token", help="print a new feed token and its token_sha256")
    args = parser.parse_args(argv)
    # 256 bits from a CSPRNG (NFR-S1); only the digest goes into config.json (D-14).
    token = secrets.token_urlsafe(32)
    members = {"token_sha256": hashlib.sha256(token.encode()).hexdigest()}
    if args.command == "init":
        # A second init's salt would change every UID (Q-13): run init once, then rotate-token.
        members = {"uid_salt": secrets.token_hex(16), **members}
    pasted = ",\n".join(f"{json.dumps(key)}: {json.dumps(value)}" for key, value in members.items())
    sys.stdout.write(f"Feed token, shown once:\n{token}\n\nPaste into config.json:\n{pasted}\n")
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    """The `python -m` entry: the pinned tzdata package decides every DST rule (DET-9)."""
    zoneinfo.reset_tzpath(to=())
    return main(argv)


if __name__ == "__main__":
    sys.exit(run())
