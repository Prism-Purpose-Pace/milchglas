# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Judge feature files against the rubrics of D-18 (`tests/meta/judges.md`).

    uv run --script scripts/judge_features.py [FILE ...]
    uv run --script scripts/judge_features.py --calibrate tests/meta/judge-set

Without FILE it judges the feature files under tests/features/ that differ from the merge
base with origin/main (else main), untracked ones included. Each file costs one request to
the Messages API with the key in ANTHROPIC_API_KEY. While the judges are advisory, the
finding lines go into the pull request body (CONTRIBUTING.md § Pull requests). Stdlib only,
like every script here: the call is one HTTPS POST.

--calibrate measures S1 of D-18 for each judge over a labelled set: `<judge>--defect-NN.feature`
holds one seeded defect of that judge, `clean-NN.feature` none for any judge. A judge passes
when it flags at least 26 of every 30 defect files and at most 3 of every 30 clean files, on at
least 30 of each.

No server-side fallback: a refusal stops the run, because an answer from another model would
not be the model the calibration measured. A change of MODEL or of the rubric reruns it.

A section of the rubric says `Status: advisory` or `Status: blocking`; a judge turns blocking
once it passes the calibration. `--blocking` (the push stage) fails only on a finding of a
blocking judge, and with no blocking judge it passes at once, without a key or a request.

Exit codes: 0 judged (advisory findings are advice) or every judge passed; 1 a blocking judge
found something, or a judge failed the calibration; 2 a usage, rubric, git or API error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, override

API = "https://api.anthropic.com/v1/messages"
VERSION = "2026-10-21"
MODEL = "claude-opus-5-5"
ROOT = Path(__file__).resolve().parents[1]
RUBRIC = Path("tests/meta/judges.md")
FEATURES = Path("tests/features")
SECTION = re.compile(r"^## (judge-[a-z]+)\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
SEED = re.compile(r"(?:(judge-[a-z]+)--defect|clean)-\d+\.feature")
STATUS = re.compile(r"^Status: (advisory|blocking)$", re.MULTILINE)
SEEDS, FOUND, FALSE = 30, 26, 3  # S1: per 30 seeds, at least 26 found and at most 3 false
INSTRUCTION = """\
You review one Gherkin feature file against the rubrics below. Report a finding only where a
rubric's Flag list clearly applies; when in doubt, report nothing. A finding names the judge,
the line number printed before `|`, and one sentence why. A file with no defect gets an empty
list."""

type Post = Callable[[dict[str, Any]], dict[str, Any]]


class JudgeError(Exception):
    """A rubric, git or API failure: the run cannot judge, so it must not pass."""


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    judge: str
    reason: str

    @override
    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.judge}: {self.reason}"


def rubrics(text: str) -> dict[str, str]:
    """Each `## judge-<name>` section of the rubric file, by judge."""
    found = {match[1]: match[2].strip() for match in SECTION.finditer(text)}
    if not found:
        msg = "the rubric holds no `## judge-<name>` section"
        raise JudgeError(msg)
    return found


def blocking(rubric: Mapping[str, str]) -> set[str]:
    """The judges whose section says `Status: blocking`; each section must state a status."""
    found: set[str] = set()
    for name, text in rubric.items():
        if not (match := STATUS.search(text)):
            msg = f"{name} has no `Status: advisory` or `Status: blocking` line"
            raise JudgeError(msg)
        if match[1] == "blocking":
            found.add(name)
    return found


def sender(environ: Mapping[str, str]) -> Post:
    """The real API call, with the key from the environment; no key, no run."""
    if not (key := environ.get("ANTHROPIC_API_KEY", "")):
        msg = "ANTHROPIC_API_KEY is not set: the judges need it (CI never runs them)"
        raise JudgeError(msg)
    return partial(post, key=key)


def request(feature: str, rubric: Mapping[str, str]) -> dict[str, Any]:
    """The Messages API body that judges one feature file; findings come back as JSON."""
    numbered = "\n".join(f"{n:>4}| {line}" for n, line in enumerate(feature.splitlines(), 1))
    sections = "\n\n".join(
        f"## {name}\n{STATUS.sub('', text).strip()}" for name, text in rubric.items()
    )
    finding = {
        "type": "object",
        "properties": {
            "judge": {"type": "string", "enum": list(rubric)},
            "line": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["judge", "line", "reason"],
        "additionalProperties": False,
    }
    schema = {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": finding}},
        "required": ["findings"],
        "additionalProperties": False,
    }
    return {
        "model": MODEL,
        "max_tokens": 16000,
        "system": f"{INSTRUCTION}\n\n{sections}",
        "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        "messages": [{"role": "user", "content": numbered}],
    }


def post(
    body: dict[str, Any], key: str, opener: Callable[..., Any] = urllib.request.urlopen
) -> dict[str, Any]:
    """Send one request; an HTTP error becomes a JudgeError that names the status, never the key."""
    headers = {"content-type": "application/json", "x-api-key": key, "anthropic-version": VERSION}
    call = urllib.request.Request(
        API, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with opener(call, timeout=600) as response:
            answer: dict[str, Any] = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        msg = f"the Messages API answered {error.code}: {detail}"
        raise JudgeError(msg) from None
    except urllib.error.URLError as error:
        msg = f"the Messages API is unreachable: {error.reason}"
        raise JudgeError(msg) from None
    return answer


def findings(file: str, answer: Mapping[str, Any], judges: Sequence[str]) -> list[Finding]:
    """The findings of one answer; any stop but end_turn means no verdict."""
    if answer.get("stop_reason") != "end_turn":
        msg = f"{file}: the model stopped with {answer.get('stop_reason')!r}, no verdict"
        raise JudgeError(msg)
    text = "".join(block["text"] for block in answer["content"] if block["type"] == "text")
    try:
        listed = json.loads(text)["findings"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        msg = f"{file}: the answer is no findings list ({error})"
        raise JudgeError(msg) from None
    return [
        Finding(file, int(item["line"]), item["judge"], item["reason"])
        for item in listed
        if item["judge"] in judges
    ]


def judge(paths: Sequence[Path], rubric: Mapping[str, str], send: Post) -> list[Finding]:
    found: list[Finding] = []
    for path in paths:
        answer = send(request(path.read_text(encoding="utf-8"), rubric))
        found += findings(path.as_posix(), answer, list(rubric))
    return found


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def changed(root: Path) -> list[Path]:
    """Feature files that differ from the merge base with main, untracked ones included."""
    for ref in ("origin/main", "main"):
        if (fork := git(root, "merge-base", "HEAD", ref)).returncode == 0:
            break
    else:
        msg = "neither origin/main nor main to compare with: name the files"
        raise JudgeError(msg)
    scope = ("--", FEATURES.as_posix())
    diffed = git(root, "diff", "--name-only", "--diff-filter=d", fork.stdout.strip(), *scope)
    untracked = git(root, "ls-files", "--others", "--exclude-standard", *scope)
    names = {*diffed.stdout.splitlines(), *untracked.stdout.splitlines()}
    return [root / name for name in sorted(names) if name.endswith(".feature")]


def calibrate(folder: Path, rubric: Mapping[str, str], send: Post) -> tuple[list[str], bool]:
    """S1 per judge: the lines to print and whether every judge passed."""
    labels: dict[Path, str | None] = {}
    for path in sorted(folder.glob("*.feature")):
        if not (match := SEED.fullmatch(path.name)) or (match[1] and match[1] not in rubric):
            msg = f"{path}: not <judge>--defect-NN.feature or clean-NN.feature of a known judge"
            raise JudgeError(msg)
        labels[path] = match[1]
    flagged = {path: {f.judge for f in judge([path], rubric, send)} for path in labels}
    clean = [path for path, label in labels.items() if label is None]
    lines, passed = [], True
    for name in rubric:
        defects = [path for path, label in labels.items() if label == name]
        found = sum(name in flagged[path] for path in defects)
        false = sum(name in flagged[path] for path in clean)
        ok = min(len(defects), len(clean)) >= SEEDS
        ok = ok and found * SEEDS >= FOUND * len(defects) and false * SEEDS <= FALSE * len(clean)
        passed = passed and ok
        verdict = (
            "pass" if ok else f"FAIL (needs {FOUND}/{SEEDS} found, at most {FALSE}/{SEEDS} false)"
        )
        lines.append(
            f"{name}: {found}/{len(defects)} defects found, {false}/{len(clean)} clean files flagged: {verdict}"
        )
    return lines, passed


def main(
    argv: Sequence[str] | None = None,
    send: Post | None = None,
    environ: Mapping[str, str] = os.environ,
    rubric_file: Path = ROOT / RUBRIC,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("files", nargs="*", type=Path, help="feature files (default: changed ones)")
    parser.add_argument(
        "--calibrate", type=Path, metavar="DIR", help="measure S1 over a labelled set"
    )
    parser.add_argument(
        "--blocking", action="store_true", help="fail on a finding of a blocking judge (push stage)"
    )
    args = parser.parse_args(argv)
    try:
        rubric = rubrics(rubric_file.read_text(encoding="utf-8"))
        gate = blocking(rubric)
        if args.calibrate is not None:
            lines, passed = calibrate(args.calibrate, rubric, send or sender(environ))
            print("\n".join(lines))
            return 0 if passed else 1
        if args.blocking and not gate:
            return 0  # no judge has passed its calibration yet: nothing blocks, no key needed
        paths = args.files or changed(ROOT)
        found = judge(paths, rubric, send or sender(environ)) if paths else []
    except JudgeError as error:
        print(f"judge_features: {error}", file=sys.stderr)
        return 2
    for finding in found:
        print(finding)
    return 1 if args.blocking and any(finding.judge in gate for finding in found) else 0


if __name__ == "__main__":
    sys.exit(main())
